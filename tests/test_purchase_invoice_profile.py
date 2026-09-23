from __future__ import annotations

import unittest

from src.u8.purchase_invoice_profile import (FORBIDDEN_ACTIONS, PROTECTED_FIELDS,
                                              resolve_special_purchase_invoice)


def control(title: str, class_name: str, left: int, top: int, right: int, bottom: int,
            *, visible: bool = True, enabled: bool = True, handle: int | None = None) -> dict[str, object]:
    return {
        "title": title, "class_name": class_name, "visible": visible, "enabled": enabled,
        "handle": handle, "rectangle": {"left": left, "top": top, "right": right, "bottom": bottom},
    }


class PurchaseInvoiceProfileTests(unittest.TestCase):
    def test_resolves_real_label_to_same_row_edit_without_coordinates_as_selector(self) -> None:
        snapshot = [
            control("PUM030601{##}专用采购发票", "WindowsForms10.Window", 75, 134, 1735, 996),
            control("", "VSFlexGrid8N", 91, 330, 1714, 957),
            control("开票日期", "Static", 93, 209, 156, 223),
            control("2026-12-01", "Edit", 162, 208, 605, 226, handle=134190),
            control("供应商", "Static", 649, 209, 700, 223),
            control("", "Edit", 706, 208, 1142, 226, handle=199704),
        ]
        result = resolve_special_purchase_invoice(snapshot)
        self.assertTrue(result.page_detected)
        self.assertTrue(result.form_active)
        self.assertEqual(result.fields["invoice_date"].observed_handle, 134190)
        self.assertEqual(result.fields["supplier"].observed_handle, 199704)
        self.assertIn("system_invoice_number", result.unresolved_fields)

    def test_modal_lookup_makes_form_not_active(self) -> None:
        snapshot = [
            control("PUM030601{##}专用采购发票", "WindowsForms10.Window", 75, 134, 1735, 996),
            control("", "VSFlexGrid8N", 91, 330, 1714, 957),
            control("专用发票", "ThunderRT6FormDC", 75, 134, 1735, 996, enabled=False),
        ]
        result = resolve_special_purchase_invoice(snapshot)
        self.assertTrue(result.modal_dialog_open)
        self.assertFalse(result.form_active)

    def test_protected_financial_actions_remain_forbidden(self) -> None:
        self.assertIn("system_invoice_number", PROTECTED_FIELDS)
        self.assertTrue({"save", "audit", "post", "close_period"}.issubset(FORBIDDEN_ACTIONS))


if __name__ == "__main__":
    unittest.main()
