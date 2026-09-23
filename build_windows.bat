@echo off
setlocal

if not "%OS%"=="Windows_NT" (
  echo This build script must be run on Windows.
  exit /b 1
)

echo Installing Windows build dependencies...
py -3.11 -m pip install --upgrade pip
if errorlevel 1 exit /b 1
py -3.11 -m pip install -r requirements.txt pyinstaller pywin32 comtypes
if errorlevel 1 exit /b 1

echo Building Windows 10/11 x64 U8 diagnostics executable...
py -3.11 -m PyInstaller --noconfirm --clean "U8诊断工具.spec"
if errorlevel 1 exit /b 1

echo Building Windows 10/11 x64 U8Assistant manual-assistance executable...
py -3.11 -m PyInstaller --noconfirm --clean "U8Assistant.spec"
if errorlevel 1 exit /b 1

echo.
echo Build complete:
echo   dist\U8诊断工具-Win10-x64.exe
echo   dist\U8Assistant-Win10-x64.exe
endlocal
