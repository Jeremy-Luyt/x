# Optional bundled PDF asset

To make `U8Assistant.exe` fully offline, a developer may place the authorized
`业财税2023.pdf` file in this folder before building on Windows. The PyInstaller
spec will then include it inside the EXE. Do not commit or upload the PDF unless
you have permission to distribute the teaching material.

Without this asset, `U8Assistant.exe` still provides its task list, category,
checklist, progress and manual-assistance UI, but it cannot display PDF pages.
