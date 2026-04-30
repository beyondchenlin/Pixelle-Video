# IndexTTS2 VRAM Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Pixelle's local ComfyUI cleanup release both ComfyUI-managed models and the private `ComfyUI-Index-TTS` IndexTTS2 CUDA cache.

**Architecture:** Add a repeatable plugin patch that registers all `IndexTTS2Loader` instances, exposes `POST /pixelle/indextts2/free`, and clears private PyTorch references. Extend Pixelle's maintenance client and local ComfyUI lifecycle so queue cleanup, OOM recovery, and IndexTTS2 session exit call the right model-release contract without disabling `keep_models_cached` inside a TTS batch.

**Tech Stack:** Python 3.11, pytest, httpx `AsyncBaseTransport`, Pydantic config schema, Streamlit settings UI, ComfyUI custom node `PromptServer` routes.

---

## File Structure

- Modify `tools/patch_indextts2_plugin.py`: add model-loader patching and managed `pixelle_routes.py` generation for `ComfyUI-Index-TTS`.
- Modify `tests/test_patch_indextts2_plugin.py`: prove the plugin patch adds loader registry, release function, route registration, and stays idempotent.
- Modify `pixelle_video/services/comfyui_maintenance.py`: add extension release methods and combined `/free` + extension cleanup.
- Modify `tests/test_comfyui_maintenance.py`: prove call order, optional 404 handling, required 404 handling, and idle checks.
- Modify `pixelle_video/config/schema.py`, `pixelle_video/config/manager.py`, `web/components/settings.py`, `web/i18n/locales/zh_CN.json`, `web/i18n/locales/en_US.json`, `config.example.yaml`: expose `model_cleanup_mode`.
- Modify `tests/test_comfykit_config.py`: cover config defaults, manager exposure, and update path.
- Modify `pixelle_video/service.py`: wire model cleanup into pre-generation, OOM recovery, and IndexTTS2 session exit.
- Modify `tests/test_generation_coordinator.py`: cover local lifecycle behavior.
- Modify `docs/en/reference/config-schema.md`, `docs/zh/reference/config-schema.md`, `workflows/down/tts_index2_8g_依赖与下载说明.md`, `workflows/down/索引语音二代_依赖与下载说明.md`: document the new cleanup contract.

---

### Task 1: Patch ComfyUI-Index-TTS With A Managed Release Endpoint

**Files:**
- Modify: `tools/patch_indextts2_plugin.py`
- Test: `tests/test_patch_indextts2_plugin.py`

- [ ] **Step 1: Add failing plugin patch tests**

Append these samples and tests to `tests/test_patch_indextts2_plugin.py`.

```python
MODEL_LOADER_SAMPLE = """import os
import sys
import gc
import torch
from typing import Optional, Dict, Any


class IndexTTS2Loader:
    DEFAULT_DIRNAME = "IndexTTS-2"

    def __init__(self, models_root: Optional[str] = None, device: Optional[str] = None, dtype: Optional[str] = None):
        self._models_root = models_root or "models"
        self._model_dir = os.path.join(self._models_root, self.DEFAULT_DIRNAME)
        self._device = torch.device(device) if device else torch.device("cuda")
        self._dtype = torch.float16
        self._cache: Dict[str, Any] = {}

    def get_tts(self):
        if "tts" in self._cache:
            return self._cache["tts"]
        self._cache["tts"] = object()
        return self._cache["tts"]

    def unload_tts(self) -> None:
        try:
            tts = self._cache.pop("tts", None)
            del tts
        except Exception:
            pass
        try:
            gc.collect()
        except Exception:
            pass
        try:
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
        except Exception:
            pass
"""


PLUGIN_INIT_SAMPLE = '''"""IndexTTS custom node."""

import os
import sys

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
'''


def create_minimal_plugin_with_loader_and_init(tmp_path):
    plugin_dir, utils_path, infer_path = create_minimal_plugin(tmp_path)
    loader_path = plugin_dir / "indextts2" / "model_loader.py"
    init_path = plugin_dir / "__init__.py"
    loader_path.write_text(MODEL_LOADER_SAMPLE, encoding="utf-8")
    init_path.write_text(PLUGIN_INIT_SAMPLE, encoding="utf-8")
    return plugin_dir, utils_path, infer_path, loader_path, init_path


def test_patch_plugin_adds_indextts2_release_contract_idempotently(tmp_path):
    patch_module = load_module()
    plugin_dir, utils_path, infer_path, loader_path, init_path = create_minimal_plugin_with_loader_and_init(tmp_path)
    routes_path = plugin_dir / "pixelle_routes.py"

    first_result = patch_module.patch_plugin(plugin_dir)
    first_loader = loader_path.read_text(encoding="utf-8")
    first_init = init_path.read_text(encoding="utf-8")
    first_routes = routes_path.read_text(encoding="utf-8")
    second_result = patch_module.patch_plugin(plugin_dir)

    assert loader_path in first_result.changed_files
    assert init_path in first_result.changed_files
    assert routes_path in first_result.changed_files
    assert second_result.changed_files == []

    assert loader_path.read_text(encoding="utf-8") == first_loader
    assert init_path.read_text(encoding="utf-8") == first_init
    assert routes_path.read_text(encoding="utf-8") == first_routes

    assert "weakref.WeakSet()" in first_loader
    assert "_INDEXTTS2_LOADER_REGISTRY.add(self)" in first_loader
    assert "def unload_all_indextts2" in first_loader
    assert "cuda_allocated_before" in first_loader
    assert "torch.cuda.ipc_collect()" in first_loader
    assert "semantic_model" in first_loader
    assert "bigvgan" in first_loader

    assert "from . import pixelle_routes as _pixelle_routes" in first_init
    assert "@PromptServer.instance.routes.post(\"/pixelle/indextts2/free\")" in first_routes
    assert "unload_all_indextts2()" in first_routes


def test_patch_plugin_requires_model_loader_for_release_contract(tmp_path):
    patch_module = load_module()
    plugin_dir, utils_path, infer_path = create_minimal_plugin(tmp_path)

    with pytest.raises(FileNotFoundError, match="indextts2/model_loader.py"):
        patch_module.patch_plugin(plugin_dir)
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
uv run pytest tests/test_patch_indextts2_plugin.py::test_patch_plugin_adds_indextts2_release_contract_idempotently tests/test_patch_indextts2_plugin.py::test_patch_plugin_requires_model_loader_for_release_contract -q
```

