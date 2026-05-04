# Dual ComfyUI Backends Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add production-grade multi-backend ComfyUI routing so standard video generation runs image and TTS workflows in isolated ComfyUI processes with profile-level lifecycle management.

**Architecture:** Introduce structured ComfyUI backend profiles and a central registry that owns role resolution, ComfyKit config, maintenance clients, and managed backend creation. PixelleVideoCore keeps per-backend ComfyKit instances, execution locks, workflow sessions, and restart tasks. Standard video image/TTS stages route through dedicated roles and trigger profile-level background restarts after each batch.

**Tech Stack:** Python 3.12, Pydantic config models, ComfyKit, asyncio, Streamlit settings UI, PowerShell backend scripts, pytest.

---

## Source Spec

- `docs/superpowers/specs/2026-05-04-dual-comfyui-backends-design.md`

## File Structure

- Modify `pixelle_video/config/schema.py`: add `ComfyUIBackendProfile`, `ComfyUIWorkflowRouting`, normalization validators, and fields on `ComfyUIConfig`.
- Modify `pixelle_video/config/manager.py`: expose structured backends/routing and support structured saves from Settings.
- Create `pixelle_video/services/comfyui_backend_registry.py`: central profile normalization, role resolution, ComfyKit config creation, maintenance client creation, managed backend creation, and dedicated-backend checks.
- Modify `pixelle_video/service.py`: replace single ComfyKit/cache/lock/backend manager with per-role registry-backed state; add role-aware workflow execution, maintenance, restart scheduling, and ready waiting.
- Modify `pixelle_video/services/comfy_base_service.py`: pass `backend_role` through `_execute_workflow`.
- Modify `pixelle_video/services/media.py`: resolve image workflow backend role through core registry and pass it to execution.
- Modify `pixelle_video/services/tts_service.py`: resolve TTS workflow backend role through core registry and pass it to execution.
- Modify `pixelle_video/pipelines/standard.py` and `pixelle_video/services/frame_processor.py`: ensure local workflow sessions bind to one backend role and schedule image/TTS restarts after their batches.
- Modify `pixelle_video/services/comfyui_backend_manager.py`: accept profile/runtime fields and call scripts with DataRoot, RuntimeDir, LogsDir, DatabaseUrl, and role metadata.
- Modify `scripts/comfyui/backend_common.ps1`, `start_backend.ps1`, `stop_backend.ps1`, `check_backend.ps1`: initialize profile directories, use profile-specific pid/log files, and constrain stop/cleanup to matching DataRoot + port + main.py.
- Modify `web/components/settings.py`, `web/i18n/locales/zh_CN.json`, `web/i18n/locales/en_US.json`: add simple multi-backend settings UI that writes structured profiles.
- Add/modify tests:
  - `tests/test_comfyui_backend_profiles.py`
  - `tests/test_comfyui_backend_registry.py`
  - `tests/test_comfykit_config.py`
  - `tests/test_comfyui_backend_manager.py`
  - `tests/test_comfyui_backend_scripts.py`
  - `tests/test_comfyui_backend_routing.py`
  - `tests/test_comfyui_settings_contract.py`

## Implementation Notes

- Do not introduce flat long-term config fields such as `image_comfyui_url` or `tts_comfyui_url`.
- Do not share DataRoot across managed profiles.
- Do not let services mutate global `comfyui_url` at runtime.
- Do not make CPU OOM recovery depend on VRAM release confirmation.
- Keep `11.md` untracked and out of every commit.
- Commit after each task with a Chinese `<类型>: <标题>` message.

---

### Task 1: Config Models And Normalization

**Files:**
- Modify: `pixelle_video/config/schema.py`
- Modify: `pixelle_video/config/manager.py`
- Test: `tests/test_comfyui_backend_profiles.py`
- Test: `tests/test_comfykit_config.py`

- [ ] **Step 1: Write failing config profile tests**

Create `tests/test_comfyui_backend_profiles.py`:

```python
import pytest

from pixelle_video.config.schema import ComfyUIConfig, PixelleVideoConfig


def test_empty_backends_create_default_profile_from_comfyui_url():
    config = PixelleVideoConfig.model_validate(
        {"comfyui": {"comfyui_url": "http://127.0.0.1:8000"}}
    )

    default = config.comfyui.backends["default"]

    assert default.url == "http://127.0.0.1:8000"
    assert default.data_root.replace("\\", "/").endswith("/pixelle-default")
    assert default.runtime_dir.replace("\\", "/").endswith("_runtime/comfyui/default")
    assert default.logs_dir.replace("\\", "/").endswith("logs/comfyui/default")
    assert default.database_url.replace("\\", "/").endswith(
        "/pixelle-default/user/comfyui.db"
    )


def test_config_keeps_structured_profiles_and_routing():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "comfyui_url": "http://127.0.0.1:8000",
                "backends": {
                    "image": {
                        "url": "http://127.0.0.1:8001",
                        "restart_after_batch": True,
                    },
                    "tts": {
                        "url": "http://127.0.0.1:8002",
                        "restart_after_batch": True,
                    },
                },
                "workflow_routing": {
                    "image": "image",
                    "tts": "tts",
                    "default": "default",
                },
            }
        }
    )

    assert set(config.comfyui.backends) == {"default", "image", "tts"}
    assert config.comfyui.backends["image"].url == "http://127.0.0.1:8001"
    assert config.comfyui.backends["image"].restart_after_batch is True
    assert config.comfyui.workflow_routing.image == "image"
    assert config.comfyui.workflow_routing.tts == "tts"


@pytest.mark.parametrize("bad_name", ["Image", "../image", "image role", "tts.role"])
def test_backend_profile_names_are_restricted(bad_name):
    with pytest.raises(ValueError, match="backend profile name"):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        bad_name: {"url": "http://127.0.0.1:8001"},
                    }
                }
            }
        )


def test_workflow_routing_must_reference_existing_profile():
    with pytest.raises(ValueError, match="workflow_routing.image"):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "image": {"url": "http://127.0.0.1:8001"},
                    },
                    "workflow_routing": {
                        "image": "missing",
                    },
                }
            }
        )
```

