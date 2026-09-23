"""Read-only U8 lab diagnostics with evidence-rich, failure-tolerant reports.

This module never clicks, types, saves, or otherwise changes U8. It only reads
Windows accessibility/window metadata and optionally captures screenshots.
"""

from __future__ import annotations

import argparse
import ctypes
import io
import json
import platform
import re
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable, Iterable, Literal


U8_WORDS = ("u8", "用友", "企业应用平台", "新道")
U8_RELATED_DIALOG_WORDS = ("供应商", "存货", "参照")
LEGACY_DIALOG_CLASSES = frozenset({"thunderrt6formdc"})
# The probe's own title deliberately contains U8 so ordinary users know what it
# is for.  It is never evidence of a running U8 business application.
PROBE_WINDOW_TITLE_MARKERS = ("环境诊断工具",)
INTERACTIVE_TYPES = {
    "Edit", "Button", "ComboBox", "CheckBox", "RadioButton", "TreeView", "List",
    "ListItem", "DataGrid", "DataItem", "MenuItem", "TabItem",
}
CLASS_TO_CONTROL_TYPE = {
    "edit": "Edit", "button": "Button", "combobox": "ComboBox",
    "comboboxex32": "ComboBox", "syscheckbox32": "CheckBox",
    "sysradiobutton32": "RadioButton", "systreeview32": "TreeView",
    "syslistview32": "List", "listbox": "List", "menuitem": "MenuItem",
    "systabcontrol32": "TabItem",
    # The diagnosed U8 pages and lookup windows use classic VB6 controls.
    # Normalising them gives the interactive-controls report a useful grid and
    # input inventory even where UI Automation exposes no control type.
    "thunderrt6textbox": "Edit", "thunderrt6commandbutton": "Button",
    "thunderrt6checkbox": "CheckBox", "thunderrt6optionbutton": "RadioButton",
    "vsflexgrid8n": "DataGrid", "vsflexgrid8u": "DataGrid",
}

# Desktop enumeration occasionally includes a protected or hung application on
# old lab machines.  Win32 calls against that process can block rather than
# raise, so normal try/except alone is not enough.  These limits only apply to
# discovery; a timed-out call is recorded and the report continues.
TOP_WINDOW_ENUM_TIMEOUT_SECONDS = 12.0
TOP_WINDOW_RECORD_TIMEOUT_SECONDS = 2.0
TOP_WINDOW_DISCOVERY_TIMEOUT_SECONDS = 30.0
BACKEND_WINDOW_INSPECTION_TIMEOUT_SECONDS = 45.0
RELATED_DIALOG_DETAILS_TIMEOUT_SECONDS = 3.0
RELATED_DIALOG_INSPECTION_TIMEOUT_SECONDS = 12.0
SCREENSHOT_TIMEOUT_SECONDS = 20.0


@dataclass
class ErrorRecorder:
    """Append failures as they occur, so late faults never hide earlier evidence."""

    path: Path
    messages: list[str] = field(default_factory=list)

    def record(self, context: str, exc: BaseException | str) -> None:
        kind = type(exc).__name__ if isinstance(exc, BaseException) else "Error"
        message = f"{datetime.now().isoformat(timespec='seconds')} | {context} | {kind}: {exc}"
        self.messages.append(message)
        try:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(message + "\n")
        except OSError:
            pass


@dataclass
class BackendResult:
    backend: str
    status: Literal["success", "failed", "skipped"]
    identifiers: str
    windows: list[dict[str, Any]] = field(default_factory=list)
    hierarchy: list[dict[str, Any]] = field(default_factory=list)
    interactive_controls: list[dict[str, Any]] = field(default_factory=list)
    screenshot_roots: list[Any] = field(default_factory=list)
    error: str | None = None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _safe_label(label: str | None) -> str | None:
    if not label:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", label).strip("._-")
    return cleaned[:80] or "probe"


def _create_output_dir(output_base: Path, directory_name: str) -> Path:
    """Create a fresh report directory even for two probes started in one second."""
    candidate = output_base / directory_name
    suffix = 1
    while True:
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            candidate = output_base / f"{directory_name}_{suffix:02d}"
            suffix += 1


