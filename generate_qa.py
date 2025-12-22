import os
import sys
import json
import glob
import re
import yaml  # pip install pyyaml
from openai import AzureOpenAI
from dotenv import load_dotenv
import config

load_dotenv()

# 設定路徑
PROCESSED_DIR = config.PROCESSED_DIR
QA_OUTPUT_DIR = os.path.join(config.BASE_DIR, "qa_dataset")
os.makedirs(QA_OUTPUT_DIR, exist_ok=True)

# Azure Client
client = AzureOpenAI(
    api_key=config.AZURE_OPENAI_API_KEY,
    api_version=config.AZURE_OPENAI_API_VERSION,
    azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
)


def extract_metadata_and_content(md_content):
    """
    分離 Markdown 的 YAML 檔頭與內文
    """
    # 簡單 regex 抓取 --- 之間的內容
    match = re.match(r"^---\n(.*?)\n---\n(.*)", md_content, re.DOTALL)
    if match:
        yaml_text = match.group(1)
        body = match.group(2)
        try:
            meta = yaml.safe_load(yaml_text)
            return meta, body
        except:
            return {}, md_content
    return {}, md_content


def generate_qa(md_content):
    """
    輸入：Markdown 全文 (含圖片分析內容)
    輸出：JSON 物件 { "question": "...", "answer": "..." }
    """
    system_prompt = """
    你是一名企業知識庫 QA 整理專用 AI 助手，負責將 Asana 任務紀錄（Markdown 格式） 轉換為結構化、可審計、可追溯來源的 Q&A 資料。

    你的核心原則是：
    只整理已發生與已被證實的內容，不補寫、不推論、不改寫使用者的問題語意。

    一、輸入資料理解

    Asana 任務描述中，已包含一份結構化的使用者問題回報表單，格式固定，可能包含：

    - 提問人營運單位  
    - 提問人姓名  
    - 提問人 Line 顯示名稱  
    - 提問人聯絡電話  
    - 提問人聯絡信箱  
    - 提問人問題主旨  
    - 提問人問題內文  
    - Line 客服平台連結  

    二、Question（Q）產生規則（嚴格鎖定）

    Question 的唯一來源

    僅能由以下兩個欄位組成：
    - 提問人問題主旨  
    - 提問人問題內文  

    組成方式
    直接以以下格式串接：

    `<提問人問題主旨> - <提問人問題內文>`

    不得改寫語意  
    不得補充背景  
    不得調整問題範圍  

    允許的最小處理（僅限格式）
    - 移除多餘空白或換行  
    - 修正明顯的標點錯誤  
    - 確保為單一句可讀的問句  

    嚴格禁止
    - 重新描述問題  
    - 改寫成更通用的問法  
    - 新增系統名稱、流程或限制條件  
    - 推測使用者實際想問的「延伸問題」  

    📌 原則：
    Question 必須與使用者原始提問語意完全一致，可一對一回溯。

    三、Answer（A）產生規則

    Answer 僅能根據以下內容產生：
    - 討論紀錄（Stories）中已明確達成共識的結論  
    - 子任務中已完成且具體的處理方式  
    - 圖片分析結果中已出現的操作步驟或判斷結果  

    Answer 必須：
    - 描述實際採取的解決方式或確認結果  
    - 使用中立、制式、可操作的文字  
    - 不包含推論或假設  

    Answer 禁止：
    - 補充「可能原因」  
    - 延伸「建議做法」  
    - 合併多種未定論說法  

    四、Q&A 有效性判斷（不可妥協）

    若任務最終結果僅包含以下任一情況，必須回傳 `valid: false`：
    - 僅表示狀態（已修正、已完成、已結案）  
    - 僅表示流程轉交（已轉交其他部門）  
    - 僅有確認性回覆（OK、Done）  
    - 無任何可重複的操作、設定或判斷條件  

    判斷標準：
    若其他人無法依此內容自行處理相同問題，則不得產生 Q&A。

    五、個人資料與敏感資訊遮罩（雙重防線）
    即使 Question 來自使用者原文，仍需確保輸出結果中不殘留任何個資或敏感資訊：

    - 人名 → `[人員]`  
    - 電話 → `[PHONE]`  
    - Email → `[EMAIL]`  
    - 員工 / 客戶編號 → `[USER_ID]`  
    - 保單號碼、案件編號、交易序號、證照號碼等具唯一識別性的編號 → `[REFERENCE_ID]`  
    - 其他疑似敏感資訊 → `[SENSITIVE_INFO]`  

    原則：
    寧可誤遮，也不可漏遮

    六、分類與標籤

    - `category`：依問題本質推測分類（如：BMS、權限、流程、系統錯誤）  

    - `tags`：  
        - 2–5 個關鍵字  
        - 只使用任務中已出現的詞彙  
        - 不新增推測性關鍵字  

    七、輸出格式（JSON Mode，嚴格遵守）

    有效 Q&A：
    ```json
    {
    "valid": true,
    "question": "提問人問題主旨 - 提問人問題內文",
    "answer": "依任務紀錄整理出的最終處理方式",
    "category": "問題分類",
    "tags": ["關鍵字1", "關鍵字2"]
    }

    無效 Q&A：
    ```json
    {
    "valid": false
    }

    """

    try:
        response = client.chat.completions.create(
            model=config.AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": md_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ QA 生成失敗: {e}")
        return None