Append to `tests/test_comfykit_config.py`:

```python
def test_comfyui_config_exposes_backends_and_workflow_routing(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "comfyui_url": "http://127.0.0.1:8000",
                    "backends": {
                        "image": {"url": "http://127.0.0.1:8001"},
                        "tts": {"url": "http://127.0.0.1:8002"},
                    },
                    "workflow_routing": {"image": "image", "tts": "tts"},
                }
            }
        ),
    )

    comfyui_config = config_manager.get_comfyui_config()

    assert comfyui_config["backends"]["image"]["url"] == "http://127.0.0.1:8001"
    assert comfyui_config["backends"]["tts"]["url"] == "http://127.0.0.1:8002"
    assert comfyui_config["workflow_routing"]["image"] == "image"
    assert comfyui_config["workflow_routing"]["tts"] == "tts"
```

- [ ] **Step 2: Run failing config tests**

Run:

```bash
uv run pytest tests/test_comfyui_backend_profiles.py tests/test_comfykit_config.py -q
```

Expected: fails because `ComfyUIBackendProfile`, `workflow_routing`, and `backends` support do not exist.

- [ ] **Step 3: Implement config models**

In `pixelle_video/config/schema.py`, add imports if missing:

```python
import re
from pathlib import Path
```

Add models near `ComfyUIConfig`:

```python
_BACKEND_PROFILE_NAME_RE = re.compile(r"^[a-z0-9_-]+$")


class ComfyUIBackendProfile(BaseModel):
    url: str
    managed: bool = True
    restart_after_batch: bool = False
    data_root: Optional[str] = None
    runtime_dir: Optional[str] = None
    logs_dir: Optional[str] = None
    python_exe: Optional[str] = None
    comfyui_root: Optional[str] = None
    frontend_root: Optional[str] = None
    extra_models_config: Optional[str] = None
    database_url: Optional[str] = None


class ComfyUIWorkflowRouting(BaseModel):
    image: str = "default"
    tts: str = "default"
    default: str = "default"
```

Add fields to `ComfyUIConfig`:

```python
    backends: dict[str, ComfyUIBackendProfile] = Field(default_factory=dict)
    workflow_routing: ComfyUIWorkflowRouting = Field(
        default_factory=ComfyUIWorkflowRouting
    )
```

Inside the existing `ComfyUIConfig` `model_validator(mode="before")`, after legacy cleanup normalization, normalize profile input:

```python
        raw_backends = normalized.get("backends")
        if raw_backends is None:
            raw_backends = {}
        if not isinstance(raw_backends, dict):
            raise ValueError("comfyui.backends must be a mapping")
        backends = dict(raw_backends)
        backends.setdefault(
            "default",
            {"url": normalized.get("comfyui_url") or "http://127.0.0.1:8188"},
        )
        for name, profile in list(backends.items()):
            if not isinstance(name, str) or not _BACKEND_PROFILE_NAME_RE.match(name):
                raise ValueError(f"Invalid backend profile name: {name}")
            if not isinstance(profile, dict):
                raise ValueError(f"Backend profile {name} must be a mapping")
            profile = dict(profile)
            profile.setdefault("url", normalized.get("comfyui_url") or "http://127.0.0.1:8188")
            profile.setdefault("data_root", f"E:/ComfyUIData/pixelle-{name}")
            profile.setdefault("runtime_dir", f"_runtime/comfyui/{name}")
            profile.setdefault("logs_dir", f"logs/comfyui/{name}")
            data_root = str(profile["data_root"]).replace("\\", "/").rstrip("/")
            profile.setdefault("database_url", f"sqlite:///{data_root}/user/comfyui.db")
            backends[name] = profile
        normalized["backends"] = backends
```

Add an `after` validator:

```python
    @model_validator(mode="after")
    def validate_backend_routing(self):
        known = set(self.backends)
        for field_name in ("image", "tts", "default"):
            role = getattr(self.workflow_routing, field_name)
            if role not in known:
                raise ValueError(
                    f"workflow_routing.{field_name} references unknown backend profile: {role}"
                )
        return self
```

In `pixelle_video/config/manager.py`, include these in `get_comfyui_config()`:

```python
            "backends": {
                name: profile.model_dump()
                for name, profile in self.config.comfyui.backends.items()
            },
            "workflow_routing": self.config.comfyui.workflow_routing.model_dump(),
```

Extend `set_comfyui_config()` signature with:

```python
        backends: Optional[dict] = None,
        workflow_routing: Optional[dict] = None,
```

and add:

```python
        if backends is not None:
            updates["backends"] = backends
        if workflow_routing is not None:
            updates["workflow_routing"] = workflow_routing
```

- [ ] **Step 4: Run config tests**

Run:

```bash
uv run pytest tests/test_comfyui_backend_profiles.py tests/test_comfykit_config.py -q
```

Expected: pass.

- [ ] **Step 5: Commit config models**

```bash
git add pixelle_video/config/schema.py pixelle_video/config/manager.py tests/test_comfyui_backend_profiles.py tests/test_comfykit_config.py
git commit -m "feat: 增加ComfyUI后端profile配置"
```

---

### Task 2: Backend Registry

**Files:**
- Create: `pixelle_video/services/comfyui_backend_registry.py`
- Modify: `pixelle_video/service.py`
- Test: `tests/test_comfyui_backend_registry.py`

- [ ] **Step 1: Write failing registry tests**

Create `tests/test_comfyui_backend_registry.py`:

```python
from pathlib import Path

from pixelle_video.config.schema import ComfyUIConfig
from pixelle_video.services.comfyui_backend_registry import ComfyUIBackendRegistry


def make_registry() -> ComfyUIBackendRegistry:
    config = ComfyUIConfig.model_validate(
        {
            "comfyui_url": "http://127.0.0.1:8000",
            "executor_type": None,
            "runninghub_api_key": "rh",
            "runninghub_instance_type": "plus",
            "backends": {
                "image": {"url": "http://127.0.0.1:8001"},
                "tts": {"url": "http://127.0.0.1:8002"},
            },
            "workflow_routing": {"image": "image", "tts": "tts"},
        }
    )
    return ComfyUIBackendRegistry(config, repo_root=Path.cwd())


def test_registry_resolves_media_and_tts_roles():
    registry = make_registry()

    assert registry.resolve_role_for_media("selfhost/image_z.json", "image") == "image"
    assert registry.resolve_role_for_tts("selfhost/tts_index2.json") == "tts"
    assert registry.resolve_role_for_workflow("selfhost/video_wan.json") == "default"
    assert registry.resolve_role_for_workflow("runninghub/image.json") == "default"


def test_registry_builds_role_specific_comfykit_config():
    registry = make_registry()

    config = registry.get_comfykit_config("image")

    assert config["comfyui_url"] == "http://127.0.0.1:8001"
    assert config["executor_type"] == "http"
    assert config["runninghub_api_key"] == "rh"
    assert config["runninghub_instance_type"] == "plus"


def test_registry_reports_dedicated_backend():
    registry = make_registry()

    assert registry.is_dedicated_backend("image") is True
    assert registry.is_dedicated_backend("tts") is True
    assert registry.is_dedicated_backend("default") is False
```

- [ ] **Step 2: Run failing registry tests**

Run:

```bash
uv run pytest tests/test_comfyui_backend_registry.py -q
```

Expected: fails because the registry module does not exist.

- [ ] **Step 3: Implement registry**

Create `pixelle_video/services/comfyui_backend_registry.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from pixelle_video.config.schema import ComfyUIBackendProfile, ComfyUIConfig
from pixelle_video.services.comfyui_backend_manager import ManagedComfyUIBackend
from pixelle_video.services.comfyui_maintenance import ComfyUIMaintenanceClient


class ComfyUIBackendRegistry:
    def __init__(self, config: ComfyUIConfig, *, repo_root: str | Path) -> None:
        self.config = config
        self.repo_root = Path(repo_root)

    def profile(self, role: str) -> ComfyUIBackendProfile:
        try:
            return self.config.backends[role]
        except KeyError as exc:
            raise ValueError(f"Unknown ComfyUI backend role: {role}") from exc

    def resolve_role_for_media(self, workflow_key: str | None, media_type: str) -> str:
        if media_type == "image" and str(workflow_key or "").startswith("selfhost/"):
            return self.config.workflow_routing.image
        return self.resolve_role_for_workflow(workflow_key)

    def resolve_role_for_tts(self, workflow_key: str | None) -> str:
        if str(workflow_key or "").startswith("selfhost/"):
            return self.config.workflow_routing.tts
        return "default"

    def resolve_role_for_workflow(self, workflow_key: str | None) -> str:
        key = str(workflow_key or "")
        if not key.startswith("selfhost/"):
            return "default"
        if "/image_" in key or key.startswith("selfhost/image_"):
            return self.config.workflow_routing.image
        if "/tts_" in key or key.startswith("selfhost/tts_"):
            return self.config.workflow_routing.tts
        return self.config.workflow_routing.default

    def is_dedicated_backend(self, role: str) -> bool:
        return role != "default" and role in self.config.backends

    def get_comfykit_config(self, role: str) -> dict[str, Any]:
        profile = self.profile(role)
        kit_config: dict[str, Any] = {"comfyui_url": profile.url}
        executor_type = self.config.executor_type or "http"
        kit_config["executor_type"] = executor_type
        if self.config.comfyui_api_key:
            kit_config["api_key"] = self.config.comfyui_api_key
        if self.config.runninghub_api_key:
            kit_config["runninghub_api_key"] = self.config.runninghub_api_key
        if self.config.runninghub_instance_type:
            kit_config["runninghub_instance_type"] = self.config.runninghub_instance_type
        return kit_config

    def maintenance_client(self, role: str) -> ComfyUIMaintenanceClient:
        profile = self.profile(role)
        return ComfyUIMaintenanceClient(
            profile.url,
            api_key=self.config.comfyui_api_key,
        )

    def managed_backend(self, role: str) -> ManagedComfyUIBackend:
        profile = self.profile(role)
        return ManagedComfyUIBackend(
            repo_root=self.repo_root,
            profile_name=role,
            profile=profile,
            management_mode=self.config.backend_management_mode,
        )
```