Expected: both tests fail because `patch_plugin()` does not require or patch `indextts2/model_loader.py`, does not create `pixelle_routes.py`, and does not import the route file from plugin `__init__.py`.

- [ ] **Step 3: Add patch constants and target files**

In `tools/patch_indextts2_plugin.py`, add constants near the existing relative paths.

```python
MODEL_LOADER_RELATIVE_PATH = Path("indextts2") / "model_loader.py"
PLUGIN_INIT_RELATIVE_PATH = Path("__init__.py")
PIXELLE_ROUTES_RELATIVE_PATH = Path("pixelle_routes.py")
```

Update `patch_plugin()` so it resolves, requires, patches, and records these files.

```python
    model_loader_path = plugin_dir / MODEL_LOADER_RELATIVE_PATH
    plugin_init_path = plugin_dir / PLUGIN_INIT_RELATIVE_PATH
    routes_path = plugin_dir / PIXELLE_ROUTES_RELATIVE_PATH
    _require_file(model_loader_path, MODEL_LOADER_RELATIVE_PATH)
    _require_file(plugin_init_path, PLUGIN_INIT_RELATIVE_PATH)

    changed_files: list[Path] = []
    if _patch_file(utils_path, _patch_utils):
        changed_files.append(utils_path)
    if _patch_file(infer_path, _patch_infer_v2):
        changed_files.append(infer_path)
    if engine_path.exists() and _patch_file(engine_path, _patch_engine):
        changed_files.append(engine_path)
    if _patch_file(model_loader_path, _patch_model_loader):
        changed_files.append(model_loader_path)
    if _patch_file(plugin_init_path, _patch_plugin_init):
        changed_files.append(plugin_init_path)
    if _write_stable_file(routes_path, STABLE_PIXELLE_ROUTES):
        changed_files.append(routes_path)
    return PatchResult(changed_files=changed_files)
```

Add this helper after `_patch_file()`.

```python
def _write_stable_file(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8") if path.exists() else None
    if original == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True
```

- [ ] **Step 4: Add the model-loader patch implementation**

Add these helpers and stable code blocks to `tools/patch_indextts2_plugin.py`.

