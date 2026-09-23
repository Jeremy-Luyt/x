from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from src.u8.diagnostic_bundle import create_diagnostic_zip
from src.u8.probe import (BackendResult, ErrorRecorder, _control_stats, _create_output_dir,
                          _bounded_call, _json_safe, _matches_u8, _safe_label, _window_record, inspect_backend, list_top_windows, run_probe,
                          write_summary)


class FakeWindow:
    def __init__(self, title: str = "U8 企业应用平台", broken_handle: bool = False) -> None:
        self.title = title
        self.broken_handle = broken_handle

    def window_text(self) -> str:
        return self.title

    @property
    def handle(self) -> int:
        if self.broken_handle:
            raise OSError(1400, "无效的窗口句柄")
        return 123

    def class_name(self) -> str:
        return "MainWindow"

    def rectangle(self) -> object:
        return type("Rect", (), {"left": 0, "top": 0, "right": 100, "bottom": 100})()

    def is_visible(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return True


class DeniedElement:
    @property
    def control_type(self) -> str:
        raise PermissionError(5, "拒绝访问")

    @property
    def automation_id(self) -> str:
        raise PermissionError(5, "拒绝访问")


class WindowWithDeniedElement(FakeWindow):
    @property
    def element_info(self) -> DeniedElement:
        return DeniedElement()


class FakeTreeWindow(FakeWindow):
    def __init__(self, title: str, handle: int, class_name: str,
                 visible: bool = True, enabled: bool = True,
                 descendants: list["FakeTreeWindow"] | None = None) -> None:
        super().__init__(title=title)
        self._handle = handle
        self._class_name = class_name
        self._visible = visible
        self._enabled = enabled
        self._descendants = descendants or []

    @property
    def handle(self) -> int:
        return self._handle

    def class_name(self) -> str:
        return self._class_name

    def rectangle(self) -> object:
        return type("Rect", (), {"left": 100, "top": 100, "right": 800, "bottom": 600})()

    def is_visible(self) -> bool:
        return self._visible

    def is_enabled(self) -> bool:
        return self._enabled

    def descendants(self) -> list["FakeTreeWindow"]:
        return self._descendants

    def parent(self) -> None:
        return None


class ProbeReportTests(unittest.TestCase):
    def test_invalid_win32_title_surrogate_is_replaced_before_json_output(self) -> None:
        self.assertEqual(_json_safe({"title": "bad\ud991title"})["title"], "bad?title")

    def test_probe_window_is_not_mistaken_for_u8(self) -> None:
        self.assertFalse(_matches_u8({"title": "U8 环境诊断工具"}))
        self.assertTrue(_matches_u8({"title": "新道 U8"}))

    def test_blocking_window_query_times_out_and_probe_can_continue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            errors = ErrorRecorder(Path(temporary) / "diagnostics_errors.log")
            started = time.monotonic()
            result = _bounded_call(
                "skipped", errors, "fake.blocking_window", lambda: time.sleep(1), 0.01,
            )
        self.assertEqual(result, "skipped")
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertTrue(any("blocking_window" in message for message in errors.messages))

    def test_denied_element_properties_are_recorded_without_aborting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            errors = ErrorRecorder(Path(temporary) / "diagnostics_errors.log")
            record = _window_record(WindowWithDeniedElement(), errors, "fake")
        self.assertEqual(record["title"], "U8 企业应用平台")
        self.assertIsNone(record["control_type"])
        self.assertIsNone(record["automation_id"])
        self.assertTrue(any("control_type" in message for message in errors.messages))
        self.assertTrue(any("automation_id" in message for message in errors.messages))

    def test_invalid_handles_in_top_window_enumeration_do_not_stop_remaining_windows(self) -> None:
        windows = [FakeWindow(title=f"窗口 {index}", broken_handle=index in {3, 8, 15}) for index in range(20)]
        module = ModuleType("pywinauto")
        module.Desktop = lambda backend: type("Desktop", (), {"windows": lambda self: windows})()
        with tempfile.TemporaryDirectory() as temporary, patch.dict("sys.modules", {"pywinauto": module}):
            errors = ErrorRecorder(Path(temporary) / "diagnostics_errors.log")
            records, error = list_top_windows(errors)
        self.assertIsNone(error)
        self.assertEqual(len(records), 20)
        self.assertEqual(records[4]["handle"], 123)
        self.assertTrue(any("handle" in message for message in errors.messages))

    def test_untitled_supplier_lookup_is_captured_only_when_invoice_form_is_disabled(self) -> None:
        disabled_invoice_form = FakeTreeWindow("专用发票", 101, "ThunderRT6FormDC", enabled=False)
        u8_main = FakeTreeWindow("新道 U8", 100, "WindowsForms10.Window.8.app.0.378734a",
                                 descendants=[disabled_invoice_form])
        lookup_dialog = FakeTreeWindow("", 200, "ThunderRT6FormDC", descendants=[
            FakeTreeWindow("供应商名称", 201, "Static"),
            FakeTreeWindow("", 202, "Edit"),
            FakeTreeWindow("", 203, "VSFlexGrid8N"),
            FakeTreeWindow("确定", 204, "Button"),
        ])
        module = ModuleType("pywinauto")
        module.Desktop = lambda backend: type("Desktop", (), {"windows": lambda self: [u8_main, lookup_dialog]})()
        with tempfile.TemporaryDirectory() as temporary, patch.dict("sys.modules", {"pywinauto": module}):
            result = inspect_backend("win32", ErrorRecorder(Path(temporary) / "diagnostics_errors.log"))
        self.assertEqual(len(result.windows), 2)
        self.assertEqual(result.windows[1]["window"]["title"], "")
        self.assertIn("Related Legacy Dialog", result.identifiers)
        self.assertTrue(any(record["control_type"] == "DataGrid" for record in result.interactive_controls))

    def test_untitled_legacy_form_is_not_inspected_without_disabled_invoice_form(self) -> None:
        active_invoice_form = FakeTreeWindow("专用发票", 101, "ThunderRT6FormDC", enabled=True)
        u8_main = FakeTreeWindow("新道 U8", 100, "WindowsForms10.Window.8.app.0.378734a",
                                 descendants=[active_invoice_form])
        unrelated_form = FakeTreeWindow("", 200, "ThunderRT6FormDC")
        module = ModuleType("pywinauto")
        module.Desktop = lambda backend: type("Desktop", (), {"windows": lambda self: [u8_main, unrelated_form]})()
        with tempfile.TemporaryDirectory() as temporary, patch.dict("sys.modules", {"pywinauto": module}):
            result = inspect_backend("win32", ErrorRecorder(Path(temporary) / "diagnostics_errors.log"))
        self.assertEqual(len(result.windows), 1)

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

    def test_backend_and_screenshot_failures_still_leave_report_and_zip(self) -> None:
        win32 = BackendResult("win32", "success", "ok", windows=[{"window": {"title": "U8"}, "controls": []}])

        def inspect(name: str, errors: ErrorRecorder) -> BackendResult:
            if name == "uia":
                raise RuntimeError("UIA unavailable")
            return win32

        with tempfile.TemporaryDirectory() as temporary, patch("src.u8.probe.environment_snapshot", return_value={"administrator": {"is_administrator": False}}), patch("src.u8.probe.list_top_windows", return_value=([{"title": "U8"}], None)), patch("src.u8.probe.inspect_backend", side_effect=inspect), patch("src.u8.probe._capture_screenshots", side_effect=RuntimeError("screenshot unavailable")):
            root = Path(temporary)
            report = run_probe(root)
            archive = create_diagnostic_zip(report, root / "desktop")
            outcome = (report / "probe_outcome.json").read_text(encoding="utf-8")
            self.assertTrue((report / "environment.json").is_file())
            self.assertTrue((report / "u8_win32.txt").is_file())
            self.assertTrue((report / "u8_uia.txt").is_file())
            self.assertTrue((report / "diagnostics_errors.log").is_file())
            self.assertTrue(archive.is_file())
            self.assertIn('"u8_found": true', outcome)


if __name__ == "__main__":
    unittest.main()
