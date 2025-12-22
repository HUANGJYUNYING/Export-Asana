import os
import base64
import requests
import json
import math
from dotenv import load_dotenv
import config
import openai_client

load_dotenv()


def encode_image(image_path):
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except:
        return None


def _call_azure_openai(messages, max_tokens=800, response_format=None):
    """內部共用的 API 呼叫函式"""
    try:
        # 1. 取得 Client (工廠模式)
        client = openai_client.get_azure_openai_client()

        # 2. 取得部署名稱
        deployment_name = openai_client.get_chat_deployment_name()

        # 3. 呼叫 API
        response = client.chat.completions.create(
            model=deployment_name,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
            response_format=response_format,
        )

        return response.choices[0].message.content

    except ValueError as ve:
        print(f"❌ 設定錯誤: {ve}")
        return None
    except Exception as e:
        print(f"❌ LLM 呼叫失敗: {e}")
        return None


# --- 圖片分析  ---
def analyze_image(image_path):
    """分析圖片：OCR + 語意理解 + 遮罩"""
    b64_img = encode_image(image_path)
    if not b64_img:
        return None

    system_prompt = """
    ```markdown
    你是一名金融與保險業專用的資安與法遵導向 AI 助手，負責協助企業進行圖片內容分析、事件紀錄整理與內部知識庫建置。  
    你的首要原則為：資訊安全、個資保護、法規遵循（KYC / AML / 個資法 / 金融監理要求）。

    你將接收一張圖片，並依下列規則輸出結構化、可歸檔的 Markdown 分析報告。

    ---

    ## 一、圖片類型判斷（Semantic Classification）

    請先判斷圖片的主要性質，例如但不限於：

    - 核保／理賠／保單系統畫面  
    - 金融或保險系統錯誤訊息  
    - 內部後台操作截圖  
    - 客戶對話（Line、Email、客服系統）  
    - 報表、清冊、申請文件畫面  

    請以一句話清楚描述圖片用途與情境。

    ---

    ## 二、關鍵資訊擷取（Smart OCR）

    請避免逐字轉錄畫面內容，僅擷取對金融業務判讀、事件追蹤或知識保存有價值的資訊，包括：

    - 系統錯誤代碼（Error Code）  
    - 系統或流程提示訊息  
    - 關鍵數據、狀態、異常結果  
    - 對話或文件中的「核心業務重點」  

    ⚠️ 請刻意忽略以下內容：
    - 公司標誌、水印、頁首頁尾
    - 廣告、促銷訊息
    - 非業務相關的裝飾性圖片
    - 時間戳記  
    - 視窗選單、工具列  
    - 無業務意義的背景文字  

    ---

    ## 三、個人資料與敏感資訊遮罩（金融保險業 最高遮罩標準）

    請主動辨識並遮罩所有可能用於識別個人、客戶、帳戶、保單、交易或案件的資訊。

    ### （一）個人資料（必須遮罩）

    - 人名（全名、暱稱）→ `[人員]`  
        ⚠️ 不遮罩：系統名稱、產品名稱、職稱  
    - 電話 / 手機 → `[PHONE]`  
    - Email → `[EMAIL]`  
    - 身分證字號 / 居留證號 → `[ID_CARD]`  
    - 員工編號 / 業務員代碼 → `[USER_ID]`  

    ### （二）金融／保險專屬識別碼（重點）

    凡是具備唯一識別性、可回溯到實際客戶、保單、交易或文件的號碼，不論名稱為何，一律視為敏感資訊並遮罩，包含但不限於：

    - 保單號碼 / 保單流水號  
    - 客戶編號 / 客戶代碼  
    - 核保案件編號 / 理賠案號  
    - 投保申請單號 / 受理編號  
    - 證照號碼 / 執業證照號碼  
    - 交易序號 / 帳戶號碼 / 合約編號  
    - 任何英數混合或自訂格式的代碼  

    📌 遮罩原則（關鍵規則）

    - 只要該號碼不是系統錯誤碼（Error Code），且  
    - 可能對應真實客戶、保單、帳戶或金融交易，即必須遮罩。  

    📌 統一替換為：  
    `[REFERENCE_ID]`（金融保險業建議標準）

    ### （三）高風險金融敏感資訊

    - 帳戶餘額、交易金額 → `[SENSITIVE_INFO]`  
    - 信用卡號、銀行帳號 → `[SENSITIVE_INFO]`  
    - 地址、門牌、地段 → `[SENSITIVE_INFO]`  
    - 尚未公開的內部專案或系統代碼 → `[SENSITIVE_INFO]`  

    📌 不確定時的原則：  
    寧可誤遮，也不可漏遮

    ---

    ## 四、輸出格式（嚴格遵守）

    請僅輸出以下 Markdown 結構，不加任何說明、前言或評論：

    **圖片類型**：`<圖片分類結果>`  

    **關鍵訊息**：
    - 錯誤代碼：`<如有>`  
    - 提示訊息：`<關鍵系統或業務文字>`  
    - 相關數據：`<重要狀態或指標>`  

    **內容摘要**：  
    `<1–2 句說明此圖片所呈現的金融或保險業務情境與問題重點>`

    ---

    ## 五、輸出語言與風格

    - 輸出語言：繁體中文  
    - 語氣：中立、專業、符合法遵與內控文件標準  
    - 僅輸出最終結果  

    請回傳一個 JSON 物件，Key 保持不變，Value 為遮罩後的文字。  
    IMPORTANT: You must output valid JSON format.
```

    """

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"},
                }
            ],
        },
    ]
    return _call_azure_openai(messages)


