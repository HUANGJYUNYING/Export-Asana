import os
import sys
import datetime
from typing import Callable, List, Optional

from asana import ApiClient, Configuration
from asana.api.attachments_api import AttachmentsApi
from asana.api.projects_api import ProjectsApi
from asana.api.sections_api import SectionsApi
from asana.api.stories_api import StoriesApi
from asana.api.tasks_api import TasksApi
from asana.rest import ApiException

# 檔案用途：Asana 專案匯出腳本；mask_fn 可由 LLM 或外部模組注入

import config
import utils
from sync_manager import SyncManager
from models import TaskRenderContext, AsanaApis
from asana_fetch import fetch_task_context
from markdown_render import render_markdown
from storage import write_markdown_file


def maybe_post_mask_preview(
    client: Optional[ApiClient],
    task_gid: str,
    masked_title: str,
    masked_notes: str,
    preview_stories: List[str],
    mask_fn: Optional[Callable[[str], str]],
) -> None:
    """
    依條件決定是否上傳遮罩預覽。

    Args:
        client (ApiClient | None): Asana API client；離線時可為 None。
        task_gid (str): 任務 GID。
        masked_title (str): 遮罩後標題。
        masked_notes (str): 遮罩後描述。
        preview_stories (List[str]): 遮罩後留言抽樣。
        mask_fn (Callable[[str], str] | None): 遮罩函式。
    """
    if mask_fn is None or not callable(mask_fn):
        return
    if os.getenv("ENABLE_UPLOAD_PREVIEW", "").strip().lower() != "true":
        return  # 可關閉預覽上傳以支援離線或僅匯出場景
    if client is None:
        return
    if not preview_stories:
        return

    utils.post_masking_preview(
        client,
        task_gid,
        masked_title,
        masked_notes,
        preview_stories,
    )


