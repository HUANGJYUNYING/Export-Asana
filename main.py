import os
import sys
import datetime
from asana import Configuration, ApiClient
from asana.api.projects_api import ProjectsApi
from asana.api.tasks_api import TasksApi
from asana.api.stories_api import StoriesApi
from asana.api.attachments_api import AttachmentsApi
from asana.api.sections_api import SectionsApi

# 引入模組
import config
import utils
from sync_manager import SyncManager

# ==========================================
# 1. 初始化設定
# ==========================================
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
PROJECT_ID = selected["project"]

# API Setup
conf = Configuration()
conf.access_token = selected["token"]
client = ApiClient(configuration=conf)
projects_api = ProjectsApi(client)
tasks_api = TasksApi(client)
stories_api = StoriesApi(client)
attachments_api = AttachmentsApi(client)
sections_api = SectionsApi(client)
sync_mgr = SyncManager()

print(f"⏳ 連線至 [{selected['name']}]...")

# ==========================================
# 2. 掃描與過濾
# ==========================================
try:
    p_info = utils.ensure_dict(projects_api.get_project(PROJECT_ID, opts={}))
    proj_name = p_info["name"]
    sec_res = sections_api.get_sections_for_project(PROJECT_ID, opts={})
    sections_map = {
        s["gid"]: utils.clean_filename(s["name"])
        for s in [utils.ensure_dict(x) for x in sec_res]
    }
    sections_map["uncategorized"] = "未分類"
except Exception as e:
    sys.exit(f"❌ API Error: {e}")

# 黑名單
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

# 全域掃描
curr_time_iso = datetime.datetime.now(datetime.timezone.utc).strftime(
    "%Y-%m-%dT%H:%M:%S.%fZ"
)
print("\n🔍 掃描全專案 Metadata...")
tasks_res = tasks_api.get_tasks_for_project(
    PROJECT_ID,
    opts={
        "opt_fields": "gid,name,created_at,modified_at,completed,due_on,notes,memberships.project.gid,memberships.section.gid,custom_fields.name,custom_fields.display_value"
    },
)
all_tasks = [utils.ensure_dict(t) for t in tasks_res]
last_sync = sync_mgr.get_last_sync(PROJECT_ID)

# 模式選擇
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
            - datetime.timedelta(minutes=5)
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        final_tasks = [t for t in all_tasks if t["modified_at"] > threshold]
elif mode == "2":
    print("輸入 'full' 或日期 'YYYY-MM-DD~YYYY-MM-DD'")
    d_in = input("👉 ").strip().lower()
    if d_in == "full":
        final_tasks = all_tasks
    elif "~" in d_in:
        try:
            s, e = d_in.split("~")
            final_tasks = [
                t for t in all_tasks if s.strip() <= t["created_at"][:10] <= e.strip()
            ]
        except:
            pass

if not final_tasks:
    if mode == "1" and input("❓ 更新時間戳記? (y/n): ").lower() == "y":
        sync_mgr.save_sync_time(PROJECT_ID, curr_time_iso)
    sys.exit("⚠️ 無任務需處理")

# ==========================================
# 3. 執行匯出
# ==========================================
root_dir = os.path.join(os.path.expanduser("~"), "Downloads", "Asana_Knowledge_Base")
proj_dir = os.path.join(root_dir, utils.clean_filename(proj_name))
att_dir = os.path.join(proj_dir, "attachments")

os.makedirs(proj_dir, exist_ok=True)
if config.DOWNLOAD_ATTACHMENTS:
    os.makedirs(att_dir, exist_ok=True)

print(f"\n🚀 處理 {len(final_tasks)} 筆任務...")