```python
def _patch_model_loader(text: str) -> str:
    text = _ensure_import(text, "import threading")
    text = _ensure_import(text, "import weakref")

    if "def unload_all_indextts2" not in text:
        text = text.replace("\n\nclass IndexTTS2Loader:", "\n\n" + STABLE_INDEXTTS2_RELEASE_SUPPORT + "class IndexTTS2Loader:", 1)

    if "_INDEXTTS2_LOADER_REGISTRY.add(self)" not in text:
        text = re.sub(
            r"(?P<indent>\s*)self\._cache:\s*Dict\[str,\s*Any\]\s*=\s*\{\}\s*$",
            "\\g<0>\n\\g<indent>with _INDEXTTS2_LOADER_REGISTRY_LOCK:\n\\g<indent>    _INDEXTTS2_LOADER_REGISTRY.add(self)",
            text,
            count=1,
            flags=re.MULTILINE,
        )

    return _replace_function(text, "unload_tts", STABLE_UNLOAD_TTS)


STABLE_INDEXTTS2_RELEASE_SUPPORT = '''_INDEXTTS2_LOADER_REGISTRY = weakref.WeakSet()
_INDEXTTS2_LOADER_REGISTRY_LOCK = threading.RLock()
_INDEXTTS2_TTS_ATTRS = (
    "gpt",
    "semantic_model",
    "semantic_codec",
    "s2mel",
    "campplus_model",
    "bigvgan",
    "qwen_emo",
    "extract_features",
    "semantic_mean",
    "semantic_std",
    "tokenizer",
    "model",
)


def _cuda_memory_stats() -> dict:
    stats = {
        "cuda_available": False,
        "cuda_allocated": None,
        "cuda_reserved": None,
    }
    try:
        if torch.cuda.is_available():
            stats["cuda_available"] = True
            stats["cuda_allocated"] = int(torch.cuda.memory_allocated())
            stats["cuda_reserved"] = int(torch.cuda.memory_reserved())
    except Exception as exc:
        stats["cuda_error"] = str(exc)
    return stats


def _clear_cuda_cache() -> None:
    try:
        gc.collect()
    except Exception:
        pass
    try:
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


def _release_tts_object(tts: Any) -> None:
    if tts is None:
        return
    for attr in _INDEXTTS2_TTS_ATTRS:
        try:
            if hasattr(tts, attr):
                setattr(tts, attr, None)
        except Exception:
            pass


def unload_all_indextts2() -> dict:
    before = _cuda_memory_stats()
    with _INDEXTTS2_LOADER_REGISTRY_LOCK:
        loaders = list(_INDEXTTS2_LOADER_REGISTRY)

    released = 0
    errors = []
    for loader in loaders:
        try:
            if loader.unload_tts():
                released += 1
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

    _clear_cuda_cache()
    after = _cuda_memory_stats()
    return {
        "released": released > 0,
        "loaders_seen": len(loaders),
        "loaders_released": released,
        "errors": errors,
        "cuda_allocated_before": before.get("cuda_allocated"),
        "cuda_allocated_after": after.get("cuda_allocated"),
        "cuda_reserved_before": before.get("cuda_reserved"),
        "cuda_reserved_after": after.get("cuda_reserved"),
    }


'''


STABLE_UNLOAD_TTS = '''def unload_tts(self) -> bool:
        """
        Best-effort unload of cached TTS instance and free GPU cache to reduce VRAM.
        Safe to call even if not loaded.
        """
        released = False
        try:
            tts = self._cache.pop("tts", None)
            released = tts is not None
            _release_tts_object(tts)
            del tts
        except Exception:
            pass
        _clear_cuda_cache()
        return released
'''
```

- [ ] **Step 5: Add route generation and plugin init import patch**

Add this patcher and stable route content to `tools/patch_indextts2_plugin.py`.

```python
def _patch_plugin_init(text: str) -> str:
    import_line = "from . import pixelle_routes as _pixelle_routes"
    if import_line in text:
        return text

    lines = text.splitlines()
    insert_at = 0
    if lines and lines[0].startswith('"""'):
        insert_at = 1
        while insert_at < len(lines) and not lines[insert_at].endswith('"""'):
            insert_at += 1
        insert_at = min(insert_at + 1, len(lines))

    while insert_at < len(lines) and (lines[insert_at].startswith("import ") or lines[insert_at].startswith("from ") or not lines[insert_at].strip()):
        insert_at += 1

    lines.insert(insert_at, import_line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


STABLE_PIXELLE_ROUTES = '''from aiohttp import web
from server import PromptServer

from .indextts2.model_loader import unload_all_indextts2


@PromptServer.instance.routes.post("/pixelle/indextts2/free")
async def pixelle_free_indextts2(request):
    result = unload_all_indextts2()
    status = 500 if result.get("errors") else 200
    return web.json_response(result, status=status)
'''
```

- [ ] **Step 6: Run plugin patch tests**

Run:

```powershell
uv run pytest tests/test_patch_indextts2_plugin.py -q
```

Expected: all tests in `tests/test_patch_indextts2_plugin.py` pass.

- [ ] **Step 7: Commit Task 1**

Run:

```powershell
git add tools/patch_indextts2_plugin.py tests/test_patch_indextts2_plugin.py
git commit -m "fix: 为 IndexTTS2 插件补充显存释放端点"
git push
```

---

### Task 2: Extend The Pixelle ComfyUI Maintenance Client

**Files:**
- Modify: `pixelle_video/services/comfyui_maintenance.py`
- Test: `tests/test_comfyui_maintenance.py`

- [ ] **Step 1: Add failing maintenance-client tests**

Append these tests to `tests/test_comfyui_maintenance.py`.

```python
@pytest.mark.asyncio
async def test_free_memory_with_extensions_calls_comfyui_free_then_indextts2_endpoint():
    transport = _RecordingTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    results = await client.free_memory_with_extensions("high", extensions=("indextts2",))

    assert [result.extension for result in results] == ["indextts2"]
    assert results[0].released is True
    assert transport.calls == [
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
        ("POST", "/pixelle/indextts2/free", {}),
    ]


@pytest.mark.asyncio
async def test_free_extension_models_treats_missing_optional_endpoint_as_warning(caplog):
    class _MissingEndpointTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/pixelle/indextts2/free":
                return httpx.Response(404, request=request)
            return httpx.Response(200, request=request)

    transport = _MissingEndpointTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    results = await client.free_extension_models(
        extensions=("indextts2",),
        missing_endpoint="optional",
    )

    assert results[0].extension == "indextts2"
    assert results[0].released is False
    assert results[0].missing_endpoint is True
    assert "tools/patch_indextts2_plugin.py" in results[0].message


@pytest.mark.asyncio
async def test_free_extension_models_raises_when_required_endpoint_is_missing():
    class _MissingEndpointTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/pixelle/indextts2/free":
                return httpx.Response(404, request=request)
            return httpx.Response(200, request=request)

    transport = _MissingEndpointTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    with pytest.raises(RuntimeError, match="/pixelle/indextts2/free"):
        await client.free_extension_models(
            extensions=("indextts2",),
            missing_endpoint="required",
        )


@pytest.mark.asyncio
async def test_free_extension_models_when_idle_skips_busy_queue():
    transport = _RecordingTransport(queue_payload={"queue_running": [["running"]], "queue_pending": []})
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    released = await client.free_extension_models_when_idle(extensions=("indextts2",))

    assert released is False
    assert transport.calls == [("GET", "/queue", None)]
```

