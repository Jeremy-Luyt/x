"""Evidence-based, write-safe recognition for the special purchase invoice page.

This module deliberately resolves *form structure*, not accounting actions.  It
uses the real Win32 diagnosis of the NewDo U8 page but never stores ephemeral
window handles or fixed screen coordinates as selectors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


PROFILE_ID = "special_purchase_invoice_win32_v1"
PAGE_TITLE_MARKER = "专用采购发票"
GRID_CLASS = "VSFlexGrid8N"
PROTECTED_FIELDS = frozenset({"system_invoice_number"})
FORBIDDEN_ACTIONS = frozenset({"save", "audit", "post", "close_period"})


@dataclass(frozen=True)
class FieldAnchor:
    """A stable visual relationship, not a persistent window handle."""

    name: str
    label: str
    writable: bool = True


@dataclass(frozen=True)
class ResolvedField:
    """A field found in one diagnostic snapshot; handle is evidence only."""

    name: str
    label: str
    class_name: str | None
    observed_handle: int | None
    candidate_count: int


@dataclass(frozen=True)
class PageResolution:
    profile_id: str
    page_detected: bool
    form_active: bool
    modal_dialog_open: bool
    fields: dict[str, ResolvedField]
    unresolved_fields: tuple[str, ...]


SPECIAL_PURCHASE_INVOICE_FIELDS = (
    FieldAnchor("business_type", "业务类型"),
    FieldAnchor("invoice_type", "发票类型"),
    FieldAnchor("invoice_date", "开票日期"),
    FieldAnchor("supplier", "供应商"),
    FieldAnchor("purchase_type", "采购类型"),
    FieldAnchor("tax_rate", "税率"),
    FieldAnchor("currency", "币种"),
    FieldAnchor("department", "部门名称"),
    FieldAnchor("exchange_rate", "汇率"),
    FieldAnchor("supplier_invoice_number", "供应商发票号"),
    FieldAnchor("system_invoice_number", "系统发票号", writable=False),
)


def _is_visible(record: dict[str, Any]) -> bool:
    return record.get("visible") is True


def _rectangle(record: dict[str, Any]) -> dict[str, int] | None:
    rectangle = record.get("rectangle")
    if not isinstance(rectangle, dict):
        return None
    required = ("left", "top", "right", "bottom")
    if not all(isinstance(rectangle.get(key), int) for key in required):
        return None
    return rectangle  # type: ignore[return-value]


def _vertical_distance(left: dict[str, int], right: dict[str, int]) -> float:
    return abs((left["top"] + left["bottom"]) / 2 - (right["top"] + right["bottom"]) / 2)


def _is_invoice_page(records: Iterable[dict[str, Any]]) -> bool:
    controls = list(records)
    has_page_title = any(
        _is_visible(record) and PAGE_TITLE_MARKER in str(record.get("title") or "")
        for record in controls
    )
    has_grid = any(
        _is_visible(record) and record.get("class_name") == GRID_CLASS
        for record in controls
    )
    return has_page_title and has_grid


def _form_is_disabled(records: Iterable[dict[str, Any]]) -> bool:
    """A modal lookup disables the VB6 invoice form; never write in that state."""
    return any(
        _is_visible(record)
        and record.get("class_name") == "ThunderRT6FormDC"
        and record.get("enabled") is False
        and "专用发票" in str(record.get("title") or "")
        for record in records
    )


def _find_input_after_label(label_record: dict[str, Any], records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find editable controls on the same row, immediately right of a label.

    The relation is calculated from live control rectangles.  It is not a
    screen coordinate and must be revalidated before any future live action.
    """
    label_rect = _rectangle(label_record)
    if label_rect is None:
        return []
    candidates: list[dict[str, Any]] = []
    for record in records:
        rectangle = _rectangle(record)
        if (not _is_visible(record) or record.get("enabled") is not True
                or record.get("class_name") not in {"Edit", "ComboBox"}
                or rectangle is None):
            continue
        horizontal_gap = rectangle["left"] - label_rect["right"]
        if horizontal_gap < 0 or horizontal_gap > 100 or _vertical_distance(label_rect, rectangle) > 12:
            continue
        candidates.append(record)
    return sorted(candidates, key=lambda record: _rectangle(record)["left"] if _rectangle(record) else 0)


def resolve_special_purchase_invoice(controls: Iterable[dict[str, Any]]) -> PageResolution:
    """Resolve the observed, writable header fields in a diagnostic snapshot."""
    records = list(controls)
    page_detected = _is_invoice_page(records)
    modal_dialog_open = _form_is_disabled(records)
    fields: dict[str, ResolvedField] = {}
    unresolved: list[str] = []
    for anchor in SPECIAL_PURCHASE_INVOICE_FIELDS:
        labels = [
            record for record in records
            if _is_visible(record) and str(record.get("title") or "").strip() == anchor.label
            and record.get("class_name") == "Static"
        ]
        candidates = [candidate for label in labels for candidate in _find_input_after_label(label, records)]
        # More than one matching control is treated as ambiguity; a future live
        # adapter must refuse the write rather than choose based on a guess.
        unique = {candidate.get("handle"): candidate for candidate in candidates if candidate.get("handle") is not None}
        if len(unique) != 1:
            unresolved.append(anchor.name)
            continue
        candidate = next(iter(unique.values()))
        fields[anchor.name] = ResolvedField(
            name=anchor.name,
            label=anchor.label,
            class_name=candidate.get("class_name"),
            observed_handle=candidate.get("handle") if isinstance(candidate.get("handle"), int) else None,
            candidate_count=len(unique),
        )
    return PageResolution(
        profile_id=PROFILE_ID,
        page_detected=page_detected,
        form_active=page_detected and not modal_dialog_open,
        modal_dialog_open=modal_dialog_open,
        fields=fields,
        unresolved_fields=tuple(unresolved),
    )
