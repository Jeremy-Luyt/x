"""Application entry point: parse bookmarks first, then open the task viewer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.gui.main_window import MainWindow
from src.pdf.task_parser import parse_pdf
from src.tasks.repository import save_tasks
from src.utils.logging import configure_logging


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_PDF_NAME = "业财税2023.pdf"


def _configured_pdf() -> Path | None:
    config_path = PROJECT_ROOT / "config" / "config.json"
    if not config_path.is_file():
        return None
    try:
        configured = json.loads(config_path.read_text(encoding="utf-8")).get("pdf_path", "")
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"配置文件无法读取：{config_path}（{exc}）") from exc
    return Path(configured).expanduser() if configured else None


def locate_pdf(argument: str | None) -> Path:
    candidates = [Path(argument).expanduser()] if argument else []
    configured = _configured_pdf()
    if configured:
        candidates.append(configured)
    candidates.extend([PROJECT_ROOT / DEFAULT_PDF_NAME, Path.home() / "Downloads" / DEFAULT_PDF_NAME])
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    formatted = "\n".join(f"  - {candidate}" for candidate in candidates)
    raise FileNotFoundError(
        f"未找到 {DEFAULT_PDF_NAME}。可把 PDF 放入项目目录，配置 config/config.json，或传入 --pdf。\n已检查：\n{formatted}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="U8Assistant - 业财税实验辅助工具")
    parser.add_argument("--pdf", help="业财税 PDF 的路径")
    parser.add_argument("--no-gui", action="store_true", help="仅解析 PDF 并生成 data/tasks.json")
    args = parser.parse_args()
    logger = configure_logging(PROJECT_ROOT)
    try:
        pdf_path = locate_pdf(args.pdf)
        logger.info("Reading native PDF bookmarks: %s", pdf_path)
        tasks = parse_pdf(pdf_path)
        save_tasks(PROJECT_ROOT / "data" / "tasks.json", tasks, pdf_path)
        warning_count = sum(len(task.warnings) for task in tasks)
        print(f"已读取 {len(tasks)} 个一级任务书签，生成 data/tasks.json（{warning_count} 条解析警告）。")
        if args.no_gui:
            return 0
        import tkinter as tk
        root = tk.Tk()
        MainWindow(root, tasks, pdf_path, PROJECT_ROOT, logger)
        root.mainloop()
        return 0
    except Exception as exc:
        logger.exception("Application startup failed")
        print(f"启动失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