- [ ] **Step 2: Run new tests and verify they fail**

Run:

```powershell
uv run pytest tests/test_comfyui_maintenance.py -q
```

Expected: the new tests fail because `ComfyUIMaintenanceClient` does not yet expose extension release methods or result objects.

- [ ] **Step 3: Add result type and extension endpoints**

In `pixelle_video/services/comfyui_maintenance.py`, add imports and types.

```python
from dataclasses import dataclass
from typing import Any
```

Add these definitions after the existing type aliases.

```python
ComfyUIExtensionName = Literal["indextts2"]
ComfyUIExtensionMissingEndpointMode = Literal["optional", "required"]

_EXTENSION_RELEASE_ENDPOINTS: dict[ComfyUIExtensionName, str] = {
    "indextts2": "/pixelle/indextts2/free",
}


@dataclass(frozen=True)
class ComfyUIExtensionReleaseResult:
    extension: str
    released: bool
    missing_endpoint: bool = False
    message: str = ""
    response: dict[str, Any] | None = None
```

- [ ] **Step 4: Implement extension release methods**

Add these methods inside `ComfyUIMaintenanceClient`.

```python
    async def free_memory_with_extensions(
        self,
        intensity: ComfyUIReleaseIntensity = "high",
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> list[ComfyUIExtensionReleaseResult]:
        await self.free_memory(intensity)
        return await self.free_extension_models(
            extensions=extensions,
            missing_endpoint=missing_endpoint,
        )

    async def free_extension_models(
        self,
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> list[ComfyUIExtensionReleaseResult]:
        results: list[ComfyUIExtensionReleaseResult] = []
        for extension in extensions:
            endpoint = _EXTENSION_RELEASE_ENDPOINTS[extension]
            try:
                response = await self._request("POST", endpoint, json={})
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    message = (
                        f"ComfyUI extension cleanup endpoint {endpoint} is missing. "
                        "Run tools/patch_indextts2_plugin.py against ComfyUI-Index-TTS, "
                        "then restart ComfyUI."
                    )
                    if missing_endpoint == "optional":
                        logger.warning(message)
                        results.append(
                            ComfyUIExtensionReleaseResult(
                                extension=extension,
                                released=False,
                                missing_endpoint=True,
                                message=message,
                            )
                        )
                        continue
                    raise RuntimeError(message) from exc
                raise

            payload = response.json()
            data = payload if isinstance(payload, dict) else {}
            results.append(
                ComfyUIExtensionReleaseResult(
                    extension=extension,
                    released=bool(data.get("released")),
                    response=data,
                )
            )
        return results

    async def free_extension_models_when_idle(
        self,
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> bool:
        queue = await self._get_queue()
        running, pending = self._queue_counts(queue)
        if running or pending:
            logger.info(
                "Skipping ComfyUI extension memory release because queue is busy "
                f"(running={running}, pending={pending})"
            )
            return False

        results = await self.free_extension_models(
            extensions=extensions,
            missing_endpoint=missing_endpoint,
        )
        return any(result.released for result in results)
```

- [ ] **Step 5: Update `_RecordingTransport` for endpoint payloads**

Update `_RecordingTransport.handle_async_request()` in `tests/test_comfyui_maintenance.py` so the extension endpoint returns useful JSON.

```python
        if request.url.path == "/queue" and request.method == "GET":
            if self.queue_payloads:
                return httpx.Response(200, json=self.queue_payloads.pop(0), request=request)
            return httpx.Response(200, json=self.queue_payload, request=request)
        if request.url.path == "/pixelle/indextts2/free":
            return httpx.Response(200, json={"released": True, "loaders_seen": 1, "loaders_released": 1}, request=request)
        return httpx.Response(200, request=request)
```

- [ ] **Step 6: Run maintenance tests**

Run:

```powershell
uv run pytest tests/test_comfyui_maintenance.py -q
```

Expected: all maintenance tests pass.

- [ ] **Step 7: Commit Task 2**

Run:

```powershell
git add pixelle_video/services/comfyui_maintenance.py tests/test_comfyui_maintenance.py
git commit -m "feat: 增加 ComfyUI 扩展显存释放客户端"
git push
```

---

### Task 3: Add Model Cleanup Configuration And Settings UI

**Files:**
- Modify: `pixelle_video/config/schema.py`
- Modify: `pixelle_video/config/manager.py`
- Modify: `web/components/settings.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `config.example.yaml`
- Test: `tests/test_comfykit_config.py`

- [ ] **Step 1: Add failing config tests**

Append these tests to `tests/test_comfykit_config.py`.

```python
def test_comfyui_model_cleanup_mode_defaults_to_extensions():
    config = PixelleVideoConfig()

    assert config.comfyui.model_cleanup_mode == "comfyui_and_extensions"


