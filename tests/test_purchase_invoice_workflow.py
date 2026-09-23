from decimal import Decimal
import unittest
from src.u8.purchase_invoice_workflow import (CalculatedTotals, GridCapability, PurchaseInvoiceLine, WorkflowState,
    detect_grid_capability, expected_totals, normalize_supplier, stop, supplier_matches, verify_totals)

class WorkflowTests(unittest.TestCase):
 def test_supplier_normalization_is_strict_not_fuzzy(self):
  self.assertTrue(supplier_matches(" 湖南 矿业 ", "湖南　矿业")); self.assertFalse(supplier_matches("湖南矿业", "湖北矿业"))
 def test_grid_capability_marks_real_diagnostic_grid_self_drawn(self):
  self.assertEqual(detect_grid_capability([{"class_name":"VSFlexGrid8N","visible":True}]), GridCapability.SELF_DRAWN_HWND)
 def test_decimal_totals_and_mismatch_stop(self):
  totals=expected_totals(PurchaseInvoiceLine(None,"煤",Decimal("28000"),Decimal("0.30")),Decimal("13"))
  self.assertEqual(totals, CalculatedTotals(Decimal("8400.00"),Decimal("1092.00"),Decimal("9492.00")))
  self.assertFalse(verify_totals(totals, CalculatedTotals(Decimal("8400.00"),Decimal("1092.01"),Decimal("9492.01"))))
  self.assertFalse(stop(WorkflowState.WRITE_QUANTITY,"GRID_CELL_NOT_FOUND","未找到").success)

