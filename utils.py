import re
import os
import requests
import config  # 引入設定檔


def ensure_dict(obj):
    """確保物件轉換為 dict"""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return obj


def clean_filename(name):
    """清理檔名"""
    if not name:
        return "untitled"
    name = re.sub(r'[\\/*?:"<>|]', "_", name).replace("\n", "").strip()
    return name[:80]


def process_attachment_link(att, parent_gid, save_dir):
    """
    處理附件下載邏輯

    Returns:
        tuple: (Markdown連結字串, 本地檔案絕對路徑)
        如果沒有下載或下載失敗，本地路徑會回傳 None
    """
    att = ensure_dict(att)
    a_name = att.get("name", "unknown")
    a_url = att.get("download_url")
    a_gid = att.get("gid")

    # 檢查全域設定是否開啟下載
    if config.DOWNLOAD_ATTACHMENTS and a_url and save_dir:
        safe_fname = clean_filename(a_name)
        # 唯一檔名
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
