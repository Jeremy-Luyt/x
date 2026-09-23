# Build this spec on Windows only. It makes a one-file, windowed U8Assistant.exe.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


hiddenimports = [
    "fitz",
    "PIL.Image",
    "PIL.ImageTk",
]
hiddenimports += collect_submodules("fitz")

datas = [("data/tasks.json", "data")]
pdf_asset = Path("assets") / "业财税2023.pdf"
if pdf_asset.is_file():
    datas.append((str(pdf_asset), "assets"))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas + collect_data_files("fitz"),
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="U8Assistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