def _safe_call(default: Any, errors: ErrorRecorder, context: str, callback: Any) -> Any:
    try:
        return callback()
    except Exception as exc:
        errors.record(context, exc)
        return default


def _bounded_call(default: Any, errors: ErrorRecorder, context: str,
                  callback: Callable[[], Any], timeout_seconds: float) -> Any:
    """Run a potentially blocking Win32 query without holding the probe forever.

    Python cannot safely terminate a thread in a native Windows call.  The
    worker is therefore daemon-only: on timeout the probe keeps going and the
    process can still exit normally once the report is saved.
    """
    completed = threading.Event()
    result: dict[str, Any] = {"value": default}

    def invoke() -> None:
        try:
            result["value"] = callback()
        except Exception as exc:
            result["exception"] = exc
        finally:
            completed.set()

    threading.Thread(target=invoke, daemon=True, name="u8-probe-window-read").start()
    if not completed.wait(timeout_seconds):
        errors.record(context, TimeoutError(f"Windows 查询超过 {timeout_seconds:.0f} 秒，已跳过"))
        return default
    if "exception" in result:
        errors.record(context, result["exception"])
        return default
    return result["value"]


def _rectangle(window: Any, errors: ErrorRecorder, context: str) -> dict[str, int] | None:
    rectangle = _safe_call(None, errors, f"{context}.rectangle", lambda: window.rectangle())
    if rectangle is None:
        return None
    return {
        "left": _safe_call(None, errors, f"{context}.rectangle.left", lambda: rectangle.left),
        "top": _safe_call(None, errors, f"{context}.rectangle.top", lambda: rectangle.top),
        "right": _safe_call(None, errors, f"{context}.rectangle.right", lambda: rectangle.right),
        "bottom": _safe_call(None, errors, f"{context}.rectangle.bottom", lambda: rectangle.bottom),
    }


def _normalise_control_type(raw_type: Any, class_name: Any) -> str | None:
    if isinstance(raw_type, str) and raw_type.strip():
        return raw_type.strip()
    return CLASS_TO_CONTROL_TYPE.get(class_name.casefold()) if isinstance(class_name, str) else None


def _window_record(window: Any, errors: ErrorRecorder, context: str) -> dict[str, Any]:
    """Read every remote-window field independently; no property access is trusted."""
    element = _safe_call(None, errors, f"{context}.element_info", lambda: getattr(window, "element_info", None))
    title = _safe_call("", errors, f"{context}.title", lambda: window.window_text())
    handle = _safe_call(None, errors, f"{context}.handle", lambda: window.handle)
    class_name = _safe_call(None, errors, f"{context}.class_name", lambda: window.class_name())
    if not class_name and element is not None:
        class_name = _safe_call(None, errors, f"{context}.element_class_name", lambda: getattr(element, "class_name"))
    control_type = _safe_call(None, errors, f"{context}.control_type", lambda: getattr(element, "control_type")) if element is not None else None
    automation_id = _safe_call(None, errors, f"{context}.automation_id", lambda: getattr(element, "automation_id")) if element is not None else None
    return {
        "title": title,
        "handle": handle,
        "class_name": class_name,
        "control_type": _normalise_control_type(control_type, class_name),
        "automation_id": automation_id,
        "rectangle": _rectangle(window, errors, context),
        "visible": _safe_call(None, errors, f"{context}.visible", lambda: window.is_visible()),
        "enabled": _safe_call(None, errors, f"{context}.enabled", lambda: window.is_enabled()),
    }


def _candidate_record(window: Any, errors: ErrorRecorder, context: str) -> dict[str, Any]:
    """Use only low-risk metadata while deciding whether a top-level window is U8."""
    return {
        "title": _safe_call("", errors, f"{context}.title", lambda: window.window_text()),
        "handle": _safe_call(None, errors, f"{context}.handle", lambda: window.handle),
        "class_name": _safe_call(None, errors, f"{context}.class_name", lambda: window.class_name()),
    }


def _matches_u8(record: dict[str, Any]) -> bool:
    title = str(record.get("title") or "").casefold()
    return (not any(marker in title for marker in PROBE_WINDOW_TITLE_MARKERS)
            and any(word in title for word in U8_WORDS))


