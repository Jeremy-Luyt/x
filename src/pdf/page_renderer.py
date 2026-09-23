"""Lazy PDF page rendering with a cache keyed by page number and zoom."""

from __future__ import annotations

from pathlib import Path


class PdfPageRenderer:
    def __init__(self, pdf_path: Path, cache_dir: Path) -> None:
        self.pdf_path = pdf_path
        self.cache_dir = cache_dir

    def render_page(self, page_number: int, zoom: float = 1.25) -> Path:
        """Render a one-based page only when the matching PNG is absent."""
        if page_number < 1:
            raise ValueError("PDF 页码必须从 1 开始。")
        zoom = max(0.5, min(3.0, zoom))
        zoom_key = int(round(zoom * 100))
        target = self.cache_dir / f"page_{page_number:03d}_{zoom_key}.png"
        if target.is_file():
            return target
        try:
            import fitz
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("缺少 PyMuPDF，无法渲染 PDF 页面。") from exc
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with fitz.open(self.pdf_path) as document:
            if page_number > document.page_count:
                raise ValueError(f"页码 {page_number} 超出 PDF 范围（共 {document.page_count} 页）。")
            # get_page is zero-based; converting exactly once prevents off-by-one errors.
            pixmap = document.load_page(page_number - 1).get_pixmap(
                matrix=fitz.Matrix(zoom, zoom), alpha=False
            )
            pixmap.save(target)
        return target
