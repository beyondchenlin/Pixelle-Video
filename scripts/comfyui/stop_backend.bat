@echo off
setlocal
pushd "%~dp0..\.."
if "%~1"=="" (
  uv run python -m scripts.comfyui.backend_cli stop
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_backend.ps1" %*
)
set "EXIT_CODE=%ERRORLEVEL%"
popd
echo.
if "%EXIT_CODE%"=="0" (
  echo [Pixelle] Command completed successfully.
) else (
  echo [Pixelle] Command failed with exit code %EXIT_CODE%.
)
echo.
pause
exit /b %EXIT_CODE%