def _matches_u8_related_dialog(record: dict[str, Any]) -> bool:
    """Capture a U8 lookup dialog only after a genuine U8 root was found."""
    title = str(record.get("title") or "").casefold()
    return any(word in title for word in U8_RELATED_DIALOG_WORDS)


def _is_legacy_dialog_candidate(record: dict[str, Any]) -> bool:
    """Return True for the untitled VB6 forms used by U8 reference lookups.

    This is deliberately only a *candidate* check.  It is considered only
    after the current U8 special-invoice form was observed disabled, then a
    bounded detailed read verifies that it is a visible, usable dialog.
    """
    return str(record.get("class_name") or "").casefold() in LEGACY_DIALOG_CLASSES


def _is_visible_legacy_dialog(record: dict[str, Any]) -> bool:
    rectangle = record.get("rectangle")
    if not (record.get("visible") is True and record.get("enabled") is True
            and isinstance(rectangle, dict)):
        return False
    try:
        return (int(rectangle["right"]) - int(rectangle["left"]) >= 200
                and int(rectangle["bottom"]) - int(rectangle["top"]) >= 120)
    except (KeyError, TypeError, ValueError):
        return False


def _special_invoice_lookup_is_open(result: BackendResult) -> bool:
    """Detect the observed modal state without assuming a popup caption.

    In the lab evidence the ``采购供应商档案`` popup is a blank-caption VB6
    window.  The dependable state signal is instead that its parent
    ``专用发票`` form is visible but disabled.
    """
    for window in result.windows:
        for control in window.get("controls", []):
            if (control.get("visible") is True and control.get("enabled") is False
                    and str(control.get("class_name") or "").casefold() == "thunderrt6formdc"
                    and "专用发票" in str(control.get("title") or "")):
                return True
    return False


def _is_interactive(record: dict[str, Any]) -> bool:
    return record.get("control_type") in INTERACTIVE_TYPES


def _node_key(record: dict[str, Any]) -> str:
    if record.get("handle") is not None:
        return f"handle:{record['handle']}"
    return "|".join(str(record.get(key) or "") for key in ("title", "class_name", "automation_id"))


def _parent_and_depth(control: Any, root_key: str, errors: ErrorRecorder, context: str) -> tuple[dict[str, Any] | None, int]:
    parent = _safe_call(None, errors, f"{context}.parent", lambda: control.parent())
    if parent is None:
        return None, 0
    direct_parent = _window_record(parent, errors, f"{context}.parent_record")
    depth, cursor, seen = 1, parent, {_node_key(direct_parent)}
    while depth < 30 and _node_key(direct_parent) != root_key:
        next_parent = _safe_call(None, errors, f"{context}.ancestor_{depth}", lambda: cursor.parent())
        if next_parent is None:
            break
        cursor = next_parent
        ancestor = _window_record(cursor, errors, f"{context}.ancestor_record_{depth}")
        key = _node_key(ancestor)
        if key in seen:
            break
        seen.add(key)
        direct_parent = ancestor
        depth += 1
    return _window_record(parent, errors, f"{context}.parent_final"), depth


def _is_obvious_dialog(record: dict[str, Any], root_record: dict[str, Any]) -> bool:
    if _node_key(record) == _node_key(root_record):
        return False
    return (str(record.get("control_type") or "").casefold() in {"window", "dialog"}
            or str(record.get("class_name") or "").casefold() == "#32770")


def _dpi_scaling(errors: ErrorRecorder) -> dict[str, Any]:
    if platform.system() != "Windows":
        return {"available": False, "reason": "not_windows"}
    try:
        user32 = ctypes.windll.user32
        # SetProcessDPIAware is present on Windows 7; newer GetDpiForSystem is
        # not.  Each optional call is guarded so the report still completes.
        set_aware = getattr(user32, "SetProcessDPIAware", None)
        if set_aware is not None:
            set_aware()
        get_dpi_for_system = getattr(user32, "GetDpiForSystem", None)
        if get_dpi_for_system is not None:
            dpi = get_dpi_for_system()
            method = "GetDpiForSystem"
        else:
            hdc = user32.GetDC(None)
            if not hdc:
                raise OSError("GetDC failed while reading DPI")
            try:
                # LOGPIXELSX (88) is available on Windows 7 through gdi32.
                dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
            finally:
                user32.ReleaseDC(None, hdc)
            method = "GetDeviceCaps"
        return {
            "available": True,
            "dpi": dpi,
            "scale_percent": round(dpi / 96 * 100),
            "method": method,
        }
    except Exception as exc:  # pragma: no cover - Windows variants
        errors.record("dpi_scaling", exc)
        return {"available": False, "error": str(exc)}


