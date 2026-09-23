"""Local, JSON-only user progress for manual U8 task entry."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal


TaskStatus = Literal["未开始", "进行中", "已完成", "需复查"]
VALID_STATUSES: tuple[TaskStatus, ...] = ("未开始", "进行中", "已完成", "需复查")


@dataclass
class TaskProgress:
    status: TaskStatus = "未开始"
    checklist: dict[str, bool] = field(default_factory=dict)


class ProgressRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._items: dict[str, TaskProgress] = {}

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            for task_id, value in payload.get("tasks", {}).items():
                status = value.get("status", "未开始")
                self._items[str(task_id)] = TaskProgress(
                    status=status if status in VALID_STATUSES else "未开始",
                    checklist={str(key): bool(checked) for key, checked in value.get("checklist", {}).items()},
                )
        except (OSError, json.JSONDecodeError):
            # A broken local progress file must not prevent access to the original PDF.
            self._items = {}

    def get(self, task_id: str | None) -> TaskProgress:
        return self._items.setdefault(str(task_id or "unparsed"), TaskProgress())

    def set_status(self, task_id: str | None, status: TaskStatus) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"不支持的任务状态：{status}")
        self.get(task_id).status = status
        self.save()

    def set_checklist_item(self, task_id: str | None, key: str, checked: bool) -> None:
        self.get(task_id).checklist[key] = checked
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "tasks": {task_id: asdict(item) for task_id, item in self._items.items()}}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
