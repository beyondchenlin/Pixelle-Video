@echo off
setlocal
pushd "%~dp0\..\.."

REM Create custom_nodes junction if not exists
if not exist "E:\ComfyUIData\pixelle-image\custom_nodes" (
    if exist "E:\ComfyUIData\custom_nodes" (
        mklink /J "E:\ComfyUIData\pixelle-image\custom_nodes" "E:\ComfyUIData\custom_nodes"
    )
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_backend.ps1" -Port 8001 -DataRoot "E:\ComfyUIData\pixelle-image" -RuntimeDir "_runtime\comfyui\image" -LogsDir "logs\comfyui\image" -PythonExe "E:\ComfyUIData\.venv\Scripts\python.exe"
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
