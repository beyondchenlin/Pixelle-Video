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
if "%PIXELLE_API_PORT%"=="" set "PIXELLE_API_PORT=8001"
if "%PIXELLE_API_BASE_URL%"=="" set "PIXELLE_API_BASE_URL=http://localhost:%PIXELLE_API_PORT%/api"

echo Starting Pixelle-Video API...
echo.

start "Pixelle-Video API" /min uv run uvicorn api.app:app --host 127.0.0.1 --port %PIXELLE_API_PORT%
timeout /t 2 /nobreak >nul

echo Starting Pixelle-Video Web UI...
echo.

uv run streamlit run web/app.py

if errorlevel 1 (
    echo.
    echo ========================================
    echo   [ERROR] Failed to Start
    echo ========================================
    echo.
    echo It appears you downloaded the SOURCE CODE directly.
    echo.
    echo ========================================
    echo   For Regular Users:
    echo ========================================
    echo Please download the ONE-CLICK PACKAGE from:
    echo https://github.com/AIDC-AI/Pixelle-Video/releases
    echo.
    echo The one-click package includes:
    echo   - Pre-configured Python environment
    echo   - All required dependencies
    echo   - FFmpeg tools
    echo   - Ready to use, no setup needed
    echo.
    echo ========================================
    echo   For Developers:
    echo ========================================
    echo If you intend to develop or modify the code:
    echo   1. Install uv: https://docs.astral.sh/uv/
    echo   2. Run: uv sync
    echo   3. Then run this script again
    echo.
    echo ========================================
    echo.
    pause
)
