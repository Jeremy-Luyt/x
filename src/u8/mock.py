"""Safe default controller: records intent but never interacts with U8."""

from __future__ import annotations

import logging
from pathlib import Path

from .base import ControlTarget, U8Controller


class MockU8Controller(U8Controller):
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("u8assistant")
        self.connected = False
        self.actions: list[str] = []

    def _record(self, action: str, **details: object) -> None:
        lines = ["[DRY RUN]", action, *(f"{key}={value}" for key, value in details.items())]
        message = "\n".join(lines)
        self.actions.append(message)
        self.logger.info(message)

    def connect(self) -> bool:
        self.connected = True
        self._record("connect", backend="mock")
        return True

    def disconnect(self) -> None:
        self.connected = False
        self._record("disconnect")

    def find_window(self) -> object | None:
        self._record("find_window")
        return None

    def click(self, control: ControlTarget) -> None:
        self._record("click", control=control.name)

    def set_text(self, control: ControlTarget, value: str) -> None:
        self._record("set_text", field=control.name, value=value)

    def select(self, control: ControlTarget, value: str) -> None:
        self._record("select", field=control.name, value=value)

    def press_key(self, key: str) -> None:
        self._record("press_key", key=key)

    def wait_for(self, control: ControlTarget, timeout_seconds: float = 10.0) -> bool:
        self._record("wait_for", control=control.name, timeout_seconds=timeout_seconds)
        return True

    def take_screenshot(self, destination: Path | None = None) -> Path | None:
        self._record("take_screenshot", destination=destination or "(none)")
        return None

    def save(self) -> None:
        # No mock action can cause saving; calling this only documents future intent.
        self._record("save", permitted=False)