def test_comfyui_config_exposes_model_cleanup_mode(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                model_cleanup_mode="comfyui",
            )
        ),
    )

    assert config_manager.get_comfyui_config()["model_cleanup_mode"] == "comfyui"


def test_set_comfyui_config_updates_model_cleanup_mode(monkeypatch):
    config = PixelleVideoConfig()
    monkeypatch.setattr(config_manager, "config", config)

    config_manager.set_comfyui_config(model_cleanup_mode="disabled")

    assert config_manager.config.comfyui.model_cleanup_mode == "disabled"
```

- [ ] **Step 2: Run new config tests and verify they fail**

Run:

```powershell
uv run pytest tests/test_comfykit_config.py::test_comfyui_model_cleanup_mode_defaults_to_extensions tests/test_comfykit_config.py::test_comfyui_config_exposes_model_cleanup_mode tests/test_comfykit_config.py::test_set_comfyui_config_updates_model_cleanup_mode -q
```

Expected: tests fail because `model_cleanup_mode` does not exist yet.

- [ ] **Step 3: Add schema and manager support**

In `pixelle_video/config/schema.py`, add the field to `ComfyUIConfig` after `pre_generation_cleanup_timeout_seconds`.

```python
    model_cleanup_mode: Literal["disabled", "comfyui", "comfyui_and_extensions"] = Field(
        default="comfyui_and_extensions",
        description="Model memory cleanup scope used after forced queue cleanup and explicit recovery paths",
    )
```

In `pixelle_video/config/manager.py`, add it to `get_comfyui_config()`.

```python
            "model_cleanup_mode": self.config.comfyui.model_cleanup_mode,
```

Update `set_comfyui_config()` signature and body.

```python
        model_cleanup_mode: Optional[str] = None,
```

```python
        if model_cleanup_mode is not None:
            updates["model_cleanup_mode"] = model_cleanup_mode
```

- [ ] **Step 4: Add settings UI control**

In `web/components/settings.py`, add labels next to `cleanup_mode_labels`.

```python
                model_cleanup_labels = {
                    "disabled": tr("settings.comfyui.model_cleanup_disabled"),
                    "comfyui": tr("settings.comfyui.model_cleanup_comfyui"),
                    "comfyui_and_extensions": tr("settings.comfyui.model_cleanup_comfyui_and_extensions"),
                }
```

Resolve current value after `current_cleanup_mode`.

```python
                current_model_cleanup_mode = comfyui_config.get("model_cleanup_mode", "comfyui_and_extensions")
                if current_model_cleanup_mode not in model_cleanup_labels:
                    current_model_cleanup_mode = "comfyui_and_extensions"
```

Add the selectbox after `cleanup_timeout_seconds`.

```python
                model_cleanup_mode = st.selectbox(
                    tr("settings.comfyui.model_cleanup_mode"),
                    options=list(model_cleanup_labels.keys()),
                    index=list(model_cleanup_labels.keys()).index(current_model_cleanup_mode),
                    format_func=lambda key: model_cleanup_labels[key],
                    help=tr("settings.comfyui.model_cleanup_mode_help"),
                    key="comfyui_model_cleanup_mode_input",
                )
```

Pass the value to `set_comfyui_config()`.

```python
                        model_cleanup_mode=model_cleanup_mode,
```

- [ ] **Step 5: Add i18n keys**

Add these keys to `web/i18n/locales/zh_CN.json`.

```json
    "settings.comfyui.model_cleanup_mode": "模型显存释放",
    "settings.comfyui.model_cleanup_mode_help": "控制强制清理和恢复路径是否释放 ComfyUI 标准模型以及 Pixelle 管理的插件私有缓存。IndexTTS2 需要插件释放端点生效。",
    "settings.comfyui.model_cleanup_disabled": "不释放模型",
    "settings.comfyui.model_cleanup_comfyui": "仅 ComfyUI 标准模型",
    "settings.comfyui.model_cleanup_comfyui_and_extensions": "ComfyUI 标准模型 + 插件缓存",
```

Add these keys to `web/i18n/locales/en_US.json`.

```json
    "settings.comfyui.model_cleanup_mode": "Model VRAM Cleanup",
    "settings.comfyui.model_cleanup_mode_help": "Controls whether forced cleanup and recovery paths release ComfyUI-managed models and Pixelle-managed plugin private caches. IndexTTS2 requires the plugin release endpoint.",
    "settings.comfyui.model_cleanup_disabled": "Do not unload models",
    "settings.comfyui.model_cleanup_comfyui": "ComfyUI-managed models only",
    "settings.comfyui.model_cleanup_comfyui_and_extensions": "ComfyUI models + plugin caches",
```

- [ ] **Step 6: Update example config**

In `config.example.yaml`, add this line after `pre_generation_cleanup_timeout_seconds`.

```yaml
  model_cleanup_mode: comfyui_and_extensions  # disabled=no model unload, comfyui=/free only, comfyui_and_extensions=/free plus Pixelle plugin cache cleanup
