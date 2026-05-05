@echo off
setlocal
pushd "%~dp0..\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_backend.ps1" -Port 8001 -DataRoot "E:\ComfyUIData\pixelle-image" -RuntimeDir "_runtime\comfyui\image" -LogsDir "logs\comfyui\image"
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