def _is_administrator(errors: ErrorRecorder) -> dict[str, Any]:
    if platform.system() != "Windows":
        return {"available": False, "is_administrator": None, "reason": "not_windows"}
    try:
        return {"available": True, "is_administrator": bool(ctypes.windll.shell32.IsUserAnAdmin())}
    except Exception as exc:  # pragma: no cover - Windows variants
        errors.record("administrator_check", exc)
        return {"available": False, "is_administrator": None, "error": str(exc)}


def _pywinauto_version(errors: ErrorRecorder) -> str | None:
    try:
        return version("pywinauto")
    except PackageNotFoundError as exc:
        errors.record("pywinauto_version", exc)
        return None


def environment_snapshot(errors: ErrorRecorder) -> dict[str, Any]:
    try:
        from PIL import ImageGrab
        screen = ImageGrab.grab().size
    except Exception as exc:
        errors.record("screen_resolution", exc)
        screen, screen_error = None, str(exc)
    else:
        screen_error = None
    return {
        "python_version": sys.version,
        "windows_version": platform.platform(),
        "platform": platform.system(),
        "screen_resolution": {"width": screen[0], "height": screen[1]} if screen else None,
        "screen_error": screen_error,
        "dpi_scaling": _dpi_scaling(errors),
        "administrator": _is_administrator(errors),
        "pywinauto_version": _pywinauto_version(errors),
    }


def list_top_windows(errors: ErrorRecorder) -> tuple[list[dict[str, Any]], str | None]:
    try:
        from pywinauto import Desktop
    except Exception as exc:
        errors.record("top_level_windows", exc)
        return [], f"无法列举顶层窗口：{type(exc).__name__}: {exc}"
    windows = _bounded_call(
        [], errors, "top_level_windows.enumeration",
        lambda: Desktop(backend="win32").windows(), TOP_WINDOW_ENUM_TIMEOUT_SECONDS,
    )
    if not windows:
        return [], "顶层窗口列举超时或不可用；已跳过无响应的系统窗口。"
    records: list[dict[str, Any]] = []
    deadline = time.monotonic() + TOP_WINDOW_DISCOVERY_TIMEOUT_SECONDS
    for index, window in enumerate(windows, 1):
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                errors.record("top_level_windows.discovery", TimeoutError(
                    f"顶层窗口筛选超过 {TOP_WINDOW_DISCOVERY_TIMEOUT_SECONDS:.0f} 秒，已停止继续读取"))
                break
            # Do not request element_info, visibility or rectangles for every
            # unrelated desktop window.  Those remote reads are both slow and
            # the source of AccessDenied/hangs seen on Windows 7.
            candidate = _bounded_call(
                None, errors, f"top_window_{index}.candidate",
                lambda window=window, index=index: _candidate_record(window, errors, f"top_window_{index}"),
                min(TOP_WINDOW_RECORD_TIMEOUT_SECONDS, remaining),
            )
            if candidate is None:
                continue
            if _matches_u8(candidate):
                # Only suspected U8 windows need detailed metadata for the
                # report.  Give each one its own short bound as well.
                detailed = _bounded_call(
                    None, errors, f"top_window_{index}.details",
                    lambda window=window, index=index: _window_record(window, errors, f"top_window_{index}"),
                    min(TOP_WINDOW_RECORD_TIMEOUT_SECONDS, max(0.1, deadline - time.monotonic())),
                )
                records.append(detailed if detailed is not None else candidate)
            else:
                records.append(candidate)
        except Exception as exc:
            # Handles can disappear between Desktop.windows() and inspection.
            errors.record(f"top_window_{index}.skip", exc)
    return records, None


