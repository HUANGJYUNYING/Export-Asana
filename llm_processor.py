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
    你是一個資安助手。請分析圖片內容：
    1. 轉錄關鍵文字 (OCR)。
    2. 說明圖片意義 (例如：系統報錯截圖)。
    3. **個資遮罩**：將人名替換為 [人員]、身分證 [ID_CARD]、電話 [PHONE]、Email [EMAIL]。
    請直接輸出最終結果，不要廢話。
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

    # 分批處理 (Chunking) - 避免一次送太多導致 Timeout 或 Token 溢出
    # 設定每批處理 20 個字串 (依您的內容長度可調整)
    CHUNK_SIZE = 20
    final_mapping = {}

    system_prompt = """
    你是一個專業的資料去識別化專家 (DLP)。
    我會給你一個 JSON 物件，Key 是 ID，Value 是原始文字。
    請將使用者提供的文字進行【個資遮罩】，規則如下：
    
    1. **人名**：替換為 [人員]。包含全名(王小明)或暱稱(小明、阿明)。
       - 注意：不要遮掉公眾人物、系統名稱(如: 飛鴿, Tia)或職稱。
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

    請回傳一個 JSON 物件，Key 保持不變，Value 為遮罩後的文字。
    
    IMPORTANT: You must output valid JSON format.
    """

    # 計算批次
    total_chunks = math.ceil(len(unique_texts) / CHUNK_SIZE)

    for i in range(total_chunks):
        chunk = unique_texts[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]

        # 轉換為 JSON 格式送給 AI { "0": "文字A", "1": "文字B" }
        input_json = {str(idx): txt for idx, txt in enumerate(chunk)}

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(input_json, ensure_ascii=False)},
        ]

    try:
        # 強制要求回傳 JSON Object
        response_str = _call_azure_openai(
            messages, response_format={"type": "json_object"}
        )

        if response_str:
            output_json = json.loads(response_str)
            # 將結果映射回原始文字
            for idx, masked_txt in output_json.items():
                original_txt = input_json.get(idx)
                if original_txt:
                    final_mapping[original_txt] = masked_txt
    except Exception as e:
        print(f"⚠️ 批次遮罩部分失敗: {e}")
        # 失敗時，保留原值以免程式崩潰
        for txt in chunk:
            final_mapping[txt] = txt

    return final_mapping