In `pixelle_video/service.py`, initialize `self._comfyui_backend_registry = None` in `__init__` and add:

```python
    def _get_comfyui_backend_registry(self):
        self.config = config_manager.config.to_dict()
        return ComfyUIBackendRegistry(
            config_manager.config.comfyui,
            repo_root=Path(__file__).resolve().parents[1],
        )
```

Import:

```python
from pixelle_video.services.comfyui_backend_registry import ComfyUIBackendRegistry
```

- [ ] **Step 4: Run registry tests**

Run:

```bash
uv run pytest tests/test_comfyui_backend_registry.py -q
```

Expected: pass.

- [ ] **Step 5: Commit registry**

```bash
git add pixelle_video/services/comfyui_backend_registry.py pixelle_video/service.py tests/test_comfyui_backend_registry.py
git commit -m "feat: 增加ComfyUI后端注册表"
```

---

### Task 3: Profile-Aware Managed Backend Scripts

**Files:**
- Modify: `pixelle_video/services/comfyui_backend_manager.py`
- Modify: `scripts/comfyui/backend_common.ps1`
- Modify: `scripts/comfyui/start_backend.ps1`
- Modify: `scripts/comfyui/stop_backend.ps1`
- Modify: `scripts/comfyui/check_backend.ps1`
- Test: `tests/test_comfyui_backend_manager.py`
- Test: `tests/test_comfyui_backend_scripts.py`

- [ ] **Step 1: Write failing backend manager tests**

Append to `tests/test_comfyui_backend_manager.py`:

```python
from pixelle_video.config.schema import ComfyUIBackendProfile


def test_managed_backend_uses_profile_runtime_arguments(tmp_path):
    profile = ComfyUIBackendProfile(
        url="http://127.0.0.1:8001",
        data_root=str(tmp_path / "image-data"),
        runtime_dir=str(tmp_path / "runtime" / "image"),
        logs_dir=str(tmp_path / "logs" / "image"),
        database_url=f"sqlite:///{(tmp_path / 'image-data' / 'user' / 'comfyui.db').as_posix()}",
    )
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        profile_name="image",
        profile=profile,
        management_mode="required",
    )

    args = backend._script_args()

    assert "-DataRoot" in args
    assert str(tmp_path / "image-data") in args
    assert "-RuntimeDir" in args
    assert str(tmp_path / "runtime" / "image") in args
    assert "-LogsDir" in args
    assert str(tmp_path / "logs" / "image") in args
    assert "-DatabaseUrl" in args
```

Append to `tests/test_comfyui_backend_scripts.py`:

```python
def test_start_backend_dry_run_initializes_missing_profile_dirs(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    for child in ("input", "output", "user"):
        target = data_root / child
        if target.exists():
            os.rmdir(target)
    runtime_dir = tmp_path / "runtime" / "image"
    logs_dir = tmp_path / "logs" / "image"

    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        runtime_dir,
        "-LogsDir",
        logs_dir,
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        "65500",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data_root"] == str(data_root)
    assert payload["runtime_dir"] == str(runtime_dir)
    assert payload["logs_dir"] == str(logs_dir)
    assert (data_root / "input").is_dir()
    assert (data_root / "output").is_dir()
    assert (data_root / "user").is_dir()
    assert runtime_dir.is_dir()
    assert logs_dir.is_dir()


def test_backend_pid_and_logs_are_profile_scoped(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    runtime_dir = tmp_path / "runtime" / "tts"
    logs_dir = tmp_path / "logs" / "tts"

    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        runtime_dir,
        "-LogsDir",
        logs_dir,
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        "65501",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["pid_file"] == str(runtime_dir / "comfyui-backend.pid")
    assert payload["stdout_log"] == str(logs_dir / "comfyui-backend.stdout.log")
    assert payload["stderr_log"] == str(logs_dir / "comfyui-backend.stderr.log")
```

- [ ] **Step 2: Run failing script tests**

Run:

```bash
uv run pytest tests/test_comfyui_backend_manager.py tests/test_comfyui_backend_scripts.py -q
```

Expected: fails because manager does not accept profile and scripts do not initialize missing DataRoot children.

- [ ] **Step 3: Implement profile-aware manager and scripts**

In `pixelle_video/services/comfyui_backend_manager.py`:

- Add `profile_name: str = "default"` and `profile: ComfyUIBackendProfile | None = None`.
- Preserve legacy `comfyui_url` constructor support by creating an internal profile when `profile is None`.
- Add `_script_args()` returning args for profile-specific values.
- Include `-DataRoot`, `-RuntimeDir`, `-LogsDir`, and `-DatabaseUrl` in `_run_script()`.

