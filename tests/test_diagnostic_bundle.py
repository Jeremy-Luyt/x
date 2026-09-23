from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from src.gui.diagnostic_window import diagnostic_result_kind
from src.u8.diagnostic_bundle import create_diagnostic_zip


class DiagnosticBundleTests(unittest.TestCase):
    def test_zip_contains_report_and_screenshot_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "20260923_160000"
            report.mkdir()
            (report / "environment.json").write_text("{}", encoding="utf-8")
            (report / "diagnostics_errors.log").write_text("", encoding="utf-8")
            archive_path = create_diagnostic_zip(report, root / "desktop")
            self.assertEqual(archive_path.name, "U8诊断结果_20260923_160000.zip")
            with zipfile.ZipFile(archive_path) as archive:
                names = archive.namelist()
            self.assertIn("20260923_160000/environment.json", names)
            self.assertIn("20260923_160000/screenshots/", names)

    def test_gui_outcome_never_exposes_technical_details(self) -> None:
        self.assertEqual(diagnostic_result_kind({"u8_found": True}), "success")
        self.assertEqual(diagnostic_result_kind({"u8_found": False, "possible_permission_mismatch": True}), "permission")
        self.assertEqual(diagnostic_result_kind({"u8_found": False}), "not_found")


if __name__ == "__main__":
    unittest.main()
