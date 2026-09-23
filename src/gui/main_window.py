"""Manual-assistance GUI: PDF-first, copy helpers, checklists, and no U8 control."""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from ..pdf.page_renderer import PdfPageRenderer
from ..tasks.business_data import TaskBusinessData, checklist_for_task, extract_task_business_data, search_text
from ..tasks.models import Task
from ..tasks.progress import ProgressRepository, TaskStatus, VALID_STATUSES


MISSING_VALUE = "未提取，请查看原始凭证"
STATUS_ICONS = {"未开始": "○", "进行中": "◐", "已完成": "✓", "需复查": "!"}


class MainWindow:
    """A desktop reader that reduces manual entry without automating U8."""

    def __init__(self, root: tk.Tk, tasks: list[Task], pdf_path: Path | None, project_root: Path, logger: logging.Logger) -> None:
        self.root = root
        self.tasks = tasks
        self.pdf_path = pdf_path
        self.project_root = project_root
        self.logger = logger
        self.renderer = PdfPageRenderer(pdf_path, project_root / "screenshots" / "pdf_cache") if pdf_path else None
        self.progress = ProgressRepository(project_root / "data" / "progress.json")
        self.progress.load()
        self.data_cache: dict[str, TaskBusinessData] = {}
        self.visible_indices = list(range(len(tasks)))
        self.selected_index = 0
        self.page_index = 0
        self.zoom = 1.0
        self.image_ref: ImageTk.PhotoImage | None = None
        self.selected_copy_value: str | None = None
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="状态：尚未开始")
        self.task_info_var = tk.StringVar()
        self.subtasks_var = tk.StringVar()
        self.page_var = tk.StringVar(value="尚未选择任务")
        self.copy_status_var = tk.StringVar(value="点击复制按钮后，可在 U8 中使用 Ctrl+V。")
        self.status_choice = tk.StringVar()
        self.checklist_vars: list[tk.BooleanVar] = []
        self._build()
        if tasks:
            self._select_task(0)

    def _build(self) -> None:
        self.root.title("U8Assistant - 人工辅助模式")
        self.root.geometry("1600x920")
        self.root.minsize(1180, 700)
        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        self._build_task_list(outer)
        self._build_task_viewer(outer)
        self._build_manual_panel(outer)
        self.root.bind_all("<Control-c>", self._copy_selected_value)
        self.root.bind_all("<Control-Right>", lambda _: self._move_task(1))
        self.root.bind_all("<Control-Left>", lambda _: self._move_task(-1))
        self.root.bind_all("<Control-Return>", self._mark_completed)

    def _build_task_list(self, outer: ttk.Frame) -> None:
        left = ttk.LabelFrame(outer, text="任务列表", padding=6)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        ttk.Entry(left, textvariable=self.search_var, width=25).grid(row=0, column=0, sticky="ew")
        ttk.Button(left, text="搜索", command=self._apply_search).grid(row=0, column=1, padx=(4, 0))
        ttk.Button(left, text="跳到下一个未完成任务", command=self._jump_to_next_unfinished).grid(row=1, column=0, columnspan=2, sticky="ew", pady=6)
        self.listbox = tk.Listbox(left, width=31, exportselection=False)
        scrollbar = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.grid(row=2, column=0, sticky="ns")
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.listbox.bind("<<ListboxSelect>>", self._on_list_selection)
        self.search_var.trace_add("write", lambda *_: self._apply_search())
        self._refresh_task_list()

    def _build_task_viewer(self, outer: ttk.Frame) -> None:
        center = ttk.Frame(outer)
        center.grid(row=0, column=1, sticky="nsew")
        center.columnconfigure(0, weight=1)
        center.rowconfigure(2, weight=1)
        ttk.Label(center, textvariable=self.task_info_var, font=("Microsoft YaHei UI", 14, "bold"), wraplength=720).grid(row=0, column=0, sticky="ew", pady=(0, 3))
        ttk.Label(center, textvariable=self.subtasks_var, wraplength=720, foreground="#555555").grid(row=1, column=0, sticky="ew", pady=(0, 6))
        image_box = ttk.Frame(center, relief=tk.SUNKEN)
        image_box.grid(row=2, column=0, sticky="nsew")
        image_box.columnconfigure(0, weight=1)
        image_box.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(image_box, background="#4b5563", highlightthickness=0)
        yscroll = ttk.Scrollbar(image_box, orient=tk.VERTICAL, command=self.canvas.yview)
        xscroll = ttk.Scrollbar(image_box, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        page_controls = ttk.Frame(center)
        page_controls.grid(row=3, column=0, pady=6)
        ttk.Button(page_controls, text="上一页", command=self._previous_page).grid(row=0, column=0, padx=3)
        ttk.Label(page_controls, textvariable=self.page_var).grid(row=0, column=1, padx=8)
        ttk.Button(page_controls, text="下一页", command=self._next_page).grid(row=0, column=2, padx=3)
        ttk.Button(page_controls, text="缩小", command=lambda: self._change_zoom(-0.2)).grid(row=0, column=3, padx=(18, 3))
        ttk.Button(page_controls, text="放大", command=lambda: self._change_zoom(0.2)).grid(row=0, column=4, padx=3)
        task_controls = ttk.Frame(center)
        task_controls.grid(row=4, column=0, pady=(0, 2))
        ttk.Button(task_controls, text="上一任务  Ctrl+←", command=lambda: self._move_task(-1)).grid(row=0, column=0, padx=4)
        ttk.Button(task_controls, text="下一任务  Ctrl+→", command=lambda: self._move_task(1)).grid(row=0, column=1, padx=4)
        ttk.Button(task_controls, text="标记已完成  Ctrl+Enter", command=lambda: self._mark_completed(None)).grid(row=0, column=2, padx=4)

    def _build_manual_panel(self, outer: ttk.Frame) -> None:
        self.right = ttk.Frame(outer, width=365)
        self.right.grid(row=0, column=2, sticky="nse", padx=(8, 0))
        self._refresh_manual_panel()

    def _data_for_task(self, task: Task) -> TaskBusinessData:
        key = task.task_id or task.raw_title
        if key not in self.data_cache:
            self.data_cache[key] = extract_task_business_data(task, self.pdf_path)
        return self.data_cache[key]

    def _refresh_manual_panel(self) -> None:
        for child in self.right.winfo_children():
            child.destroy()
        if not self.tasks:
            return
        task = self.tasks[self.selected_index]
        data = self._data_for_task(task)
        progress = self.progress.get(task.task_id)
        data_box = ttk.LabelFrame(self.right, text="本任务录入数据", padding=8)
        data_box.pack(fill=tk.X, pady=(0, 8))
        self._data_row(data_box, "业务分类", data.business_category, None, 0)
        self._data_row(data_box, "单据类型", data.document_type, None, 1)
        self._data_row(data_box, "日期", data.date, "复制日期", 2)
        party_label = "供应商" if data.business_category == "采购" else "客户" if data.business_category == "销售" else "往来单位"
        self._data_row(data_box, party_label, data.counterparty, f"复制{party_label}", 3)
        self._data_row(data_box, "发票号", data.invoice_number, "复制发票号", 4)
        self._data_row(data_box, "税率", data.tax_rate, None, 5)
        self._data_row(data_box, "币种", data.currency, None, 6)
        ttk.Label(data_box, text="明细", font=("Microsoft YaHei UI", 10, "bold")).grid(row=7, column=0, sticky="w", pady=(8, 2))
        details = ttk.Treeview(data_box, columns=("inventory", "quantity", "price", "amount"), show="headings", height=3)
        for column, label, width in (("inventory", "存货", 112), ("quantity", "数量", 55), ("price", "单价", 65), ("amount", "金额", 65)):
            details.heading(column, text=label)
            details.column(column, width=width, anchor=tk.W)
        if data.line_items:
            for line in data.line_items:
                details.insert("", tk.END, values=(line.inventory_name or MISSING_VALUE, line.quantity or MISSING_VALUE, line.unit_price or MISSING_VALUE, line.amount or MISSING_VALUE))
        else:
            details.insert("", tk.END, values=(MISSING_VALUE, MISSING_VALUE, MISSING_VALUE, MISSING_VALUE))
        details.grid(row=8, column=0, columnspan=2, sticky="ew")
        copies = ttk.Frame(data_box)
        copies.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        self._copy_button(copies, "复制数量", data.line_items[0].quantity if data.line_items else None, 0)
        self._copy_button(copies, "复制单价", data.line_items[0].unit_price if data.line_items else None, 1)
        self._copy_button(copies, "复制金额", data.line_items[0].amount if data.line_items else None, 2)
        ttk.Label(data_box, textvariable=self.copy_status_var, foreground="#555555", wraplength=325).grid(row=10, column=0, columnspan=2, sticky="w", pady=(6, 0))
        for note in data.extraction_notes:
            ttk.Label(data_box, text=note, foreground="#8a4b00", wraplength=325).grid(row=11, column=0, columnspan=2, sticky="w", pady=(4, 0))

        checklist_box = ttk.LabelFrame(self.right, text="录入清单", padding=8)
        checklist_box.pack(fill=tk.X, pady=(0, 8))
        self.checklist_vars = []
        checklist = checklist_for_task(task)
        for row, item in enumerate(checklist.items):
            variable = tk.BooleanVar(value=progress.checklist.get(item.key, False))
            self.checklist_vars.append(variable)
            ttk.Checkbutton(checklist_box, text=item.label, variable=variable, command=lambda key=item.key, var=variable: self._set_checklist_item(key, var.get())).grid(row=row, column=0, sticky="w")

        status_box = ttk.LabelFrame(self.right, text="完成状态", padding=8)
        status_box.pack(fill=tk.X, pady=(0, 8))
        self.status_choice.set(progress.status)
        selector = ttk.Combobox(status_box, textvariable=self.status_choice, values=VALID_STATUSES, state="readonly", width=12)
        selector.grid(row=0, column=0, sticky="w")
        selector.bind("<<ComboboxSelected>>", lambda _: self._set_status(self.status_choice.get()))
        ttk.Label(status_box, text="状态会自动保存。", foreground="#555555").grid(row=1, column=0, sticky="w", pady=(4, 0))

        automation_box = ttk.LabelFrame(self.right, text="U8 自动化", padding=8)
        automation_box.pack(fill=tk.X)
        ttk.Label(automation_box, text="尚未配置", foreground="#8a4b00").grid(row=0, column=0, sticky="w")
        ttk.Button(automation_box, text="检测 U8", command=self._show_manual_mode_message).grid(row=1, column=0, sticky="w", pady=(5, 0))

    def _data_row(self, parent: ttk.Frame, label: str, value: str | None, copy_label: str | None, row: int) -> None:
        ttk.Label(parent, text=f"{label}：").grid(row=row, column=0, sticky="nw", pady=2)
        ttk.Label(parent, text=value or MISSING_VALUE, wraplength=195).grid(row=row, column=1, sticky="nw", pady=2)
        if copy_label:
            button = ttk.Button(parent, text=copy_label, command=lambda: self._copy_value(copy_label, value), width=11)
            if not value:
                button.state(["disabled"])
            button.grid(row=row, column=2, padx=(5, 0), pady=2)

    def _copy_button(self, parent: ttk.Frame, label: str, value: str | None, column: int) -> None:
        button = ttk.Button(parent, text=label, command=lambda: self._copy_value(label, value), width=10)
        if not value:
            button.state(["disabled"])
        button.grid(row=0, column=column, padx=2)

    def _copy_value(self, label: str, value: str | None) -> None:
        if not value:
            return
        self.selected_copy_value = value
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()
        self.copy_status_var.set(f"已复制{label.replace('复制', '')}。切换到 U8 后按 Ctrl+V。")

    def _copy_selected_value(self, _: object) -> str:
        if self.selected_copy_value:
            self._copy_value("当前选中值", self.selected_copy_value)
        else:
            self.copy_status_var.set("请先点击一个可用的复制按钮。")
        return "break"

    def _apply_search(self) -> None:
        query = self.search_var.get().strip().casefold()
        self.visible_indices = [index for index, task in enumerate(self.tasks) if not query or query in search_text(task, self.data_cache.get(task.task_id or task.raw_title))]
        self._refresh_task_list()

    def _refresh_task_list(self) -> None:
        if not hasattr(self, "listbox"):
            return
        self.listbox.delete(0, tk.END)
        for index in self.visible_indices:
            task = self.tasks[index]
            status = self.progress.get(task.task_id).status
            self.listbox.insert(tk.END, f"{STATUS_ICONS[status]} 任务 {task.task_id or '未识别'} · {task.title[:18]}")
        if self.selected_index in self.visible_indices:
            position = self.visible_indices.index(self.selected_index)
            self.listbox.selection_set(position)
            self.listbox.see(position)

    def _on_list_selection(self, _: object) -> None:
        selected = self.listbox.curselection()
        if selected:
            self._select_task(self.visible_indices[selected[0]])

    def _select_task(self, index: int) -> None:
        if not self.tasks:
            return
        self.selected_index = max(0, min(index, len(self.tasks) - 1))
        self.page_index = 0
        self.selected_copy_value = None
        task = self.tasks[self.selected_index]
        data = self._data_for_task(task)
        self.task_info_var.set(f"任务编号：{task.task_id or '未识别'}  |  日期：{task.date or MISSING_VALUE}  |  分类：{data.business_category}\n任务标题：{task.title or task.raw_title}")
        subtask_text = "、".join(f"{item.name}（PDF 第 {item.page} 页）" if item.page else item.name for item in task.subtasks)
        pages = "、".join(str(page) for page in task.source_pages) or "未提取"
        self.subtasks_var.set(f"子任务：{subtask_text or '无'}\nPDF 对应页：{pages}")
        self._show_current_page()
        self._refresh_manual_panel()
        self._refresh_task_list()

    def _show_current_page(self) -> None:
        task = self.tasks[self.selected_index]
        if self.renderer is None:
            self.canvas.delete("all")
            self.canvas.create_text(300, 200, text="未找到原始 PDF。\n请使用包含实验 PDF 的完整 U8Assistant 包。", fill="white", font=("Microsoft YaHei UI", 14), anchor=tk.CENTER)
            self.page_var.set("原始 PDF 不可用")
            return
        if not task.source_pages:
            self.canvas.delete("all")
            self.canvas.create_text(300, 200, text="该任务没有可靠的 PDF 页码。\n请查看原始任务书签。", fill="white", font=("Microsoft YaHei UI", 14), anchor=tk.CENTER)
            self.page_var.set("无可靠页面")
            return
        page = task.source_pages[self.page_index]
        try:
            image_path = self.renderer.render_page(page, self.zoom)
            with Image.open(image_path) as image:
                self.image_ref = ImageTk.PhotoImage(image.copy())
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.image_ref)
            self.canvas.configure(scrollregion=(0, 0, self.image_ref.width(), self.image_ref.height()))
            self.page_var.set(f"PDF 第 {page} 页（任务内 {self.page_index + 1}/{len(task.source_pages)}，{self.zoom:.1f}x）")
        except Exception as exc:
            self.logger.exception("PDF rendering failed")
            self.canvas.delete("all")
            self.canvas.create_text(300, 200, text="页面渲染失败。请确认原始 PDF 文件仍在原位置。", fill="white", anchor=tk.CENTER)

    def _previous_page(self) -> None:
        if self.page_index > 0:
            self.page_index -= 1
            self._show_current_page()

    def _next_page(self) -> None:
        task = self.tasks[self.selected_index]
        if self.page_index < len(task.source_pages) - 1:
            self.page_index += 1
            self._show_current_page()

    def _change_zoom(self, adjustment: float) -> None:
        self.zoom = max(0.5, min(3.0, round(self.zoom + adjustment, 1)))
        self._show_current_page()

    def _move_task(self, adjustment: int) -> str:
        try:
            position = self.visible_indices.index(self.selected_index)
        except ValueError:
            position = 0
        new_position = position + adjustment
        if 0 <= new_position < len(self.visible_indices):
            self._select_task(self.visible_indices[new_position])
        return "break"

    def _jump_to_next_unfinished(self) -> None:
        if not self.tasks:
            return
        for offset in range(1, len(self.tasks) + 1):
            index = (self.selected_index + offset) % len(self.tasks)
            if self.progress.get(self.tasks[index].task_id).status != "已完成":
                self.search_var.set("")
                self._select_task(index)
                return
        messagebox.showinfo("任务完成", "所有任务都已标记为已完成。")

    def _set_status(self, status: str) -> None:
        self.progress.set_status(self.tasks[self.selected_index].task_id, status)  # type: ignore[arg-type]
        self.status_var.set(f"状态：{status}（已自动保存）")
        self._refresh_task_list()

    def _set_checklist_item(self, key: str, checked: bool) -> None:
        self.progress.set_checklist_item(self.tasks[self.selected_index].task_id, key, checked)
        self.status_var.set("清单已自动保存")

    def _mark_completed(self, _: object | None) -> str:
        self._set_status("已完成")
        self.status_choice.set("已完成")
        return "break"

    def _show_manual_mode_message(self) -> None:
        messagebox.showinfo("人工辅助模式", "当前仅支持人工辅助模式。\n\n请使用 PDF 页面、复制按钮和录入清单完成手工录入。\n不会自动操作 U8。")
