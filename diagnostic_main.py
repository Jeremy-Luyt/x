"""Entry point used by the Windows-only U8 diagnostics executable."""

from __future__ import annotations

import tkinter as tk

from src.gui.diagnostic_window import DiagnosticWindow
from src.u8.diagnostic_bundle import diagnostics_data_directory
from src.utils.logging import configure_logging


def main() -> int:
    root = tk.Tk()
    # In a one-file EXE, __file__ is a temporary extraction directory. Logs belong
    # in user-writable app data alongside the raw diagnostic reports instead.
    DiagnosticWindow(root, configure_logging(diagnostics_data_directory().parent))
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
