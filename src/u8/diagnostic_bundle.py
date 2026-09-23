"""User-facing storage and ZIP packaging for read-only diagnostic reports."""

from __future__ import annotations

import ctypes
import os
import re
import zipfile
from pathlib import Path


APP_FOLDER_NAME = "U8Assistant"


def desktop_directory() -> Path:
    """Return the Windows Desktop known folder, with a portable development fallback."""
    if os.name == "nt":
        try:
            buffer = ctypes.create_unicode_buffer(260)
            # CSIDL_DESKTOPDIRECTORY respects redirected / localized Desktop folders.
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buffer) == 0:
                return Path(buffer.value)
        except Exception:
            pass
    return Path.home() / "Desktop"


def diagnostics_data_directory() -> Path:
    """Keep verbose raw reports out of the ordinary user's project folders."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".local" / "share"
    directory = base / APP_FOLDER_NAME / "diagnostics"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _timestamp_from_report_name(report_dir: Path) -> str:
    match = re.match(r"(\d{8}_\d{6})", report_dir.name)
    return match.group(1) if match else "unknown_time"


def _unique_path(directory: Path, filename: str) -> Path:
    target = directory / filename
    index = 1
    while target.exists():
        target = directory / f"{Path(filename).stem}_{index:02d}{Path(filename).suffix}"
        index += 1
    return target


def create_diagnostic_zip(report_dir: Path, destination_dir: Path | None = None) -> Path:
    """Archive one probe directory into a desktop-friendly, self-contained ZIP."""
    if not report_dir.is_dir():
        raise FileNotFoundError(f"诊断结果目录不存在：{report_dir}")
    destination = destination_dir or desktop_directory()
    destination.mkdir(parents=True, exist_ok=True)
    archive_path = _unique_path(destination, f"U8诊断结果_{_timestamp_from_report_name(report_dir)}.zip")
    root_name = report_dir.name
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        # Preserve an explicit screenshot folder even if this run found no U8 window.
        archive.writestr(f"{root_name}/screenshots/", "")
        for source in sorted(report_dir.rglob("*")):
            if source.is_file():
                relative = source.relative_to(report_dir)
                archive.write(source, arcname=f"{root_name}/{relative.as_posix()}")
    return archive_path
