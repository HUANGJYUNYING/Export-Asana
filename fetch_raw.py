import os
import sys
import json
import datetime
import dataclasses
from asana import Configuration, ApiClient
from asana.api.projects_api import ProjectsApi
from asana.api.tasks_api import TasksApi
from asana.api.stories_api import StoriesApi
from asana.api.attachments_api import AttachmentsApi
from asana.api.sections_api import SectionsApi

import config
import utils
import asana_fetch
from sync_manager import SyncManager
from models import AsanaApis


# JSON 編碼器：處理 dataclass (AttachmentData) 轉 dict
class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


def run_fetch():
    """
    執行第一階段：資料擷取
    Returns:
        str: 處理的專案資料夾名稱 (safe_proj_name)，若取消或失敗回傳 None
    """
    profiles = config.load_asana_profiles()
    if not profiles:
        print("❌ .env 設定錯誤")
        return None

    print("\n📋 [Stage 1] 原始資料擷取 (Raw Data Fetch)")
    print("請選擇專案 Profile：")
    for i, p in enumerate(profiles):
        print(f"  {i+1}) {p['name']}")

    choice = input("\n👉 請輸入編號 (n離開)：").strip()
    if choice.lower() == "n":
        return None
    if not choice.isdigit() or not (1 <= int(choice) <= len(profiles)):
        print("❌ 選項無效")
        return None

    selected = profiles[int(choice) - 1]
    PROJECT_ID = selected["project"]

    # API Setup
    conf = Configuration()
    conf.access_token = selected["token"]
    client = ApiClient(configuration=conf)
    apis = AsanaApis(
        ProjectsApi(client),
        TasksApi(client),
        StoriesApi(client),
        AttachmentsApi(client),
        SectionsApi(client),
    )
    sync_mgr = SyncManager()

    print(f"⏳ 連線至 [{selected['name']}]...")

    # 掃描與黑名單設定
    blacklist = set()

    # 取得專案資訊與 Section 列表
    try:
        p_info = utils.ensure_dict(apis.projects.get_project(PROJECT_ID, opts={}))
        proj_name = p_info["name"]
        # 取得 Sections 並轉為 List
        sec_generator = apis.sections.get_sections_for_project(PROJECT_ID, opts={})
        all_sections = [utils.ensure_dict(s) for s in sec_generator]
        # 建立 Section Map
        sections_map = {s["gid"]: utils.clean_filename(s["name"]) for s in all_sections}
        sections_map["uncategorized"] = "未分類"
        print("\n🚫 選擇排除區段 (Enter 跳過)：")
        # 過濾掉沒意義的區段名稱，只顯示有效的
        ui_sections = [
            s
            for s in all_sections
            if s["name"] not in ["Untitled section", "未命名區段"]
        ]

        for i, s in enumerate(ui_sections, 1):
            print(f"  {i}. {s['name']}")

        blk_in = input("👉 編號 (如 1,3)：").strip()
        if blk_in:
            for p in blk_in.split(","):
                if p.strip().isdigit():
                    idx = int(p.strip())
                    if 1 <= idx <= len(ui_sections):
                        target_gid = ui_sections[idx - 1]["gid"]
                        blacklist.add(target_gid)
                        print(f"   ⛔ 已排除: {ui_sections[idx-1]['name']}")
    except Exception as e:
        print(f"❌ API Error: {e}")
        return None

    # 執行全量同步或增量同步
    curr_time_iso = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    print("\n🔍 掃描全專案 Metadata...")
    tasks_res = apis.tasks.get_tasks_for_project(
        PROJECT_ID,
        opts={
            "opt_fields": "gid,name,created_at,modified_at,completed,due_on,notes,memberships.project.gid,memberships.section.gid,custom_fields.name,custom_fields.display_value"
        },
    )
    all_tasks_raw = [utils.ensure_dict(t) for t in tasks_res]
    last_sync = sync_mgr.get_last_sync(PROJECT_ID)

    print(f"\n專案: {proj_name} | 總筆數: {len(all_tasks_raw)}")
    print(f"上次同步: {last_sync or '無'}")
    mode = input("1. 🚀 增量同步 (只抓異動)\n2. 🛠️ 全量同步\n👉 ").strip()
    final_tasks = []

    if mode == "1":
        if not last_sync:
            print("⚠️ 無上次紀錄，將執行全量同步 (僅已完成)。")
            final_tasks = [t for t in all_tasks_raw if t.get("completed")]
        else:
            try:
                # 嘗試格式 1 (含微秒): 2025-12-16T10:00:00.123456Z
                last_sync_dt = datetime.datetime.strptime(
                    last_sync, "%Y-%m-%dT%H:%M:%S.%fZ"
                )
            except ValueError:
                try:
                    # 嘗試格式 2 (無微秒): 2025-12-16T10:00:00Z
                    last_sync_dt = datetime.datetime.strptime(
                        last_sync, "%Y-%m-%dT%H:%M:%SZ"
                    )
                except ValueError:
                    # 如果都失敗，直接當作沒同步過
                    print("⚠️ 時間格式解析失敗，重置同步時間。")
                    last_sync_dt = None

            if last_sync_dt:
                # 設定時區並回推 5 分鐘緩衝
                threshold_dt = last_sync_dt.replace(
                    tzinfo=datetime.timezone.utc
                ) - datetime.timedelta(minutes=5)
                threshold = threshold_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                print(f"🔍 比對異動中 ( > {threshold})...")

                # 篩選：時間夠新 AND 已完成
                final_tasks = [
                    t
                    for t in all_tasks_raw
                    if t["modified_at"] > threshold and t.get("completed")
                ]

                # --- 清理邏輯：處理變回未完成的任務 ---
                safe_proj_name = utils.clean_filename(proj_name)
                json_storage_dir = os.path.join(
                    config.RAW_DIR, safe_proj_name, "json_tasks"
                )

                for t in all_tasks_raw:
                    if t["modified_at"] > threshold and not t.get("completed"):
                        c_at = t["created_at"][:10].replace("-", "")
                        fname = f"{c_at}_{t['gid']}.json"
                        fpath = os.path.join(json_storage_dir, fname)
                        if os.path.exists(fpath):
                            try:
                                os.remove(fpath)
                                print(f"🗑️ 任務已變回未完成，刪除舊 JSON: {t['name']}")
                            except:
                                pass
            else:
                final_tasks = [t for t in all_tasks_raw if t.get("completed")]

    else:
        # 全量模式：只抓已完成
        final_tasks = [t for t in all_tasks_raw if t.get("completed")]

    print(f"✅ 符合條件且已完成的任務: {len(final_tasks)} 筆")

    if not final_tasks:
        if mode == "1" and input("❓ 更新時間戳記? (y/n): ").lower() == "y":
            sync_mgr.save_sync_time(PROJECT_ID, curr_time_iso)
        return None

    # 資料夾路徑設定
    raw_root = os.path.join(os.path.expanduser("~"), "Downloads", "Asana_Raw_Data")
    safe_proj_name = utils.clean_filename(proj_name)
    proj_dir = os.path.join(config.RAW_DIR, safe_proj_name)
    att_dir = os.path.join(proj_dir, "attachments")
    json_dir = os.path.join(proj_dir, "json_tasks")

    os.makedirs(att_dir, exist_ok=True)
    os.makedirs(json_dir, exist_ok=True)

    print(f"\n🚀 開始擷取 {len(final_tasks)} 筆任務...")
    print(f"📂 Raw Data: {proj_dir}")

    # .迴圈下載
    for idx, t in enumerate(final_tasks):
        sys.stdout.write(f"\r   進度 ({idx+1}/{len(final_tasks)}): {t['name'][:15]}...")
        sys.stdout.flush()
        sec_gid = next(
            (
                m["section"]["gid"]
                for m in t.get("memberships", [])
                if m.get("project")
                and m["project"]["gid"] == PROJECT_ID
                and m.get("section")
            ),
            "uncategorized",
        )

        if sec_gid in blacklist:
            # 這裡不 print 跳過訊息以免洗版，默默跳過即可
            continue

        sec_name = sections_map.get(sec_gid, "未分類")

        tid = t["gid"]

        try:
            task_attachments, story_attachment_map, stories, subtasks = (
                asana_fetch.fetch_task_context(tid, apis, att_dir)
            )

            sec_gid = next(
                (
                    m["section"]["gid"]
                    for m in t.get("memberships", [])
                    if m.get("project")
                    and m["project"]["gid"] == PROJECT_ID
                    and m.get("section")
                ),
                "uncategorized",
            )
            sec_name = sections_map.get(sec_gid, "未分類")

            data_package = {
                "metadata": t,
                "section_name": sec_name,
                "stories": stories,
                "task_attachments": task_attachments,
                "story_attachment_map": story_attachment_map,
                "subtasks": subtasks,
                "fetched_at": curr_time_iso,
            }
            # 存檔(.json)
            c_at = t["created_at"][:10].replace("-", "")
            fname = f"{c_at}_{tid}.json"
            with open(os.path.join(json_dir, fname), "w", encoding="utf-8") as f:
                json.dump(
                    data_package,
                    f,
                    cls=EnhancedJSONEncoder,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            print(f" Error: {e}")
            continue

    if mode == "1":
        sync_mgr.save_sync_time(PROJECT_ID, curr_time_iso)
        print(f"\n✅ 增量擷取完成！")
    else:
        print(f"\n✅ 全量擷取完成！")

    return safe_proj_name


if __name__ == "__main__":
    # 允許獨立執行
    proj = run_fetch()
    if proj:
        # 這裡可以選擇是否自動接續，或僅單獨執行
        print("獨立執行完成。")
