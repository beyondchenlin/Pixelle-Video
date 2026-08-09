@echo off
chcp 65001 >nul 2>&1
setlocal

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

uv run python -m scripts.launch_web
set "EXIT_CODE=%ERRORLEVEL%"

if "%EXIT_CODE%"=="130" exit /b 0
if not "%EXIT_CODE%"=="0" (
    echo.
    echo ========================================
    echo   [ERROR] Failed to Start
    echo ========================================
    echo.
    echo Review the launch error above. For a source checkout, run "uv sync" first.
    echo.
    pause
)

exit /b %EXIT_CODE%
