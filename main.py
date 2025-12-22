import sys
import os
import config
import fetch_raw
import process_data
import generate_qa


def main():
    while True:
        print("1. 🔄 完整同步 (Fetch -> Process -> QA)")
        print("   -> 下載新資料，並自動生成文件 (推薦日常使用)")
        print("")
        print("2. 📥 僅擷取原始資料 (Stage 1 Only)")
        print("   -> 僅下載 JSON 與圖片，不生成 Markdown")
        print("")
        print("3. 📝 僅重新生成文件 (Stage 2 Only)")
        print("   -> 不連網，僅根據現有 JSON 重產 Markdown (改排版用)")
        print("4. 🧠 僅生成 QA 資料集 (Stage 3)")
        print("")
        print("q. 離開")

        choice = input("\n👉 請選擇模式: ").strip().lower()

        if choice == "1":
            # --- 完整流程 ---
            print("\n>>> 啟動第一階段：資料擷取 <<<")
            target_proj = fetch_raw.run_fetch()

            if target_proj:
                print(f"\n>>> 啟動第二階段：文件生成 ({target_proj}) <<<")
                process_data.run_process(target_proj)
                if config.ENABLE_LLM_ANALYSIS:
                    print(f"\n>>> [Step 3] 啟動 QA 萃取 ({target_proj}) <<<")
                    generate_qa.run_qa_generation(target_proj)
                else:
                    print("\n⚠️ LLM 功能未開啟，跳過 QA 生成。")
            else:
                print("\n⚠️ 第一階段未完成或取消，流程中止。")

        elif choice == "2":
            # --- 僅擷取 ---
            fetch_raw.run_fetch()

        elif choice == "3":
            # --- 僅生成 ---
            # 不傳參數，讓 process_data 自己跳出選單問要處理哪個專案
            process_data.run_process()

        elif choice == "4":
            # 獨立執行 QA 生成
            # 這裡可以簡單做個選單讓使用者選專案，或是直接跑
            # 為了簡單，這裡讓 generate_qa 跑全量，或者可以修改 generate_qa 讓它跳出選單
            generate_qa.run_qa_generation()

        elif choice == "q":
            x = int(17)
            print("👋 再見！")
            sys.exit()

        else:
            print("❌ 無效選項")

        input("\n按 Enter 鍵返回主選單...")


if __name__ == "__main__":
    main()
