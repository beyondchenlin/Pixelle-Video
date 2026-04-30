# Pixelle ComfyUI Backend Scripts

These scripts run a single Pixelle-managed ComfyUI backend for local `selfhost` workflows.
After the backend starts, the ComfyUI GUI is still available in a browser:

```text
http://127.0.0.1:8000
```

Pixelle generation does not require ComfyUI Desktop to be open. Use ComfyUI Desktop for node installation, model management, and manual debugging; use this managed backend for Pixelle production generation.

## Windows Double-Click Entry Points

Double-clicking `.ps1` files on Windows usually opens an editor or Notepad. That is the default Windows safety behavior, and changing the file association is not recommended.

For double-click usage, run the `.bat` files in this directory:

```text
check_backend.bat
start_backend.bat
stop_backend.bat
```

Double-click `.bat` files to run the matching command instead of opening script source code.

Each `.bat` file calls the matching PowerShell script with:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File ...
```

The window stays open after the command finishes so you can read the output.

## PowerShell Commands

For command-line and automation usage, call the `.ps1` scripts directly:

```powershell
scripts\comfyui\check_backend.ps1
scripts\comfyui\start_backend.ps1
scripts\comfyui\stop_backend.ps1
```

`start_backend.ps1` deliberately avoids `--log-stdout` and `--enable-manager`, and redirects stdout / stderr to:

```text
logs\comfyui\
```

## Defaults

- ComfyUI Python: `E:\ComfyUIData\.venv\Scripts\python.exe`
- ComfyUI root: `E:\comfyui\resources\ComfyUI`
- ComfyUI data root: `E:\ComfyUIData`
- Frontend root: `E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app`
- Database URL: `sqlite:///E:/ComfyUIData/user/comfyui.db`
- Host/port: `127.0.0.1:8000`
- Backend PID file: `_runtime\comfyui\comfyui-backend.pid`
- Launcher PID file: `_runtime\comfyui\comfyui-backend.launcher.pid`

## Overrides

You can override defaults with script parameters or environment variables:

```powershell
$env:PIXELLE_COMFYUI_PYTHON = 'E:\ComfyUIData\.venv\Scripts\python.exe'
$env:PIXELLE_COMFYUI_ROOT = 'E:\comfyui\resources\ComfyUI'
$env:PIXELLE_COMFYUI_DATA_ROOT = 'E:\ComfyUIData'
$env:PIXELLE_COMFYUI_FRONTEND_ROOT = 'E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app'
$env:PIXELLE_COMFYUI_DATABASE_URL = 'sqlite:///E:/ComfyUIData/user/comfyui.db'
$env:PIXELLE_COMFYUI_PORT = '8000'
```

If port `8000` is already occupied by an unmanaged process, `start_backend.ps1` refuses to start another backend instead of drifting to a new port.

`stop_backend.ps1` primarily uses the PID files above. If the PID files are missing but the listener command line still matches the configured ComfyUI root and data root, it can safely stop that matching backend and recreate a clean managed state on the next start. It still refuses to stop unrelated processes on the same port.