```

- [ ] **Step 7: Run config tests**

Run:

```powershell
uv run pytest tests/test_comfykit_config.py -q
```

Expected: all config tests pass.

- [ ] **Step 8: Commit Task 3**

Run:

```powershell
git add pixelle_video/config/schema.py pixelle_video/config/manager.py web/components/settings.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json config.example.yaml tests/test_comfykit_config.py
git commit -m "feat: 增加 ComfyUI 模型显存释放配置"
git push
```

---

### Task 4: Wire Cleanup Into Pixelle Local ComfyUI Lifecycle

**Files:**
- Modify: `pixelle_video/service.py`
- Test: `tests/test_generation_coordinator.py`

- [ ] **Step 1: Add failing lifecycle tests**

Append these tests to `tests/test_generation_coordinator.py`.

```python
@pytest.mark.asyncio
async def test_prepare_comfyui_for_local_workflow_releases_models_when_configured(monkeypatch):
    events = []

    class _Client:
        def __init__(
            self,
            base_url,
            *,
            api_key=None,
            timeout=5.0,
            transport=None,
            idle_wait_timeout=20.0,
        ):
            events.append(("client", base_url, api_key, idle_wait_timeout))

        async def cleanup_before_generation(self, mode):
            events.append(("cleanup", mode))

        async def free_memory_with_extensions(self, intensity="high", *, extensions=("indextts2",), missing_endpoint="optional"):
            events.append(("free_with_extensions", intensity, extensions, missing_endpoint))
            return []

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                comfyui_api_key="secret",
                pre_generation_cleanup_mode="force",
                model_cleanup_mode="comfyui_and_extensions",
            )
        ),
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)

    core = PixelleVideoCore()

    await core.prepare_comfyui_for_local_workflow()

    assert events == [
        ("client", "http://127.0.0.1:8000", "secret", 20.0),
        ("cleanup", "force"),
        ("free_with_extensions", "high", ("indextts2",), "optional"),
    ]


@pytest.mark.asyncio
async def test_force_release_comfyui_memory_uses_required_extension_endpoint(monkeypatch):
    events = []

    class _Client:
        def __init__(self, base_url, *, api_key=None):
            events.append(("client", base_url, api_key))

        async def free_memory_with_extensions(self, intensity="high", *, extensions=("indextts2",), missing_endpoint="optional"):
            events.append(("free_with_extensions", intensity, extensions, missing_endpoint))
            return []

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                comfyui_api_key="secret",
                model_cleanup_mode="comfyui_and_extensions",
            )
        ),
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)

    core = PixelleVideoCore()

    assert await core.force_release_comfyui_memory(context="oom-recovery") is True
    assert events == [
        ("client", "http://127.0.0.1:8000", "secret"),
        ("free_with_extensions", "high", ("indextts2",), "required"),
    ]


@pytest.mark.asyncio
async def test_index_tts2_workflow_session_releases_extension_once_at_session_exit():
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        events.append(("prepare",))

    async def _release_extension(*, context, missing_endpoint="optional"):
        events.append(("release_extension", context, missing_endpoint))
        return True

    async def _get_kit():
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_extension_models_when_idle = _release_extension
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_workflow_session():
        await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_index2.json",
            {},
            workflow_source="selfhost",
        )
        await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_index2.json",
            {},
            workflow_source="selfhost",
        )

    assert events == [
        ("prepare",),
        ("execute", "workflows/selfhost/tts_index2.json"),
        ("execute", "workflows/selfhost/tts_index2.json"),
        ("release_extension", "post-index-tts2-workflow", "optional"),
    ]
```

- [ ] **Step 2: Run new lifecycle tests and verify they fail**

Run:

```powershell
uv run pytest tests/test_generation_coordinator.py::test_prepare_comfyui_for_local_workflow_releases_models_when_configured tests/test_generation_coordinator.py::test_force_release_comfyui_memory_uses_required_extension_endpoint tests/test_generation_coordinator.py::test_index_tts2_workflow_session_releases_extension_once_at_session_exit -q
```

Expected: tests fail because service lifecycle does not call the new maintenance methods or track IndexTTS2 session usage.

- [ ] **Step 3: Import IndexTTS2 workflow detection**

In `pixelle_video/service.py`, add this import near other Pixelle imports.

```python
from pixelle_video.tts_workflow_contract import is_index_tts2_workflow_key
```

- [ ] **Step 4: Track IndexTTS2 use in local sessions and task scopes**

Extend `_LocalComfyUIWorkflowSession`.

```python
        self.used_index_tts2 = False
```

Extend `_LocalComfyUITaskScope`.

```python
        self.pending_extension_memory_release = False
```

Add this helper to `PixelleVideoCore`.

```python
    def _mark_index_tts2_workflow_use(self, workflow_input) -> None:
        if not is_index_tts2_workflow_key(workflow_input):
            return

        session = self._local_comfyui_workflow_session.get()
        if session is not None:
            session.used_index_tts2 = True

        scope = self._local_comfyui_task_scope.get()
        if scope is not None:
            scope.pending_extension_memory_release = True