In `scripts/comfyui/backend_common.ps1`:

- Change `Assert-BackendPrerequisites` so it verifies `PythonExe`, `main.py`, extra models config, and frontend root, but creates `DataRoot/input`, `DataRoot/output`, and `DataRoot/user` when missing.
- Keep `Get-BackendPidFile` returning `Join-Path $Config.RuntimeDir 'comfyui-backend.pid'`.
- Keep `Get-BackendStdoutLog` returning `Join-Path $Config.LogsDir 'comfyui-backend.stdout.log'`.
- Update `Test-ManagedComfyUIProcess` to require command line matches `main.py`, `--base-directory`, target DataRoot, `--port`, and target port.
- Update `Stop-ManagedComfyUIProcessesForConfig` to match the same DataRoot and port.

In `start_backend.ps1` dry-run payload and success payload, include:

```powershell
data_root = $config.DataRoot
runtime_dir = $config.RuntimeDir
logs_dir = $config.LogsDir
database_url = $config.DatabaseUrl
```

In `check_backend.ps1` and `stop_backend.ps1`, include the same fields in JSON payloads where practical.

- [ ] **Step 4: Run script tests**

Run:

```bash
uv run pytest tests/test_comfyui_backend_manager.py tests/test_comfyui_backend_scripts.py -q
```

Expected: pass.

- [ ] **Step 5: Commit profile-aware scripts**

```bash
git add pixelle_video/services/comfyui_backend_manager.py scripts/comfyui/backend_common.ps1 scripts/comfyui/start_backend.ps1 scripts/comfyui/stop_backend.ps1 scripts/comfyui/check_backend.ps1 tests/test_comfyui_backend_manager.py tests/test_comfyui_backend_scripts.py
git commit -m "feat: 隔离ComfyUI托管后端profile运行目录"
```

---

### Task 4: Role-Aware ComfyKit Execution

**Files:**
- Modify: `pixelle_video/service.py`
- Modify: `pixelle_video/services/comfy_base_service.py`
- Modify: `pixelle_video/services/media.py`
- Modify: `pixelle_video/services/tts_service.py`
- Test: `tests/test_comfyui_backend_routing.py`

- [ ] **Step 1: Write failing execution routing tests**

Create `tests/test_comfyui_backend_routing.py`:

```python
import pytest

from pixelle_video.config import config_manager
from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.service import PixelleVideoCore


@pytest.mark.asyncio
async def test_core_caches_comfykit_per_backend(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "image": {"url": "http://127.0.0.1:8001"},
                        "tts": {"url": "http://127.0.0.1:8002"},
                    },
                    "workflow_routing": {"image": "image", "tts": "tts"},
                }
            }
        ),
    )
    created = []

    class FakeComfyKit:
        def __init__(self, **config):
            self.config = config
            created.append(config)

    monkeypatch.setattr("pixelle_video.service.ComfyKit", FakeComfyKit)

    core = PixelleVideoCore()
    image_kit = await core._get_or_create_comfykit("image")
    tts_kit = await core._get_or_create_comfykit("tts")
    image_kit_again = await core._get_or_create_comfykit("image")

    assert image_kit is image_kit_again
    assert image_kit is not tts_kit
    assert created[0]["comfyui_url"] == "http://127.0.0.1:8001"
    assert created[1]["comfyui_url"] == "http://127.0.0.1:8002"


def test_media_and_tts_services_choose_dedicated_roles(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "image": {"url": "http://127.0.0.1:8001"},
                        "tts": {"url": "http://127.0.0.1:8002"},
                    },
                    "workflow_routing": {"image": "image", "tts": "tts"},
                }
            }
        ),
    )
    core = PixelleVideoCore()
    registry = core._get_comfyui_backend_registry()

    assert registry.resolve_role_for_media("selfhost/image_z.json", "image") == "image"
    assert registry.resolve_role_for_tts("selfhost/tts_index2.json") == "tts"
```

- [ ] **Step 2: Run failing routing tests**

Run:

```bash
uv run pytest tests/test_comfyui_backend_routing.py -q
```

Expected: fails because `_get_or_create_comfykit(role)` and service role propagation do not exist.

- [ ] **Step 3: Implement role-aware ComfyKit cache and execute path**

In `pixelle_video/service.py`:

- Replace `_comfykit` with `_comfykit_by_backend`.
- Replace `_comfykit_config_hash` with `_comfykit_config_hash_by_backend`.
- Change `_get_comfykit_config(self, backend_role="default")` to use registry.
- Change `_get_or_create_comfykit(self, backend_role="default")`.
- Change `_close_comfykit_instance(self, backend_role: str | None = None)` to close one role or all roles.
- Change `_execute_local_comfykit_workflow_once(..., backend_role="default")`.
- Change `_execute_local_comfykit_workflow(..., backend_role="default")`.
- Change `execute_comfykit_workflow()` to accept `backend_role="default"` and pass it through.

In `pixelle_video/services/comfy_base_service.py`, change `_execute_workflow` to accept:

```python
        backend_role: str = "default",
```

and pass it to `execute_comfykit_workflow`.

In `pixelle_video/services/media.py`, after resolving `workflow_info`, compute:

```python
backend_role = "default"
if workflow_info["source"] == "selfhost":
    backend_role = self.core._get_comfyui_backend_registry().resolve_role_for_media(
        workflow_info["key"],
        media_type,
    )
```

