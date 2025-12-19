# 檔案用途：集中定義資料模型與型別（無 I/O、副作用）。

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from asana.api.attachments_api import AttachmentsApi
from asana.api.projects_api import ProjectsApi
from asana.api.sections_api import SectionsApi
from asana.api.stories_api import StoriesApi
from asana.api.tasks_api import TasksApi


@dataclass
class TaskRenderContext:
    """渲染 Markdown 所需的資料集合。

    屬性:
        task (dict): Asana 任務原始資料。
        project_id (str): 專案 GID。
        section_name (str): 區段名稱，已清洗。
        att_dir (str): 附件儲存目錄路徑。
        task_attachments (List[dict]): 任務層級附件列表。
        stories (List[dict]): 留言列表。
        story_attachment_map (Dict[str, List[dict]]): 留言附件映射。
        subtasks (List[dict]): 子任務與其留言、附件的集合。
    """

    task: dict
    project_id: str
    section_name: str
    att_dir: str
    task_attachments: List[dict] = field(default_factory=list)
    stories: List[dict] = field(default_factory=list)
    story_attachment_map: Dict[str, List[dict]] = field(default_factory=dict)
    subtasks: List[dict] = field(default_factory=list)


@dataclass
class AsanaApis:
    """封裝 Asana API client，便於在層與層之間傳遞。

    屬性:
        projects (ProjectsApi): 專案相關 API。
        tasks (TasksApi): 任務相關 API。
        stories (StoriesApi): 留言相關 API。
        attachments (AttachmentsApi): 附件相關 API。
        sections (SectionsApi): 區段相關 API。
    """

    projects: ProjectsApi
    tasks: TasksApi
    stories: StoriesApi
    attachments: AttachmentsApi
    sections: SectionsApi


@dataclass
class AttachmentData:
    """附件的標準化資料結構 (含 LLM 分析結果)"""

    gid: str
    name: str
    download_url: str
    local_path: Optional[str] = None  # 下載後的本地路徑
    ocr_text: Optional[str] = None  # LLM 分析結果
