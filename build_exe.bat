@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ASCII-ONLY on purpose. cmd.exe reads .bat as GBK; Chinese bytes can
REM turn into & or | and be executed as commands.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual env not found.
    pause
    exit /b 1
)

echo Building onedir package...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean build_exe.spec
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
if "%EXTRAP_ONEFILE%"=="1" echo Done: dist\ExtrapolationPlotter.exe [single file]
if not "%EXTRAP_ONEFILE%"=="1" echo Done: dist\ExtrapolationPlotter\ExtrapolationPlotter.exe
echo For a single-file build: set EXTRAP_ONEFILE=1 then run this script again.
pause
