from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.tasks.business_data import _labelled_value, checklist_for_task, classify_business_category
from src.tasks.models import Task
from src.tasks.progress import ProgressRepository


def task_with_title(title: str, task_id: str = "1") -> Task:
    return Task(task_id=task_id, raw_title=title, date="12月7日", title=title, start_page=1, end_page=1)


class BusinessDataTests(unittest.TestCase):
    def test_classification_is_bookmark_based_and_conservative(self) -> None:
        self.assertEqual(classify_business_category(task_with_title("采购材料，验收入库")), "采购")
        self.assertEqual(classify_business_category(task_with_title("支付本厂车队修理费")), "费用")
        self.assertEqual(classify_business_category(task_with_title("期末存货盘点")), "月末处理")
        self.assertEqual(classify_business_category(task_with_title("未说明的事项")), "其他/未知")

    def test_purchase_checklist_has_no_automatic_audit_step(self) -> None:
        checklist = checklist_for_task(task_with_title("采购材料"))
        labels = [item.label for item in checklist.items]
        self.assertIn("已选择供应商", labels)
        self.assertNotIn("已审核", labels)

    def test_only_explicit_native_text_labels_are_extracted(self) -> None:
        text = "供应商：湖南新风机械股份有限公司\n供应商发票号：FP-2023-17"
        self.assertEqual(_labelled_value(text, ("供应商",)), "湖南新风机械股份有限公司")
        self.assertEqual(_labelled_value(text, ("供应商发票号",)), "FP-2023-17")
        self.assertIsNone(_labelled_value("页面没有字段标签", ("供应商",)))

    def test_progress_persists_status_and_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "progress.json"
            repository = ProgressRepository(path)
            repository.set_status("17", "进行中")
            repository.set_checklist_item("17", "date", True)
            reloaded = ProgressRepository(path)
            reloaded.load()
            self.assertEqual(reloaded.get("17").status, "进行中")
            self.assertTrue(reloaded.get("17").checklist["date"])


if __name__ == "__main__":
    unittest.main()
