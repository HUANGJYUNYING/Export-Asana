# 檔案用途：封裝 Asana API 相關取數邏輯（含網路/I/O 副作用）。

from typing import Dict, List, Tuple

from asana.rest import ApiException

import utils
from models import AsanaApis


def fetch_task_context(
    task_gid: str,
    apis: AsanaApis,
) -> Tuple[List[dict], Dict[str, List[dict]], List[dict], List[dict]]:
    """
    取得單一任務的留言、附件、留言附件對應、子任務完整內容。

    Args:
        task_gid (str): 任務 GID。
        apis (AsanaApis): Asana API client 集合。

    Returns:
        Tuple[List[dict], Dict[str, List[dict]], List[dict], List[dict]]:
            (task_attachments, story_attachment_map, stories, full_subs)
    """
    stories = [
        utils.ensure_dict(s)
        for s in apis.stories.get_stories_for_task(
            task_gid,
            opts={"opt_fields": "gid,created_at,resource_subtype,text,created_by.name"},
        )
    ]

    all_raw_attachments = [
        utils.ensure_dict(a)
        for a in apis.attachments.get_attachments_for_object(
            parent=task_gid,
            opts={
                "opt_fields": "gid,name,download_url,parent.resource_type,parent.gid"
            },
        )
    ]

    task_attachments: List[dict] = []
    story_attachment_map: Dict[str, List[dict]] = {}
    for att in all_raw_attachments:
        p_type = att.get("parent", {}).get("resource_type")
        p_gid = att.get("parent", {}).get("gid")
        if p_type == "story" and p_gid:
            story_attachment_map.setdefault(p_gid, []).append(att)
        else:
            task_attachments.append(att)

    subs_meta = [
        utils.ensure_dict(s)
        for s in apis.tasks.get_subtasks_for_task(
            task_gid, opts={"opt_fields": "gid,name"}
        )
    ]
    full_subs: List[dict] = []
    for sm in subs_meta:
        try:
            sd = utils.ensure_dict(
                apis.tasks.get_task(
                    sm["gid"],
                    opts={"opt_fields": "gid,name,completed,notes,due_on"},
                )
            )
            ss = [
                utils.ensure_dict(s)
                for s in apis.stories.get_stories_for_task(
                    sm["gid"],
                    opts={
                        "opt_fields": "gid,created_at,resource_subtype,text,created_by.name"
                    },
                )
            ]
            sa = [
                utils.ensure_dict(a)
                for a in apis.attachments.get_attachments_for_object(
                    parent=sm["gid"], opts={"opt_fields": "gid,name,download_url"}
                )
            ]
            full_subs.append({"meta": sd, "stories": ss, "attachments": sa})
        except ApiException as e:
            print(
                f"⚠️ 抓取子任務失敗 {sm.get('gid')}: {getattr(e, 'status', '')} {getattr(e, 'reason', e)}"
            )
            full_subs.append({"meta": sm, "stories": [], "attachments": []})
        except Exception as e:
            print(f"⚠️ 抓取子任務失敗 {sm.get('gid')}: {e}")
            full_subs.append({"meta": sm, "stories": [], "attachments": []})

    return task_attachments, story_attachment_map, stories, full_subs
