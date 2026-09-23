from __future__ import annotations

import unittest

from src.u8.supplier_lookup_profile import SupplierLookupState, resolve_supplier_lookup


def record(title: str, class_name: str, handle: int, left: int, top: int,
           right: int, bottom: int, visible: bool = True, enabled: bool = True) -> dict[str, object]:
    return {
        "title": title,
        "class_name": class_name,
        "handle": handle,
        "visible": visible,
        "enabled": enabled,
        "rectangle": {"left": left, "top": top, "right": right, "bottom": bottom},
    }


class SupplierLookupProfileTests(unittest.TestCase):
    def test_resolves_verified_supplier_lookup_filter_without_coordinates_as_selector(self) -> None:
        root = record("", "ThunderRT6FormDC", 328406, 694, 333, 1214, 783)
        controls = [
            record("供应商简称", "ComboBox", 328448, 696, 365, 866, 385),
            record("包含", "ComboBox", 328452, 868, 365, 1038, 385),
            record("", "Edit", 328422, 1040, 365, 1210, 385),
            record("过滤(&F)", "Button", 393978, 1124, 387, 1205, 410),
            record("", "VSFlexGrid8U", 328410, 847, 422, 1214, 721),
            record("确定", "Button", 393976, 970, 335, 1020, 355),
        ]
        result = resolve_supplier_lookup(root, controls)
        self.assertEqual(result.state, SupplierLookupState.READY_TO_FILTER)
        self.assertEqual(result.controls["query_input"].observed_handle, 328422)
        self.assertEqual(result.controls["filter"].observed_handle, 393978)
        self.assertEqual(result.controls["result_grid"].class_name, "VSFlexGrid8U")

    def test_duplicate_filter_button_fails_closed(self) -> None:
        root = record("", "ThunderRT6FormDC", 328406, 694, 333, 1214, 783)
        controls = [
            record("供应商简称", "ComboBox", 1, 696, 365, 866, 385),
            record("包含", "ComboBox", 2, 868, 365, 1038, 385),
            record("", "Edit", 3, 1040, 365, 1210, 385),
            record("过滤(&F)", "Button", 4, 1124, 387, 1205, 410),
            record("过滤(&F)", "Button", 5, 1124, 410, 1205, 430),
            record("", "VSFlexGrid8U", 6, 847, 422, 1214, 721),
            record("确定", "Button", 7, 970, 335, 1020, 355),
        ]
        result = resolve_supplier_lookup(root, controls)
        self.assertEqual(result.state, SupplierLookupState.AMBIGUOUS)
        self.assertIn("filter", result.unresolved_controls)

    def test_non_lookup_form_is_not_accepted(self) -> None:
        root = record("供应商", "ThunderRT6FormDC", 328406, 694, 333, 1214, 783)
        result = resolve_supplier_lookup(root, [])
        self.assertEqual(result.state, SupplierLookupState.NOT_OPEN)


if __name__ == "__main__":
    unittest.main()
