"""Build-time conversion of the fixed teaching PDF into Win7-safe JPEG pages."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_pdf_pages(pdf_path: Path, output_dir: Path, dpi: int = 150, quality: int = 84) -> dict[str, int | str]:
    """Render every page as RGB JPEG; only intended for the CI build host."""
    import fitz
    from PIL import Image

    if not pdf_path.is_file():
        raise FileNotFoundError(f"未找到待预渲染 PDF：{pdf_path}")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    scale = dpi / 72
    with fitz.open(pdf_path) as document:
        page_count = document.page_count
        width = height = 0
        for index in range(page_count):
            pixmap = document.load_page(index).get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            image.save(output_dir / f"page_{index + 1:03d}.jpg", format="JPEG", quality=quality, optimize=True)
            width, height = image.size
    manifest = {"page_count": page_count, "dpi": dpi, "width": width, "height": height, "source_pdf_sha256": _sha256(pdf_path)}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build-time PDF prerendering for Win7 x86")
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--quality", type=int, default=84)
    args = parser.parse_args()
    print(json.dumps(render_pdf_pages(args.pdf, args.output, args.dpi, args.quality), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
