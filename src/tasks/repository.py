"""JSON persistence for parsed tasks; a database is intentionally not used."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Task


def save_tasks(path: Path, tasks: list[Task], source_pdf: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "source_pdf": str(source_pdf),
        "tasks": [task.to_dict() for task in tasks],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_tasks(path: Path) -> list[Task]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"未找到任务数据文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"任务数据文件不是有效 JSON：{path}") from exc
    return [Task.from_dict(item) for item in payload.get("tasks", [])]
