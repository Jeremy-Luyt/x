"""Vendor-neutral automation boundary for the future U8 adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ControlTarget:
    """A semantic control reference, never a screen coordinate."""

    name: str
    criteria: dict[str, Any] = field(default_factory=dict)


class U8Controller(ABC):
    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def find_window(self) -> object | None: ...

    @abstractmethod
    def click(self, control: ControlTarget) -> None: ...

    @abstractmethod
    def set_text(self, control: ControlTarget, value: str) -> None: ...

    @abstractmethod
    def select(self, control: ControlTarget, value: str) -> None: ...

    @abstractmethod
    def press_key(self, key: str) -> None: ...

    @abstractmethod
    def wait_for(self, control: ControlTarget, timeout_seconds: float = 10.0) -> bool: ...

    @abstractmethod
    def take_screenshot(self, destination: Path | None = None) -> Path | None: ...

    @abstractmethod
    def save(self) -> None: ...