```

Call it before each local workflow execution:

- In `_execute_scoped_local_comfykit_workflow()`, immediately before `return await self._execute_local_comfykit_workflow(...)`.
- In `execute_comfykit_workflow()` standalone selfhost path, immediately after `await self._register_local_comfyui_task_use()`.

- [ ] **Step 5: Add model cleanup helpers in `service.py`**

Add this helper.

```python
    def _get_comfyui_model_cleanup_mode(self, comfyui_config: dict) -> str:
        mode = (comfyui_config.get("model_cleanup_mode") or "comfyui_and_extensions").lower()
        if mode not in {"disabled", "comfyui", "comfyui_and_extensions"}:
            logger.warning(f"Unsupported ComfyUI model cleanup mode: {mode}")
            return "disabled"
        return mode
```

Add this method.

```python
    async def release_comfyui_extension_models_when_idle(
        self,
        *,
        context: str,
        missing_endpoint: str = "optional",
    ) -> bool:
        self.config = config_manager.config.to_dict()
        comfyui_config = self.config.get("comfyui", {})
        base_url = comfyui_config.get("comfyui_url")
        if not base_url:
            return False

        client = ComfyUIMaintenanceClient(
            base_url,
            api_key=comfyui_config.get("comfyui_api_key"),
        )
        try:
            released = await client.free_extension_models_when_idle(
                extensions=("indextts2",),
                missing_endpoint=missing_endpoint,
            )
            if released:
                logger.info(f"Released ComfyUI extension model cache after {context}")
            return released
        except Exception as e:
            logger.warning(f"ComfyUI {context} extension memory release failed, continuing: {e}")
            return False
```

- [ ] **Step 6: Wire pre-generation model cleanup**

In `prepare_comfyui_for_local_workflow()`, after `await client.cleanup_before_generation(mode)`, add:

```python
            model_cleanup_mode = self._get_comfyui_model_cleanup_mode(comfyui_config)
            if model_cleanup_mode == "comfyui":
                await client.free_memory("high")
            elif model_cleanup_mode == "comfyui_and_extensions":
                await client.free_memory_with_extensions(
                    "high",
                    extensions=("indextts2",),
                    missing_endpoint="optional",
                )
```

- [ ] **Step 7: Wire OOM forced release**

In `force_release_comfyui_memory()`, replace the current `await client.free_memory("high")` call with:

```python
            model_cleanup_mode = self._get_comfyui_model_cleanup_mode(comfyui_config)
            if model_cleanup_mode == "disabled":
                return False
            if model_cleanup_mode == "comfyui":
                await client.free_memory("high")
            else:
                await client.free_memory_with_extensions(
                    "high",
                    extensions=("indextts2",),
                    missing_endpoint="required",
                )
            return True
```

- [ ] **Step 8: Release IndexTTS2 once at session exit**

Update `_release_local_comfyui_after_workflow_session()`:

```python
        if session.used_index_tts2:
            released = await self.release_comfyui_extension_models_when_idle(
                context="post-index-tts2-workflow",
                missing_endpoint="optional",
            )
            if released:
                self._mark_local_comfyui_released()
                scope = self._local_comfyui_task_scope.get()
                if scope is not None:
                    scope.pending_extension_memory_release = False
            return
```

Place that block before the existing `if self._should_release_local_comfyui_after_workflow():` block.

Update `local_comfyui_task_scope()` exit so it retries extension release when the session release did not succeed.

```python
                if scope.pending_extension_memory_release and should_release:
                    released = await self.release_comfyui_extension_models_when_idle(
                        context="post-task-index-tts2-fallback",
                        missing_endpoint="optional",
                    )
                    if released:
                        scope.pending_extension_memory_release = False
```

Place this before the existing normal `release_comfyui_after_local_task()` fallback.

- [ ] **Step 9: Update existing lifecycle tests whose expectations change**

Change `test_index_tts2_workflow_session_defers_normal_release_to_task_exit()` so it expects extension release at session exit rather than normal task release. Rename it to `test_index_tts2_workflow_session_releases_extension_at_session_exit()`.

Use this expected event list:

```python
    assert events == [
        ("prepare",),
        ("execute", "workflows/selfhost/tts_index2.json"),
        ("extension_release", "post-index-tts2-workflow"),
    ]
```

Change `test_index_tts2_workflow_session_does_not_force_release_on_normal_completion()` so it asserts `force_release_comfyui_memory` is still not called, while extension release is called once.

Use this event list after the task scope exits:

```python
    assert events == [
        ("prepare",),
        ("execute", "workflows/selfhost/tts_index2.json"),
        ("extension_release", "post-index-tts2-workflow"),
    ]
```

- [ ] **Step 10: Run lifecycle tests**

Run:

```powershell
uv run pytest tests/test_generation_coordinator.py -q
```

Expected: all lifecycle tests pass.

- [ ] **Step 11: Commit Task 4**

Run:

```powershell
git add pixelle_video/service.py tests/test_generation_coordinator.py
git commit -m "fix: 接入 IndexTTS2 显存释放生命周期"
git push
```

---

### Task 5: Update Documentation And Verify The Full Cleanup Contract

**Files:**
- Modify: `docs/en/reference/config-schema.md`
- Modify: `docs/zh/reference/config-schema.md`
- Modify: `workflows/down/tts_index2_8g_依赖与下载说明.md`
- Modify: `workflows/down/索引语音二代_依赖与下载说明.md`

- [ ] **Step 1: Update English config docs**

In `docs/en/reference/config-schema.md`, add `model_cleanup_mode` to the ComfyUI example.

```yaml
comfyui:
  pre_generation_cleanup_mode: "force"
  pre_generation_cleanup_timeout_seconds: 20
  model_cleanup_mode: "comfyui_and_extensions"
