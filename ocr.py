# 1. 安裝 PaddlePaddle 核心 (CPU 版比較簡單，若有 GPU 可裝 paddlepaddle-gpu) : pip install paddlepaddle

# 2. 安裝 PaddleOCR : pip install paddleocr

# 3. (選擇性) 如果報錯缺少 cv2，請安裝 opencv : pip install opencv-python-headless

import os
import logging
from dotenv import load_dotenv

# 載入 .env
load_dotenv()

# 設定是否啟用 OCR
ENABLE_OCR = os.getenv("ENABLE_OCR", "False").lower() in ("true", "1", "yes")

# 全域變數存放引擎實例
_ocr_engine = None


def _get_engine():
    """
    單例模式取得 PaddleOCR 引擎
    避免每次呼叫都重新載入模型 (那樣會超慢)
    """
    global _ocr_engine
    if not ENABLE_OCR:
        return None

    if _ocr_engine is None:
        try:
            # 延遲引入，避免沒啟用 OCR 時還報錯
            from paddleocr import PaddleOCR

            print("⏳ 正在載入 PaddleOCR 模型 (首次執行會自動下載)...")

            # 設定 logging 等級，避免 Paddle 印出一堆 debug 訊息
            logging.getLogger("ppocr").setLevel(logging.WARNING)

            # 初始化：use_angle_cls=True (自動轉正), lang='ch' (中英文通用)
            _ocr_engine = PaddleOCR(use_angle_cls=True, lang="ch")
            print("✅ PaddleOCR 載入完成")

        except ImportError:
            print("❌ 錯誤：找不到 paddleocr 套件。")
            print("請執行: pip install paddlepaddle paddleocr opencv-python-headless")
            return None
        except Exception as e:
            print(f"❌ OCR 初始化失敗: {e}")
            return None

    return _ocr_engine


def extract_text_from_image(image_path):
    """
    傳入圖片路徑，回傳辨識後的文字字串
    """
    if not ENABLE_OCR:
        return None

    # 檢查檔案是否存在
    if not os.path.exists(image_path):
        return None

    # 檢查副檔名 (只處理圖片)
    ext = os.path.splitext(image_path)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".bmp", ".tiff"]:
        return None

    engine = _get_engine()
    if not engine:
        return None

    try:
        # 執行辨識
        result = engine.ocr(image_path, cls=False)

        if not result:
            return None  # result 是 None 或空列表
        if result[0] is None:
            return None  # 第一個元素是 None

        # 提取文字 (增加 try-except 避免單行解析失敗)
        text_lines = []
        for line in result[0]:
            try:
                # PaddleOCR 格式: [ [[x,y],...], ("文字", 0.99) ]
                text = line[1][0]
                score = line[1][1]
                if score > 0.6:
                    text_lines.append(text)
            except:
                continue

        full_text = "\n".join(text_lines)
        return full_text if full_text.strip() else None

    except Exception as e:
        # print(f"⚠️ OCR Skip: {e}")
        return None
