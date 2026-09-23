from __future__ import annotations

import builtins
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from src.pdf.page_renderer import PdfPageRenderer


class StaticPageRendererTests(unittest.TestCase):
    def test_page_17_uses_exact_static_image_without_importing_fitz(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pages = root / "rendered_pages"
            pages.mkdir()
            Image.new("RGB", (40, 30), "navy").save(pages / "page_017.jpg", quality=84)
            (pages / "manifest.json").write_text(json.dumps({"page_count": 17}), encoding="utf-8")
            renderer = PdfPageRenderer(None, root / "cache", pages)
            original_import = builtins.__import__

            def guarded_import(name: str, *args: object, **kwargs: object) -> object:
                if name == "fitz":
                    raise AssertionError("static Win7 renderer must not import fitz")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=guarded_import):
                image_path = renderer.render_page(17, 1.0)
            with Image.open(image_path) as rendered:
                self.assertEqual(rendered.size, (40, 30))
            self.assertIn("page_017_100", image_path.name)

    def test_page_numbers_are_one_based(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pages = root / "rendered_pages"
            pages.mkdir()
            Image.new("RGB", (8, 8), "red").save(pages / "page_017.jpg")
            renderer = PdfPageRenderer(None, root / "cache", pages)
            with self.assertRaises(FileNotFoundError):
                renderer.render_page(16)
            with self.assertRaises(ValueError):
                renderer.render_page(0)


if __name__ == "__main__":
    unittest.main()
