@echo off
setlocal
pushd "%~dp0..\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_backend.ps1" %*
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
