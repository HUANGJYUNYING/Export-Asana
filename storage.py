# 檔案用途：處理檔案系統 I/O（命名、寫入、目錄）。

import os
from typing import List

import utils


def build_markdown_filename(task: dict) -> str:
    """
    根據任務資訊生成 Markdown 檔名（含長度截斷）。

    Args:
        task (dict): 任務原始資料。

    Returns:
        str: 適用檔案系統的檔名，已做長度截斷。
    """
    fname = f"{task['created_at'][:10].replace('-','')}_{utils.clean_filename(task.get('name') or 'untitled')}.md"
    if len(fname) > 100:
        base = fname[:-3] if fname.endswith(".md") else fname
        fname = base[:96] + ".md"
    return fname


def write_markdown_file(
    md_lines: List[str],
    sec_dir: str,
    task: dict,
) -> str:
    """
    將 Markdown 行寫入檔案並處理檔名長度與清理。

    Args:
        md_lines (List[str]): Markdown 內容行列表。
        sec_dir (str): 區段目錄路徑。
        task (dict): 任務原始資料，用於命名。

    Returns:
        str: 實際寫入的檔案完整路徑。
    """
    fname = build_markdown_filename(task)
    full_path = os.path.join(sec_dir, fname)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    return full_path
