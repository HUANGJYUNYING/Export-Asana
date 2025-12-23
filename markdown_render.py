# 檔案用途：負責將任務上下文轉換為 Markdown 與遮罩預覽資料（純轉換，無 I/O）
import datetime
import os
import utils
import re
import config


def render_markdown(data, mask_func):
    """
    輸入:
      data: 包含 metadata, stories, attachments 等的字典 (from JSON)
      mask_func: 已綁定 context 的遮罩函式
    回傳:
      List[str]: Markdown 的每一行
    """
    t = data["metadata"]
    # 0. lookup table
    # Key: asset_id (gid), Value: attachment_data
    att_lookup = {}

    # 追蹤已被使用的附件 GID
    rendered_gids = set()

    # 收集所有附件
    all_atts = []
    if data.get("task_attachments"):
        all_atts.extend(data["task_attachments"])
    if data.get("story_attachment_map"):
        for alist in data["story_attachment_map"].values():
            all_atts.extend(alist)
    if data.get("subtasks"):
        for sub in data["subtasks"]:
            if sub.get("attachments"):
                all_atts.extend(sub["attachments"])

    for a in all_atts:
        att_lookup[a["gid"]] = a

    # 產生圖片+OCR 的 Markdown 區塊

    def get_attachment_markdown(gid, indent_level=""):
        """
        根據 GID 產生圖片連結與 OCR 文字
        格式：
        > 📎 [檔名](路徑)
        > 🖼️ LLM分析: ...
        """
        if gid not in att_lookup:
            return None  # 找不到對應附件

        # 標記此附件已被使用
        rendered_gids.add(gid)

        a = att_lookup[gid]
        dname = mask_func(a["name"])

        # 處理路徑 (這裡先產生相對路徑，process_data.py 會再修整)
        if a.get("local_path"):
            fname = os.path.basename(a["local_path"])
            link_md = f"[{dname}](../attachments/{fname})"
        else:
            link_md = f"[{dname} (未下載)]({a['download_url']})"

        # 如果有 OCR 內容，以內容為主，連結為輔
        if a.get("ocr_text"):
            safe_ocr = mask_func(a["ocr_text"]).replace("\n", f"\n{indent_level}> ")
            return f"{indent_level}> 🖼️ **內容分析** (📎 {link_md}):\n{indent_level}> {safe_ocr}"
        else:
            # 如果沒有 OCR 內容 (例如非圖片檔)，維持原樣顯示連結
            return f"{indent_level}📎 {link_md}"

    # 1. Metadata
    safe_title = mask_func(t["name"])
    c_at = t["created_at"][:10]
    expiry_date_str = None

    # 先找看看有沒有這個欄位值
    if t.get("custom_fields"):
        for cf in t["custom_fields"]:
            # 這裡可以用名稱判斷 (需確保名稱跟 Asana 一致)
            # 或者在 fetch_raw 時我們有把計算結果放在 t['calculated_expiry_date'] 也可以用
            if cf["name"] == config.EXPIRY_FIELD_NAME and cf.get("display_value"):
                expiry_date_str = cf["display_value"]
                break

    # 如果真的沒找到 (例如該專案沒這個欄位)，才用預設推算
    if not expiry_date_str:
        expiry_date_str = (
            datetime.datetime.strptime(c_at, "%Y-%m-%d") + datetime.timedelta(days=365)
        ).strftime("%Y-%m-%d")

    status_str = "completed" if t.get("completed") else "active"

    # 提取自訂欄位
    cf_data = {}
    if t.get("custom_fields"):
        for cf in t["custom_fields"]:
            if cf.get("display_value"):
                cf_data[cf["name"]] = cf["display_value"]

    md = [
        "---",
        "type: task",
        f"gid: {t['gid']}",
        f'title: "{utils.clean_filename(safe_title)}"',
        f"status: {status_str}",
        f"created_date: {c_at}",
        f"modified_at: {t.get('modified_at')}",
        f"expiry_date: {expiry_date_str}",
        f"section: \"{data['section_name']}\"",
    ]
    for k, v in cf_data.items():
        md.append(f'cf_{utils.clean_filename(k)}: "{mask_func(v)}"')
    md.append("---\n")

    # 2. 標題與基本資訊
    md.append(f"# {'✅' if t['completed'] else '🔲'} {safe_title}")

    # 基本資訊連結處理，如果是連到附件的，就展開
    # 但通常 permalink 是連到 Task 本身，所以維持原樣
    plink = f"https://app.asana.com/0/{t.get('memberships', [{}])[0].get('project', {}).get('gid', '0')}/{t['gid']}"

    # 這裡的 PROJECT_ID 無法直接取得，可以從 permalink 判斷或忽略連結，若 metadata 沒有 permalink_url，可以拼出一個通用的連結
    md.append(f"\n## 📌 基本資訊\n- **建立日期**: {c_at}")
    if cf_data:
        md.append("- **自訂欄位**:")
        for k, v in cf_data.items():
            md.append(f"  - {k}: `{mask_func(v)}`")

    # 3. 描述(支援內嵌圖片)
    def replace_asset_link(match):
        """Regex 回呼函式：將 asset_id 連結替換為圖片區塊"""

        # 嘗試取得圖片 Markdown，縮排層級設為空 (因為描述通常不在 > 內)
        img_block = get_attachment_markdown(match.group(1), indent_level="> ")

        return f"\n{img_block}\n" if img_block else match.group(0)

    raw_notes = mask_func(t.get("notes")) or "*(無)*"
    processed_notes = re.sub(
        r"https://app\.asana\.com/[^\s]*asset_id=(\d+)", replace_asset_link, raw_notes
    )

    md.append(f"\n## 📝 任務描述\n{processed_notes}")

    # 4. 討論紀錄 (支援內嵌圖片)
    if data.get("stories"):
        md.append("\n## 💬 討論紀錄")
        for s in data["stories"]:
            if s["resource_subtype"] == "comment_added":
                u = mask_func(s.get("created_by", {}).get("name", "User"))

                # 處理留言內容
                raw_text = mask_func(s["text"])

                # 定義留言專用的替換函式 (增加縮排)
                def replace_story_asset(match):
                    asset_gid = match.group(1)
                    img_block = get_attachment_markdown(asset_gid, indent_level="> ")
                    if img_block:
                        return f"{match.group(0)}\n>\n{img_block}\n>"
                    return match.group(0)

                processed_text = re.sub(
                    r"https://app\.asana\.com/[^\s]*asset_id=(\d+)",
                    replace_story_asset,
                    raw_text,
                )

                # 整理換行，確保每一行都有 "> "
                final_story = processed_text.replace("\n", "\n> ")

                md.append(f"> **{u} ({s['created_at'][:10]})**:\n> {final_story}\n")

    # 5. 子任務
    if data.get("subtasks"):
        md.append("\n---\n## 🔨 子任務")
        for i, item in enumerate(data["subtasks"], 1):
            s = item["meta"]
            md.append(f"### {i}. {mask_func(s['name'])}")

            # 處理子任務描述的內嵌圖片
            if s.get("notes"):
                raw_sub_notes = mask_func(s["notes"])

                # 子任務描述通常會縮排顯示
                def replace_sub_asset(match):
                    gid = match.group(1)
                    blk = get_attachment_markdown(gid, indent_level="  > ")
                    return f"{match.group(0)}\n  >\n{blk}" if blk else match.group(0)

                proc_sub_notes = re.sub(
                    r"https://app\.asana\.com/[^\s]*asset_id=(\d+)",
                    replace_sub_asset,
                    raw_sub_notes,
                )
                # 補上縮排
                md.append(f"  > {proc_sub_notes.replace(chr(10), chr(10)+'  >')}\n")

            # 子任務留言
            if item.get("stories"):
                md.append("  - **留言**:")
                for sc in item["stories"]:
                    if sc["resource_subtype"] == "comment_added":
                        su = mask_func(sc.get("created_by", {}).get("name", "U"))
                        stxt = mask_func(sc["text"])

                        # 子任務留言圖片處理
                        def replace_sub_story(m):
                            blk = get_attachment_markdown(
                                m.group(1), indent_level="    "
                            )
                            return f"{m.group(0)}\n{blk}" if blk else m.group(0)

                        proc_stxt = re.sub(r"asset_id=(\d+)", replace_sub_story, stxt)

                        md.append(f"    - **{su}**: {proc_stxt.replace(chr(10), ' ')}")
            md.append("")
    # 6. 剩餘附件總覽 (扣除留言附件後的)
    all_att_objects = []
    if data.get("task_attachments"):
        all_att_objects.extend(data["task_attachments"])
    if data.get("story_attachment_map"):
        for alist in data["story_attachment_map"].values():
            all_att_objects.extend(alist)

    # 過濾出未使用的 GID
    remaining_atts = [a for a in all_att_objects if a["gid"] not in rendered_gids]

    if remaining_atts:
        md.append("\n## 📎 其他附件")
        for a in remaining_atts:
            # 這裡呼叫 get_attachment_markdown，但 indent 設為空
            # 因為這是在最外層列表
            # 注意：這裡會重複加入 rendered_gids，但不影響結果

            dname = mask_func(a["name"])
            if a.get("local_path"):
                fname = os.path.basename(a["local_path"])
                link = f"[{dname}](../attachments/{fname})"
            else:
                link = f"[{dname} (未下載)]({a['download_url']})"

            md.append(f"- {link}")
            # 可選擇是否秀出總覽區的 OCR內容
            """
            if a.get('ocr_text'):
                safe_ocr = mask_func(a['ocr_text']).replace('\n', ' ')
                md.append(f"  > 🖼️ **簡要**: {safe_ocr[:50]}...") # 只秀前50字摘要
            """

    return md
