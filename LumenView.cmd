@echo off
rem Lumen View launcher (script fallback for LumenView.exe)
setlocal
set "ROOT=%~dp0"
set "PYTHONPATH=%ROOT%;%ROOT%.pylibs"

if exist "%ROOT%.venv\Scripts\pythonw.exe" (
    start "" "%ROOT%.venv\Scripts\pythonw.exe" -m lumenview %*
    exit /b
)

if exist "C:\Users\zkang\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe" (
    start "" "C:\Users\zkang\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe" -m lumenview %*
    exit /b
)

py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    start "" pyw -3.12 -m lumenview %*
    exit /b
)

start "" pythonw -m lumenview %*
