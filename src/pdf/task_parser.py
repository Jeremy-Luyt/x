"""Convert native PDF bookmarks into cautious, traceable task records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .bookmark_parser import Bookmark, read_bookmarks
from ..tasks.models import SubTask, Task


# PDFs use both “任务【17】” and “【任务77】”.  A token must contain either
# “任务” or an opening bracket, so a date such as 12月7日 cannot become a task ID.
TASK_PREFIX = r"(?:任务\s*[\[【]?\s*|[\[【]\s*任务\s*|[\[【]\s*)"
TASK_TOKEN = TASK_PREFIX + r"(\d+)\s*[】\]]?"
RANGE_PATTERN = re.compile(TASK_TOKEN + r"\s*[—–-]+\s*" + TASK_TOKEN)
TASK_PATTERN = re.compile(TASK_TOKEN)
DATE_PATTERN = re.compile(r"(\d{1,2})月\s*(\d{1,2})日")


@dataclass
class _Draft:
    bookmark: Bookmark
    task: Task


def _valid_page(page: int, page_count: int) -> bool:
    # PyMuPDF TOC pages are one-based.  Keep API index conversion out of parsing.
    return 1 <= page <= page_count


def _clean_title(raw_title: str, identifier_match: re.Match[str] | None) -> tuple[str | None, str]:
    remainder = raw_title
    if identifier_match:
        remainder = remainder[:identifier_match.start()] + remainder[identifier_match.end():]
    date_match = DATE_PATTERN.search(remainder)
    date = None
    if date_match:
        date = f"{int(date_match.group(1))}月{int(date_match.group(2))}日"
        remainder = remainder[:date_match.start()] + remainder[date_match.end():]
    title = remainder.strip(" \t\r\n，,。．.：:；;、-—–")
    return date, title


def _make_task(bookmark: Bookmark, page_count: int) -> Task:
    raw_title = bookmark.title.strip()
    range_match = RANGE_PATTERN.search(raw_title)
    if range_match:
        task_id = f"{range_match.group(1)}-{range_match.group(2)}"
        date, title = _clean_title(raw_title, range_match)
        kind = "range"
    else:
        task_match = TASK_PATTERN.search(raw_title)
        task_id = task_match.group(1) if task_match else None
        date, title = _clean_title(raw_title, task_match)
        kind = "task" if task_match else "unparsed"

    warnings: list[str] = []
    start_page: int | None = bookmark.page if _valid_page(bookmark.page, page_count) else None
    if start_page is None:
        warnings.append(f"invalid_top_level_bookmark_page:{bookmark.page}")
    if kind == "unparsed":
        warnings.append("could_not_parse_task_identifier")
    return Task(
        task_id=task_id,
        raw_title=raw_title,
        date=date,
        title=title,
        start_page=start_page,
        end_page=None,
        kind=kind,
        warnings=warnings,
    )


def _with_pages(drafts: list[_Draft], page_count: int) -> list[Task]:
    results: list[Task] = []
    for index, draft in enumerate(drafts):
        task = draft.task
        warnings = list(task.warnings)
        start = task.start_page
        # A corrupt top-level page is recoverable only when a direct subtask page exists.
        if start is None:
            valid_children = [s.page for s in task.subtasks if s.page is not None]
            if valid_children:
                start = min(valid_children)
                warnings.append("used_first_valid_subtask_page_as_start")

        following_start = None
        if index + 1 < len(drafts):
            following_start = drafts[index + 1].task.start_page

        if start is None:
            end = None
            source_pages: list[int] = []
        elif following_start is None:
            # Do not make the terminal bookmark claim every remaining PDF page.
            end = start
            source_pages = [start]
            warnings.append("no_reliable_following_task_page")
        elif following_start <= start:
            end = start
            source_pages = [start]
            warnings.append(f"non_increasing_next_task_page:{following_start}")
        else:
            end = following_start - 1
            source_pages = list(range(start, end + 1))

        # Defensive cap: every emitted source page is a PDF's one-based page number.
        source_pages = [page for page in source_pages if _valid_page(page, page_count)]
        results.append(Task(
            task_id=task.task_id,
            raw_title=task.raw_title,
            date=task.date,
            title=task.title,
            start_page=start,
            end_page=end,
            subtasks=task.subtasks,
            source_pages=source_pages,
            kind=task.kind,
            warnings=warnings,
        ))
    return results


def parse_bookmarks(bookmarks: list[Bookmark], page_count: int) -> list[Task]:
    """Parse L1 task headings and their direct L2 children without OCR.

    The next L1 bookmark defines an inclusive page interval.  Invalid or out-of-order
    intervals are deliberately reduced to a safe page and annotated with a warning.
    """
    if page_count < 1:
        raise ValueError("PDF 没有可用页面。")
    drafts: list[_Draft] = []
    for bookmark in bookmarks:
        if bookmark.level == 1:
            drafts.append(_Draft(bookmark=bookmark, task=_make_task(bookmark, page_count)))
        elif bookmark.level == 2 and drafts:
            page = bookmark.page if _valid_page(bookmark.page, page_count) else None
            current = drafts[-1].task
            warnings = list(current.warnings)
            if page is None:
                warnings.append(f"invalid_subtask_bookmark_page:{bookmark.page}")
            drafts[-1].task = Task(
                task_id=current.task_id, raw_title=current.raw_title, date=current.date,
                title=current.title, start_page=current.start_page, end_page=current.end_page,
                subtasks=[*current.subtasks, SubTask(bookmark.title.strip(), page)],
                source_pages=current.source_pages, kind=current.kind, warnings=warnings,
            )
    return _with_pages(drafts, page_count)


def parse_pdf(pdf_path: Path) -> list[Task]:
    page_count, bookmarks = read_bookmarks(pdf_path)
    return parse_bookmarks(bookmarks, page_count)
