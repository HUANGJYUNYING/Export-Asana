import os
from dotenv import load_dotenv

# 載入 .env
load_dotenv()


def str_to_bool(value):
    if not value:
        return False
    return value.lower() in ("true", "1", "yes", "on")


# 全域設定
DOWNLOAD_ATTACHMENTS = str_to_bool(os.getenv("DOWNLOAD_ATTACHMENTS", "True"))
ENABLE_MASKING = str_to_bool(os.getenv("MASK_PII", "0"))
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "service_account.json")


# 讀取 Profiles
def load_asana_profiles():
    profiles = []
    idx = 1
    while True:
        name = os.getenv(f"ASANA_PROFILE_{idx}_NAME")
        token = os.getenv(f"ASANA_PROFILE_{idx}_TOKEN")
        project = os.getenv(f"ASANA_PROFILE_{idx}_PROJECT")
        if not (name and token and project):
            break
        profiles.append({"name": name, "token": token, "project": project})
        idx += 1
    return profiles
