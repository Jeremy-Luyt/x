"""Read-only U8 lab diagnostics with evidence-rich, failure-tolerant reports.

This module never clicks, types, saves, or otherwise changes U8. It only reads
Windows accessibility/window metadata and optionally captures screenshots.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import io
import json
import platform
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable, Iterable, Literal


U8_WORDS = ("u8", "用友", "企业应用平台")
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
}


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


def _rectangle(window: Any, errors: ErrorRecorder, context: str) -> dict[str, int] | None:
    rectangle = _safe_call(None, errors, f"{context}.rectangle", window.rectangle)
    if rectangle is None:
        return None
    return {"left": rectangle.left, "top": rectangle.top, "right": rectangle.right, "bottom": rectangle.bottom}


def _normalise_control_type(raw_type: Any, class_name: Any) -> str | None:
    if isinstance(raw_type, str) and raw_type.strip():
        return raw_type.strip()
    return CLASS_TO_CONTROL_TYPE.get(class_name.casefold()) if isinstance(class_name, str) else None


def _window_record(window: Any, errors: ErrorRecorder, context: str) -> dict[str, Any]:
    element = getattr(window, "element_info", None)
    class_name = _safe_call(getattr(element, "class_name", None), errors, f"{context}.class_name", window.class_name)
    return {
        "title": _safe_call("", errors, f"{context}.title", window.window_text),
        "handle": _safe_call(None, errors, f"{context}.handle", lambda: window.handle),
        "class_name": class_name,
        "control_type": _normalise_control_type(getattr(element, "control_type", None), class_name),
        "automation_id": getattr(element, "automation_id", None),
        "rectangle": _rectangle(window, errors, context),
        "visible": _safe_call(None, errors, f"{context}.visible", window.is_visible),
        "enabled": _safe_call(None, errors, f"{context}.enabled", window.is_enabled),
    }


def _matches_u8(record: dict[str, Any]) -> bool:
    title = str(record.get("title") or "").casefold()
    return any(word in title for word in U8_WORDS)


def _is_interactive(record: dict[str, Any]) -> bool:
    return record.get("control_type") in INTERACTIVE_TYPES


def _node_key(record: dict[str, Any]) -> str:
    if record.get("handle") is not None:
        return f"handle:{record['handle']}"
    return "|".join(str(record.get(key) or "") for key in ("title", "class_name", "automation_id"))


def _parent_and_depth(control: Any, root_key: str, errors: ErrorRecorder, context: str) -> tuple[dict[str, Any] | None, int]:
    parent = _safe_call(None, errors, f"{context}.parent", control.parent)
    if parent is None:
        return None, 0
    direct_parent = _window_record(parent, errors, f"{context}.parent_record")
    depth, cursor, seen = 1, parent, {_node_key(direct_parent)}
    while depth < 30 and _node_key(direct_parent) != root_key:
        next_parent = _safe_call(None, errors, f"{context}.ancestor_{depth}", cursor.parent)
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
        windows = Desktop(backend="win32").windows()
    except Exception as exc:
        errors.record("top_level_windows", exc)
        return [], f"无法列举顶层窗口：{type(exc).__name__}: {exc}"
    return ([_window_record(window, errors, f"top_window_{index}") for index, window in enumerate(windows, 1)], None)


def _inspect_window(backend: str, window: Any, index: int, errors: ErrorRecorder) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[Any], str]:
    root = _window_record(window, errors, f"{backend}.window_{index}")
    hierarchy = [{"backend": backend, "parent": None, "child": root, "depth": 0}]
    controls: list[dict[str, Any]] = []
    dialogs: list[Any] = []
    identifiers = io.StringIO()
    try:
        with contextlib.redirect_stdout(identifiers):
            window.print_control_identifiers()
    except Exception as exc:
        errors.record(f"{backend}.window_{index}.print_control_identifiers", exc)
        identifiers.write(f"print_control_identifiers failed: {type(exc).__name__}: {exc}\n")
    descendants = _safe_call([], errors, f"{backend}.window_{index}.descendants", window.descendants)
    for control_index, control in enumerate(descendants, 1):
        context = f"{backend}.window_{index}.control_{control_index}"
        try:
            record = _window_record(control, errors, context)
            controls.append(record)
            parent, depth = _parent_and_depth(control, _node_key(root), errors, context)
            hierarchy.append({"backend": backend, "parent": parent, "child": record, "depth": depth})
            if _is_obvious_dialog(record, root):
                dialogs.append(control)
        except Exception as exc:
            errors.record(context, exc)
    return ({"window": root, "controls": controls}, hierarchy,
            [record for record in controls if _is_interactive(record)], dialogs, identifiers.getvalue())


def inspect_backend(backend: str, errors: ErrorRecorder) -> BackendResult:
    try:
        from pywinauto import Desktop
        windows = Desktop(backend=backend).windows()
    except Exception as exc:
        errors.record(f"{backend}.desktop", exc)
        return BackendResult(backend, "failed", f"{backend} backend failed but probe continued:\n{type(exc).__name__}: {exc}\n", error=str(exc))
    result = BackendResult(backend, "success", "")
    matches = []
    for index, window in enumerate(windows, 1):
        if _matches_u8(_window_record(window, errors, f"{backend}.candidate_{index}")):
            matches.append(window)
    if not matches:
        result.identifiers = "未找到标题含 U8、用友或企业应用平台的窗口。\n"
        return result
    sections: list[str] = []
    for index, window in enumerate(matches, 1):
        try:
            structured, hierarchy, interactive, dialogs, identifiers = _inspect_window(backend, window, index, errors)
            result.windows.append(structured)
            result.hierarchy.extend(hierarchy)
            result.interactive_controls.extend({"backend": backend, **record} for record in interactive)
            result.screenshot_roots.extend([window, *dialogs])
            sections.append(f"\n=== Matching window {index}: {structured['window']['title']} ===\n{identifiers}")
        except Exception as exc:
            errors.record(f"{backend}.matching_window_{index}", exc)
            sections.append(f"\n=== Matching window {index} failed ===\n{type(exc).__name__}: {exc}\n")
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
    environment = environment_snapshot(errors)
    (output_dir / "environment.json").write_text(json.dumps(environment, ensure_ascii=False, indent=2), encoding="utf-8")
    _notify(progress, "正在寻找 U8 企业应用平台……")
    windows, top_error = list_top_windows(errors)
    suspected_count = sum(_matches_u8(record) for record in windows)
    (output_dir / "windows.json").write_text(json.dumps({"window_count": len(windows), "suspected_u8_window_count": suspected_count, "windows": windows, "error": top_error}, ensure_ascii=False, indent=2), encoding="utf-8")
    if suspected_count:
        _notify(progress, "已找到 U8。")
    _notify(progress, "正在分析当前 U8 页面……")
    selected = ("win32", "uia") if backend == "both" else (backend,)
    results: list[BackendResult] = []
    for name in ("win32", "uia"):
        result = inspect_backend(name, errors) if name in selected else BackendResult(name, "skipped", f"{name} backend skipped by --backend {backend}.\n")
        results.append(result)
        (output_dir / f"u8_{name}.txt").write_text(result.identifiers, encoding="utf-8")
        (output_dir / f"u8_{name}.json").write_text(json.dumps(result.windows, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "interactive_controls.json").write_text(json.dumps([record for result in results for record in result.interactive_controls], ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "window_hierarchy.json").write_text(json.dumps([entry for result in results for entry in result.hierarchy], ensure_ascii=False, indent=2), encoding="utf-8")
    _capture_screenshots(output_dir, results, errors, take_screenshots)
    _notify(progress, "正在保存诊断结果……")
    write_summary(output_dir, environment, windows, results)
    backend_found = any(result.windows for result in results)
    is_non_admin = environment.get("administrator", {}).get("is_administrator") is False
    outcome = {
        "u8_found": bool(suspected_count or backend_found),
        "possible_permission_mismatch": bool(platform.system() == "Windows" and is_non_admin and not (suspected_count or backend_found)),
    }
    (output_dir / "probe_outcome.json").write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "diagnostics_errors.log").touch(exist_ok=True)
    _notify(progress, "诊断完成。")
    print(f"Probe completed: {output_dir}")
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only U8 desktop diagnostics")
    parser.add_argument("--label", help="目录标签，例如 purchase_order")
    parser.add_argument("--backend", choices=("win32", "uia", "both"), default="both", help="默认 both")
    parser.add_argument("--no-screenshot", action="store_true", help="不捕获窗口截图")
    args = parser.parse_args()
    run_probe(label=args.label, backend=args.backend, take_screenshots=not args.no_screenshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
