import os
import json
import glob
import sys
import re
from asana import Configuration, ApiClient

import config
import utils
import markdown_render
import llm_processor

def protect_asana_links(text):
    """
    將 Asana 附件連結替換為特殊 Placeholder，避免被 LLM 遮罩成 [LINK]
    Target: https://app.asana.com/.../get_asset?asset_id=123456
    Result: <<<ASSET_123456>>>
    """
    if not text:
        return text
    # Regex 抓取 asset_id
    pattern = r"https://app\.asana\.com/[^\s]*asset_id=(\d+)"
    return re.sub(pattern, r"<<<ASSET_\1>>>", text)


def restore_asana_links(text):
    """
    將 Placeholder 還原回原始連結，以便 markdown_render 進行處理
    Target: <<<ASSET_123456>>>
    Result: https://app.asana.com/app/asana/-/get_asset?asset_id=123456
    """
    if not text:
        return text
    # 還原回標準 Asana Asset URL 格式 (這格式是固定的)
    return re.sub(
        r"<<<ASSET_(\d+)>>>",
        r"https://app.asana.com/app/asana/-/get_asset?asset_id=\1",
        text,
    )


def collect_texts_to_mask(data):
    """
    從 JSON 資料中遞迴收集所有需要遮罩的字串
    """
    texts = set()
    t = data["metadata"]

    # 1. 主任務
    if t.get("name"):
        texts.add(t["name"])
    if t.get("notes"):
        texts.add(protect_asana_links(t["notes"]))
    # 自訂欄位
    if t.get("custom_fields"):
        for cf in t["custom_fields"]:
            if cf.get("display_value"):
                texts.add(cf["display_value"])

    # 2. 附件名稱
    if data.get("task_attachments"):
        for a in data["task_attachments"]:
            if a.get("name"):
                texts.add(a["name"])
            if a.get("ocr_text"):
                texts.add(a["ocr_text"])

    # 3. 留言
    if data.get("stories"):
        for s in data["stories"]:
            if s.get("text"):
                texts.add(protect_asana_links(s["text"]))
            user_name = (s.get("created_by") or {}).get("name")
            if user_name:
                texts.add(user_name)

    # 4. 子任務 (遞迴概念)
    if data.get("subtasks"):
        for sub in data["subtasks"]:
            sm = sub["meta"]
            if sm.get("name"):
                texts.add(sm["name"])
            if sm.get("notes"):
                texts.add(protect_asana_links(sm["notes"]))

            # 子任務附件
            if sub.get("attachments"):
                for sa in sub["attachments"]:
                    if sa.get("name"):
                        texts.add(sa["name"])
                    if sa.get("ocr_text"):
                        texts.add(sa["ocr_text"])

            # 子任務留言
            if sub.get("stories"):
                for ss in sub["stories"]:
                    if ss.get("text"):
                        texts.add(protect_asana_links(ss["text"]))
                    sub_user_name = (ss.get("created_by") or {}).get("name")
                    if sub_user_name:
                        texts.add(sub_user_name)

    return list(texts)


def run_process(target_proj_name=None):
    if not os.path.exists(config.RAW_DIR):
        print("❌ 找不到原始資料")
        return

    # 選擇專案
    if target_proj_name:
        target_proj = target_proj_name
    else:
        projects = [
            d
            for d in os.listdir(config.RAW_DIR)
            if os.path.isdir(os.path.join(config.RAW_DIR, d))
        ]
        if not projects:
            print("❌ 無專案資料")
            return
        print("\n📋 資料處理與生成")
        for i, p in enumerate(projects):
            print(f"  {i+1}) {p}")
        try:
            idx = int(input("👉 編號：")) - 1
            target_proj = projects[idx]
        except:
            return

    json_path = os.path.join(config.RAW_DIR, target_proj, "json_tasks")
    output_proj_path = os.path.join(config.PROCESSED_DIR, target_proj)

    # 準備 API (用於預覽)
    profiles = config.load_asana_profiles()
    token = profiles[0]["token"]
    conf = Configuration()
    conf.access_token = token
    client = ApiClient(configuration=conf)

    files = glob.glob(os.path.join(json_path, "*.json"))
    print(f"\n🚀 [Stage 2] 開始處理 {len(files)} 個檔案...")
    print(f"🔒 遮罩: {'True' if config.ENABLE_LLM_ANALYSIS else 'False'}")

    for i, fpath in enumerate(files):
        sys.stdout.write(f"\r   進度: {i+1}/{len(files)}...")
        sys.stdout.flush()

        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)

        t = data["metadata"]

        # 批次遮罩 (Batch Masking)
        mask_lookup = {}

        if config.ENABLE_LLM_ANALYSIS:
            # 1. 收集所有字串
            all_texts = collect_texts_to_mask(data)

            # 2. 一次性送給 LLM(讓llm_processor 內部自動分批處理以符合 token 限制, LLM 會看到 <<<ASSET_123>>> 並保留它)
            mask_lookup = llm_processor.mask_batch_texts(all_texts)

        # 3. 定義快速查找函式
        def _mask(txt):
            if not txt:
                return ""
            if not config.ENABLE_LLM_ANALYSIS:
                return txt

            # A. 先保護傳入的文字 (因為 lookup key 是保護過的)
            protected_txt = protect_asana_links(txt)

            # B. 查表取得遮罩後結果
            masked_txt = mask_lookup.get(protected_txt, protected_txt)

            # C. 還原連結 (讓 markdown_render 能讀到 ID)
            final_txt = restore_asana_links(masked_txt)

            return final_txt

        # 渲染與存檔
        md_lines = markdown_render.render_markdown(data, _mask)

        # Raw Data 相對路徑
        final_md_lines = []
        path_prefix = f"../../../raw_data/{target_proj}/attachments/"
        for line in md_lines:
            line = line.replace("../attachments/", path_prefix)
            final_md_lines.append(line)

        final_md_content = "\n".join(final_md_lines)
        # 存檔
        sec_dir = os.path.join(output_proj_path, data["section_name"])
        os.makedirs(sec_dir, exist_ok=True)

        safe_title = _mask(t["name"])
        c_at = t["created_at"][:10].replace("-", "")
        fname = f"{c_at}_{utils.clean_filename(safe_title)}.md"
        if len(fname) > 100:
            fname = fname[:100] + ".md"

        with open(os.path.join(sec_dir, fname), "w", encoding="utf-8") as f:
            f.write("\n".join(final_md_lines))

        # 寫回預覽
        if config.ENABLE_LLM_ANALYSIS and os.getenv("ENABLE_UPLOAD_PREVIEW") == "True":
            preview_stories = []
            for s in data["stories"]:
                if s["resource_subtype"] == "comment_added":
                    u = _mask(s.get("created_by", {}).get("name", "User"))
                    txt = _mask(s["text"])
                    preview_stories.append(f"{u}: {txt}")

            utils.post_masking_preview(
                client, t["gid"], final_md_content
            )  # 直接傳送檔案內容

    print(f"\n✅ 處理完成！")


if __name__ == "__main__":
    run_process()
