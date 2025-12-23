# Asana Knowledge Base Generator

## 專案簡介
本專案旨在將 Asana 專案中的任務資料自動化匯出、處理並轉換為結構化的企業知識庫 (Knowledge Base)。
系統具備增量同步、個資自動遮罩 (PII Masking)、附件 OCR 分析以及 AI 自動生成問答集 (Q&A) 的功能，適合用於將非結構化的任務流轉換為可搜尋、可訓練的知識資產。

## 主要功能
1. **資料擷取 (Fetch)**: 支援全量與增量同步，自動下載任務 metadata、留言 (Stories) 與附件。
2. **智慧分析 (Analyze)**: 整合 Azure OpenAI (GPT-4o)，對圖片附件進行 OCR 與情境分析。
3. **個資保護 (Privacy)**: 具備敏感個資 (PII) 自動遮罩功能，保護姓名、電話、身分證字號等資訊。
4. **文件生成 (Render)**: 自動生成排版精美的 Markdown 文件，包含內嵌圖片與對話紀錄。
5. **QA 資料及生成**: 針對處理後的文件，自動萃取高品質的 Q&A 對答，可用於訓練企業聊天機器人。

## 系統架構與檔案說明 (Refactored)

本專案採用領域驅動的模組化結構：

### 專案結構
```
project/
├── main.py                  # 主程式入口
├── core/                    # 核心基礎模組
│   ├── config.py            # 環境變數與全域設定
│   ├── utils.py             # 通用工具函式
│   ├── models.py            # 資料模型定義
│   └── storage.py           # 檔案 I/O 操作
├── services/                # 外部服務整合
│   ├── openai_client.py     # Azure OpenAI Client
│   └── llm_processor.py     # 圖片 OCR 與遮罩邏輯
├── fetch/                   # 資料擷取模組
│   ├── run_fetch.py         # 擷取主流程 (Raw Data)
│   ├── asana_api.py         # Asana API 封裝
│   └── sync_manager.py      # 同步狀態管理
├── process/                 # 資料處理模組
│   ├── run_process.py       # 處理主流程 (Masking & Rendering)
│   └── renderer.py          # Markdown 排版引擎
└── qa/                      # QA 生成模組
    └── run_qa.py            # QA 萃取主流程
```

### 核心執行檔與使用方式

建議一律從專案根目錄執行 `main.py`：
```bash
python main.py
```

若需單獨執行特定模組，請使用 `-m` 參數以確保引用路徑正確：

| 模組功能 | 執行指令 |
| :--- | :--- |
| **資料擷取** | `python -m fetch.run_fetch` |
| **資料處理** | `python -m process.run_process` |
| **QA 生成** | `python -m qa.run_qa` |

## 功能詳解

### 核心 (Core)
- **`config.py`**: 集中管理所有路徑與 API Key，避免散落在各處。
- **`utils.py`**: 提供下載、字串處理等共用功能。

### 服務 (Services)
- **`llm_processor.py`**: 圖片分析與文字遮罩的核心邏輯所在，會呼叫 OpenAI API。

### 擷取 (Fetch)
- **`run_fetch.py`**: 負責連線 Asana，根據上次同步時間下載新任務。會自動計算並回寫「知識截止日」。

### 處理 (Process)
- **`run_process.py`**: 將 JSON 原始檔轉換為 Markdown。包含 PII 遮罩流程。
- **`renderer.py`**: 複雜的 Markdown 排版邏輯，包含圖片內嵌與子任務巢狀結構。

### QA (QA)
- **`run_qa.py`**: 讀取生成的 Markdown，利用 Prompt Engineering 萃取 Q&A。

## 設定檔
- **`.env`**: 存放 API Token、資料庫連線字串等敏感設定 (請參考 `.env.example` 建立)。
- **`requirements.txt`**: Python 套件依賴列表。

## 快速開始

1. **安裝依賴**:
   ```bash
   pip install -r requirements.txt
   ```

2. **設定環境變數**:
   複製 `.env.example` 為 `.env`，並填入：
   - Asana Personal Access Token (PAT)
   - Azure OpenAI Endpoint / API Key
   - 本地儲存路徑設定

3. **執行程式**:
   ```bash
   python main.py
   ```
