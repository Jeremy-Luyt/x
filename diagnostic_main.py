"""Entry point used by the Windows-only U8 diagnostics executable."""

from __future__ import annotations

from src.utils.startup import configure_startup_logging


def main() -> int:
    startup_logger = configure_startup_logging("U8诊断工具")
    try:
        startup_logger.info("stage: importing diagnostic GUI modules")
        import tkinter as tk

        from src.gui.diagnostic_window import DiagnosticWindow
        from src.u8.diagnostic_bundle import diagnostics_data_directory
        from src.utils.logging import configure_logging

        startup_logger.info("stage: initializing Tkinter GUI")
        root = tk.Tk()
        # In a one-file EXE, __file__ is a temporary extraction directory. Logs
        # belong in user-writable app data alongside the raw diagnostic reports.
        DiagnosticWindow(root, configure_logging(diagnostics_data_directory().parent))
        startup_logger.info("stage: GUI ready")
        root.mainloop()
        return 0
    except Exception:
        startup_logger.exception("Diagnostic GUI startup failed")
        try:
            from tkinter import messagebox
            messagebox.showerror("U8 环境诊断工具", "程序暂时无法启动。请联系老师或技术人员，并提供 startup.log。")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
