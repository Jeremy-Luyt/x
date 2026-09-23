# Build only with 32-bit Python 3.8 on Windows.  PyInstaller cannot cross-compile.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


hiddenimports = [
    "PIL.Image",
    "PIL.ImageTk",
]

datas = [("data/tasks.json", "data")]
rendered_pages = Path("assets") / "rendered_pages"
if not (rendered_pages / "manifest.json").is_file():
    raise SystemExit("Win7 x86 build requires assets/rendered_pages/manifest.json. Run tools/render_pdf_pages.py first.")
for source in rendered_pages.rglob("*"):
    if source.is_file():
        datas.append((str(source), str(source.parent)))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Win7 runtime never imports PyMuPDF: pages were rendered during CI build.
    excludes=["fitz", "pymupdf", "_fitz", "_extra"],
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
    name="U8Assistant-Win7-x86",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