for idx, t in enumerate(final_tasks):
    sys.stdout.write(f"\r   進度 ({idx+1}/{len(final_tasks)}): {t['name'][:10]}...")
    sys.stdout.flush()

    # Section
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
        continue

    sec_name = sections_map.get(sec_gid, "未分類")
    sec_dir = os.path.join(proj_dir, sec_name)

    # 狀態檢查與清理
    if not t.get("completed"):
        if os.path.exists(sec_dir):
            for fname in os.listdir(sec_dir):
                if fname.endswith(".md"):
                    fpath = os.path.join(sec_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            head = [next(f) for _ in range(6)]
                        if any(f"gid: {t['gid']}" in line for line in head):
                            f.close()
                            os.remove(fpath)
                            sys.stdout.write(
                                f"\r   🗑️  刪除未完成舊檔: {fname[:20]}...       \n"
                            )
                    except:
                        pass
        continue

    os.makedirs(sec_dir, exist_ok=True)

    # ----------------------------------------------------------
    # 🧩 Fetch Data (修正變數定義位置)
    # ----------------------------------------------------------
    tid = t["gid"]

    # 1. 抓取留言 (定義 stories)
    stories = [
        utils.ensure_dict(s)
        for s in stories_api.get_stories_for_task(
            tid, opts={"opt_fields": "created_at,resource_subtype,text,created_by.name"}
        )
    ]

    # 2. 抓取附件 (含 parent 資訊，用於分類)
    all_raw_attachments = [
        utils.ensure_dict(a)
        for a in attachments_api.get_attachments_for_object(
            parent=tid,
            opts={
                "opt_fields": "gid,name,download_url,parent.resource_type,parent.gid"
            },
        )
    ]

    # 分類附件
    task_attachments = []
    story_attachment_map = {}

    for att in all_raw_attachments:
        p_type = att.get("parent", {}).get("resource_type")
        p_gid = att.get("parent", {}).get("gid")

        if p_type == "story" and p_gid:
            if p_gid not in story_attachment_map:
                story_attachment_map[p_gid] = []
            story_attachment_map[p_gid].append(att)
        else:
            task_attachments.append(att)

    # 3. 抓取子任務
    subs_meta = [
        utils.ensure_dict(s)
        for s in tasks_api.get_subtasks_for_task(tid, opts={"opt_fields": "gid,name"})
    ]
    full_subs = []
    for sm in subs_meta:
        try:
            sd = utils.ensure_dict(
                tasks_api.get_task(
                    sm["gid"], opts={"opt_fields": "gid,name,completed,notes,due_on"}
                )
            )
            ss = [
                utils.ensure_dict(s)
                for s in stories_api.get_stories_for_task(
                    sm["gid"],
                    opts={
                        "opt_fields": "created_at,resource_subtype,text,created_by.name"
                    },
                )
            ]
            # 子任務附件也需要抓
            sa = [
                utils.ensure_dict(a)
                for a in attachments_api.get_attachments_for_object(
                    parent=sm["gid"], opts={"opt_fields": "gid,name,download_url"}
                )
            ]
            full_subs.append({"meta": sd, "stories": ss, "attachments": sa})
        except:
            full_subs.append({"meta": sm, "stories": [], "attachments": []})

    # ----------------------------------------------------------
    # 📝 Markdown Gen (修正後的邏輯)
    # ----------------------------------------------------------
    safe_title = t.get("name") or "untitled"
    c_at = t["created_at"][:10]
    exp = (
        datetime.datetime.strptime(c_at, "%Y-%m-%d") + datetime.timedelta(days=365)
    ).strftime("%Y-%m-%d")
    status_str = "completed" if t.get("completed") else "active"

    md = [
        "---",
        "type: task",
        f"gid: {tid}",
        f'title: "{utils.clean_filename(safe_title)}"',
        f"status: {status_str}",
        f"created_date: {c_at}",
        f"modified_at: {t.get('modified_at')}",
        f"expiry_date: {exp}",
        f'section: "{sections_map.get(sec_gid)}"',
    ]

    if t.get("custom_fields"):
        for cf in t["custom_fields"]:
            if cf.get("display_value"):
                md.append(
                    f"cf_{utils.clean_filename(cf['name'])}: \"{cf['display_value']}\""
                )
    md.append("---\n")

    md.append(f"# {'✅' if t['completed'] else '🔲'} {safe_title}")
    md.append(
        f"\n## 📌 基本資訊\n- **連結**: [Asana](https://app.asana.com/0/{PROJECT_ID}/{tid})"
    )
    if t.get("custom_fields"):
        md.append("- **自訂欄位**:")
        for cf in t["custom_fields"]:
            if cf.get("display_value"):
                md.append(f"  - {cf['name']}: `{cf['display_value']}`")

    md.append(f"\n## 📝 任務描述\n{t.get('notes') or '*(無)*'}")

    # (A) 任務附件 (扣除留言附件)
    if task_attachments:
        md.append("\n## 📎 任務附件")
        for a in task_attachments:
            link, _ = utils.process_attachment_link(a, tid, att_dir)
            md.append(f"- {link}")

    # (B) 討論紀錄 (含附件)
    if stories:
        md.append("\n## 💬 討論紀錄")
        for s in stories:
            if s["resource_subtype"] == "comment_added":
                u = s.get("created_by", {}).get("name", "User")
                txt = s["text"]
                md.append(
                    f"> **{u} ({s['created_at'][:10]})**: {txt.replace(chr(10), '  '+chr(10))}"
                )

                # 檢查是否有附件歸屬於此留言
                s_gid = s["gid"]
                if s_gid in story_attachment_map:
                    for sa in story_attachment_map[s_gid]:
                        link, _ = utils.process_attachment_link(sa, tid, att_dir)
                        md.append(f"  > 📎 {link}")
                md.append("")

    # (C) 子任務
    if full_subs:
        md.append("\n---\n## 🔨 子任務")
        for i, item in enumerate(full_subs, 1):
            s = item["meta"]
            md.append(f"### {i}. {s['name']}")
            if s.get("notes"):
                md.append(f"  > {s['notes'].replace(chr(10), chr(10)+'  >')}\n")

            if item["attachments"]:
                md.append("  - **附件**:")
                for sa in item["attachments"]:
                    link, _ = utils.process_attachment_link(sa, s["gid"], att_dir)
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

    # Save
    fname = f"{c_at.replace('-','')}_{utils.clean_filename(safe_title)}.md"
    if len(fname) > 100:
        fname = fname[:100] + ".md"
    with open(os.path.join(sec_dir, fname), "w", encoding="utf-8") as f:
        f.write("\n".join(md))

if mode == "1":
    sync_mgr.save_sync_time(PROJECT_ID, curr_time_iso)
    print(f"\n✅ 增量同步完成！時間戳記已更新。")
else:
    print(f"\n✅ 匯出完成！")
