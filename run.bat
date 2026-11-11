@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ============================================================
REM  Extrapolation Plotter (WinUI3) - launch from source
REM  IMPORTANT: keep this file ASCII-ONLY. cmd.exe parses .bat
REM  with the system ANSI code page (GBK); non-ASCII bytes can be
REM  decoded into & or | and then executed as commands.
REM ============================================================

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual env not found. Recreate with:
    echo   "D:\codeeeee\python\pyhton314\python.exe" -m venv --system-site-packages .venv
    echo   ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo [ERROR] Launch failed. See error.log / xaml_error.log in this folder.
    pause
)
