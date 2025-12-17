import spacy
import re
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# ======================================================
# 1. 初始化
# ======================================================
try:
    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "zh", "model_name": "zh_core_web_lg"}],
    }
    provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
    nlp_engine = provider.create_engine()
except OSError:
    print(
        "❌ 錯誤: 找不到 spaCy 模型。請先執行: python -m spacy download zh_core_web_lg"
    )
    exit()

analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["zh"])
anonymizer = AnonymizerEngine()


# ======================================================
# 2. 輔助函數 (針對 Markdown 格式強化)
# ======================================================
def extract_known_names_from_asana(text):
    known_names = set()

    # 1. 抓 Header (提問人)
    # 允許中間有空白或 Markdown 符號
    known_names.update(re.findall(r"提問人姓名\s*[:：]\s*(.+)", text))
    known_names.update(re.findall(r"Line顯示名稱\s*[:：]\s*(.+)", text))

    # 2. 截取對話紀錄
    # 原始: > **朱OO (2025...
    # Regex 解釋:
    # >         開頭
    # \s*       空白
    # (?:\*\*)?  可選的粗體起始符號 **
    # ([^\(\*\s]+?)  捕捉名字 (排除括號、星號、空白)
    # (?:\*\*)?  可選的粗體結束符號 **
    # \s*       空白
    # \(        左括號
    # \d{4}     年份
    chat_pattern = r">\s*(?:\*\*)?([^\(\*\s]+?)(?:\*\*)?\s*\(\d{4}"
    known_names.update(re.findall(chat_pattern, text))

    # 3. 清洗
    cleaned_names = [n.strip() for n in known_names]
    # 過濾掉太短的字 (避免誤抓 "我", "你")
    cleaned_names = [n for n in cleaned_names if len(n) >= 2]

    # 排序：長的名字優先處理
    return sorted(list(set(cleaned_names)), key=len, reverse=True)


# ======================================================
# 3. 主處理邏輯
# ======================================================
def mask_asana_content(text):
    # A. 提取名單
    known_names = extract_known_names_from_asana(text)
    print(f"Debug - 偵測到已知人名: {known_names}")

    # 已知人名遮掉
    for name in known_names:
        # 使用 escape 避免名字裡有特殊符號
        # 並使用 compiled regex 確保全域替換
        text = re.sub(re.escape(name), "[人員]", text)

    # C. 第二層：Presidio 補漏
    # 設定白名單 (Allow List)，防止 reset, TIA, E學院 被當成人名
    allow_list = ["reset", "Reset", "TIA", "Tia", "E學院", "公文", "開門紅"]
    ad_hoc_recognizers = []

    # 1. 台灣身分證 (TW_ID)
    # 規則：首字大寫英文 + 第二字1/2/8/9 + 後面8碼數字
    # \b 代表單字邊界，避免抓到亂碼
    tw_id_pattern = Pattern(
        name="tw_id_regex", regex=r"\b[A-Z][1289]\d{8}\b", score=1.0
    )
    tw_id_recognizer = PatternRecognizer(
        supported_entity="TW_ID",
        patterns=[tw_id_pattern],
        context=["身分證", "證號", "ID", "id"],  # 如果附近有這些詞，準確度更高
    )
    ad_hoc_recognizers.append(tw_id_recognizer)

    # 2. 員工ID (EMP_ID)
    # 假設規則：6~8碼純數字 (依實際情況調整 regex)
    emp_id_pattern = Pattern(name="emp_id_regex", regex=r"\b\d{6,8}\b", score=0.8)
    emp_id_recognizer = PatternRecognizer(
        supported_entity="EMP_ID",
        patterns=[emp_id_pattern],
        context=["員編", "員工編號", "工號", "user id", "編號"],
    )
    ad_hoc_recognizers.append(emp_id_recognizer)

    # 3. 台灣手機/市話 (TW_PHONE) - 覆蓋 Presidio 預設
    # 支援：0912-345-678, 0912345678, 02-23456789
    phone_regex = r"(09\d{2}[-\s]?\d{3}[-\s]?\d{3})|(0\d{1,2}[-\s]?\d{6,8})"
    phone_pattern = Pattern(name="tw_phone_regex", regex=phone_regex, score=0.8)
    phone_recognizer = PatternRecognizer(
        supported_entity="PHONE_NUMBER", patterns=[phone_pattern]  # 使用標準標籤
    )
    ad_hoc_recognizers.append(phone_recognizer)

    results = analyzer.analyze(
        text=text, language="zh", allow_list=allow_list  # 告訴 AI 這些白名單內不是人名
    )

    # D. 匿名化設定
    operators = {
        "PERSON": OperatorConfig("replace", {"new_value": "[人員]"}),
        "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
        "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
        # 保留日期與時間，維持順序性
        "DATE_TIME": OperatorConfig("keep"),
        "NRP": OperatorConfig("keep"),
        "URL": OperatorConfig("replace", {"new_value": "[URL]"}),
    }

    anonymized_result = anonymizer.anonymize(
        text=text, analyzer_results=results, operators=operators
    )

    return anonymized_result.text