def run_qa_generation(target_proj_name=None):
    """
    Args:
        target_proj_name (str): 若有指定，只處理該專案；否則處理全部。
    """
    if not config.ENABLE_LLM_ANALYSIS:
        print("⚠️ LLM 分析功能未開啟，跳過 QA 生成。")
        return

    # 搜尋來源
    if target_proj_name:
        search_path = os.path.join(config.PROCESSED_DIR, target_proj_name, "**", "*.md")
    else:
        search_path = os.path.join(config.PROCESSED_DIR, "**", "*.md")

    md_files = glob.glob(search_path, recursive=True)
    if not md_files:
        print("❌ 找不到來源文件。")
        return

    print(f"\n🚀 [Stage 3] QA 生成中 (共 {len(md_files)} 檔)...")

    for i, fpath in enumerate(md_files):
        # 顯示進度
        sys.stdout.write(f"\r   處理中 ({i+1}/{len(md_files)})...")
        sys.stdout.flush()

        with open(fpath, "r", encoding="utf-8") as f:
            raw_content = f.read()

        # 1. 提取 Metadata (為了繼承 expiry_date)
        meta, body = extract_metadata_and_content(raw_content)

        # 簡單過濾：如果沒有 meta 或未完成，跳過
        if not meta or meta.get("status") != "completed":
            continue

        # 2. 生成 QA
        qa_result = generate_qa(body)

        if qa_result and qa_result.get("valid"):
            # 3. 準備存檔路徑
            rel_path = os.path.relpath(fpath, config.PROCESSED_DIR)
            save_path = os.path.join(config.QA_DIR, rel_path)

            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            # 4. 製作 QA Markdown (含 Metadata)
            qa_md_lines = [
                "---",
                "type: qa_pair",
                f"source_gid: {meta.get('gid')}",
                f"title: \"{meta.get('title')}\"",
                f"created_date: {meta.get('created_date')}",
                f"expiry_date: {meta.get('expiry_date')}",
                f"section: \"{meta.get('section')}\"",
                "---",
                "\n",
                f"# ❓ {qa_result['question']}",
                "\n",
                f"## 💡 解答",
                f"{qa_result['answer']}",
                "\n",
                f"## 🏷️ 標籤",
                f"{', '.join(qa_result.get('tags', []))}",
                "\n",
                f"> [查看原始文件](../../processed_data/{rel_path.replace(os.sep, '/')})",
            ]

            with open(save_path, "w", encoding="utf-8") as f:
                f.write("\n".join(qa_md_lines))

    print(f"\n✅ QA 生成完成！儲存於: {config.QA_DIR}")


if __name__ == "__main__":
    # 獨立執行時不指定專案，跑全量
    run_qa_generation()
