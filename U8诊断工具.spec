# Build this spec on Windows only. PyInstaller does not cross-compile Windows EXEs from macOS.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


hiddenimports = [
    "pywinauto.application",
    "pywinauto.desktop",
    "pywinauto.findwindows",
    "pywinauto.win32functions",
    "pywinauto.uia_defines",
    "pywinauto.controls",
    "pywinauto.controls.win32_controls",
    "pywinauto.controls.uia_controls",
    "comtypes",
    "comtypes.client",
    "comtypes.gen",
    "PIL.Image",
    "PIL.ImageGrab",
    "win32api",
    "win32con",
    "win32gui",
    "win32process",
    "win32ui",
    "pywintypes",
    "pythoncom",
]
hiddenimports += collect_submodules("pywinauto")
hiddenimports += collect_submodules("comtypes")

a = Analysis(
    ["diagnostic_main.py"],
    pathex=[],
    binaries=[],
    datas=collect_data_files("pywinauto"),
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
    name="U8诊断工具",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
# No COLLECT block is intentional: EXE receives all binaries and data, producing
# PyInstaller's one-file executable. console=False makes it a windowed application.