# ======================================================
# 4. 測試 (使用您的案例)
# ======================================================
asana_raw_text = """
---
type: task
gid: 1209846697814388
title: "250331026-黃楷嫆-登入認證問題"
created_date: 2025-03-31
modified_at: 2025-04-07T01:29:25.632Z
expiry_date: 2026-03-31
section: "TIA問題"
---

# ✅ 250331026-黃楷嫆-登入認證問題

## 📌 基本資訊
- **連結**: [Asana](https://app.asana.com/0/1200608352272998/1209846697814388)

## 📝 任務描述
提問人營運單位：新竹營運處
提問人姓名：黃楷嫆
提問人Line顯示名稱：嫆嫆Carol
提問人聯絡電話：0932595602
提問人連絡信箱：carolicx100@gmail.com
提問人問題主旨：登入認證問題
提問人問題內文：飛鴿您好我的夥伴黃琪惠要登入Tia，如截圖畫面找不到驗證問題處，請問可以從哪裡進行Tia的驗證呢？
另外想請問那這位夥伴確定可以拿到告五人演唱會的票及我是她的直屬主管也可以拿到一張票，共兩張票對嗎？因為夥伴需提前安排行程了，謝謝您❤️
另外想問我們公司有外幣及投資型考照班嗎？琪惠近日也希望能考取此兩張證照❤️
Line 客服平台連結：https://manager.line.biz/

## 📎 附件
- [250331026_1.png](../attachments/1209846697814388_1209846697814398_250331026_1.png)
- [image.png](../attachments/1209846697814388_1209866854386545_image.png)

## 💬 討論紀錄
> **朱依禾 (2025-04-01)**: 嫆嫆Carol 您好，回覆您案件編號250331026  
1. 請夥伴黃琪惠在對話框輸入reset後使用驗證碼重新綁定，營運單位及主管是否可以正確顯示  
2. 關於演唱會門票以及考取證照問題，我將轉給相關承辦人員回覆你，感謝您的耐心等候

> **朱依禾 (2025-04-01)**: Hi https://app.asana.com/0/profile/1205015175780993  
關於演唱會門票以及考取證照問題，再請協助轉給相關承辦人回覆，謝謝

> **王智 (2025-04-01)**: https://app.asana.com/0/profile/1208762008209411請協助回覆演唱會門票問題，謝謝

> **王智 (2025-04-01)**: https://app.asana.com/0/profile/1209302669846460請協助回覆課程問題，謝謝

> **蘇丹慈 (2025-04-01)**: 您好！  
有關考照班部份，您可以上E學院>精選課程>03證照考照班中前去觀看即可，謝謝！

> **楊欣慧 (2025-04-01)**: 楷嫆您好，關於開門紅的門票公文已發，再請您詳閱20250033公文，謝謝。  


> **朱依禾 (2025-04-02)**: https://app.asana.com/app/asana/-/get_asset?asset_id=1209866854386545  


> **朱依禾 (2025-04-07)**: 夥伴於3日內無提出新問題，故結案


"""

print("\n--- 處理結果 ---")
final_text = mask_asana_content(asana_raw_text)
print(final_text)
