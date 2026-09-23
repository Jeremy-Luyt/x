"""Tkinter UI for reading task pages and safely exercising the mock controller."""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from PIL import Image, ImageTk

from ..pdf.page_renderer import PdfPageRenderer
from ..tasks.models import Task
from ..u8.base import ControlTarget
from ..u8.mock import MockU8Controller


class MainWindow:
    def __init__(self, root: tk.Tk, tasks: list[Task], pdf_path: Path, project_root: Path, logger: logging.Logger) -> None:
        self.root = root
        self.tasks = tasks
        self.pdf_path = pdf_path
        self.project_root = project_root
        self.logger = logger
        self.controller = MockU8Controller(logger)
        self.renderer = PdfPageRenderer(pdf_path, project_root / "screenshots" / "pdf_cache")
        self.selected_index = 0
        self.page_index = 0
        self.zoom = 1.0
        self.paused = True
        self.image_ref: ImageTk.PhotoImage | None = None
        self.status_var = tk.StringVar(value="U8 状态：未连接（Mock 模式）")
        self.task_info_var = tk.StringVar()
        self.page_var = tk.StringVar(value="尚未选择任务")
        self._build()
        if tasks:
            self.listbox.selection_set(0)
            self._select_task(0)

    def _build(self) -> None:
        self.root.title("U8Assistant - 业财税实验辅助工具")
        self.root.geometry("1380x850")
        self.root.minsize(1050, 650)
        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(outer, text="任务列表", padding=6)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        self.listbox = tk.Listbox(left, width=30, exportselection=False)
        scrollbar = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.grid(row=0, column=0, sticky="ns")
        scrollbar.grid(row=0, column=1, sticky="ns")
        for task in self.tasks:
            label = f"任务 {task.task_id or '未识别'}"
            if task.kind == "range":
                label += "（范围）"
            self.listbox.insert(tk.END, label)
        self.listbox.bind("<<ListboxSelect>>", self._on_list_selection)

        center = ttk.Frame(outer)
        center.grid(row=0, column=1, sticky="nsew")
        center.columnconfigure(0, weight=1)
        center.rowconfigure(1, weight=1)
        ttk.Label(center, textvariable=self.task_info_var, font=("Microsoft YaHei UI", 13, "bold"), wraplength=700).grid(row=0, column=0, sticky="ew", pady=(0, 5))
        image_box = ttk.Frame(center, relief=tk.SUNKEN)
        image_box.grid(row=1, column=0, sticky="nsew")
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
        page_controls.grid(row=2, column=0, pady=6)
        ttk.Button(page_controls, text="上一页", command=self._previous_page).grid(row=0, column=0, padx=3)
        ttk.Label(page_controls, textvariable=self.page_var).grid(row=0, column=1, padx=8)
        ttk.Button(page_controls, text="下一页", command=self._next_page).grid(row=0, column=2, padx=3)
        ttk.Button(page_controls, text="缩小", command=lambda: self._change_zoom(-0.2)).grid(row=0, column=3, padx=(20, 3))
        ttk.Button(page_controls, text="放大", command=lambda: self._change_zoom(0.2)).grid(row=0, column=4, padx=3)
        task_controls = ttk.Frame(center)
        task_controls.grid(row=3, column=0, pady=(0, 3))
        ttk.Button(task_controls, text="上一任务", command=lambda: self._move_task(-1)).grid(row=0, column=0, padx=4)
        ttk.Button(task_controls, text="下一任务", command=lambda: self._move_task(1)).grid(row=0, column=1, padx=4)

        right = ttk.LabelFrame(outer, text="Automation Panel", padding=8)
        right.grid(row=0, column=2, sticky="nse", padx=(8, 0))
        ttk.Label(right, textvariable=self.status_var, wraplength=230).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        buttons = [
            ("测试连接", self._test_connection), ("探测 U8", self._probe_message),
            ("Dry Run", self._dry_run), ("执行当前步骤", self._execute_step),
            ("暂停", self._pause), ("停止", self._emergency_stop),
        ]
        for row, (label, command) in enumerate(buttons, start=1):
            ttk.Button(right, text=label, command=command).grid(row=row, column=0, sticky="ew", pady=3)
        ttk.Separator(right).grid(row=7, column=0, sticky="ew", pady=10)
        ttk.Label(right, text="安全策略\n• 默认 Dry Run\n• 不会自动 Save\n• 每步后暂停\n• 紧急停止：Ctrl + Alt + Q", justify=tk.LEFT).grid(row=8, column=0, sticky="w")
        self.root.bind_all("<Control-Alt-q>", lambda _: self._emergency_stop())

    def _on_list_selection(self, _: object) -> None:
        selected = self.listbox.curselection()
        if selected:
            self._select_task(selected[0])

    def _select_task(self, index: int) -> None:
        if not self.tasks:
            return
        self.selected_index = max(0, min(index, len(self.tasks) - 1))
        self.page_index = 0
        task = self.tasks[self.selected_index]
        parts = [f"任务编号：{task.task_id or '未识别'}"]
        if task.date:
            parts.append(f"日期：{task.date}")
        if task.title:
            parts.append(f"标题：{task.title}")
        if task.kind == "range":
            parts.append("（任务范围书签，未展开为单项任务）")
        self.task_info_var.set("  |  ".join(parts))
        self._show_current_page()

    def _show_current_page(self) -> None:
        task = self.tasks[self.selected_index]
        if not task.source_pages:
            self.canvas.delete("all")
            self.canvas.create_text(300, 200, text="该任务没有可靠的 PDF 页码。\n请查看 tasks.json 中的 warnings。", fill="white", font=("Microsoft YaHei UI", 14), anchor=tk.CENTER)
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
            self.canvas.create_text(300, 200, text=f"页面渲染失败：{exc}", fill="white", anchor=tk.CENTER)

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

    def _move_task(self, adjustment: int) -> None:
        new_index = self.selected_index + adjustment
        if 0 <= new_index < len(self.tasks):
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(new_index)
            self.listbox.see(new_index)
            self._select_task(new_index)

    def _test_connection(self) -> None:
        def action() -> None:
            self.controller.connect()
            self.status_var.set("U8 状态：已连接（Mock 模式；未连接真实 U8）")
        self._run_automation_safely(action)

    def _probe_message(self) -> None:
        messagebox.showinfo("机房探测", "请在 Windows 机房运行：\npython -m src.u8.probe\n\n结果会保存到 diagnostics/时间戳/。")

    def _dry_run(self) -> None:
        self._run_automation_safely(self._perform_dry_run)
        messagebox.showinfo("Dry Run", "已记录 Mock 动作。未操作真实 U8，也不会保存。")

    def _perform_dry_run(self) -> None:
        task = self.tasks[self.selected_index]
        self.controller.set_text(ControlTarget("date"), task.date or "")

    def _execute_step(self) -> None:
        # This intentionally remains a single mock operation until a probe-backed adapter exists.
        def action() -> None:
            self._perform_dry_run()
            self.paused = True
            self.status_var.set("U8 状态：已暂停（步骤已 Dry Run，等待用户确认）")
        self._run_automation_safely(action)

    def _pause(self) -> None:
        self.paused = True
        self.status_var.set("U8 状态：已暂停")

    def _emergency_stop(self) -> None:
        self.paused = True
        self.controller.disconnect()
        self.status_var.set("U8 状态：已停止（Emergency Stop）")
        self.logger.warning("Emergency Stop triggered")

    def _run_automation_safely(self, action: Callable[[], None]) -> None:
        """Make the mandatory fail-safe rule explicit for future real controllers."""
        try:
            action()
        except Exception as exc:
            self.logger.exception("Automation exception; triggering Emergency Stop")
            self._emergency_stop()
            messagebox.showerror("自动化已停止", f"自动化发生异常，已执行 Emergency Stop：\n{exc}")
