@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   Pixelle-Video - Windows Launcher
echo ========================================
echo.

:: Set environment variables
set "PYTHON_HOME=%~dp0python\python311"
set "PATH=%PYTHON_HOME%;%PYTHON_HOME%\Scripts;%~dp0tools\ffmpeg\bin;%PATH%"
set "PROJECT_ROOT=%~dp0Pixelle-Video"

:: Change to project directory
cd /d "%PROJECT_ROOT%"

:: Set PYTHONPATH to project root for module imports
set "PYTHONPATH=%PROJECT_ROOT%"

:: Set PIXELLE_VIDEO_ROOT environment variable for reliable path resolution
set "PIXELLE_VIDEO_ROOT=%PROJECT_ROOT%"
set "PIXELLE_VIDEO_RUNTIME_ROOT=%PROJECT_ROOT%\_runtime"
set "TMP=%PIXELLE_VIDEO_RUNTIME_ROOT%\tmp"
set "TEMP=%PIXELLE_VIDEO_RUNTIME_ROOT%\tmp"
set "TMPDIR=%PIXELLE_VIDEO_RUNTIME_ROOT%\tmp"
set "UV_CACHE_DIR=%PIXELLE_VIDEO_RUNTIME_ROOT%\uv-cache"
set "RUFF_CACHE_DIR=%PIXELLE_VIDEO_RUNTIME_ROOT%\ruff-cache"

if not exist "%PIXELLE_VIDEO_RUNTIME_ROOT%" mkdir "%PIXELLE_VIDEO_RUNTIME_ROOT%"
if not exist "%TMP%" mkdir "%TMP%"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%"
if not exist "%RUFF_CACHE_DIR%" mkdir "%RUFF_CACHE_DIR%"
:: Validate configuration, supervise the API, then start the Web UI.
echo [Starting] Launching Pixelle-Video services
echo Browser will open automatically.
echo.
echo Note: Configure API keys and settings in the Web UI.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

"%PYTHON_HOME%\python.exe" -m scripts.launch_web
set "PIXELLE_LAUNCH_EXIT_CODE=!ERRORLEVEL!"

if "!PIXELLE_LAUNCH_EXIT_CODE!"=="130" exit /b 0
if not "!PIXELLE_LAUNCH_EXIT_CODE!"=="0" (
    echo.
    echo [ERROR] Failed to start. Review the launch error above.
    echo.
    pause
)
