# 檔案用途：負責將任務上下文轉換為 Markdown 與遮罩預覽資料（純轉換，無 I/O）。

import datetime
from typing import Callable, List, Optional, Tuple

import utils
from models import TaskRenderContext


def ensure_mask_fn(mask_fn: Optional[Callable[[str], str]]) -> Callable[[str], str]:
    """
    產生可用遮罩函式；未提供時回傳直通函式。
    採用具名內部函式，便於除錯與追蹤呼叫堆疊。

    Args:
        mask_fn (Callable[[str], str] | None): 可選的遮罩函式。

    Returns:
        Callable[[str], str]: 實際可呼叫的遮罩函式。

    Raises:
        TypeError: 當 mask_fn 不是可呼叫物件時。
    """
    if mask_fn is None:

        def _passthrough(text: str) -> str:
            return text or ""

        return _passthrough
    if not callable(mask_fn):
        raise TypeError("mask_fn 必須為可呼叫物件")

    def _mask(text: str) -> str:
        return mask_fn(text or "")

    return _mask


def render_markdown(
    ctx: TaskRenderContext,
    mask_fn: Optional[Callable[[str], str]] = None,
) -> Tuple[List[str], str, str, List[str]]:
    """
    建立任務的 Markdown 內容與遮罩預覽資料。

    Args:
        ctx (TaskRenderContext): 渲染所需的上下文資料。
        mask_fn (Callable[[str], str] | None): 遮罩函式，無則直通。

    Returns:
        Tuple[List[str], str, str, List[str]]: (Markdown 行列表, 遮罩後標題, 遮罩後描述, 遮罩留言預覽)。
    """
    mask = ensure_mask_fn(mask_fn)

    safe_title = ctx.task.get("name") or "untitled"
    c_at = ctx.task["created_at"][:10]
    exp = ctx.task.get("expiry_date") or (
        (datetime.datetime.strptime(c_at, "%Y-%m-%d") + datetime.timedelta(days=365))
        .date()
        .isoformat()
    )
    status_str = "completed" if ctx.task.get("completed") else "active"

    md: List[str] = [
        "---",
        "type: task",
        f"gid: {ctx.task['gid']}",
        f'title: "{utils.clean_filename(safe_title)}"',
        f"status: {status_str}",
        f"created_date: {c_at}",
        f"modified_at: {ctx.task.get('modified_at')}",
        f"expiry_date: {exp}",
        f'section: "{ctx.section_name}"',
    ]

    if ctx.task.get("custom_fields"):
        for cf in ctx.task["custom_fields"]:
            if cf.get("display_value"):
                md.append(
                    f"cf_{utils.clean_filename(cf['name'])}: \"{cf['display_value']}\""
                )
    md.append("---\n")

    md.append(f"# {'✅' if ctx.task['completed'] else '🔲'} {safe_title}")
    md.append(
        f"\n## 📌 基本資訊\n- **連結**: [Asana](https://app.asana.com/0/{ctx.project_id}/{ctx.task['gid']})"
    )
    if ctx.task.get("custom_fields"):
        md.append("- **自訂欄位**:")
        for cf in ctx.task["custom_fields"]:
            if cf.get("display_value"):
                md.append(f"  - {cf['name']}: `{cf['display_value']}`")

    md.append(f"\n## 📝 任務描述\n{ctx.task.get('notes') or '*(無)*'}")

    if ctx.task_attachments:
        md.append("\n## 📎 任務附件")
        for a in ctx.task_attachments:
            link, _ = utils.process_attachment_link(a, ctx.task["gid"], ctx.att_dir)
            md.append(f"- {link}")

    if ctx.stories:
        md.append("\n## 💬 討論紀錄")
        for s in ctx.stories:
            if s["resource_subtype"] == "comment_added":
                u = s.get("created_by", {}).get("name", "User")
                txt = s["text"]
                md.append(
                    f"> **{u} ({s['created_at'][:10]})**: {txt.replace(chr(10), '  '+chr(10))}"
                )

                s_gid = s["gid"]
                if s_gid in ctx.story_attachment_map:
                    for sa in ctx.story_attachment_map[s_gid]:
                        link, _ = utils.process_attachment_link(
                            sa, ctx.task["gid"], ctx.att_dir
                        )
                        md.append(f"  > 📎 {link}")
                md.append("")

    if ctx.subtasks:
        md.append("\n---\n## 🔨 子任務")
        for i, item in enumerate(ctx.subtasks, 1):
            s = item["meta"]
            md.append(f"### {i}. {s['name']}")
            if s.get("notes"):
                md.append(f"  > {s['notes'].replace(chr(10), chr(10)+'  >')}\n")

            if item["attachments"]:
                md.append("  - **附件**:")
                for sa in item["attachments"]:
                    link, _ = utils.process_attachment_link(sa, s["gid"], ctx.att_dir)
                    md.append(f"    - {link}")

            if item["stories"]:
                md.append("  - **留言**:")
                for sc in item["stories"]:
                    if sc["resource_subtype"] == "comment_added":
                        su = sc.get("created_by", {}).get("name", "User")
                        stxt = sc["text"]
                        md.append(
                            f"    - `{sc['created_at'][:10]}` **{su}**: {stxt.replace(chr(10), ' ')}"
                        )
            md.append("")

    preview_stories: List[str] = []
    if ctx.stories:
        for s in ctx.stories:
            if s["resource_subtype"] == "comment_added":
                u = mask(s.get("created_by", {}).get("name", "User"))
                t_content = mask(s["text"])
                preview_stories.append(f"{u}: {t_content}")

    masked_title = mask(safe_title)
    masked_notes = mask(ctx.task.get("notes", ""))

    return md, masked_title, masked_notes, preview_stories
