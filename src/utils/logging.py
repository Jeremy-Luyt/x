"""Project logging setup."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def configure_logging(project_root: Path) -> logging.Logger:
    log_dir = project_root / "diagnostics"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("u8assistant")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        file_handler = logging.FileHandler(log_dir / "u8assistant.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        # PyInstaller windowed executables can set stdout/stderr to None.
        if sys.stderr is not None:
            stream = logging.StreamHandler()
            stream.setFormatter(formatter)
            logger.addHandler(stream)
    return logger
