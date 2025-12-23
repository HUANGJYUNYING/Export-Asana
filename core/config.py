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
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "service_account.json")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
ENABLE_LLM_ANALYSIS = str_to_bool(os.getenv("ENABLE_LLM_ANALYSIS", "True"))
EXPIRY_FIELD_NAME = os.getenv("EXPIRY_FIELD_NAME", "知識截止日")


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


# --- 路徑設定(本地測試用) ---
BASE_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Asana_Knowledge_Base")
RAW_DIR = os.path.join(BASE_DIR, "raw_data")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed_data")
QA_DIR = os.path.join(BASE_DIR, "qa_data")
