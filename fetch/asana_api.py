# 檔案用途：封裝 Asana API 相關取數邏輯

from typing import Dict, List, Tuple
from asana.rest import ApiException

from core import utils, config
from core.models import AsanaApis, AttachmentData
from services import llm_processor


def _process_attachments_with_llm(
    api_attachments: List[dict], parent_gid: str, save_dir: str
) -> List[AttachmentData]:
    """
    內部輔助函式：批次處理附件列表
    動作：1. 下載檔案  2. 呼叫 GPT-4o-mini 分析  3. 封裝資料
    """
    processed_list = []

    for att in api_attachments:
        att = utils.ensure_dict(att)

        # 1. 下載檔案 (並取得本地路徑)
        # utils.process_attachment_link 會回傳 (markdown_link, local_path)
        # 這裡我們只需要 local_path
        _, local_path = utils.process_attachment_link(att, parent_gid, save_dir)

        # 2. 執行 LLM 分析 (僅當有本地檔案且設定開啟時)
        analysis_result = None
        if local_path and config.DOWNLOAD_ATTACHMENTS:
            # 呼叫 GPT-4o-mini
            analysis_result = llm_processor.analyze_image(local_path)

        # 3. 封裝資料為 AttachmentData 物件，讓後續的流程能用 .ocr_text 拿到 AI 的分析結果
        processed_list.append(
            AttachmentData(
                gid=att["gid"],
                name=att["name"],
                download_url=att.get("download_url"),
                local_path=local_path,
                ocr_text=analysis_result,  # 這裡存的是 LLM 的分析結果
            )
        )

    return processed_list


def fetch_task_context(
    task_gid: str, apis: AsanaApis, att_dir: str  # 參數：附件儲存目錄 (用途:下載附件)
) -> Tuple[
    List[AttachmentData], Dict[str, List[AttachmentData]], List[dict], List[dict]
]:
    """
    取得單一任務的完整上下文 (Context)，並完成所有前處理。

    Returns:
        task_attachments (List[AttachmentData]): 主任務附件
        story_attachment_map (Dict): 留言附件對照表
        stories (List[dict]): 留言列表
        full_subs (List[dict]): 子任務詳情
    """

    # ==========================================
    # 1. 抓取留言
    # ==========================================
    stories = [
        utils.ensure_dict(s)
        for s in apis.stories.get_stories_for_task(
            task_gid,
            opts={"opt_fields": "gid,created_at,resource_subtype,text,created_by.name"},
        )
    ]

    # ==========================================
    # 2. 抓取附件 & 歸位 & LLM 分析
    # ==========================================
    # 先抓取所有附件的 Metadata
    all_raw_attachments = [
        utils.ensure_dict(a)
        for a in apis.attachments.get_attachments_for_object(
            parent=task_gid,
            opts={
                "opt_fields": "gid,name,download_url,parent.resource_type,parent.gid"
            },
        )
    ]

    # 分類：這張圖屬於 Task 還是 Story？
    task_atts_raw: List[dict] = []
    story_atts_map_raw: Dict[str, List[dict]] = {}

    for att in all_raw_attachments:
        p_type = att.get("parent", {}).get("resource_type")
        p_gid = att.get("parent", {}).get("gid")

        if p_type == "story" and p_gid:
            story_atts_map_raw.setdefault(p_gid, []).append(att)
        else:
            task_atts_raw.append(att)

    # 處理任務附件(下載 + LLM)
    task_attachments = _process_attachments_with_llm(task_atts_raw, task_gid, att_dir)

    # 處理留言附件 (批次處理 map 中的每一組)
    story_attachment_map = {}
    for s_gid, att_list in story_atts_map_raw.items():
        story_attachment_map[s_gid] = _process_attachments_with_llm(
            att_list, task_gid, att_dir
        )

    # ==========================================
    # 3. 抓取子任務
    # ==========================================
    subs_meta = [
        utils.ensure_dict(s)
        for s in apis.tasks.get_subtasks_for_task(
            task_gid, opts={"opt_fields": "gid,name"}
        )
    ]

    full_subs: List[dict] = []
    for sm in subs_meta:
        try:
            # 3-1. 子任務詳情
            sd = utils.ensure_dict(
                apis.tasks.get_task(
                    sm["gid"],
                    opts={
                        "opt_fields": "gid,name,completed,notes,due_on,custom_fields.name,custom_fields.display_value"
                    },
                )
            )
            # 3-2. 子任務留言
            ss = [
                utils.ensure_dict(s)
                for s in apis.stories.get_stories_for_task(
                    sm["gid"],
                    opts={
                        "opt_fields": "gid,created_at,resource_subtype,text,created_by.name"
                    },
                )
            ]
            # 3-3. 子任務附件 (也要下載 + LLM)
            sa_raw = [
                utils.ensure_dict(a)
                for a in apis.attachments.get_attachments_for_object(
                    parent=sm["gid"], opts={"opt_fields": "gid,name,download_url"}
                )
            ]
            sa_processed = _process_attachments_with_llm(sa_raw, sm["gid"], att_dir)

            # 這裡 subtask 的結構稍微不同，attachments 欄位存放的是處理過的 AttachmentData 列表
            full_subs.append({"meta": sd, "stories": ss, "attachments": sa_processed})

        except (ApiException, Exception) as e:
            print(f"⚠️ 抓取子任務失敗 {sm.get('gid')}: {e}")
            full_subs.append({"meta": sm, "stories": [], "attachments": []})

    return task_attachments, story_attachment_map, stories, full_subs
