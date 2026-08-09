@echo off
chcp 65001 >nul 2>&1
setlocal

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

set "PIXELLE_VIDEO_ROOT=%CD%"
set "PIXELLE_VIDEO_RUNTIME_ROOT=%CD%\_runtime"
set "TMP=%PIXELLE_VIDEO_RUNTIME_ROOT%\tmp"
set "TEMP=%PIXELLE_VIDEO_RUNTIME_ROOT%\tmp"
set "TMPDIR=%PIXELLE_VIDEO_RUNTIME_ROOT%\tmp"
set "UV_CACHE_DIR=%PIXELLE_VIDEO_RUNTIME_ROOT%\uv-cache"
set "RUFF_CACHE_DIR=%PIXELLE_VIDEO_RUNTIME_ROOT%\ruff-cache"

if not exist "%PIXELLE_VIDEO_RUNTIME_ROOT%" mkdir "%PIXELLE_VIDEO_RUNTIME_ROOT%"
if not exist "%TMP%" mkdir "%TMP%"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%"
if not exist "%RUFF_CACHE_DIR%" mkdir "%RUFF_CACHE_DIR%"
if "%PRODUCER_HEADLESS_SHELL_PATH%"=="" if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "PRODUCER_HEADLESS_SHELL_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if "%PRODUCER_HEADLESS_SHELL_PATH%"=="" if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "PRODUCER_HEADLESS_SHELL_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if "%PRODUCER_HEADLESS_SHELL_PATH%"=="" if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "PRODUCER_HEADLESS_SHELL_PATH=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if "%PRODUCER_HEADLESS_SHELL_PATH%"=="" if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "PRODUCER_HEADLESS_SHELL_PATH=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if "%PRODUCER_HEADLESS_SHELL_PATH%"=="" if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "PRODUCER_HEADLESS_SHELL_PATH=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"

if not "%PRODUCER_HEADLESS_SHELL_PATH%"=="" echo Using browser: %PRODUCER_HEADLESS_SHELL_PATH%

echo Starting Pixelle-Video services...
echo.

uv run python -m scripts.launch_web
set "PIXELLE_LAUNCH_EXIT_CODE=%ERRORLEVEL%"

if "%PIXELLE_LAUNCH_EXIT_CODE%"=="130" exit /b 0
if not "%PIXELLE_LAUNCH_EXIT_CODE%"=="0" (
    echo.
    echo ========================================
    echo   [ERROR] Failed to Start
    echo ========================================
    echo.
    echo Review the launch error above. For a source checkout, run "uv sync" first.
    echo.
    pause
)
