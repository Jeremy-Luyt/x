from __future__ import annotations

import unittest

from src.pdf.bookmark_parser import Bookmark
from src.pdf.task_parser import parse_bookmarks


class TaskParserTests(unittest.TestCase):
    def test_regular_task_uses_next_top_level_page_as_exclusive_boundary(self) -> None:
        tasks = parse_bookmarks([
            Bookmark(1, "任务【17】 12月7日 采购材料，验收入库。（款项原已预付）", 31),
            Bookmark(2, "任务17-1", 31),
            Bookmark(2, "任务17-2", 32),
            Bookmark(1, "任务【18】 12月7日 上交增值税", 34),
        ], page_count=40)
        self.assertEqual(tasks[0].task_id, "17")
        self.assertEqual(tasks[0].date, "12月7日")
        self.assertEqual(tasks[0].title, "采购材料，验收入库。（款项原已预付）")
        self.assertEqual(tasks[0].source_pages, [31, 32, 33])
        self.assertEqual([(item.name, item.page) for item in tasks[0].subtasks], [("任务17-1", 31), ("任务17-2", 32)])

    def test_range_bookmark_is_not_a_regular_task(self) -> None:
        tasks = parse_bookmarks([
            Bookmark(1, "任务【32】—— 任务【35】", 63),
            Bookmark(2, "任务35-1", 64),
            Bookmark(1, "任务【36】 12月11日 支付修理费", 65),
        ], page_count=70)
        self.assertEqual(tasks[0].kind, "range")
        self.assertEqual(tasks[0].task_id, "32-35")
        self.assertEqual(tasks[0].source_pages, [63, 64])

    def test_range_with_task_word_inside_brackets_is_also_a_range(self) -> None:
        tasks = parse_bookmarks([
            Bookmark(1, "【任务55】——【任务68】", 112),
            Bookmark(1, "【任务69】 12月31日 期末存货盘点", 113),
        ], page_count=125)
        self.assertEqual(tasks[0].kind, "range")
        self.assertEqual(tasks[0].task_id, "55-68")

    def test_invalid_top_level_page_is_retained_and_recovered_from_subtask_with_warning(self) -> None:
        tasks = parse_bookmarks([
            Bookmark(1, "【任务77】 12月31日 支付上月电费", -1),
            Bookmark(2, "任务77-1", 119),
            Bookmark(1, "【任务78】 12月31日 计提电费", 120),
        ], page_count=125)
        self.assertEqual(tasks[0].start_page, 119)
        self.assertEqual(tasks[0].source_pages, [119])
        self.assertIn("invalid_top_level_bookmark_page:-1", tasks[0].warnings)
        self.assertIn("used_first_valid_subtask_page_as_start", tasks[0].warnings)

    def test_decreasing_bookmark_page_never_creates_an_invalid_page_range(self) -> None:
        tasks = parse_bookmarks([
            Bookmark(1, "【任务73】 12月31日 计提减值", 117),
            Bookmark(1, "【任务74】 12月31日 处理折旧", 116),
        ], page_count=125)
        self.assertEqual(tasks[0].source_pages, [117])
        self.assertIn("non_increasing_next_task_page:116", tasks[0].warnings)


if __name__ == "__main__":
    unittest.main()