def _inspect_window(backend: str, window: Any, index: int, errors: ErrorRecorder) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[Any], str]:
    root = _window_record(window, errors, f"{backend}.window_{index}")
    hierarchy = [{"backend": backend, "parent": None, "child": root, "depth": 0}]
    controls: list[dict[str, Any]] = []
    dialogs: list[Any] = []
    # Desktop.windows() returns wrappers on some pywinauto/Win7 combinations,
    # not WindowSpecification objects.  Calling print_control_identifiers on a
    # wrapper causes a misleading AttributeError.  The structured text below
    # is an equivalent control tree and is valid for both kinds of object.
    identifiers = io.StringIO()
    identifiers.write(
        f"=== Root window ===\n"
        f"title: {root.get('title')!r}\nclass_name: {root.get('class_name')!r}\n"
        f"handle: {root.get('handle')!r}\n\n=== Descendant controls ===\n"
    )
    descendants = _safe_call([], errors, f"{backend}.window_{index}.descendants", lambda: window.descendants())
    for control_index, control in enumerate(descendants, 1):
        context = f"{backend}.window_{index}.control_{control_index}"
        try:
            record = _window_record(control, errors, context)
            controls.append(record)
            identifiers.write(
                f"{control_index:04d} | type={record.get('control_type')!r} | "
                f"title={record.get('title')!r} | class={record.get('class_name')!r} | "
                f"automation_id={record.get('automation_id')!r} | handle={record.get('handle')!r}\n"
            )
            parent, depth = _parent_and_depth(control, _node_key(root), errors, context)
            hierarchy.append({"backend": backend, "parent": parent, "child": record, "depth": depth})
            if _is_obvious_dialog(record, root):
                dialogs.append(control)
        except Exception as exc:
            errors.record(context, exc)
    return ({"window": root, "controls": controls}, hierarchy,
            [record for record in controls if _is_interactive(record)], dialogs, identifiers.getvalue())


def _append_window_inspection(result: BackendResult, backend: str, window: Any,
                              index: int, errors: ErrorRecorder, sections: list[str],
                              timeout_seconds: float, description: str) -> bool:
    """Inspect one already-selected window, preserving all earlier evidence on failure."""
    try:
        inspected = _bounded_call(
            None, errors, f"{backend}.{description}_{index}.inspection",
            lambda: _inspect_window(backend, window, index, errors), timeout_seconds,
        )
        if inspected is None:
            sections.append(f"\n=== {description.title()} {index} timed out and was skipped ===\n")
            return False
        structured, hierarchy, interactive, dialogs, identifiers = inspected
        result.windows.append(structured)
        result.hierarchy.extend(hierarchy)
        result.interactive_controls.extend({"backend": backend, **record} for record in interactive)
        # Hidden historical U8 windows produced confusing cropped
        # ``u8_dialog_01`` images in the first reports.  Keep screenshot names
        # meaningful by queueing only windows that are visible at capture time.
        if structured["window"].get("visible") is True:
            result.screenshot_roots.append(window)
        result.screenshot_roots.extend(dialogs)
        title = structured["window"].get("title") or "(untitled window)"
        sections.append(f"\n=== {description.title()} {index}: {title} ===\n{identifiers}")
        return True
    except Exception as exc:
        errors.record(f"{backend}.{description}_{index}", exc)
        sections.append(f"\n=== {description.title()} {index} failed ===\n{type(exc).__name__}: {exc}\n")
        return False


