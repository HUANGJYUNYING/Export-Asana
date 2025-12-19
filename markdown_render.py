# 檔案用途：負責將任務上下文轉換為 Markdown 與遮罩預覽資料（純轉換，無 I/O）
import datetime
import os
import utils


def render_markdown(data, mask_func):
    """
    輸入:
      data: 包含 metadata, stories, attachments 等的字典 (from JSON)
      mask_func: 已綁定 context 的遮罩函式
    回傳:
      List[str]: Markdown 的每一行
    """
    t = data["metadata"]

    # 1. Metadata
    safe_title = mask_func(t["name"])
    c_at = t["created_at"][:10]
    exp = (
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
        f"expiry_date: {exp}",
        f"section: \"{data['section_name']}\"",
    ]
    for k, v in cf_data.items():
        md.append(f'cf_{utils.clean_filename(k)}: "{mask_func(v)}"')
    md.append("---\n")

    # 2. 標題與基本資訊
    md.append(f"# {'✅' if t['completed'] else '🔲'} {safe_title}")
    # 這裡的 PROJECT_ID 無法直接取得，可以從 permalink 判斷或忽略連結
    # 為了簡化，若 metadata 沒有 permalink_url，可以拼出一個通用的連結
    md.append(f"\n## 📌 基本資訊\n- **建立日期**: {c_at}")
    if cf_data:
        md.append("- **自訂欄位**:")
        for k, v in cf_data.items():
            md.append(f"  - {k}: `{mask_func(v)}`")

    # 3. 描述
    md.append(f"\n## 📝 任務描述\n{mask_func(t.get('notes')) or '*(無)*'}")

    # Helper: 附件渲染
    def _render_atts(att_list, indent=""):
        lines = []
        for a in att_list:
            dname = mask_func(a["name"])
            # 建立相對路徑連結: ../attachments/filename
            if a.get("local_path"):
                fname = os.path.basename(a["local_path"])
                link = f"[{dname}](../attachments/{fname})"
            else:
                link = f"[{dname} (未下載)]({a['download_url']})"

            lines.append(f"{indent}- {link}")

            # 顯示 LLM 分析結果 (原 ocr_text)
            if a.get("ocr_text"):
                # 遮罩分析結果並縮排
                safe_ocr = mask_func(a["ocr_text"]).replace("\n", " ")
                lines.append(f"{indent}  > 🖼️ **內容分析**: {safe_ocr}")
        return lines

    # 4. 任務附件 (扣除留言附件後的)
    if data.get("task_attachments"):
        md.append("\n## 📎 任務附件")
        md.extend(_render_atts(data["task_attachments"]))

    # 5. 討論紀錄 (含附件歸位)
    if data.get("stories"):
        md.append("\n## 💬 討論紀錄")
        story_att_map = data.get("story_attachment_map", {})

        for s in data["stories"]:
            if s["resource_subtype"] == "comment_added":
                u = mask_func(s.get("created_by", {}).get("name", "User"))
                txt = mask_func(s["text"])
                md.append(
                    f"> **{u} ({s['created_at'][:10]})**: {txt.replace(chr(10), '  '+chr(10))}"
                )

                # 檢查此留言是否有附件
                s_gid = s["gid"]
                if s_gid in story_att_map:
                    md.extend(_render_atts(story_att_map[s_gid], indent="  "))

                md.append("")

    # 6. 子任務
    if data.get("subtasks"):
        md.append("\n---\n## 🔨 子任務")
        for i, item in enumerate(data["subtasks"], 1):
            s = item["meta"]
            md.append(f"### {i}. {mask_func(s['name'])}")
            if s.get("notes"):
                md.append(
                    f"  > {mask_func(s['notes']).replace(chr(10), chr(10)+'  >')}\n"
                )

            # 子任務附件
            if item.get("attachments"):
                md.append("  - **附件**:")
                md.extend(_render_atts(item["attachments"], indent="    "))

            # 子任務留言
            if item.get("stories"):
                md.append("  - **留言**:")
                for sc in item["stories"]:
                    if sc["resource_subtype"] == "comment_added":
                        su = mask_func(sc.get("created_by", {}).get("name", "U"))
                        stxt = mask_func(sc["text"])
                        md.append(f"    - **{su}**: {stxt.replace(chr(10), ' ')}")
            md.append("")

    return md