```

Add this bullet near the existing cleanup bullets.

```markdown
- `model_cleanup_mode`: Model memory cleanup scope used after forced queue cleanup and explicit recovery paths. `disabled` leaves models loaded, `comfyui` calls ComfyUI `/free`, and `comfyui_and_extensions` calls `/free` plus Pixelle-managed extension cleanup endpoints such as `/pixelle/indextts2/free`.
```

- [ ] **Step 2: Update Chinese config docs**

In `docs/zh/reference/config-schema.md`, add `model_cleanup_mode` to the ComfyUI example.

```yaml
comfyui:
  pre_generation_cleanup_mode: "force"
  pre_generation_cleanup_timeout_seconds: 20
  model_cleanup_mode: "comfyui_and_extensions"
```

Add this bullet near the cleanup bullets.

```markdown
- `model_cleanup_mode`：强制队列清理和显式恢复路径使用的模型显存释放范围。`disabled` 保留模型常驻，`comfyui` 调用 ComfyUI `/free`，`comfyui_and_extensions` 会同时调用 `/free` 和 Pixelle 管理的插件清理端点，例如 `/pixelle/indextts2/free`。
```

- [ ] **Step 3: Update IndexTTS2 workflow dependency docs**

In both `workflows/down/tts_index2_8g_依赖与下载说明.md` and `workflows/down/索引语音二代_依赖与下载说明.md`, add this section near the existing plugin patch instructions.

````markdown
### Pixelle 显存释放补丁

Pixelle 通过 `tools/patch_indextts2_plugin.py` 管理 `ComfyUI-Index-TTS` 的本地兼容补丁。该脚本现在还会安装 `POST /pixelle/indextts2/free` 端点，用于释放插件私有的 IndexTTS2 PyTorch 缓存。

执行补丁：

```powershell
python tools\patch_indextts2_plugin.py --target E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS
```

验证端点文件已安装：

```powershell
Test-Path E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS\pixelle_routes.py
Select-String -Path E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS\pixelle_routes.py -Pattern "/pixelle/indextts2/free"
```

补丁后需要重启 ComfyUI。Pixelle 的 `model_cleanup_mode: comfyui_and_extensions` 会先调用 ComfyUI `/free`，再调用 `/pixelle/indextts2/free`，从而覆盖 z-image 这类标准模型和 IndexTTS2 插件私有缓存。
````

- [ ] **Step 4: Run focused tests**

Run:

```powershell
uv run pytest tests/test_patch_indextts2_plugin.py tests/test_comfyui_maintenance.py tests/test_comfykit_config.py tests/test_generation_coordinator.py -q
```

Expected: all focused tests pass.

- [ ] **Step 5: Run the existing selfhost workflow assertions**

Run:

```powershell
uv run pytest tests/test_selfhost_workflows.py tests/test_tts_service_workflow_params.py -q
```

Expected: tests pass and `tts_index2_8g.json` still asserts `keep_models_cached` is `true`.

- [ ] **Step 6: Commit Task 5**

Run:

```powershell
git add docs/en/reference/config-schema.md docs/zh/reference/config-schema.md workflows/down/tts_index2_8g_依赖与下载说明.md workflows/down/索引语音二代_依赖与下载说明.md
git commit -m "docs: 说明 IndexTTS2 显存释放补丁"
git push
```

---

## Final Verification

- [ ] **Step 1: Run all focused tests**

Run:

```powershell
uv run pytest tests/test_patch_indextts2_plugin.py tests/test_comfyui_maintenance.py tests/test_comfykit_config.py tests/test_generation_coordinator.py tests/test_selfhost_workflows.py tests/test_tts_service_workflow_params.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Apply the plugin patch to the live ComfyUI-Index-TTS install**

Run:

```powershell
python tools\patch_indextts2_plugin.py --target E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS
```

Expected: output lists patched files or reports the plugin is already patched. Restart ComfyUI after this command so the new route is registered.

- [ ] **Step 3: Verify the live route file exists**

Run:

```powershell
Test-Path E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS\pixelle_routes.py
Select-String -Path E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS\pixelle_routes.py -Pattern "/pixelle/indextts2/free"
```

Expected: `Test-Path` prints `True`, and `Select-String` prints the route registration line.

- [ ] **Step 4: Verify ComfyUI route after restart**

Run after restarting ComfyUI:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/pixelle/indextts2/free
```

Expected: JSON includes `released`, `loaders_seen`, `loaders_released`, `cuda_allocated_before`, and `cuda_allocated_after`.

- [ ] **Step 5: Confirm no unintended workflow cache change**

Run:

```powershell
Select-String -Path workflows\selfhost\tts_index2_8g.json -Pattern '"keep_models_cached": true'
```

Expected: the line remains present.