def inspect_backend(backend: str, errors: ErrorRecorder) -> BackendResult:
    try:
        from pywinauto import Desktop
    except Exception as exc:
        errors.record(f"{backend}.desktop", exc)
        return BackendResult(backend, "failed", f"{backend} backend failed but probe continued:\n{type(exc).__name__}: {exc}\n", error=str(exc))
    windows = _bounded_call(
        [], errors, f"{backend}.desktop.enumeration",
        lambda: Desktop(backend=backend).windows(), TOP_WINDOW_ENUM_TIMEOUT_SECONDS,
    )
    if not windows:
        message = f"{backend} backend 未返回窗口（超时或不可用），已跳过。\n"
        return BackendResult(backend, "failed", message, error="desktop enumeration timed out or returned no windows")
    result = BackendResult(backend, "success", "")
    candidates: list[tuple[Any, dict[str, Any]]] = []
    deadline = time.monotonic() + TOP_WINDOW_DISCOVERY_TIMEOUT_SECONDS
    for index, window in enumerate(windows, 1):
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                errors.record(f"{backend}.candidate_discovery", TimeoutError(
                    f"{backend} 窗口筛选超过 {TOP_WINDOW_DISCOVERY_TIMEOUT_SECONDS:.0f} 秒，已停止继续读取"))
                break
            candidate = _bounded_call(
                None, errors, f"{backend}.candidate_{index}",
                lambda window=window, index=index: _candidate_record(window, errors, f"{backend}.candidate_{index}"),
                min(TOP_WINDOW_RECORD_TIMEOUT_SECONDS, remaining),
            )
            if candidate is not None:
                candidates.append((window, candidate))
        except Exception as exc:
            errors.record(f"{backend}.candidate_{index}.skip", exc)
    roots = [(window, record) for window, record in candidates if _matches_u8(record)]
    # The initial reports captured supplier lookups visually but did not add a
    # separate control tree because their title does not contain U8.  Once a
    # genuine U8 root exists, collect only relevant lookup dialogs as well.
    matches = roots + [(window, record) for window, record in candidates
                       if _matches_u8_related_dialog(record) and not _matches_u8(record)] if roots else roots
    if not matches:
        result.identifiers = "未找到标题含 U8、用友或企业应用平台的窗口。\n"
        return result
    sections: list[str] = []
    inspected_handles: set[int] = set()
    for index, (window, _candidate) in enumerate(matches, 1):
        _append_window_inspection(
            result, backend, window, index, errors, sections,
            BACKEND_WINDOW_INSPECTION_TIMEOUT_SECONDS, "matching window",
        )
        handle = _candidate.get("handle")
        if isinstance(handle, int):
            inspected_handles.add(handle)

    # The supplier-reference form seen in the lab screenshots has no title,
    # so a title-only Desktop.windows() filter cannot find it.  Only when the
    # main special-invoice form is disabled (a modal lookup is open) do we
    # examine bounded VB6-form candidates.  This avoids broad desktop scans.
    if _special_invoice_lookup_is_open(result):
        dialog_index = len(matches)
        for window, candidate in candidates:
            candidate_handle = candidate.get("handle")
            if (not _is_legacy_dialog_candidate(candidate)
                    or (isinstance(candidate_handle, int) and candidate_handle in inspected_handles)):
                continue
            detail = _bounded_call(
                None, errors, f"{backend}.legacy_dialog_candidate_{dialog_index + 1}.details",
                lambda window=window, dialog_index=dialog_index: _window_record(
                    window, errors, f"{backend}.legacy_dialog_candidate_{dialog_index + 1}"),
                RELATED_DIALOG_DETAILS_TIMEOUT_SECONDS,
            )
            if detail is None or not _is_visible_legacy_dialog(detail):
                continue
            dialog_index += 1
            _append_window_inspection(
                result, backend, window, dialog_index, errors, sections,
                RELATED_DIALOG_INSPECTION_TIMEOUT_SECONDS, "related legacy dialog",
            )
            if isinstance(candidate_handle, int):
                inspected_handles.add(candidate_handle)
    result.identifiers = "".join(sections)
    return result


def _control_stats(result: BackendResult) -> dict[str, Any]:
    controls = [control for item in result.windows for control in item.get("controls", [])]
    type_counts = Counter(str(control.get("control_type") or "(unknown)") for control in controls)
    class_counts = Counter(str(control.get("class_name") or "(unknown)") for control in controls)
    identifiers = [str(control["automation_id"]) for control in controls if control.get("automation_id")]
    id_counts = Counter(identifiers)
    return {
        "status": result.status, "error": result.error, "control_count": len(controls),
        "control_type_counts": dict(sorted(type_counts.items())),
        "class_name_counts": dict(sorted(class_counts.items())),
        "automation_id": {"non_empty_count": len(identifiers), "unique_count": len(id_counts),
                          "duplicate": {key: count for key, count in sorted(id_counts.items()) if count > 1}},
    }


def _markdown_counts(counts: dict[str, int]) -> list[str]:
    return [f"- `{name}`: {count}" for name, count in counts.items()] or ["- 无"]


