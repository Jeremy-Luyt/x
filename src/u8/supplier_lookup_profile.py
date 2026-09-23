"""Verified, fail-closed recognition for the U8 supplier reference window.

The NewDo U8 lab diagnostics show that the supplier lookup is an untitled VB6
form.  This module resolves controls from live relationships within that form;
it does not retain handles, select a result row, confirm a selection, or save.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable


LOOKUP_FORM_CLASS = "ThunderRT6FormDC"
GRID_CLASS = "VSFlexGrid8U"
SUPPLIER_FIELD_LABEL = "供应商简称"
MATCH_MODE_LABEL = "包含"
FILTER_BUTTON_LABEL = "过滤(&F)"
CONFIRM_BUTTON_LABEL = "确定"


class SupplierLookupState(str, Enum):
    NOT_OPEN = "not_open"
    READY_TO_FILTER = "ready_to_filter"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class LookupControl:
    name: str
    label: str
    class_name: str | None
    observed_handle: int | None
    candidate_count: int


@dataclass(frozen=True)
class SupplierLookupResolution:
    state: SupplierLookupState
    root_handle: int | None
    controls: dict[str, LookupControl]
    unresolved_controls: tuple[str, ...]


def _rectangle(record: dict[str, Any]) -> dict[str, int] | None:
    rectangle = record.get("rectangle")
    required = ("left", "top", "right", "bottom")
    if not isinstance(rectangle, dict) or not all(isinstance(rectangle.get(key), int) for key in required):
        return None
    return rectangle  # type: ignore[return-value]


def _is_visible_enabled(record: dict[str, Any]) -> bool:
    return record.get("visible") is True and record.get("enabled") is True


def _same_row(left: dict[str, Any], right: dict[str, Any], tolerance: int = 12) -> bool:
    left_rect, right_rect = _rectangle(left), _rectangle(right)
    if left_rect is None or right_rect is None:
        return False
    return abs((left_rect["top"] + left_rect["bottom"]) - (right_rect["top"] + right_rect["bottom"])) <= tolerance * 2


def _right_of(left: dict[str, Any], right: dict[str, Any], maximum_gap: int = 80) -> bool:
    left_rect, right_rect = _rectangle(left), _rectangle(right)
    return bool(left_rect and right_rect and 0 <= right_rect["left"] - left_rect["right"] <= maximum_gap)


def _unique_control(name: str, label: str, candidates: Iterable[dict[str, Any]]) -> tuple[LookupControl | None, bool]:
    unique = {record.get("handle"): record for record in candidates if isinstance(record.get("handle"), int)}
    if len(unique) != 1:
        return None, bool(unique)
    record = next(iter(unique.values()))
    return LookupControl(name, label, record.get("class_name"), record.get("handle"), len(unique)), False


def resolve_supplier_lookup(root: dict[str, Any], controls: Iterable[dict[str, Any]]) -> SupplierLookupResolution:
    """Resolve the observed supplier lookup controls without operating U8.

    The query input is not identified by an arbitrary ordinal: it must be the
    only visible enabled ``Edit`` immediately to the right of the observed
    ``包含`` selector in the same lookup form.
    """
    records = list(controls)
    form_is_valid = (
        str(root.get("class_name") or "").casefold() == LOOKUP_FORM_CLASS.casefold()
        and root.get("title") in (None, "")
        and _is_visible_enabled(root)
    )
    if not form_is_valid:
        return SupplierLookupResolution(SupplierLookupState.NOT_OPEN, None, {}, ())

    supplier_columns = [
        record for record in records
        if _is_visible_enabled(record) and record.get("class_name") == "ComboBox"
        and str(record.get("title") or "").strip() == SUPPLIER_FIELD_LABEL
    ]
    match_modes = [
        record for record in records
        if _is_visible_enabled(record) and record.get("class_name") == "ComboBox"
        and str(record.get("title") or "").strip() == MATCH_MODE_LABEL
    ]
    filter_buttons = [
        record for record in records
        if _is_visible_enabled(record) and record.get("class_name") == "Button"
        and str(record.get("title") or "").strip() == FILTER_BUTTON_LABEL
    ]
    result_grids = [
        record for record in records
        if _is_visible_enabled(record) and record.get("class_name") == GRID_CLASS
    ]
    confirm_buttons = [
        record for record in records
        if _is_visible_enabled(record) and record.get("class_name") == "Button"
        and str(record.get("title") or "").strip() == CONFIRM_BUTTON_LABEL
    ]
    query_inputs = [
        record for mode in match_modes for record in records
        if _is_visible_enabled(record) and record.get("class_name") == "Edit"
        and _same_row(mode, record) and _right_of(mode, record)
    ]

    specifications = (
        ("supplier_column", SUPPLIER_FIELD_LABEL, supplier_columns),
        ("match_mode", MATCH_MODE_LABEL, match_modes),
        ("query_input", "供应商检索内容", query_inputs),
        ("filter", FILTER_BUTTON_LABEL, filter_buttons),
        ("result_grid", GRID_CLASS, result_grids),
        ("confirm", CONFIRM_BUTTON_LABEL, confirm_buttons),
    )
    resolved: dict[str, LookupControl] = {}
    unresolved: list[str] = []
    ambiguous = False
    for name, label, candidates in specifications:
        control, was_ambiguous = _unique_control(name, label, candidates)
        if control is None:
            unresolved.append(name)
            ambiguous = ambiguous or was_ambiguous
        else:
            resolved[name] = control
    # ``确定`` is intentionally optional: this assistant never clicks it or
    # chooses a result row.  Some U8 skins expose the toolbar icon without a
    # readable caption, which must not prevent a harmless filter operation.
    required_for_filter = {"supplier_column", "match_mode", "query_input", "filter", "result_grid"}
    state = (SupplierLookupState.READY_TO_FILTER
             if required_for_filter.issubset(resolved) else SupplierLookupState.AMBIGUOUS)
    return SupplierLookupResolution(
        state=state,
        root_handle=root.get("handle") if isinstance(root.get("handle"), int) else None,
        controls=resolved,
        unresolved_controls=tuple(unresolved),
    )