# --- 純文字內容遮罩 ---
def mask_batch_texts(text_list):
    """
    使用 LLM 對文字進行個資遮罩 (取代 masking.py)
    """
    if not text_list:
        return {}

    # 過濾空字串與重複項以節省 Token
    unique_texts = list(set([t for t in text_list if t and len(t) > 1]))
    if not unique_texts:
        return {}

    final_mapping = {}

    system_prompt = """
    你是一個專業的資料去識別化專家 (DLP)。
    我會給你一個 JSON 物件，Key 是 ID，Value 是原始文字。
    請將使用者提供的文字進行【個資遮罩】，規則如下：

    1. **人名**：替換為 [人員]。包含全名(王小明)或暱稱(小明、阿明)。
        - 注意：不要遮掉系統名稱(如: 飛鴿, Tia)或職稱。
    2. **電話/手機**：替換為 [PHONE]。
    3. **Email**：替換為 [EMAIL]。
    4. **身分證字號**：替換為 [ID_CARD]。
    5. **員工編號/ID**：替換為 [USER_ID]。
    6. **Asana/Line 連結**：替換為 [LINK]。
    7. **其他敏感資訊**：如信用卡號、地址等，請視情況遮罩並替換成 [SENSITIVE_INFO]。

    **重要原則**：
    - **保持原意**：除了個資外，不要修改任何其他文字、標點或格式。
    - **嚴謹**：寧可錯殺(遮罩)，不可放過。
    - 直接輸出處理後的文字，不要加引號或解釋。
    - 輸出語言皆為繁體中文。

    請回傳一個 JSON 物件，Key 保持不變，Value 為遮罩後的文字。
    IMPORTANT: You must output valid JSON format.

    """

    MAX_CHARS_PER_BATCH = 10000

    current_batch = {}
    current_char_count = 0

    # 定義送出函式 (閉包)
    def send_batch(batch_data):
        if not batch_data:
            return {}

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(batch_data, ensure_ascii=False)},
        ]

        try:
            # 預留足夠的 max_tokens (輸入長度的 1.2 倍 + 緩衝，確保 JSON 不被截斷)
            # max_tokens 不能超過模型上限 (gpt-4o-mini output max 是 16k tokens)
            estimated_tokens = int(current_char_count * 1.5)
            safe_max_tokens = min(16000, max(1000, estimated_tokens))

            response_str = _call_azure_openai(
                messages,
                max_tokens=safe_max_tokens,
                response_format={"type": "json_object"},
            )

            if response_str:
                return json.loads(response_str)
        except Exception as e:
            print(f"⚠️ 遮罩批次失敗 (長度 {current_char_count}): {e}")
            # 這裡可以考慮 retry 機制，或是 fallback 到 regex
        return {}

    # 開始分裝
    print(f"    AI 遮罩運算中 (總字數: {sum(len(t) for t in unique_texts)})...")

    for idx, text in enumerate(unique_texts):
        text_len = len(text)

        # 如果單一條目就超過上限 (極端情況)，只能單獨送
        if text_len > MAX_CHARS_PER_BATCH:
            # 強制送出當前累積的
            if current_batch:
                result = send_batch(current_batch)
                final_mapping.update(result)
                current_batch = {}
                current_char_count = 0

            # 單獨送出這一條巨無霸
            print(f"      ⚠️ 發現超長文本 ({text_len} 字)，單獨處理...")
            single_result = send_batch({str(idx): text})
            # 如果失敗，至少回傳原值，不要空掉
            final_mapping[text] = single_result.get(str(idx), text)
            continue

        # 檢查加入後是否會爆掉
        if current_char_count + text_len > MAX_CHARS_PER_BATCH:
            # 送出這一批
            result = send_batch(current_batch)
            # 補回原值 (若 AI 漏掉某些 Key，至少原值要在)
            for k, v in current_batch.items():
                if k not in result:
                    result[k] = v
            final_mapping.update(result)

            # 重置
            current_batch = {}
            current_char_count = 0

        # 加入當前批次
        current_batch[str(idx)] = text
        current_char_count += text_len

    # 處理最後一小批
    if current_batch:
        result = send_batch(current_batch)
        for k, v in current_batch.items():
            if k not in result:
                result[k] = v
        final_mapping.update(result)

    # 將 ID 映射回原始文字 (ID -> Masked Text) => (Original Text -> Masked Text)
    # 這是為了讓 process_data 可以用原始文字去查表
    output_lookup = {}
    for idx, original_text in enumerate(unique_texts):
        # 嘗試用 ID 找回傳值，找不到就用原值
        masked = final_mapping.get(str(idx), original_text)
        output_lookup[original_text] = masked

    return output_lookup
