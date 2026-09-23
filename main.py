"""Application entry point: parse bookmarks first, then open the task viewer."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from src.utils.startup import configure_startup_logging


RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
PROJECT_ROOT = RESOURCE_ROOT
DEFAULT_PDF_NAME = "业财税2023.pdf"


def _writable_root() -> Path:
    """One-file EXEs must not write into PyInstaller's temporary resource folder."""
    if getattr(sys, "frozen", False) and os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "U8Assistant"
        root.mkdir(parents=True, exist_ok=True)
        return root
    return RESOURCE_ROOT


def _configured_pdf() -> Path | None:
    config_path = _writable_root() / "config" / "config.json"
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
    executable_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else RESOURCE_ROOT
    candidates.extend([
        RESOURCE_ROOT / "assets" / DEFAULT_PDF_NAME,
        executable_dir / DEFAULT_PDF_NAME,
        RESOURCE_ROOT / DEFAULT_PDF_NAME,
        Path.home() / "Downloads" / DEFAULT_PDF_NAME,
    ])
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    formatted = "\n".join(f"  - {candidate}" for candidate in candidates)
    raise FileNotFoundError(f"未找到 {DEFAULT_PDF_NAME}。已检查：\n{formatted}")


def main() -> int:
    # This is deliberately the first operation: a broken GUI/import still leaves
    # support evidence in startup.log rather than a hidden windowed traceback.
    startup_logger = configure_startup_logging("U8Assistant")
    try:
        startup_logger.info("stage: importing application modules")
        import argparse
        import json

        from src.gui.main_window import MainWindow
        from src.pdf.task_parser import parse_pdf
        from src.tasks.repository import load_tasks, save_tasks
        from src.utils.logging import configure_logging

        parser = argparse.ArgumentParser(description="U8Assistant - 业财税实验辅助工具")
        parser.add_argument("--pdf", help="业财税 PDF 的路径")
        parser.add_argument("--no-gui", action="store_true", help="仅解析 PDF 并生成 data/tasks.json")
        args = parser.parse_args()
        writable_root = _writable_root()
        logger = configure_logging(writable_root)
        static_pages_dir = RESOURCE_ROOT / "assets" / "rendered_pages"
        try:
            pdf_path = locate_pdf(args.pdf)
        except FileNotFoundError:
            pdf_path = None
        # The Win7 x86 frozen build contains verified static JPEG pages instead
        # of PyMuPDF. Ignore any same-named external PDF so native fitz is never
        # imported at runtime on that target.
        if getattr(sys, "frozen", False) and (static_pages_dir / "manifest.json").is_file():
            logger.info("Using bundled static PDF pages; runtime PyMuPDF is disabled.")
            pdf_path = None
        bundled_tasks = RESOURCE_ROOT / "data" / "tasks.json"
        if getattr(sys, "frozen", False) and bundled_tasks.is_file():
            tasks = load_tasks(bundled_tasks)
        elif pdf_path is not None:
            logger.info("Reading native PDF bookmarks: %s", pdf_path)
            tasks = parse_pdf(pdf_path)
            save_tasks(writable_root / "data" / "tasks.json", tasks, pdf_path)
        else:
            tasks = load_tasks(writable_root / "data" / "tasks.json")
        warning_count = sum(len(task.warnings) for task in tasks)
        logger.info("Loaded %s tasks with %s parsing warnings.", len(tasks), warning_count)
        if args.no_gui:
            startup_logger.info("stage: command-line validation complete")
            return 0
        startup_logger.info("stage: initializing Tkinter GUI")
        import tkinter as tk
        root = tk.Tk()
        MainWindow(root, tasks, pdf_path, writable_root, logger, static_pages_dir)
        startup_logger.info("stage: GUI ready")
        root.mainloop()
        return 0
    except Exception as exc:
        startup_logger.exception("Application startup failed")
        try:
            from tkinter import messagebox
            messagebox.showerror("U8Assistant", "程序暂时无法启动。请联系老师或技术人员，并提供 startup.log。")
        except Exception:
            # A console is intentionally absent in the packaged program.
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
