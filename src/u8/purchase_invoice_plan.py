"""Safe, data-driven execution plan for a special purchase invoice.

Plans are intentionally separate from pywinauto.  A plan can be previewed on
macOS and only becomes a live operation after the Windows adapter verifies the
page and the operator confirms each proposed field.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..tasks.business_data import TaskBusinessData


@dataclass(frozen=True)
class InvoiceStep:
    field: str
    label: str
    value: str | None
    ready: bool
    reason: str


@dataclass(frozen=True)
class PurchaseInvoicePlan:
    task_id: str | None
    supported: bool
    steps: tuple[InvoiceStep, ...]
    manual_items: tuple[str, ...]

    def preview_lines(self) -> list[str]:
        lines = ["专用采购发票 · 自动录入预览"]
        for step in self.steps:
            if step.ready:
                lines.append(f"待确认：{step.label} → {step.value}")
            else:
                lines.append(f"手工处理：{step.label}（{step.reason}）")
        lines.extend(f"手工处理：{item}" for item in self.manual_items)
        lines.append("不会自动保存、审核、记账或结账。")
        return lines


def _step(field: str, label: str, value: str | None) -> InvoiceStep:
    return InvoiceStep(field, label, value, bool(value), "原始凭证未可靠提取" if not value else "")


def build_special_purchase_invoice_plan(data: TaskBusinessData) -> PurchaseInvoicePlan:
    """Plan only explicitly extracted facts; never manufacture accounting data."""
    supported = data.business_category == "采购"
    if not supported:
        return PurchaseInvoicePlan(data.task_id, False, (), ("当前任务不是采购业务，未生成专用发票计划。",))
    steps = (
        _step("invoice_date", "开票日期", data.date),
        _step("supplier", "供应商", data.counterparty),
        _step("supplier_invoice_number", "供应商发票号", data.invoice_number),
        _step("tax_rate", "税率", data.tax_rate),
        _step("currency", "币种", data.currency),
    )
    manual = ["核对业务类型、发票类型、采购类型、部门、汇率。"]
    if data.line_items:
        manual.append("明细表格的存货、数量、单价和税额须逐行确认。")
    else:
        manual.append("明细表格未可靠提取，请查看原始凭证后录入。")
    return PurchaseInvoicePlan(data.task_id, True, steps, tuple(manual))
