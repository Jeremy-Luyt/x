"""Fail-closed state and validation logic for one unsaved purchase-invoice line."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
import re
import unicodedata
from typing import Any, Iterable


class WorkflowState(str, Enum):
    CHECK_U8 = "CHECK_U8"; CHECK_PURCHASE_INVOICE = "CHECK_PURCHASE_INVOICE"
    CHECK_NO_UNEXPECTED_DIALOG = "CHECK_NO_UNEXPECTED_DIALOG"; SELECT_SUPPLIER = "SELECT_SUPPLIER"
    VERIFY_SUPPLIER = "VERIFY_SUPPLIER"; LOCATE_DETAIL_GRID = "LOCATE_DETAIL_GRID"
    SELECT_ITEM = "SELECT_ITEM"; VERIFY_ITEM = "VERIFY_ITEM"; WRITE_QUANTITY = "WRITE_QUANTITY"
    VERIFY_QUANTITY = "VERIFY_QUANTITY"; WRITE_UNIT_PRICE = "WRITE_UNIT_PRICE"
    VERIFY_UNIT_PRICE = "VERIFY_UNIT_PRICE"; WRITE_TAX_RATE_IF_REQUIRED = "WRITE_TAX_RATE_IF_REQUIRED"
    WAIT_U8_CALCULATION = "WAIT_U8_CALCULATION"; READ_CALCULATED_VALUES = "READ_CALCULATED_VALUES"
    VERIFY_CALCULATED_VALUES = "VERIFY_CALCULATED_VALUES"; READY_FOR_HUMAN_SAVE = "READY_FOR_HUMAN_SAVE"


class GridCapability(str, Enum):
    UIA_CELLS = "uia_cells"; WIN32_CHILDREN = "win32_children"; SELF_DRAWN_HWND = "self_drawn_hwnd"; UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AutomationResult:
    success: bool
    state: WorkflowState
    error_code: str | None = None
    message: str = ""
    strategy: str | None = None


@dataclass(frozen=True)
class PurchaseInvoiceLine:
    item_code: str | None
    item_name: str | None
    quantity: Decimal
    unit_price: Decimal


@dataclass(frozen=True)
class PurchaseInvoiceData:
    invoice_date: str
    supplier_invoice_number: str
    supplier: str
    currency: str
    tax_rate: Decimal
    lines: tuple[PurchaseInvoiceLine, ...]


@dataclass(frozen=True)
class CalculatedTotals:
    amount: Decimal; tax: Decimal; total: Decimal


def normalize_supplier(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).strip())


def supplier_matches(expected: str, actual: str) -> bool:
    return normalize_supplier(expected) == normalize_supplier(actual)


def detect_grid_capability(controls: Iterable[dict[str, Any]]) -> GridCapability:
    records = list(controls)
    if any(str(r.get("control_type")) in {"DataItem", "DataGrid"} for r in records):
        return GridCapability.UIA_CELLS
    if any(r.get("class_name") in {"Edit", "ComboBox"} and r.get("visible") is True for r in records):
        # Generic child controls alone do not prove they belong to the grid.
        pass
    if any(r.get("class_name") == "VSFlexGrid8N" and r.get("visible") is True for r in records):
        return GridCapability.SELF_DRAWN_HWND
    return GridCapability.UNAVAILABLE


def expected_totals(line: PurchaseInvoiceLine, tax_rate: Decimal, precision: Decimal = Decimal("0.01")) -> CalculatedTotals:
    amount = (line.quantity * line.unit_price).quantize(precision, rounding=ROUND_HALF_UP)
    tax = (amount * tax_rate / Decimal("100")).quantize(precision, rounding=ROUND_HALF_UP)
    return CalculatedTotals(amount, tax, (amount + tax).quantize(precision, rounding=ROUND_HALF_UP))


def verify_totals(expected: CalculatedTotals, actual: CalculatedTotals) -> bool:
    return expected == actual


def stop(state: WorkflowState, code: str, message: str, strategy: str | None = None) -> AutomationResult:
    return AutomationResult(False, state, code, message, strategy)
