@echo off
setlocal
pushd "%~dp0..\.."
uv run python -m scripts.comfyui.backend_cli stop %* --profile image
set "EXIT_CODE=%ERRORLEVEL%"
popd
echo.
if "%EXIT_CODE%"=="0" (
  echo [Pixelle] image backend command completed successfully.
) else (
  echo [Pixelle] image backend command failed with exit code %EXIT_CODE%.
)
echo.
pause
exit /b %EXIT_CODE%