Then call `_execute_workflow(..., backend_role=backend_role)`.

In `pixelle_video/services/tts_service.py`, compute:

```python
backend_role = "default"
if workflow_info["source"] == "selfhost":
    backend_role = self.core._get_comfyui_backend_registry().resolve_role_for_tts(
        workflow_info["key"],
    )
```

Then call `_execute_workflow(..., backend_role=backend_role)`.

- [ ] **Step 4: Run routing tests**

Run:

```bash
uv run pytest tests/test_comfyui_backend_routing.py tests/test_comfykit_config.py -q
```

Expected: pass.

- [ ] **Step 5: Commit role-aware execution**

```bash
git add pixelle_video/service.py pixelle_video/services/comfy_base_service.py pixelle_video/services/media.py pixelle_video/services/tts_service.py tests/test_comfyui_backend_routing.py tests/test_comfykit_config.py
git commit -m "feat: 按后端角色执行本地ComfyUI工作流"
```

---

### Task 5: Per-Role Locks, Sessions, Maintenance, And OOM Restart

**Files:**
- Modify: `pixelle_video/service.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/services/frame_processor.py`
- Test: `tests/test_comfyui_backend_routing.py`
- Test: `tests/test_comfyui_maintenance.py`

- [ ] **Step 1: Write failing lifecycle tests**

Append to `tests/test_comfyui_backend_routing.py`:

```python
@pytest.mark.asyncio
async def test_restart_is_tracked_per_backend_role(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "image": {
                            "url": "http://127.0.0.1:8001",
                            "restart_after_batch": True,
                        }
                    },
                    "workflow_routing": {"image": "image"},
                }
            }
        ),
    )
    core = PixelleVideoCore()
    calls = []

    async def fake_restart(role, reason):
        calls.append((role, reason))

    monkeypatch.setattr(core, "_restart_comfyui_backend_role", fake_restart)

    core.schedule_comfyui_backend_restart("image", "post-image-batch")
    core.schedule_comfyui_backend_restart("image", "duplicate")
    await core.await_comfyui_backend_ready("image")

    assert calls == [("image", "post-image-batch")]


@pytest.mark.asyncio
async def test_cpu_oom_restarts_managed_backend_before_retry(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "image": {"url": "http://127.0.0.1:8001"},
                    },
                    "workflow_routing": {"image": "image"},
                }
            }
        ),
    )
    core = PixelleVideoCore()
    attempts = 0
    restarted = []

    async def fake_once(workflow_input, workflow_params, *, backend_role="default"):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("DefaultCPUAllocator: not enough memory")
        return "ok"

    async def fake_release(*, context, include_extensions=False, extensions=()):
        return True

    async def fake_restart(role, reason):
        restarted.append((role, reason))

    monkeypatch.setattr(core, "_execute_local_comfykit_workflow_once", fake_once)
    monkeypatch.setattr(core, "force_release_comfyui_memory", fake_release)
    monkeypatch.setattr(core, "_restart_comfyui_backend_role", fake_restart)

    result = await core._execute_local_comfykit_workflow(
        "workflows/selfhost/image_z.json",
        {},
        backend_role="image",
    )

    assert result == "ok"
    assert restarted == [("image", "oom-recovery")]
```

- [ ] **Step 2: Run failing lifecycle tests**

Run:

```bash
uv run pytest tests/test_comfyui_backend_routing.py -q
```

Expected: fails because restart scheduling and CPU OOM role restart are not implemented.

- [ ] **Step 3: Implement per-role lifecycle**

In `pixelle_video/service.py`:

- Replace `_local_comfyui_execution_lock` with `dict[str, asyncio.Lock]`.
- Add `_comfyui_restart_tasks: dict[str, asyncio.Task]`.
- Add `_get_backend_lock(role)`.
- Add `schedule_comfyui_backend_restart(role, reason)`.
- Add `await_comfyui_backend_ready(role)`.
- Add `_restart_comfyui_backend_role(role, reason)`.
- Update `prepare_comfyui_for_local_workflow(backend_role="default")` to use registry maintenance client for that role.
- Update all release methods with `backend_role="default"` and use role maintenance client.
- Update `_execute_local_comfykit_workflow` CPU OOM branch to call role release and role restart for managed profiles before retrying.
- Update local workflow session data structure to include `backend_role` and use role-specific lock.

In `pixelle_video/pipelines/standard.py` and `pixelle_video/services/frame_processor.py`:

- Update `_maybe_local_comfyui_workflow_session` helper to accept `backend_role`.
- Ensure image generation session passes `backend_role="image"` through registry role resolution.
- Ensure TTS session passes `backend_role="tts"` through registry role resolution.

- [ ] **Step 4: Run lifecycle tests**

Run:

```bash
uv run pytest tests/test_comfyui_backend_routing.py tests/test_comfyui_maintenance.py -q
```

Expected: pass.

- [ ] **Step 5: Commit lifecycle**

```bash
git add pixelle_video/service.py pixelle_video/pipelines/standard.py pixelle_video/services/frame_processor.py tests/test_comfyui_backend_routing.py tests/test_comfyui_maintenance.py
git commit -m "feat: 增加ComfyUI后端角色生命周期管理"
```

