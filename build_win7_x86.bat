@echo off
setlocal

if not "%OS%"=="Windows_NT" (
  echo This build script must be run on Windows.
  exit /b 1
)

echo Checking Python 3.8 x86 build interpreter...
py -3.8-32 -c "import platform, struct, sys; print(sys.version); print(platform.architecture()); print(struct.calcsize('P') * 8)"
if errorlevel 1 exit /b 1
for /f %%B in ('py -3.8-32 -c "import struct; print(struct.calcsize('P') * 8)"') do set POINTER_BITS=%%B
if not "%POINTER_BITS%"=="32" (
  echo ERROR: Python is not 32-bit. Refusing to build a Win7 x86 executable.
  exit /b 1
)

echo Installing locked Win7 x86 binary dependencies...
py -3.8-32 -m pip install --upgrade pip
if errorlevel 1 exit /b 1
py -3.8-32 -m pip install -r requirements-win7-x86.txt
if errorlevel 1 exit /b 1

echo Running tests with Python 3.8 x86...
py -3.8-32 -m unittest discover -s tests -v
if errorlevel 1 exit /b 1

echo Packaging U8Assistant for Windows 7 x86...
py -3.8-32 -m PyInstaller --noconfirm --clean "U8Assistant-Win7-x86.spec"
if errorlevel 1 exit /b 1

echo Packaging read-only diagnostic tool for Windows 7 x86...
py -3.8-32 -m PyInstaller --noconfirm --clean "U8诊断工具-Win7-x86.spec"
if errorlevel 1 exit /b 1

echo.
echo Build complete:
echo   dist\U8Assistant-Win7-x86.exe
echo   dist\U8诊断工具-Win7-x86.exe
endlocal
