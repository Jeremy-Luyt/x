"""Windows U8 bridge with evidence-based, guarded special-invoice support."""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from .base import ControlTarget, U8Controller
from .purchase_invoice_profile import (InvoicePageState, PROTECTED_FIELDS,
                                       PageResolution, resolve_special_purchase_invoice)
from .supplier_lookup_profile import (SupplierLookupResolution, SupplierLookupState,
                                      resolve_supplier_lookup)


WRITABLE_SPECIAL_INVOICE_FIELDS = frozenset({"invoice_date", "supplier_invoice_number", "tax_rate", "currency"})


class PyWinAutoU8Controller(U8Controller):
    """Generic bridge. Build semantic selector maps only after probe evidence exists."""

    def __init__(self, backend: str = "win32") -> None:
        if backend not in {"uia", "win32"}:
            raise ValueError("backend 必须是 'uia' 或 'win32'。")
        self.backend = backend
        self._app = None
        self._window = None
        self._invoice_controls_by_handle: dict[int, Any] = {}
        self._supplier_lookup_controls_by_handle: dict[int, Any] = {}

    def _require_windows(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("真实 U8 自动化只能在 Windows 机房环境运行。")

    def _resolve(self, control: ControlTarget) -> object:
        if self._window is None:
            raise RuntimeError("尚未连接 U8 窗口。请先运行探测并提供窗口条件。")
        if not control.criteria:
            raise RuntimeError(f"控件 {control.name} 没有诊断确认过的选择条件。")
        return self._window.child_window(**control.criteria)

    def connect(self) -> bool:
        self._require_windows()
        try:
            from pywinauto import Desktop
        except ImportError as exc:  # pragma: no cover - platform-specific
            raise RuntimeError("缺少 pywinauto。") from exc
        # The lab evidence identifies 新道 U8.  Exclude this project's own
        # diagnostic window, which intentionally also contains “U8” in its title.
        candidates = []
        for window in Desktop(backend=self.backend).windows():
            try:
                title = str(window.window_text() or "")
            except Exception:
                continue
            if "环境诊断工具" not in title and any(word in title for word in ("U8", "用友", "企业应用平台", "新道")):
                candidates.append(window)
        if not candidates:
            return False
        self._window = candidates[0]
        return True

    def disconnect(self) -> None:
        self._window = None
        self._invoice_controls_by_handle.clear()
        self._supplier_lookup_controls_by_handle.clear()

    def find_window(self) -> object | None:
        return self._window

    def click(self, control: ControlTarget) -> None:
        self._resolve(control).click_input()

    def set_text(self, control: ControlTarget, value: str) -> None:
        self._resolve(control).set_edit_text(value)

    def select(self, control: ControlTarget, value: str) -> None:
        self._resolve(control).select(value)

    def press_key(self, key: str) -> None:
        if self._window is None:
            raise RuntimeError("尚未连接 U8 窗口。")
        self._window.type_keys(key)

    def wait_for(self, control: ControlTarget, timeout_seconds: float = 10.0) -> bool:
        self._resolve(control).wait("exists enabled visible", timeout=timeout_seconds)
        return True

    def take_screenshot(self, destination: Path | None = None) -> Path | None:
        if self._window is None:
            return None
        image = self._window.capture_as_image()
        if destination is not None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.save(destination)
            return destination
        return None

    def save(self) -> None:
        raise RuntimeError("安全策略禁止自动 Save。必须由用户在确认后手工保存。")

    @staticmethod
    def _safe(default: Any, callback: Any) -> Any:
        try:
            return callback()
        except Exception:
            return default

    def _special_invoice_snapshot(self) -> list[dict[str, Any]]:
        """Take an in-memory snapshot; handles never leave this live session."""
        if self._window is None:
            raise RuntimeError("尚未连接 U8 窗口。")
        records: list[dict[str, Any]] = []
        self._invoice_controls_by_handle.clear()
        for control in self._safe([], lambda: self._window.descendants()):
            record = self._control_record(control)
            handle = record["handle"]
            records.append(record)
            if isinstance(handle, int):
                self._invoice_controls_by_handle[handle] = control
        return records

    def _control_record(self, control: Any) -> dict[str, Any]:
        """Read one live control without retaining it in a diagnostic artifact."""
        handle = self._safe(None, lambda: control.handle)
        rectangle = self._safe(None, lambda: control.rectangle())
        return {
            "title": self._safe("", lambda: control.window_text()),
            "class_name": self._safe(None, lambda: control.class_name()),
            "handle": handle,
            "visible": self._safe(False, lambda: control.is_visible()),
            "enabled": self._safe(False, lambda: control.is_enabled()),
            "rectangle": None if rectangle is None else {
                "left": self._safe(None, lambda: rectangle.left), "top": self._safe(None, lambda: rectangle.top),
                "right": self._safe(None, lambda: rectangle.right), "bottom": self._safe(None, lambda: rectangle.bottom),
            },
        }

    def inspect_special_purchase_invoice(self) -> PageResolution:
        """Validate the current page before proposing any live edit."""
        return resolve_special_purchase_invoice(self._special_invoice_snapshot())

    def fill_confirmed_special_invoice_field(self, field: str, value: str) -> None:
        """Edit one confirmed header field; never selects a supplier or saves."""
        if field in PROTECTED_FIELDS or field not in WRITABLE_SPECIAL_INVOICE_FIELDS:
            raise RuntimeError(f"字段 {field} 不允许自动填写。")
        if not value.strip():
            raise RuntimeError("输入值为空，已取消操作。")
        resolution = self.inspect_special_purchase_invoice()
        if resolution.state is not InvoicePageState.FORM_READY_FOR_REVIEW:
            raise RuntimeError("当前不是可填写的专用发票页面，或供应商选择窗口仍打开。")
        resolved = resolution.fields.get(field)
        if resolved is None or resolved.observed_handle is None:
            raise RuntimeError(f"未能唯一定位字段：{field}。")
        control = self._invoice_controls_by_handle.get(resolved.observed_handle)
        if control is None:
            raise RuntimeError(f"字段 {field} 在读取后已变化，已取消操作。")
        try:
            control.set_edit_text(value)
        except Exception as exc:
            raise RuntimeError(f"无法填写字段 {resolved.label}，未继续执行后续步骤。") from exc

    def _supplier_lookup_snapshot(self) -> SupplierLookupResolution:
        """Find exactly one verified supplier-reference popup in the live session."""
        if self._window is None:
            raise RuntimeError("尚未连接 U8 窗口。")
        try:
            from pywinauto import Desktop
        except ImportError as exc:  # pragma: no cover - platform-specific
            raise RuntimeError("缺少 pywinauto。") from exc
        matches: list[tuple[SupplierLookupResolution, dict[int, Any]]] = []
        for window in self._safe([], lambda: Desktop(backend=self.backend).windows()):
            root = self._control_record(window)
            descendants = self._safe([], lambda window=window: window.descendants())
            controls = [self._control_record(control) for control in descendants]
            resolution = resolve_supplier_lookup(root, controls)
            # An unrelated empty VB6 form is never sufficient evidence.  The
            # observed lookup needs its supplier field, match mode and result grid.
            required = {"supplier_column", "match_mode", "result_grid"}
            if not required.issubset(resolution.controls):
                continue
            controls_by_handle: dict[int, Any] = {}
            for control in descendants:
                handle = self._safe(None, lambda control=control: control.handle)
                if isinstance(handle, int):
                    controls_by_handle[handle] = control
            matches.append((resolution, controls_by_handle))
        self._supplier_lookup_controls_by_handle.clear()
        if not matches:
            return SupplierLookupResolution(SupplierLookupState.NOT_OPEN, None, {}, ())
        if len(matches) > 1:
            return SupplierLookupResolution(SupplierLookupState.AMBIGUOUS, None, {}, ("lookup_window",))
        resolution, controls_by_handle = matches[0]
        self._supplier_lookup_controls_by_handle.update(controls_by_handle)
        return resolution

    def inspect_supplier_lookup(self) -> SupplierLookupResolution:
        """Read the current supplier popup only; this method never clicks U8."""
        return self._supplier_lookup_snapshot()

    def filter_supplier_lookup(self, supplier: str) -> None:
        """Fill the verified lookup filter and run its query, but never select a row."""
        if not supplier.strip():
            raise RuntimeError("供应商名称为空，未执行筛选。")
        resolution = self._supplier_lookup_snapshot()
        if resolution.state is SupplierLookupState.NOT_OPEN:
            raise RuntimeError("未检测到供应商参照窗口。请先在 U8 中手工打开供应商选择窗口。")
        if resolution.state is not SupplierLookupState.READY_TO_FILTER:
            raise RuntimeError("供应商参照窗口控件不唯一或不完整，已停止筛选。")
        query = resolution.controls.get("query_input")
        filter_button = resolution.controls.get("filter")
        if query is None or filter_button is None or query.observed_handle is None or filter_button.observed_handle is None:
            raise RuntimeError("未能唯一定位供应商检索框或过滤按钮。")
        query_control = self._supplier_lookup_controls_by_handle.get(query.observed_handle)
        button_control = self._supplier_lookup_controls_by_handle.get(filter_button.observed_handle)
        if query_control is None or button_control is None:
            raise RuntimeError("供应商参照窗口已变化，已取消操作。")
        try:
            query_control.set_edit_text(supplier)
            button_control.click_input()
        except Exception as exc:
            raise RuntimeError("供应商筛选未完成，未继续选择记录。") from exc
