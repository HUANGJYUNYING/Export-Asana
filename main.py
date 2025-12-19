import sys
import os
import config
import fetch_raw
import process_data


def main():
    while True:
        print("1. 🔄 完整同步 (Fetch + Process)")
        print("   -> 下載新資料，並自動生成文件 (推薦日常使用)")
        print("")
        print("2. 📥 僅擷取原始資料 (Stage 1 Only)")
        print("   -> 僅下載 JSON 與圖片，不生成 Markdown")
        print("")
        print("3. 📝 僅重新生成文件 (Stage 2 Only)")
        print("   -> 不連網，僅根據現有 JSON 重產 Markdown (改排版用)")
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
            else:
                print("\n⚠️ 第一階段未完成或取消，流程中止。")

        elif choice == "2":
            # --- 僅擷取 ---
            fetch_raw.run_fetch()

        elif choice == "3":
            # --- 僅生成 ---
            # 不傳參數，讓 process_data 自己跳出選單問要處理哪個專案
            process_data.run_process()

        elif choice == "q":
            print("👋 再見！")
            sys.exit()

        else:
            print("❌ 無效選項")

        input("\n按 Enter 鍵返回主選單...")


if __name__ == "__main__":
    main()
