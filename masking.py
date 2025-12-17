# 1. 安裝微軟個資偵測套件與 spaCy : pip install presidio-analyzer presidio-anonymizer spacy

# 2. 下載 spaCy 的中文大型模型 (約 500MB，需下載一次) : python -m spacy download zh_core_web_lg

import re
import sys
import config  # 引入設定

try:
    import spacy
    from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig
except ImportError:
    print("❌ 錯誤: 缺少必要的 NLP 套件。")
    print("請執行: pip install presidio-analyzer presidio-anonymizer spacy")
    sys.exit(1)

# ======================================================
# 1. 初始化 NLP 引擎\
# ======================================================
analyzer = None
anonymizer = None

if config.ENABLE_MASKING:
    try:
        print("⏳ 正在載入 NLP 模型 (zh_core_web_lg)...")
        nlp_configuration = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "zh", "model_name": "zh_core_web_lg"}],
        }
        provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
        nlp_engine = provider.create_engine()

        analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["zh"])
        anonymizer = AnonymizerEngine()

        # --- 註冊自定義偵測器 (Ad-hoc Recognizers) ---

        # 1. 台灣身分證 (TW_ID)
        tw_id_pattern = Pattern(
            name="tw_id_regex", regex=r"\b[A-Z][1289]\d{8}\b", score=1.0
        )
        tw_id_recognizer = PatternRecognizer(
            supported_entity="TW_ID",
            patterns=[tw_id_pattern],
            context=["身分證", "證號", "ID", "id"],
        )
        analyzer.registry.add_recognizer(tw_id_recognizer)

        # 2. 台灣手機/市話 (TW_PHONE) - 增強 Presidio 預設
        phone_regex = r"(09\d{2}[-\s]?\d{3}[-\s]?\d{3})|(0\d{1,2}[-\s]?\d{6,8})"
        phone_pattern = Pattern(name="tw_phone_regex", regex=phone_regex, score=0.8)
        phone_recognizer = PatternRecognizer(
            supported_entity="PHONE_NUMBER", patterns=[phone_pattern]
        )
        analyzer.registry.add_recognizer(phone_recognizer)

        print("✅ NLP 模型載入完成")

    except OSError:
        print("❌ 錯誤: 找不到 spaCy 中文模型。")
        print("請執行: python -m spacy download zh_core_web_lg")
        sys.exit(1)


# ======================================================
# 2. 名單提取 (Context Extraction)
# ======================================================
def extract_names_from_context(full_text):
    """
    從全文中分析出需要遮罩的人名清單
    (維持原本 main.py 的呼叫介面)
    """
    if not full_text or not config.ENABLE_MASKING:
        return set()

    names = set()

    # 1. 抓 Header (提問人 & 流言人) - 允許中間有空白
    names.update(re.findall(r"提問人姓名\s*[:：]\s*(.+)", full_text))
    names.update(re.findall(r"Line顯示名稱\s*[:：]\s*(.+)", full_text))
    names.update(re.findall(r">\s*([^\(]+?)\s*\(\d{4}", full_text))

    # 1.1 衍伸暱稱
    derived_names = set()
    for name in names:
        name = name.strip()
        # 規則：如果名字是 3 個字 (eg.王大強)，嘗試取後 2 字 (大強)
        if len(name) == 3:
            nickname = name[1:]  # 取第2字到最後
            derived_names.add(nickname)

        # 規則：如果名字是 2 個字 (李明)，且第1字是常見姓氏，嘗試取後1字 (明) -> 風險高，通常不建議
        # 但如果是 Line 暱稱 (例如 "Cat Huang")，可以嘗試拆解空格
        if " " in name:
            parts = name.split(" ")
            derived_names.update(parts)  # "Cat", "Huang" 都加進去

    # 合併清單
    names.update(derived_names)

    # 2. 抓對話紀錄 (優化版 Regex)
    # 支援: > **朱OO (2025... 或 > 朱OO (2025...
    chat_pattern = r">\s*(?:\*\*)?([^\(\*\s]+?)(?:\*\*)?\s*\(\d{4}"
    names.update(re.findall(chat_pattern, full_text))

    # 3. 清洗與過濾
    cleaned_names = set()
    SAFE_WORDS = {
        "通知",
        "系統",
        "管理員",
        "測試",
        "客服",
        "夥伴",
        "User",
        "Unknown",
        "提問人",
        "admin",
        "reset",
        "Reset",
        "TIA",
        "Tia",
        "E學院",
        "公文",
        "開門紅",
        "飛鴿",
        "Asana",
        "先生",
        "小姐",
        "你好",
        "您好",
    }

    for n in names:
        n = n.strip()
        # 過濾掉太短的字、安全字、或是包含數字特殊符號的
        if len(n) >= 2 and n not in SAFE_WORDS and not re.search(r"[0-9!@#$]", n):
            cleaned_names.add(n)

    return cleaned_names


# ======================================================
# 3. 遮罩執行
# ======================================================
def apply_masking(text, names_blacklist):
    """
    應用遮罩：先遮已知清單與連結，再用 NLP 掃描剩餘個資
    """
    if not text:
        return ""
    if not config.ENABLE_MASKING:
        return text

    masked_text = text

    # --- [Layer 1] 規則遮罩 (Rule-based) ---
    # 這些是我們確定要遮，且 NLP 容易誤判或漏掉的格式

    # 1. 遮罩已知人名 (長度優先，避免誤遮)
    for name in sorted(names_blacklist, key=len, reverse=True):
        try:
            # 使用 re.escape 避免名字含特殊符號導致錯誤
            if name in masked_text:
                masked_text = re.sub(re.escape(name), "[人員]", masked_text)
        except:
            pass

    # 2. 遮罩特定連結 (Link)
    masked_text = re.sub(
        r"https://app\.asana\.com/0/profile/\d+", "[ASANA_LINK]", masked_text
    )
    masked_text = re.sub(r"https://\S+\.line\.biz/\S*", "[LINE_LINK]", masked_text)

    # --- [Layer 2] AI 遮罩 (NLP-based) ---
    # 使用 Presidio 掃描剩下的敏感資訊
    if analyzer and anonymizer:
        # 設定白名單詞彙 (告訴 AI 這些不是人名)
        allow_list = [
            "reset",
            "Reset",
            "TIA",
            "Tia",
            "E學院",
            "公文",
            "開門紅",
            "Asana",
            "LINE",
        ]

        results = analyzer.analyze(
            text=masked_text, language="zh", allow_list=allow_list
        )

        # 定義遮罩規則
        operators = {
            "PERSON": OperatorConfig("replace", {"new_value": "[人員]"}),
            "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
            "TW_ID": OperatorConfig("replace", {"new_value": "[ID_CARD]"}),
            "EMP_ID": OperatorConfig("replace", {"new_value": "[EMP_ID]"}),
            "DATE_TIME": OperatorConfig("keep"),
            "NRP": OperatorConfig("keep"),  # 國籍宗教保留
            "URL": OperatorConfig("keep"),  # 網址保留
        }

        anonymized_result = anonymizer.anonymize(
            text=masked_text, analyzer_results=results, operators=operators
        )

        masked_text = anonymized_result.text

    return masked_text
