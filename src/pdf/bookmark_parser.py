"""Thin, testable access to PyMuPDF's native PDF outline API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Bookmark:
    level: int
    title: str
    page: int


def read_bookmarks(pdf_path: Path) -> tuple[int, list[Bookmark]]:
    """Return native outline rows, retaining invalid page values for diagnostics."""
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - depends on installation
        raise RuntimeError("缺少 PyMuPDF。请先执行 pip install -r requirements.txt。") from exc

    if not pdf_path.is_file():
        raise FileNotFoundError(f"未找到 PDF 文件：{pdf_path}")
    with fitz.open(pdf_path) as document:
        rows = document.get_toc(simple=True)
        return document.page_count, [Bookmark(level, title, page) for level, title, page in rows]
