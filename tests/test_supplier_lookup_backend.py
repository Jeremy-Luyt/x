from __future__ import annotations

from types import ModuleType
from unittest.mock import patch
import unittest

from src.u8.pywinauto_backend import PyWinAutoU8Controller


class FakeControl:
    def __init__(self, title: str, class_name: str, handle: int,
                 left: int, top: int, right: int, bottom: int,
                 children: list["FakeControl"] | None = None) -> None:
        self._title = title
        self._class_name = class_name
        self.handle = handle
        self._rectangle = type("Rect", (), {"left": left, "top": top, "right": right, "bottom": bottom})()
        self._children = children or []
        self.entered_text: str | None = None
        self.clicks = 0

    def window_text(self) -> str:
        return self._title

    def class_name(self) -> str:
        return self._class_name

    def rectangle(self) -> object:
        return self._rectangle

    def is_visible(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return True

    def descendants(self) -> list["FakeControl"]:
        return self._children

    def set_edit_text(self, value: str) -> None:
        self.entered_text = value

    def click_input(self) -> None:
        self.clicks += 1


class SupplierLookupBackendTests(unittest.TestCase):
    def test_filter_uses_verified_query_and_filter_controls_but_never_confirms_selection(self) -> None:
        query = FakeControl("", "Edit", 3, 1040, 365, 1210, 385)
        filter_button = FakeControl("过滤(&F)", "Button", 4, 1124, 387, 1205, 410)
        confirm_button = FakeControl("确定", "Button", 5, 970, 335, 1020, 355)
        lookup = FakeControl("", "ThunderRT6FormDC", 100, 694, 333, 1214, 783, children=[
            FakeControl("供应商简称", "ComboBox", 1, 696, 365, 866, 385),
            FakeControl("包含", "ComboBox", 2, 868, 365, 1038, 385),
            query,
            filter_button,
            FakeControl("", "VSFlexGrid8U", 6, 847, 422, 1214, 721),
            confirm_button,
        ])
        module = ModuleType("pywinauto")
        module.Desktop = lambda backend: type("Desktop", (), {"windows": lambda self: [lookup]})()
        controller = PyWinAutoU8Controller(backend="win32")
        controller._window = object()  # A connected main U8 window is required by the public method.
        with patch.dict("sys.modules", {"pywinauto": module}):
            controller.filter_supplier_lookup("华泰通讯有限公司")
        self.assertEqual(query.entered_text, "华泰通讯有限公司")
        self.assertEqual(filter_button.clicks, 1)
        self.assertEqual(confirm_button.clicks, 0)


if __name__ == "__main__":
    unittest.main()