def write_summary(output_dir: Path, environment: dict[str, Any], top_windows: list[dict[str, Any]], backend_results: Iterable[BackendResult]) -> None:
    suspected = [record for record in top_windows if _matches_u8(record)]
    lines = ["# U8Assistant Diagnostics Summary", "", "## Environment", "",
             f"- Python: `{environment.get('python_version')}`", f"- Windows: `{environment.get('windows_version')}`",
             f"- Screen resolution: `{environment.get('screen_resolution')}`", f"- DPI scaling: `{environment.get('dpi_scaling')}`",
             f"- Administrator: `{environment.get('administrator')}`", f"- pywinauto: `{environment.get('pywinauto_version')}`", "",
             "## Top-level Windows", "", f"- Detected: **{len(top_windows)}**", f"- Suspected U8: **{len(suspected)}**", ""]
    for index, window in enumerate(suspected, 1):
        lines.extend([f"### Suspected U8 Window {index}", "", f"- title: `{window.get('title')}`", f"- class_name: `{window.get('class_name')}`",
                      f"- handle: `{window.get('handle')}`", f"- rectangle: `{window.get('rectangle')}`", f"- visible: `{window.get('visible')}`", f"- enabled: `{window.get('enabled')}`", ""])
    for result in backend_results:
        stats = _control_stats(result)
        lines.extend([f"## {result.backend} backend", "", f"- Status: **{stats['status']}**", f"- Controls: **{stats['control_count']}**"])
        if stats["error"]:
            lines.append(f"- Error: `{stats['error']}`")
        lines.extend(["", "### By control_type", "", *_markdown_counts(stats["control_type_counts"]), "", "### By class_name", "", *_markdown_counts(stats["class_name_counts"]), "", "### automation_id", "", f"- Non-empty: **{stats['automation_id']['non_empty_count']}**", f"- Unique: **{stats['automation_id']['unique_count']}**", "- Duplicate:"])
        lines.extend(_markdown_counts(stats["automation_id"]["duplicate"]))
        lines.append("")
    (output_dir / "diagnostics_summary.md").write_text("\n".join(lines), encoding="utf-8")


def _capture_screenshots(output_dir: Path, results: Iterable[BackendResult], errors: ErrorRecorder, enabled: bool) -> None:
    error_path = output_dir / "screenshot_error.txt"
    screenshot_dir = output_dir / "screenshots"
    screenshot_dir.mkdir(exist_ok=True)
    if not enabled:
        error_path.write_text("Screenshots skipped because --no-screenshot was supplied.\n", encoding="utf-8")
        return
    roots: list[Any] = []
    seen: set[int] = set()
    for result in results:
        for root in result.screenshot_roots:
            handle = _safe_call(None, errors, "screenshot.handle", lambda: root.handle)
            if handle is not None and handle in seen:
                continue
            if handle is not None:
                seen.add(handle)
            roots.append(root)
    if not roots:
        error_path.write_text("No matching U8 window was found; no screenshot captured.\n", encoding="utf-8")
        return
    try:
        image = roots[0].capture_as_image()
        image.save(output_dir / "u8.png")
        image.save(output_dir / "u8_main.png")
        image.save(screenshot_dir / "u8.png")
        image.save(screenshot_dir / "u8_main.png")
    except Exception as exc:
        errors.record("screenshot.u8_main", exc)
        error_path.write_text(f"u8_main screenshot failed: {exc}\n", encoding="utf-8")
    for index, root in enumerate(roots[1:], 1):
        try:
            image = root.capture_as_image()
            image.save(output_dir / f"u8_dialog_{index:02d}.png")
            image.save(screenshot_dir / f"u8_dialog_{index:02d}.png")
        except Exception as exc:
            errors.record(f"screenshot.dialog_{index:02d}", exc)


ProgressCallback = Callable[[str], None]


