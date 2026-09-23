from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.u8.probe import BackendResult, _control_stats, _create_output_dir, _safe_label, write_summary


class ProbeReportTests(unittest.TestCase):
    def test_label_is_safe_for_a_diagnostics_directory(self) -> None:
        self.assertEqual(_safe_label("purchase/order popup"), "purchase_order_popup")
        self.assertEqual(_safe_label("../../"), "probe")

    def test_output_directory_does_not_collide(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first = _create_output_dir(base, "20260923_160000_u8_main")
            second = _create_output_dir(base, "20260923_160000_u8_main")
            self.assertEqual(first.name, "20260923_160000_u8_main")
            self.assertEqual(second.name, "20260923_160000_u8_main_01")

    def test_control_statistics_detect_duplicate_automation_ids(self) -> None:
        result = BackendResult("uia", "success", "", windows=[{
            "window": {},
            "controls": [
                {"control_type": "Edit", "class_name": "Edit", "automation_id": "supplier"},
                {"control_type": "Button", "class_name": "Button", "automation_id": "supplier"},
            ],
        }])
        stats = _control_stats(result)
        self.assertEqual(stats["control_count"], 2)
        self.assertEqual(stats["control_type_counts"], {"Button": 1, "Edit": 1})
        self.assertEqual(stats["automation_id"]["duplicate"], {"supplier": 2})

    def test_summary_contains_backend_statistics(self) -> None:
        result = BackendResult("win32", "success", "", windows=[{
            "window": {},
            "controls": [{"control_type": "Edit", "class_name": "Edit", "automation_id": "date"}],
        }])
        environment = {
            "python_version": "3.11", "windows_version": "Windows 11",
            "screen_resolution": {"width": 1920, "height": 1080},
            "dpi_scaling": {"scale_percent": 125},
            "administrator": {"is_administrator": False}, "pywinauto_version": "0.6.9",
        }
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            write_summary(output_dir, environment, [], [result])
            content = (output_dir / "diagnostics_summary.md").read_text(encoding="utf-8")
        self.assertIn("## win32 backend", content)
        self.assertIn("`Edit`: 1", content)
        self.assertIn("Non-empty: **1**", content)


if __name__ == "__main__":
    unittest.main()
