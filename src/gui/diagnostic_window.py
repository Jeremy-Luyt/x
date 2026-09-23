"""Small Chinese GUI that makes the read-only U8 probe usable without a terminal."""

from __future__ import annotations

import json
import logging
import os
import platform
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from ..u8.diagnostic_bundle import create_diagnostic_zip, desktop_directory, diagnostics_data_directory
from ..u8.probe import run_probe


def diagnostic_result_kind(outcome: dict[str, Any]) -> str:
    """Translate technical probe metadata into one of the GUI's safe user states."""
    if outcome.get("u8_found"):
        return "success"
    if outcome.get("possible_permission_mismatch"):
        return "permission"
    return "not_found"


class DiagnosticWindow:
    """One-button front end; all U8 interaction remains observation-only in probe.py."""

    def __init__(self, root: tk.Tk, logger: logging.Logger | None = None) -> None:
        self.root = root
        self.logger = logger or logging.getLogger("u8assistant")
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.archive_path: Path | None = None
        self.status_var = tk.StringVar(value="状态：尚未开始")
        self.message_var = tk.StringVar(value="")
        self._build_initial_view()
        self.root.after(100, self._poll_events)

    def _base_window(self) -> ttk.Frame:
        self.root.title("U8 环境诊断工具")
        self.root.geometry("560x440")
        self.root.minsize(500, 390)
        self.root.resizable(False, False)
        frame = ttk.Frame(self.root, padding=36)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        return frame

    def _clear(self) -> ttk.Frame:
        for child in self.root.winfo_children():
            child.destroy()
        return self._base_window()

    def _build_initial_view(self) -> None:
        frame = self._clear()
        ttk.Label(frame, text="U8 环境诊断工具", font=("Microsoft YaHei UI", 20, "bold")).grid(row=0, column=0, pady=(10, 28))
        ttk.Label(frame, text="使用方法：\n\n1. 打开“U8 企业应用平台”\n2. 进入你需要测试的页面\n3. 点击下面的按钮", justify=tk.LEFT, font=("Microsoft YaHei UI", 12)).grid(row=1, column=0, sticky="w", padx=54)
        self.start_button = ttk.Button(frame, text="开始诊断", command=self._start, width=24)
        self.start_button.grid(row=2, column=0, pady=(34, 22), ipady=8)
        ttk.Label(frame, textvariable=self.status_var, font=("Microsoft YaHei UI", 11)).grid(row=3, column=0)

    def _build_running_view(self) -> None:
        frame = self._clear()
        ttk.Label(frame, text="U8 环境诊断工具", font=("Microsoft YaHei UI", 20, "bold")).grid(row=0, column=0, pady=(38, 35))
        self.progress = ttk.Progressbar(frame, mode="indeterminate", length=350)
        self.progress.grid(row=1, column=0, pady=12)
        self.progress.start(12)
        ttk.Label(frame, textvariable=self.status_var, font=("Microsoft YaHei UI", 13), wraplength=420).grid(row=2, column=0, pady=18)
        ttk.Label(frame, text="请保持 U8 窗口打开，诊断过程中不会修改任何内容。", foreground="#555555", font=("Microsoft YaHei UI", 10)).grid(row=3, column=0, pady=12)

    def _build_success_view(self) -> None:
        frame = self._clear()
        ttk.Label(frame, text="✅ 诊断完成", font=("Microsoft YaHei UI", 21, "bold")).grid(row=0, column=0, pady=(28, 22))
        filename = self.archive_path.name if self.archive_path else "诊断结果.zip"
        ttk.Label(frame, text=f"诊断文件已保存到桌面：\n{filename}", justify=tk.CENTER, font=("Microsoft YaHei UI", 12), wraplength=430).grid(row=1, column=0, pady=10)
        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, pady=(30, 0))
        ttk.Button(buttons, text="打开文件位置", command=self._open_archive_location, width=16).grid(row=0, column=0, padx=5, ipady=5)
        ttk.Button(buttons, text="重新诊断", command=self._reset, width=13).grid(row=0, column=1, padx=5, ipady=5)
        ttk.Button(buttons, text="退出", command=self.root.destroy, width=10).grid(row=0, column=2, padx=5, ipady=5)

    def _build_not_found_view(self, possible_permission_mismatch: bool) -> None:
        frame = self._clear()
        ttk.Label(frame, text="未检测到 U8 企业应用平台。", font=("Microsoft YaHei UI", 18, "bold")).grid(row=0, column=0, pady=(25, 20))
        if possible_permission_mismatch:
            guidance = "检测到权限可能不一致。\n\n请关闭本程序，然后右键：\n“以管理员身份运行”"
        else:
            guidance = "请：\n\n1. 确认 U8 已经打开\n2. 保持 U8 窗口不要关闭\n3. 点击“重新诊断”"
        ttk.Label(frame, text=guidance, justify=tk.LEFT, font=("Microsoft YaHei UI", 12)).grid(row=1, column=0, padx=75, sticky="w")
        ttk.Button(frame, text="重新诊断", command=self._reset, width=18).grid(row=2, column=0, pady=(35, 0), ipady=6)

    def _build_error_view(self) -> None:
        frame = self._clear()
        ttk.Label(frame, text="诊断暂时无法完成。", font=("Microsoft YaHei UI", 18, "bold")).grid(row=0, column=0, pady=(38, 20))
        ttk.Label(frame, text="请确认 U8 已打开后重新诊断。\n如仍无法完成，请联系老师或技术人员。", justify=tk.CENTER, font=("Microsoft YaHei UI", 12)).grid(row=1, column=0, pady=10)
        ttk.Button(frame, text="重新诊断", command=self._reset, width=18).grid(row=2, column=0, pady=(35, 0), ipady=6)

    def _start(self) -> None:
        self.archive_path = None
        self.status_var.set("正在检查电脑环境……")
        self._build_running_view()
        threading.Thread(target=self._run_diagnostics, daemon=True).start()

    def _run_diagnostics(self) -> None:
        try:
            report_dir = run_probe(
                output_base=diagnostics_data_directory(),
                progress=lambda message: self.events.put(("progress", message)),
            )
            outcome = json.loads((report_dir / "probe_outcome.json").read_text(encoding="utf-8"))
            result_kind = diagnostic_result_kind(outcome)
            if result_kind == "success":
                archive = create_diagnostic_zip(report_dir, desktop_directory())
                self.events.put(("success", archive))
            else:
                self.events.put(("not_found", result_kind == "permission"))
        except Exception as exc:
            self.logger.exception("GUI diagnostic failed")
            self.events.put(("error", exc))

    def _poll_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    self.status_var.set(value)
                elif kind == "success":
                    self.archive_path = value
                    self._build_success_view()
                elif kind == "not_found":
                    self._build_not_found_view(value)
                elif kind == "error":
                    self._build_error_view()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _open_archive_location(self) -> None:
        if self.archive_path is None:
            return
        directory = self.archive_path.parent
        try:
            if platform.system() == "Windows":
                os.startfile(str(directory))  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(directory)])
            else:
                subprocess.Popen(["xdg-open", str(directory)])
        except Exception:
            self.logger.exception("Could not open diagnostic archive location")

    def _reset(self) -> None:
        self.status_var.set("状态：尚未开始")
        self._build_initial_view()