def main(mask_fn: Optional[Callable[[str], str]] = None) -> None:
    """
    CLI 入口：抓取 Asana 任務、生成 Markdown、必要時上傳遮罩預覽。

    Args:
        mask_fn (Callable[[str], str] | None): 可選遮罩函式；缺省為直通。
    """
    print(f"📂 附件下載: {'ON' if config.DOWNLOAD_ATTACHMENTS else 'OFF'}")

    profiles = config.load_asana_profiles()
    if not profiles:
        sys.exit("❌ .env 設定錯誤")

    print("📋 請選擇專案 Profile：")
    for i, p in enumerate(profiles):
        print(f"  {i+1}) {p['name']}")

    choice = input("\n👉 請輸入編號：").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(profiles)):
        sys.exit("❌ 選項無效")

    selected = profiles[int(choice) - 1]
    project_id = selected["project"]

    conf = Configuration()
    conf.access_token = selected["token"]
    client = ApiClient(configuration=conf)
    apis = AsanaApis(
        projects=ProjectsApi(client),
        tasks=TasksApi(client),
        stories=StoriesApi(client),
        attachments=AttachmentsApi(client),
        sections=SectionsApi(client),
    )
    sync_mgr = SyncManager()

    print(f"⏳ 連線至 [{selected['name']}]...")

    try:
        p_info = utils.ensure_dict(apis.projects.get_project(project_id, opts={}))
        proj_name = p_info["name"]
        sec_res = apis.sections.get_sections_for_project(project_id, opts={})
        sections_map = {
            s["gid"]: utils.clean_filename(s["name"])
            for s in [utils.ensure_dict(x) for x in sec_res]
        }
        sections_map["uncategorized"] = "未分類"
    except ApiException as e:
        sys.exit(
            f"❌ Asana API Error: {getattr(e, 'status', '')} {getattr(e, 'reason', e)}"
        )
    except Exception as e:
        sys.exit(f"❌ Unexpected Error: {e}")

    print("\n🚫 選擇排除區段 (Enter 跳過)：")
    sec_list = [
        (gid, name)
        for gid, name in sections_map.items()
        if name not in ["Untitled section", "未命名區段", "未分類"]
    ]
    for i, (gid, name) in enumerate(sec_list, 1):
        print(f"  {i}. {name}")
    blk_in = input("👉 編號 (如 1,3)：").strip()
    blacklist = {
        sec_list[int(p) - 1][0]
        for p in blk_in.split(",")
        if p.isdigit() and 1 <= int(p) <= len(sec_list)
    }

    curr_time_iso = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    print("\n🔍 掃描全專案 Metadata...")
    tasks_res = apis.tasks.get_tasks_for_project(
        project_id,
        opts={
            "opt_fields": "gid,name,created_at,modified_at,completed,due_on,notes,memberships.project.gid,memberships.section.gid,custom_fields.name,custom_fields.display_value"
        },
    )
    all_tasks = [utils.ensure_dict(t) for t in tasks_res]
    last_sync = sync_mgr.get_last_sync(project_id)

    print(f"\n專案: {proj_name} | 上次同步: {last_sync or '無'}")
    mode = input("1. 🚀 增量同步\n2. 🛠️ 自訂匯出\n👉 ").strip()
    final_tasks = []

    if mode == "1":
        if not last_sync:
            final_tasks = all_tasks
        else:
            threshold = (
                datetime.datetime.strptime(last_sync, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                    tzinfo=datetime.timezone.utc
                )
                - datetime.timedelta(minutes=5)  # 提前 5 分鐘避免邊界漏抓
            ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            final_tasks = [t for t in all_tasks if t["modified_at"] > threshold]
    elif mode == "2":
        print("輸入 'full' 或日期 'YYYY-MM-DD~YYYY-MM-DD'")
        d_in = input("👉 ").strip().lower()
        if d_in == "full":
            final_tasks = all_tasks
        elif "~" in d_in:
            try:
                start_date, end_date = d_in.split("~")
                final_tasks = [
                    t
                    for t in all_tasks
                    if start_date.strip() <= t["created_at"][:10] <= end_date.strip()
                ]
            except ValueError as e:
                print(f"⚠️ 日期解析失敗: {e}")

    if not final_tasks:
        if mode == "1" and input("❓ 更新時間戳記? (y/n): ").lower() == "y":
            sync_mgr.save_sync_time(project_id, curr_time_iso)
        sys.exit("⚠️ 無任務需處理")

    root_dir = os.path.join(
        os.path.expanduser("~"), "Downloads", "Asana_Knowledge_Base"
    )
    proj_dir = os.path.join(root_dir, utils.clean_filename(proj_name))
    att_dir = os.path.join(proj_dir, "attachments")

    os.makedirs(proj_dir, exist_ok=True)
    if config.DOWNLOAD_ATTACHMENTS:
        os.makedirs(att_dir, exist_ok=True)

    print(f"\n🚀 處理 {len(final_tasks)} 筆任務...")

    for idx, t in enumerate(final_tasks):
        sys.stdout.write(f"\r   進度 ({idx+1}/{len(final_tasks)}): {t['name'][:10]}...")
        sys.stdout.flush()

        sec_gid = next(
            (
                m["section"]["gid"]
                for m in t.get("memberships", [])
                if m.get("project")
                and m["project"]["gid"] == project_id
                and m.get("section")
            ),
            "uncategorized",
        )
        if sec_gid in blacklist:
            continue

        sec_name = sections_map.get(sec_gid, "未分類")
        sec_dir = os.path.join(proj_dir, sec_name)

        if not t.get("completed"):
            if os.path.exists(sec_dir):
                for fname in os.listdir(sec_dir):
                    if fname.endswith(".md"):
                        fpath = os.path.join(sec_dir, fname)
                        try:
                            with open(fpath, "r", encoding="utf-8") as f:
                                head = [next(f) for _ in range(6)]
                            if any(f"gid: {t['gid']}" in line for line in head):
                                os.remove(
                                    fpath
                                )  # 未完成任務的舊檔清除，避免殘留過期內容
                                sys.stdout.write(
                                    f"\r   🗑️  刪除未完成舊檔: {fname[:20]}...       \n"
                                )
                        except (OSError, StopIteration) as e:
                            print(f"⚠️ 清理未完成舊檔失敗 {fname}: {e}")
            continue

        os.makedirs(sec_dir, exist_ok=True)

        tid = t["gid"]
        task_attachments, story_attachment_map, stories, full_subs = fetch_task_context(
            task_gid=tid,
            apis=apis,
        )

        ctx = TaskRenderContext(
            task=t,
            project_id=project_id,
            section_name=sec_name,
            att_dir=att_dir,
            task_attachments=task_attachments,
            stories=stories,
            story_attachment_map=story_attachment_map,
            subtasks=full_subs,
        )

        md, masked_title, masked_notes, preview_stories = render_markdown(
            ctx=ctx,
            mask_fn=mask_fn,
        )

        write_markdown_file(md_lines=md, sec_dir=sec_dir, task=t)

        maybe_post_mask_preview(
            client=client,
            task_gid=tid,
            masked_title=masked_title,
            masked_notes=masked_notes,
            preview_stories=preview_stories,
            mask_fn=mask_fn,
        )

    if mode == "1":
        sync_mgr.save_sync_time(project_id, curr_time_iso)
        print(f"\n✅ 增量同步完成！時間戳記已更新。")
    else:
        print(f"\n✅ 匯出完成！")


if __name__ == "__main__":
    main()
