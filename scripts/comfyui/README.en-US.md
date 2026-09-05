# Pixelle ComfyUI Backend Scripts

Pixelle defaults to managing the complete local ComfyUI service. It starts the service
when an image or audio workflow needs it, stops it after the complete batch is idle,
and starts it again only when the next local workflow begins. Process exit is the
memory-release boundary and does not depend on extension-private cleanup endpoints.

The scripts in this directory start, inspect, and stop the complete configured service.
They use the configured ComfyUI core, frontend, model paths, and data paths. They do not
create a ComfyUI Desktop window. The recommended profiles expose separate on-demand
browser endpoints:

```text
Image: http://127.0.0.1:8001
TTS:   http://127.0.0.1:8002
```

## Lifecycle Modes

- Recommended on-demand mode: `backend_management_mode: required`, `managed: true`,
  and `stop_after_batch: true`. Pixelle stops only the complete service it started and
  whose process identity it verified.
- Keep `resource_policy: auto` and omit `minimum_free_commit_gb` for managed Windows
  deployments. The default disables pinned host memory while preserving asynchronous
  model offload and execution caching within a batch. The startup guard derives a
  bounded 2-6 GiB operating-system reserve from the machine's commit limit; it is not
  presented as an estimate of an unknown workflow's model footprint.
- External mode: `backend_management_mode: disabled`. The user starts the instance;
  Pixelle only probes and submits work and never stops the external service.
- Reuse mode: `backend_management_mode: auto`. This may reuse an external service, so
  it cannot guarantee complete memory release after a batch.

The Desktop shell and ComfyUI core service are separate lifecycle layers. On-demand
management controls the complete core service. Its browser interface is available while
the service runs and exits with the service.

## GPU residency

A backend profile accepts `vram_mode: normal` (default) or `vram_mode: high`. High mode keeps models on the GPU to reduce host-memory transfers; enable it only after measuring that the configured workflow fits available VRAM. It does not change image models, dimensions, sampling, or creative prompts. Other profiles can retain normal mode.

The start/check/stop scripts accept `-VramMode normal|high` and include the mode in process ownership checks. Let the current batch finish and stop before switching. There is no automatic mode fallback or regeneration. Full process exit remains the cleanup boundary after a batch.

## Windows Double-Click Entry Points

Double-clicking `.ps1` files on Windows usually opens an editor or Notepad. That is the default Windows safety behavior, and changing the file association is not recommended.

For double-click usage, run the `.bat` files in this directory:

```text
check_backend.bat
start_backend.bat
stop_backend.bat
```

Double-click `.bat` files to run the matching command instead of opening script source code.

The generic launchers read the `default` profile. The image and TTS launchers read the
`image` and `tts` profiles. Equivalent commands are:

```powershell
uv run python -m scripts.comfyui.backend_cli start --profile image
uv run python -m scripts.comfyui.backend_cli check --profile tts
uv run python -m scripts.comfyui.backend_cli stop --profile tts
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

Relative runtime and log paths are always resolved from the repository root. Each
launch archives the previous backend logs and supervisor error log, retaining up to 20 archives
per stream. If the supervisor exits early, startup immediately reports its exit code
and a bounded diagnostic tail instead of waiting for the full readiness timeout.

## Defaults

- ComfyUI Python: `E:\ComfyUIData\.venv\Scripts\python.exe`
- ComfyUI root: `E:\comfyui\resources\ComfyUI`
- Image data root: `E:\ComfyUIData\pixelle-image`
- TTS data root: `E:\ComfyUIData\pixelle-tts`
- Shared models and custom nodes root: `E:\ComfyUIData`
- Frontend root: not overridden by default; ComfyUI serves its built-in frontend unless explicitly configured
- Image host/port: `127.0.0.1:8001`
- TTS host/port: `127.0.0.1:8002`
- Runtime state, logs, and databases are isolated by the `image` and `tts` profiles

## Overrides

You can override defaults with script parameters or environment variables:

```powershell
$env:PIXELLE_COMFYUI_PYTHON = 'E:\ComfyUIData\.venv\Scripts\python.exe'
$env:PIXELLE_COMFYUI_ROOT = 'E:\comfyui\resources\ComfyUI'
$env:PIXELLE_COMFYUI_DATA_ROOT = 'E:\ComfyUIData\pixelle'
$env:PIXELLE_COMFYUI_SHARED_BASE_PATH = 'E:\ComfyUIData'
$env:PIXELLE_COMFYUI_FRONTEND_ROOT = 'E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app'
$env:PIXELLE_COMFYUI_DATABASE_URL = 'sqlite:///E:/ComfyUIData/pixelle/user/comfyui.db'
$env:PIXELLE_COMFYUI_PORT = '8001'
```

The scripts do not pass `--enable-cors-header *` by default. Pixelle accesses ComfyUI server-to-server and does not need to expose the local API to arbitrary browser origins.

`start_image_backend.bat`, `start_tts_backend.bat`, and their matching check/stop
launchers operate the `image` and `tts` profiles. Each profile may use
`custom_node_loading: allowlist`; the launcher disables all custom nodes and then loads
only `allowed_custom_node_folders`. Transient startup timeouts retry three times after
the initial attempt by default, while configuration, path, port, and memory failures
fail immediately. One machine-wide operating-system mutex prevents the
image and TTS backends from owning the accelerator at the same time. During
shutdown handoff, a new backend waits up to five seconds for that mutex and
then fails explicitly if the previous owner still has not released it.

Allowlist mode resolves the effective `custom_nodes` roots using ComfyUI's own
path rules, including `--base-directory`, the application's built-in
`extra_model_paths.yaml`, and the explicitly supplied extra-model-paths config.
Exactly one effective plug-in root is required. An unregistered application copy
does not cause a false conflict, while a genuinely registered second root is
rejected before plug-in code executes. The allowlist selects plug-ins; it is not
a security sandbox, and every allowed plug-in still executes code in the ComfyUI
process.

If a configured port is occupied by an unmanaged process, `start_backend.ps1` refuses
to start another backend instead of drifting to a new port.

`stop_backend.ps1` stops a backend only when its PID, process creation time, and
configured process identity all match the ownership record. Configuration identity
covers the complete launch arguments and the contents of both built-in and explicit
extra-path configs. A config change during startup stops the new process and requires
a retry, while an already-running process is never mistaken for the changed config.
Missing, invalid, stale, legacy, or unrelated records are cleaned without terminating
the listener. This prevents PID reuse mistakes and isolates different data roots,
databases, and plug-in path configurations.

After upgrading from a version without ownership records, an existing process is treated as external. `auto` mode continues to reuse it; `required` mode needs that legacy process to be closed once so the current version can start it and create a record.
