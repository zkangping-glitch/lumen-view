@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%;%ROOT%.pylibs"
if exist "%ROOT%.venv\Scripts\pythonw.exe" (
    start "" "%ROOT%.venv\Scripts\pythonw.exe" -m lumenview %*
    exit /b
)
if exist "%ROOT%runtime\pythonw.exe" (
    start "" "%ROOT%runtime\pythonw.exe" -m lumenview %*
    exit /b
)
py -3.12 -c "import PySide6, PIL" >nul 2>nul
if errorlevel 1 (
    echo Please install 64-bit Python 3.12, then run: py -3.12 tools\fetch_libs.py
    pause
    exit /b 1
)
start "" pyw -3.12 -m lumenview %*
