# Pixelle ComfyUI Backend Scripts

Pixelle defaults to externally managed Desktop mode: the user opens ComfyUI Desktop,
then tests the connection in Pixelle settings. In this mode Pixelle never starts,
hides, stops, or restarts the Desktop process, so its window, queue, and outputs remain
visible.

The scripts in this directory are only for an explicit headless-management deployment.
They run one Pixelle-owned background process for local `selfhost` workflows. They do
not create a ComfyUI Desktop window, although the browser UI remains available:

```text
http://127.0.0.1:8000
```

## Lifecycle Modes

- Recommended Desktop mode: `backend_management_mode: disabled` and
  `restart_after_batch: false`. Open Desktop first; Pixelle only probes and submits.
  Disabled mode overrides each profile's `managed` value, so the Desktop process is
  never started, stopped, or restarted by Pixelle.
- Advanced headless mode: set `backend_management_mode` to `auto` or `required` and
  explicitly set `managed: true`. Only this mode uses the start, stop, and restart scripts.

A hidden backend and ComfyUI Desktop are different application forms. Removing the
hidden-window flag only exposes a console; it does not turn the process into Desktop.

## Windows Double-Click Entry Points

Double-clicking `.ps1` files on Windows usually opens an editor or Notepad. That is the default Windows safety behavior, and changing the file association is not recommended.

For double-click usage, run the `.bat` files in this directory:

```text
check_backend.bat
start_backend.bat
stop_backend.bat
```

Double-click `.bat` files to run the matching command instead of opening script source code.

With no arguments, each `.bat` file reads `comfyui.backends.default` from the repository `config.yaml` and invokes the unified lifecycle manager. Equivalent commands are:

```powershell
uv run python -m scripts.comfyui.backend_cli start
uv run python -m scripts.comfyui.backend_cli check
uv run python -m scripts.comfyui.backend_cli stop
```

The window stays open after the command finishes so you can read the output.

## PowerShell Commands

The `.ps1` scripts are low-level maintenance entry points and do not read `config.yaml`. Call them directly only when supplying complete path overrides, for example:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\comfyui\start_backend.ps1 `
  -PythonExe 'E:\ComfyUIData\.venv\Scripts\python.exe' `
  -ComfyUIRoot 'E:\comfyui\resources\ComfyUI' `
  -DataRoot 'E:\ComfyUIData\pixelle' `
  -SharedBasePath 'E:\ComfyUIData'
```

`start_backend.ps1` runs headlessly, deliberately avoids `--log-stdout` and
`--enable-manager`, and redirects stdout / stderr to:

```text
logs\comfyui\
```

## Defaults

- ComfyUI Python: `E:\ComfyUIData\.venv\Scripts\python.exe`
- ComfyUI root: `E:\comfyui\resources\ComfyUI`
- ComfyUI data root: `E:\ComfyUIData\pixelle`
- Shared models and custom nodes root: `E:\ComfyUIData`
- Frontend root: not overridden by default; ComfyUI serves its built-in frontend unless explicitly configured
- Database URL: `sqlite:///E:/ComfyUIData/pixelle/user/comfyui.db`
- Host/port: `127.0.0.1:8000`
- Backend PID file: `_runtime\comfyui\comfyui-backend.pid`
- Launcher PID file: `_runtime\comfyui\comfyui-backend.launcher.pid`
- Ownership record: `_runtime\comfyui\comfyui-backend.owner.json`

## Overrides

You can override defaults with script parameters or environment variables:

```powershell
$env:PIXELLE_COMFYUI_PYTHON = 'E:\ComfyUIData\.venv\Scripts\python.exe'
$env:PIXELLE_COMFYUI_ROOT = 'E:\comfyui\resources\ComfyUI'
$env:PIXELLE_COMFYUI_DATA_ROOT = 'E:\ComfyUIData\pixelle'
$env:PIXELLE_COMFYUI_SHARED_BASE_PATH = 'E:\ComfyUIData'
$env:PIXELLE_COMFYUI_FRONTEND_ROOT = 'E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app'
$env:PIXELLE_COMFYUI_DATABASE_URL = 'sqlite:///E:/ComfyUIData/pixelle/user/comfyui.db'
$env:PIXELLE_COMFYUI_PORT = '8000'
```

The scripts do not pass `--enable-cors-header *` by default. Pixelle accesses ComfyUI server-to-server and does not need to expose the local API to arbitrary browser origins.

The legacy `start_image_backend.bat`, `start_tts_backend.bat`, and matching check/stop files are upgrade shims. They all forward to the same `default` backend and never create a second instance.

If port `8000` is already occupied by an unmanaged process, `start_backend.ps1` refuses to start another backend instead of drifting to a new port.

`stop_backend.ps1` stops a backend only when its PID, process creation time, and configured process identity all match the ownership record. Missing, invalid, stale, legacy, or unrelated records are cleaned without terminating the listener. This prevents PID reuse mistakes, and a backend started by ComfyUI Desktop or another process manager is never taken over based on command-line similarity.

After upgrading from a version without ownership records, an existing process is treated as external. `auto` mode continues to reuse it; `required` mode needs that legacy process to be closed once so the current version can start it and create a record.
