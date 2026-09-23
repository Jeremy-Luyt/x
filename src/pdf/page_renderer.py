"""Page rendering with a PyMuPDF backend and a Win7-safe static-image backend."""

from __future__ import annotations

import json
from pathlib import Path


class PdfPageRenderer:
    def __init__(self, pdf_path: Path | None, cache_dir: Path,
                 static_pages_dir: Path | None = None) -> None:
        self.pdf_path = pdf_path
        self.cache_dir = cache_dir
        self.static_pages_dir = static_pages_dir if static_pages_dir and static_pages_dir.is_dir() else None

    @property
    def uses_static_pages(self) -> bool:
        return self.static_pages_dir is not None

    def _static_page_path(self, page_number: int) -> Path:
        if self.static_pages_dir is None:
            raise FileNotFoundError("未配置静态 PDF 页面目录。")
        manifest_path = self.static_pages_dir / "manifest.json"
        if manifest_path.is_file():
            try:
                page_count = int(json.loads(manifest_path.read_text(encoding="utf-8")).get("page_count", 0))
            except (OSError, ValueError, json.JSONDecodeError):
                page_count = 0
            if page_count and page_number > page_count:
                raise ValueError(f"页码 {page_number} 超出静态页面范围（共 {page_count} 页）。")
        source = self.static_pages_dir / f"page_{page_number:03d}.jpg"
        if not source.is_file():
            raise FileNotFoundError(f"未找到 PDF 第 {page_number} 页的静态图片：{source.name}")
        return source

    def _render_static_page(self, page_number: int, zoom: float, target: Path) -> Path:
        from PIL import Image

        source = self._static_page_path(page_number)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            rgb = image.convert("RGB")
            resized = rgb.resize((max(1, round(rgb.width * zoom)), max(1, round(rgb.height * zoom))), Image.LANCZOS)
            resized.save(target, format="JPEG", quality=88, optimize=True)
        return target

    def render_page(self, page_number: int, zoom: float = 1.25) -> Path:
        """Render a one-based page, preferring bundled static images."""
        if page_number < 1:
            raise ValueError("PDF 页码必须从 1 开始。")
        zoom = max(0.5, min(3.0, zoom))
        zoom_key = int(round(zoom * 100))
        target = self.cache_dir / f"page_{page_number:03d}_{zoom_key}.jpg"
        if target.is_file():
            return target
        if self.uses_static_pages:
            return self._render_static_page(page_number, zoom, target)
        if self.pdf_path is None or not self.pdf_path.is_file():
            raise FileNotFoundError("未找到原始 PDF 或预渲染页面。")
        try:
            import fitz
        except ImportError as exc:  # pragma: no cover - platform-specific native loading
            raise RuntimeError("无法加载 PDF 渲染组件（可能是本机 DLL 不兼容）。") from exc
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
