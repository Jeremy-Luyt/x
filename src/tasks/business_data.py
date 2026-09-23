"""Conservative task metadata for manual assistance; never infer accounting facts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .models import Task


BusinessCategory = Literal[
    "采购", "销售", "收款", "付款", "库存", "固定资产", "费用", "工资", "税务", "总账", "月末处理", "其他/未知",
]


@dataclass(frozen=True)
class LineItemData:
    inventory_code: str | None = None
    inventory_name: str | None = None
    specification: str | None = None
    unit: str | None = None
    quantity: str | None = None
    unit_price: str | None = None
    amount: str | None = None
    tax_rate: str | None = None
    tax_amount: str | None = None
    tax_inclusive_amount: str | None = None
    order_number: str | None = None


@dataclass(frozen=True)
class TaskBusinessData:
    task_id: str | None
    business_category: BusinessCategory
    document_type: str | None = None
    date: str | None = None
    counterparty: str | None = None
    invoice_number: str | None = None
    system_invoice_number: str | None = None
    currency: str | None = None
    tax_rate: str | None = None
    remarks: str | None = None
    line_items: list[LineItemData] = field(default_factory=list)
    source_pages: list[int] = field(default_factory=list)
    extraction_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChecklistItem:
    key: str
    label: str


@dataclass(frozen=True)
class TaskEntryChecklist:
    task_id: str | None
    category: BusinessCategory
    items: list[ChecklistItem]


def classify_business_category(task: Task) -> BusinessCategory:
    """Classify only for navigation, using explicit words in the bookmark title."""
    text = f"{task.raw_title} {task.title}"
    # Priority avoids calling a month-end closing task a routine purchase merely
    # because its description mentions a material or invoice.
    if any(word in text for word in ("期末", "月末", "年终", "年末")):
        return "月末处理"
    if any(word in text for word in ("增值税", "税收", "城建税", "教育费附加", "个人所得税", "车船税")):
        return "税务"
    if any(word in text for word in ("固定资产", "设备", "折旧", "专利", "无形资产")):
        return "固定资产"
    if any(word in text for word in ("工资", "职工", "社会保险", "住房公积金")):
        return "工资"
    if any(word in text for word in ("采购", "工程物资")):
        return "采购"
    if "销售" in text:
        return "销售"
    if any(word in text for word in ("盘点", "入库", "交库", "库存", "材料盘盈", "材料盘亏")):
        return "库存"
    if any(word in text for word in ("费用", "保险", "房租", "修理费", "广告费", "招待费", "差旅")):
        return "费用"
    if any(word in text for word in ("收到", "收款", "托收", "收账通知")):
        return "收款"
    if any(word in text for word in ("支付", "付", "预付", "借支", "报销")):
        return "付款"
    if any(word in text for word in ("结转", "计提", "利润", "减值", "摊销", "申贷")):
        return "总账"
    return "其他/未知"


CHECKLIST_TEMPLATES: dict[BusinessCategory, list[ChecklistItem]] = {
    "采购": [
        ChecklistItem("view_source", "已查看原始凭证"), ChecklistItem("date", "已填写日期"),
        ChecklistItem("counterparty", "已选择供应商"), ChecklistItem("invoice", "已填写供应商发票号"),
        ChecklistItem("inventory", "已填写存货"), ChecklistItem("quantity", "已填写数量"),
        ChecklistItem("unit_price", "已填写单价"), ChecklistItem("tax", "已核对税额"),
        ChecklistItem("saved", "已保存"),
    ],
    "销售": [
        ChecklistItem("view_source", "已查看原始凭证"), ChecklistItem("date", "已填写日期"),
        ChecklistItem("counterparty", "已选择客户"), ChecklistItem("inventory", "已填写存货"),
        ChecklistItem("quantity", "已填写数量"), ChecklistItem("unit_price", "已填写单价"),
        ChecklistItem("tax", "已核对税额"), ChecklistItem("saved", "已保存"),
    ],
    "收款": [
        ChecklistItem("view_source", "已查看原始凭证"), ChecklistItem("date", "已填写日期"),
        ChecklistItem("counterparty", "已核对往来单位"), ChecklistItem("amount", "已核对金额"),
        ChecklistItem("saved", "已保存"),
    ],
    "付款": [
        ChecklistItem("view_source", "已查看原始凭证"), ChecklistItem("date", "已填写日期"),
        ChecklistItem("counterparty", "已核对往来单位"), ChecklistItem("amount", "已核对金额"),
        ChecklistItem("saved", "已保存"),
    ],
    "库存": [
        ChecklistItem("view_source", "已查看原始凭证"), ChecklistItem("inventory", "已核对存货"),
        ChecklistItem("quantity", "已核对数量"), ChecklistItem("saved", "已保存"),
    ],
    "固定资产": [
        ChecklistItem("view_source", "已查看原始凭证"), ChecklistItem("date", "已填写日期"),
        ChecklistItem("asset", "已核对资产信息"), ChecklistItem("amount", "已核对金额"),
        ChecklistItem("saved", "已保存"),
    ],
    "费用": [
        ChecklistItem("view_source", "已查看原始凭证"), ChecklistItem("date", "已填写日期"),
        ChecklistItem("amount", "已核对金额"), ChecklistItem("saved", "已保存"),
    ],
    "工资": [
        ChecklistItem("view_source", "已查看原始凭证"), ChecklistItem("date", "已填写日期"),
        ChecklistItem("amount", "已核对金额"), ChecklistItem("saved", "已保存"),
    ],
    "税务": [
        ChecklistItem("view_source", "已查看原始凭证"), ChecklistItem("date", "已填写日期"),
        ChecklistItem("tax", "已核对税额"), ChecklistItem("saved", "已保存"),
    ],
    "总账": [
        ChecklistItem("view_source", "已查看原始凭证"), ChecklistItem("amount", "已核对金额"), ChecklistItem("saved", "已保存")],
    "月末处理": [ChecklistItem("view_source", "已查看原始凭证"), ChecklistItem("confirm", "待确认")],
    "其他/未知": [ChecklistItem("view_source", "已查看原始凭证"), ChecklistItem("confirm", "待确认")],
}


def checklist_for_task(task: Task) -> TaskEntryChecklist:
    category = classify_business_category(task)
    return TaskEntryChecklist(task.task_id, category, CHECKLIST_TEMPLATES[category])


def _clean_field(value: str) -> str | None:
    result = value.strip().strip("：:，,。；; ")
    return result if 1 <= len(result) <= 120 else None


def _labelled_value(text: str, labels: tuple[str, ...]) -> str | None:
    """Extract only an explicit same-line label/value pair from native PDF text."""
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[：:]\s*([^\r\n]+)", text)
        if match:
            return _clean_field(match.group(1))
    return None


def extract_task_business_data(task: Task, pdf_path: Path | None) -> TaskBusinessData:
    """Use native embedded PDF text only. Scanned images are intentionally not OCR'd."""
    category = classify_business_category(task)
    notes: list[str] = []
    text_parts: list[str] = []
    if pdf_path is None or not pdf_path.is_file():
        notes.append("未找到原始 PDF，请查看随程序提供的实验资料。")
    else:
        try:
            import fitz
            with fitz.open(pdf_path) as document:
                for page_number in task.source_pages:
                    if 1 <= page_number <= document.page_count:
                        text_parts.append(document.load_page(page_number - 1).get_text("text"))
        except Exception as exc:
            notes.append(f"无法读取 PDF 原生文本：{exc}")
    text = "\n".join(text_parts).strip()
    if not text:
        notes.append("未提取，请查看原始凭证（PDF 页面没有可用的原生文本，未进行 OCR）。")
    counterparty = _labelled_value(text, ("供应商", "供货单位", "客户", "购货单位")) if text else None
    invoice_number = _labelled_value(text, ("供应商发票号", "发票号码", "发票号")) if text else None
    document_type = _labelled_value(text, ("发票类型", "单据类型")) if text else None
    currency = _labelled_value(text, ("币种",)) if text else None
    tax_rate = _labelled_value(text, ("税率",)) if text else None
    if text and not any((counterparty, invoice_number, document_type, currency, tax_rate)):
        notes.append("未找到可可靠识别的标注字段，请查看原始凭证。")
    return TaskBusinessData(
        task_id=task.task_id, business_category=category, document_type=document_type,
        date=task.date, counterparty=counterparty, invoice_number=invoice_number,
        currency=currency, tax_rate=tax_rate, source_pages=list(task.source_pages),
        extraction_notes=notes,
    )


def search_text(task: Task, data: TaskBusinessData | None = None) -> str:
    values = [task.task_id or "", task.raw_title, task.title, task.date or "", *(item.name for item in task.subtasks)]
    if data:
        values.extend(filter(None, [data.business_category, data.document_type, data.counterparty, data.invoice_number]))
        for item in data.line_items:
            values.extend(filter(None, [item.inventory_code, item.inventory_name, item.specification]))
    return " ".join(values).casefold()
