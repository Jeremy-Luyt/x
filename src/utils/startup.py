"""Early, failure-tolerant startup logging for packaged Windows programs."""

from __future__ import annotations

import logging
import os
import platform
import struct
import sys
import tempfile
from pathlib import Path


def startup_data_directory(application_name: str) -> Path:
    """Return a writable, Windows 7-compatible location before a GUI exists."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".local" / "share"
    candidates = (base / application_name, Path(tempfile.gettempdir()) / application_name)
    last_error: OSError | None = None
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError as exc:
            last_error = exc
    raise OSError("无法创建启动日志目录") from last_error


def configure_startup_logging(application_name: str) -> logging.Logger:
    """Create ``startup.log`` immediately and record runtime facts for support."""
    logger = logging.getLogger("u8assistant.startup." + application_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        log_path = startup_data_directory(application_name) / "startup.log"
        handler = logging.FileHandler(str(log_path), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
        logger.addHandler(handler)
        logger.info("startup.log created: %s", log_path)
    logger.info("stage: process entry")
    logger.info("os: %s", platform.platform())
    logger.info("architecture: %s; pointer_bits: %s", platform.architecture(), struct.calcsize("P") * 8)
    logger.info("bundled_python: %s", sys.version.replace("\n", " "))
    logger.info("executable_path: %s", sys.executable)
    logger.info("frozen: %s", bool(getattr(sys, "frozen", False)))
    return logger
