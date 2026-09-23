"""Future Windows implementation with no U8-specific selectors or coordinates."""

from __future__ import annotations

import platform
from pathlib import Path

from .base import ControlTarget, U8Controller


class PyWinAutoU8Controller(U8Controller):
    """Generic bridge. Build semantic selector maps only after probe evidence exists."""

    def __init__(self, backend: str = "uia") -> None:
        if backend not in {"uia", "win32"}:
            raise ValueError("backend 必须是 'uia' 或 'win32'。")
        self.backend = backend
        self._app = None
        self._window = None

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
        # Probe is the source of actual title / selector conditions; never guess here.
        candidates = [window for window in Desktop(backend=self.backend).windows()
                      if any(word in window.window_text() for word in ("U8", "用友", "企业应用平台"))]
        if not candidates:
            return False
        self._window = candidates[0]
        return True

    def disconnect(self) -> None:
        self._window = None

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
