# Pixelle ComfyUI Backend Scripts

These scripts run a single Pixelle-managed ComfyUI backend for self-hosted workflows.
The backend is still viewable in a browser at `http://127.0.0.1:8000`; ComfyUI Desktop
is not required for Pixelle generation.

## Commands

```powershell
scripts\comfyui\check_backend.ps1
scripts\comfyui\start_backend.ps1
scripts\comfyui\stop_backend.ps1
```

The start script deliberately does not pass `--log-stdout` or `--enable-manager`.
Stdout and stderr are redirected to `logs\comfyui\`.

## Defaults

- ComfyUI Python: `E:\ComfyUIData\.venv\Scripts\python.exe`
- ComfyUI root: `E:\comfyui\resources\ComfyUI`
- ComfyUI data root: `E:\ComfyUIData`
- Host/port: `127.0.0.1:8000`
- PID file: `_runtime\comfyui\comfyui-backend.pid`
- Launcher PID file: `_runtime\comfyui\comfyui-backend.launcher.pid`

Override defaults with script parameters or these environment variables:

```powershell
$env:PIXELLE_COMFYUI_PYTHON = 'E:\ComfyUIData\.venv\Scripts\python.exe'
$env:PIXELLE_COMFYUI_ROOT = 'E:\comfyui\resources\ComfyUI'
$env:PIXELLE_COMFYUI_DATA_ROOT = 'E:\ComfyUIData'
$env:PIXELLE_COMFYUI_FRONTEND_ROOT = 'E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app'
$env:PIXELLE_COMFYUI_DATABASE_URL = 'sqlite:///E:/ComfyUIData/user/comfyui.db'
$env:PIXELLE_COMFYUI_PORT = '8000'
```

If port `8000` is already occupied by an unmanaged process, `start_backend.ps1`
refuses to start another backend instead of drifting to a new port.
