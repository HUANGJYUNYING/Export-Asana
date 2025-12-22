import re
import os
import requests
import config  # 引入設定檔
from typing import List
from asana import ApiClient, Configuration
from asana.api.stories_api import StoriesApi


def ensure_dict(obj):
    """確保物件轉換為 dict"""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return obj


def clean_filename(name):
    """
    清理檔名: 移除不合法字元，限制長度
    """

    if not name:
        return "untitled"
    name = re.sub(r'[\\/*?:"<>|]', "_", name).replace("\n", "").strip()
    return name[:80]


def process_attachment_link(att, parent_gid, save_dir):
    """
    下載附件並回傳資訊

    Args:
        att (dict): 附件物件
        parent_gid (str): 父任務 GID
        save_dir (str): 存檔目錄

    Returns:
        tuple: (Markdown連結字串, 本地檔案絕對路徑)
        * 如果沒下載或失敗，本地路徑回傳 None
    """
    att = ensure_dict(att)
    a_name = att.get("name", "unknown")
    a_url = att.get("download_url")
    a_gid = att.get("gid")

    # 檢查全域設定是否開啟下載
    if config.DOWNLOAD_ATTACHMENTS and a_url and save_dir:
        safe_fname = clean_filename(a_name)
        # 命名格式：{ParentID}_{AttachmentID}_{FileName}
        unique_fname = f"{parent_gid}_{a_gid}_{safe_fname}"
        local_path = os.path.join(save_dir, unique_fname)

        # 下載檔案 (強制覆蓋以確保最新)
        try:
            # 建議加上 stream=True 處理大檔案，這裡維持簡單寫法
            r = requests.get(a_url, timeout=30)
            if r.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(r.content)
            else:
                # 下載失敗，回傳 None 路徑
                return (f"[{a_name} (下載失敗)]({a_url})", None)
        except Exception as e:
            print(f"⚠️ 附件下載失敗 [{a_name}]: {e}")
            return (f"[{a_name} (下載失敗)]({a_url})", None)

        # ✅ 成功：回傳 (相對路徑連結, 本地絕對路徑)
        # 本地絕對路徑是用來給 OCR 讀取的
        return (f"[{a_name}](../attachments/{unique_fname})", local_path)
    else:
        # ❎ 不下載：回傳 (Asana網頁連結, None)
        return (f"[{a_name}]({a_url})", None)


def post_masking_preview(client, task_gid, markdown_content):
    """
    將遮罩結果回傳至 Asana 任務留言板供驗證

    Args:
        client: 已初始化的 ApiClient
        task_gid: 任務 GID
        masked_title: 任務標題遮罩後文字
        masked_notes: 任務描述遮罩後文字
        masked_stories: 任務留言遮罩後文字列表
    """
    # 環境變數控制是否上傳
    if os.getenv("ENABLE_UPLOAD_PREVIEW", "False") != "True":
        return

    # 加上一個簡單的 Header 區隔，避免混淆，但保留完整內容
    header = "🔒 **[系統自動生成] 完整資料處理預覽 (含個資遮罩與OCR)**\n\n"
    final_text = header + markdown_content

    # Asana 留言有字數限制 (約 65535 字元)
    # 為了防止 API 報錯導致程式中斷，做一個安全截斷
    if len(final_text) > 60000:
        final_text = final_text[:60000] + "\n\n⚠️ ...(內容過長已截斷)..."

    try:
        stories_api = StoriesApi(client)

        # Body
        request_body = {"data": {"text": final_text, "is_pinned": False}}

        # API Call
        stories_api.create_story_for_task(
            task_gid=str(task_gid), body=request_body, opts={}
        )
        print(f"   📤 已上傳完整預覽至任務: {task_gid}")

    except Exception as e:
        print(f"   ❌ 上傳預覽失敗: {e}")