def _notify(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        try:
            progress(message)
        except Exception:
            # The GUI must never prevent the evidence collection from completing.
            pass


def _write_json(path: Path, value: Any, errors: ErrorRecorder, context: str) -> None:
    try:
        path.write_text(json.dumps(_json_safe(value), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        errors.record(context, exc)


def _json_safe(value: Any) -> Any:
    """Replace invalid Win32 title surrogates instead of losing an entire report."""
    if isinstance(value, str):
        return value.encode("utf-8", errors="replace").decode("utf-8")
    if isinstance(value, dict):
        return {str(_json_safe(key)): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _write_text(path: Path, value: str, errors: ErrorRecorder, context: str) -> None:
    try:
        path.write_text(value, encoding="utf-8")
    except Exception as exc:
        errors.record(context, exc)


def run_probe(output_base: Path | None = None, label: str | None = None,
              backend: Literal["win32", "uia", "both"] = "both", take_screenshots: bool = True,
              progress: ProgressCallback | None = None) -> Path:
    """Run diagnostics and return the newly created report directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = _safe_label(label)
    directory_name = f"{timestamp}_{suffix}" if suffix else timestamp
    output_dir = _create_output_dir(output_base or _project_root() / "diagnostics", directory_name)
    errors = ErrorRecorder(output_dir / "diagnostics_errors.log")
    _notify(progress, "正在检查电脑环境……")
    environment = _safe_call({}, errors, "environment_snapshot", lambda: environment_snapshot(errors))
    _write_json(output_dir / "environment.json", environment, errors, "write.environment")
    _notify(progress, "正在寻找 U8 企业应用平台……")
    windows, top_error = list_top_windows(errors)
    suspected_count = sum(_matches_u8(record) for record in windows)
    _write_json(output_dir / "windows.json", {"window_count": len(windows), "suspected_u8_window_count": suspected_count, "windows": windows, "error": top_error}, errors, "write.windows")
    if suspected_count:
        _notify(progress, "已找到 U8。")
    _notify(progress, "正在分析当前 U8 页面……")
    selected = ("win32", "uia") if backend == "both" else (backend,)
    results: list[BackendResult] = []
    for name in ("win32", "uia"):
        if name in selected:
            result = _safe_call(BackendResult(name, "failed", f"{name} backend failed but probe continued.\n"), errors, f"{name}.inspection", lambda: inspect_backend(name, errors))
        else:
            result = BackendResult(name, "skipped", f"{name} backend skipped by --backend {backend}.\n")
        results.append(result)
        _write_text(output_dir / f"u8_{name}.txt", result.identifiers, errors, f"write.{name}.txt")
        _write_json(output_dir / f"u8_{name}.json", result.windows, errors, f"write.{name}.json")
    _write_json(output_dir / "interactive_controls.json", [record for result in results for record in result.interactive_controls], errors, "write.interactive_controls")
    _write_json(output_dir / "window_hierarchy.json", [entry for result in results for entry in result.hierarchy], errors, "write.window_hierarchy")
    _bounded_call(None, errors, "capture_screenshots",
                  lambda: _capture_screenshots(output_dir, results, errors, take_screenshots),
                  SCREENSHOT_TIMEOUT_SECONDS)
    _notify(progress, "正在保存诊断结果……")
    _safe_call(None, errors, "write_summary", lambda: write_summary(output_dir, environment, windows, results))
    backend_found = any(result.windows for result in results)
    is_non_admin = environment.get("administrator", {}).get("is_administrator") is False
    outcome = {
        "u8_found": bool(suspected_count or backend_found),
        "possible_permission_mismatch": bool(platform.system() == "Windows" and is_non_admin and not (suspected_count or backend_found)),
        "completed_with_warnings": bool(errors.messages),
    }
    _write_json(output_dir / "probe_outcome.json", outcome, errors, "write.outcome")
    (output_dir / "diagnostics_errors.log").touch(exist_ok=True)
    _notify(progress, "诊断完成。")
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only U8 desktop diagnostics")
    parser.add_argument("--label", help="目录标签，例如 purchase_order")
    parser.add_argument("--backend", choices=("win32", "uia", "both"), default="both", help="默认 both")
    parser.add_argument("--no-screenshot", action="store_true", help="不捕获窗口截图")
    args = parser.parse_args()
    output_dir = run_probe(label=args.label, backend=args.backend, take_screenshots=not args.no_screenshot)
    # Do not print here: the packaged diagnostic GUI is deliberately windowed.
    # The return value remains available to CLI integrations and tests.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
