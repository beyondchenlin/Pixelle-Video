@echo off
setlocal
pushd "%~dp0..\.."
uv run python -m scripts.comfyui.backend_cli start %* --profile tts
set "EXIT_CODE=%ERRORLEVEL%"
popd
echo.
if "%EXIT_CODE%"=="0" (
  echo [Pixelle] tts backend command completed successfully.
) else (
  echo [Pixelle] tts backend command failed with exit code %EXIT_CODE%.
)
echo.
pause
exit /b %EXIT_CODE%