---

### Task 6: Standard Pipeline Batch Restart Hooks

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/services/frame_processor.py`
- Test: `tests/test_standard_pipeline_backend_lifecycle.py`

- [ ] **Step 1: Write failing standard pipeline lifecycle tests**

Create `tests/test_standard_pipeline_backend_lifecycle.py`:

```python
from types import SimpleNamespace

import pytest

from pixelle_video.pipelines.standard import StandardPipeline


@pytest.mark.asyncio
async def test_standard_pipeline_schedules_image_restart_after_media_batch(monkeypatch):
    core = SimpleNamespace()
    scheduled = []
    core.schedule_comfyui_backend_restart = lambda role, reason: scheduled.append(
        (role, reason)
    )
    core._get_comfyui_backend_registry = lambda: SimpleNamespace(
        is_dedicated_backend=lambda role: role == "image",
        profile=lambda role: SimpleNamespace(restart_after_batch=True),
    )
    pipeline = StandardPipeline(core)

    await pipeline._schedule_stage_backend_restart_if_needed(
        backend_role="image",
        reason="post-image-batch",
    )

    assert scheduled == [("image", "post-image-batch")]


@pytest.mark.asyncio
async def test_standard_pipeline_does_not_restart_default_backend(monkeypatch):
    core = SimpleNamespace()
    scheduled = []
    core.schedule_comfyui_backend_restart = lambda role, reason: scheduled.append(
        (role, reason)
    )
    core._get_comfyui_backend_registry = lambda: SimpleNamespace(
        is_dedicated_backend=lambda role: False,
        profile=lambda role: SimpleNamespace(restart_after_batch=True),
    )
    pipeline = StandardPipeline(core)

    await pipeline._schedule_stage_backend_restart_if_needed(
        backend_role="default",
        reason="post-image-batch",
    )

    assert scheduled == []
```

- [ ] **Step 2: Run failing standard pipeline tests**

Run:

```bash
uv run pytest tests/test_standard_pipeline_backend_lifecycle.py -q
```

Expected: fails because `_schedule_stage_backend_restart_if_needed` does not exist.

- [ ] **Step 3: Implement batch restart hooks**

In `pixelle_video/pipelines/standard.py`, add helper:

```python
    async def _schedule_stage_backend_restart_if_needed(
        self,
        *,
        backend_role: str,
        reason: str,
    ) -> None:
        registry = self.core._get_comfyui_backend_registry()
        if not registry.is_dedicated_backend(backend_role):
            return
        profile = registry.profile(backend_role)
        if not profile.restart_after_batch:
            return
        self.core.schedule_comfyui_backend_restart(backend_role, reason)
```

Call it:

- after HyperFrames raw media image batch completes, with role resolved for media workflow and reason `post-image-batch`.
- after TTS block/segment synthesis completes, with role resolved for TTS workflow and reason `post-tts-batch`.

If image or TTS workflow is RunningHub, role should be `default` and no restart should be scheduled.

- [ ] **Step 4: Run standard pipeline tests**

Run:

```bash
uv run pytest tests/test_standard_pipeline_backend_lifecycle.py tests/test_comfyui_backend_routing.py -q
```

Expected: pass.

- [ ] **Step 5: Commit standard pipeline hooks**

```bash
git add pixelle_video/pipelines/standard.py pixelle_video/services/frame_processor.py tests/test_standard_pipeline_backend_lifecycle.py
git commit -m "feat: 标准视频流程按阶段重启专用ComfyUI后端"
```

---

### Task 7: Settings UI Writes Structured Backends

**Files:**
- Modify: `web/components/settings.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `pixelle_video/config/manager.py`
- Test: `tests/test_comfyui_settings_contract.py`

- [ ] **Step 1: Write failing settings contract tests**

Append to `tests/test_comfyui_settings_contract.py`:

```python
def test_settings_page_writes_structured_comfyui_backends():
    source = (PROJECT_ROOT / "web" / "components" / "settings.py").read_text(
        encoding="utf-8"
    )

    assert "backends=" in source
    assert "workflow_routing=" in source
    assert "image_comfyui_url" not in source
    assert "tts_comfyui_url" not in source


def test_settings_locales_include_multi_backend_labels():
    zh = (PROJECT_ROOT / "web" / "i18n" / "locales" / "zh_CN.json").read_text(
        encoding="utf-8"
    )
    en = (PROJECT_ROOT / "web" / "i18n" / "locales" / "en_US.json").read_text(
        encoding="utf-8"
    )

    assert "settings.comfyui.image_backend_url" in zh
    assert "settings.comfyui.tts_backend_url" in zh
    assert "settings.comfyui.image_backend_url" in en
    assert "settings.comfyui.tts_backend_url" in en
```

- [ ] **Step 2: Run failing settings tests**

Run:

```bash
uv run pytest tests/test_comfyui_settings_contract.py -q
```

Expected: fails because settings page and locales do not expose structured backend config.

- [ ] **Step 3: Implement settings UI**

In `web/components/settings.py`:

- Read `comfyui_config["backends"]` and `comfyui_config["workflow_routing"]`.
- In simple ComfyUI settings section, show:
  - default backend URL
  - image backend URL
  - TTS backend URL
  - image restart checkbox
  - TTS restart checkbox
