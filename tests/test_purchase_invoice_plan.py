from __future__ import annotations

import unittest

from src.tasks.business_data import TaskBusinessData
from src.u8.pywinauto_backend import WRITABLE_SPECIAL_INVOICE_FIELDS
from src.u8.purchase_invoice_plan import build_special_purchase_invoice_plan


class PurchaseInvoicePlanTests(unittest.TestCase):
    def test_plan_only_includes_reliably_available_values(self) -> None:
        plan = build_special_purchase_invoice_plan(TaskBusinessData(
            task_id="17", business_category="采购", date="2018-12-07", counterparty="甲公司",
        ))
        self.assertTrue(plan.supported)
        self.assertTrue(plan.steps[0].ready)
        self.assertTrue(plan.steps[1].ready)
        self.assertFalse(plan.steps[2].ready)
        self.assertIn("不会自动保存", "\n".join(plan.preview_lines()))

    def test_non_purchase_task_has_no_invoice_actions(self) -> None:
        plan = build_special_purchase_invoice_plan(TaskBusinessData(task_id="1", business_category="销售"))
        self.assertFalse(plan.supported)
        self.assertEqual(plan.steps, ())

    def test_live_write_allowlist_excludes_supplier_and_protected_actions(self) -> None:
        self.assertEqual(WRITABLE_SPECIAL_INVOICE_FIELDS, {"invoice_date", "supplier_invoice_number", "tax_rate", "currency"})


if __name__ == "__main__":
    unittest.main()
