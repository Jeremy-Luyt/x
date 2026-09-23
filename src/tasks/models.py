"""Task domain models.  These types deliberately contain no U8 UI details."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class SubTask:
    """A second-level PDF bookmark belonging to a task."""

    name: str
    page: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Task:
    """A task reconstructed from a first-level PDF bookmark."""

    task_id: str | None
    raw_title: str
    date: str | None
    title: str
    start_page: int | None
    end_page: int | None
    subtasks: list[SubTask] = field(default_factory=list)
    source_pages: list[int] = field(default_factory=list)
    kind: Literal["task", "range", "unparsed"] = "task"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "subtasks": [subtask.to_dict() for subtask in self.subtasks],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Task":
        allowed = {
            "task_id", "raw_title", "date", "title", "start_page", "end_page",
            "source_pages", "kind", "warnings",
        }
        fields = {key: value[key] for key in allowed if key in value}
        fields["subtasks"] = [SubTask(**item) for item in value.get("subtasks", [])]
        return cls(**fields)