- On save, build:

```python
backends = {
    "default": {
        "url": default_url,
        "restart_after_batch": False,
    },
    "image": {
        "url": image_url,
        "restart_after_batch": restart_image,
    },
    "tts": {
        "url": tts_url,
        "restart_after_batch": restart_tts,
    },
}
workflow_routing = {
    "image": "image" if image_url and image_url != default_url else "default",
    "tts": "tts" if tts_url and tts_url != default_url else "default",
    "default": "default",
}
```

- Call `config_manager.set_comfyui_config(..., backends=backends, workflow_routing=workflow_routing)`.
- Do not store flat `image_comfyui_url` or `tts_comfyui_url`.

In locale files, add keys:

```json
"settings.comfyui.image_backend_url": "图片 ComfyUI 地址",
"settings.comfyui.tts_backend_url": "TTS ComfyUI 地址",
"settings.comfyui.restart_image_backend_after_batch": "图片批次后重启图片后端",
"settings.comfyui.restart_tts_backend_after_batch": "TTS 批次后重启 TTS 后端"
```

and English equivalents.

- [ ] **Step 4: Run settings tests**

Run:

```bash
uv run pytest tests/test_comfyui_settings_contract.py -q
```

Expected: pass.

- [ ] **Step 5: Commit settings UI**

```bash
git add web/components/settings.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json pixelle_video/config/manager.py tests/test_comfyui_settings_contract.py
git commit -m "feat: 设置页支持结构化ComfyUI多后端配置"
```

---

### Task 8: Logging, Error Messages, And Full Verification

**Files:**
- Modify: `pixelle_video/service.py`
- Modify: `pixelle_video/services/media.py`
- Modify: `pixelle_video/services/tts_service.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Test: existing focused tests

- [ ] **Step 1: Add missing observability assertions**

Append to `tests/test_comfyui_backend_routing.py`:

```python
def test_backend_registry_error_includes_missing_role():
    config = PixelleVideoConfig.model_validate(
        {"comfyui": {"comfyui_url": "http://127.0.0.1:8000"}}
    )
    core = PixelleVideoCore()

    with pytest.raises(ValueError, match="missing-role"):
        core._get_comfyui_backend_registry().profile("missing-role")
```

If the implementation currently raises a different message, update the registry to include the role name.

- [ ] **Step 2: Implement structured logs**

Add bound logger fields where local workflow executes:

```python
logger.bind(
    channel="runtime",
    event="comfyui_backend_route",
    backend_role=backend_role,
    comfyui_url=profile.url,
    data_root=profile.data_root,
    workflow=str(workflow_input),
).info("Executing local ComfyUI workflow on backend role")
```

Add logs for:

- waiting for backend restart
- restart scheduled
- restart start
- restart success
- restart failure
- OOM restart retry

Error messages for OOM after retry must include backend role, URL, workflow, and log directory.

- [ ] **Step 3: Run focused verification**

Run:

```bash
uv run pytest tests/test_comfyui_backend_profiles.py tests/test_comfyui_backend_registry.py tests/test_comfyui_backend_routing.py tests/test_comfyui_backend_manager.py tests/test_comfyui_backend_scripts.py tests/test_comfyui_settings_contract.py tests/test_comfykit_config.py tests/test_comfyui_maintenance.py tests/test_standard_pipeline_backend_lifecycle.py -q
```

Expected: pass.

- [ ] **Step 4: Run broader regression slice**

Run:

```bash
uv run pytest tests/test_frame_processor_tts_split.py tests/test_frame_processor_negative_prompt.py tests/test_asset_based_pipeline_contract.py tests/test_hyperframes_renderer.py -q
```

Expected: pass.

- [ ] **Step 5: Manual dry-run script verification**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/comfyui/start_backend.ps1 -DryRun -Json -Port 8001 -DataRoot E:\ComfyUIData\pixelle-image -RuntimeDir _runtime\comfyui\image -LogsDir logs\comfyui\image
```

Expected: JSON includes `port: 8001`, `data_root: E:\ComfyUIData\pixelle-image`, profile-scoped `pid_file`, `stdout_log`, and `stderr_log`.

- [ ] **Step 6: Commit observability and verification updates**

```bash
git add pixelle_video/service.py pixelle_video/services/media.py pixelle_video/services/tts_service.py pixelle_video/pipelines/standard.py tests/test_comfyui_backend_routing.py
git commit -m "feat: 补齐ComfyUI多后端日志与错误上下文"
```

- [ ] **Step 7: Final status and push**

Run:

```bash
git status --short --branch
git log --oneline -8
git push origin dev
```

Expected:

- Only `11.md` remains untracked if still present.
- All implementation commits are pushed to `origin/dev`.

---

## Plan Self-Review

- Spec coverage: tasks cover config profiles, registry, ComfyKit cache, per-role locks, managed scripts, standard pipeline routing, stage restarts, CPU OOM restart, settings UI, logs, and tests.
- Marker scan: no unfinished-work markers, no vague “add tests”, no unowned files.
- Type consistency: profile names are `default`, `image`, `tts`; routing uses `workflow_routing`; execution parameter is `backend_role`.
- Technical debt check: plan avoids flat temporary URL fields, avoids shared DataRoot, centralizes backend logic in a registry, and requires test coverage before implementation.
