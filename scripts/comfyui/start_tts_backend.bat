@echo off
echo [Pixelle] Deprecated launcher: forwarding to the shared default ComfyUI backend.
call "%~dp0start_backend.bat" %*
exit /b %ERRORLEVEL%
