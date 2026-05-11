@echo off
setlocal

cd /d "%~dp0prady-trader"

if not exist "venv\Scripts\python.exe" (
    echo Python environment not found at "%CD%\venv\Scripts\python.exe".
    pause
    exit /b 1
)

set "PYTHON_GUI=venv\Scripts\pythonw.exe"
if not exist "%PYTHON_GUI%" set "PYTHON_GUI=venv\Scripts\python.exe"

start "PRADY TRADER" "%PYTHON_GUI%" "run_desktop.py"
exit /b 0
