import importlib.util
import sys
import types
from pathlib import Path

from tools import patch_gguf_plugin


PLUGIN_INIT_SAMPLE = """from .nodes import NODE_CLASS_MAPPINGS
"""


def _write_plugin(tmp_path: Path) -> Path:
    plugin_dir = tmp_path / "ComfyUI-GGUF"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text(PLUGIN_INIT_SAMPLE, encoding="utf-8")
    return plugin_dir


def test_patch_plugin_writes_routes_and_import(tmp_path):
    plugin_dir = _write_plugin(tmp_path)

    result = patch_gguf_plugin.patch_plugin(plugin_dir)

    changed = {path.name for path in result.changed_files}
    assert changed == {"__init__.py", "pixelle_routes.py"}
    init_text = (plugin_dir / "__init__.py").read_text(encoding="utf-8")
    routes_text = (plugin_dir / "pixelle_routes.py").read_text(encoding="utf-8")
    assert "from . import pixelle_routes as _pixelle_routes" in init_text
    assert '@PromptServer.instance.routes.get("/pixelle/gguf/health")' in routes_text
    assert '@PromptServer.instance.routes.post("/pixelle/gguf/free")' in routes_text
    assert '"extension": "gguf"' in routes_text
    assert '"protocol_version": 2' in routes_text
    assert '"contract_revision": _PIXELLE_GGUF_RELEASE_CONTRACT_REVISION' in routes_text
    assert "_PIXELLE_GGUF_RELEASE_CONTRACT_REVISION = 2" in routes_text
    assert '"safe_to_continue": safe_to_continue' in routes_text
    assert "safe_to_continue = not errors and not residual_objects" in routes_text
    assert "_SAFE_CUDA_ALLOCATED_BYTES" not in routes_text
    assert '"diagnostic_objects": diagnostic_objects' in routes_text
    assert '"residual_objects": residual_objects' in routes_text
    assert '"release_confirmation_reason": release_confirmation_reason' in routes_text


def test_patch_plugin_is_idempotent(tmp_path):
    plugin_dir = _write_plugin(tmp_path)

    first = patch_gguf_plugin.patch_plugin(plugin_dir)
    second = patch_gguf_plugin.patch_plugin(plugin_dir)

    assert {path.name for path in first.changed_files} == {"__init__.py", "pixelle_routes.py"}
    assert second.changed_files == []


def test_main_requires_target_or_env(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GGUF_PLUGIN_DIR", raising=False)

    try:
        patch_gguf_plugin.main([])
    except ValueError as exc:
        assert "GGUF_PLUGIN_DIR" in str(exc)
    else:
        raise AssertionError("expected ValueError when target is missing")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_generated_route_confirms_safe_after_material_cuda_release(monkeypatch):
    module, gguf_object = _load_generated_routes(
        monkeypatch,
        cuda_allocated=[9_588_530_156, 1_620_772_680],
        cuda_reserved=[9_596_567_552, 1_711_276_032],
    )
    monkeypatch.setattr(module.gc, "get_objects", lambda: [gguf_object])

    result = module.unload_gguf_models()

    assert result["safe_to_continue"] is True
    assert result["release_confirmation_reason"] == "gguf_cuda_allocated_decreased"
    assert result["contract_revision"] == 2
    assert result["diagnostic_objects"] == ["GGUFModelPatcher"]
    assert result["residual_objects"] == []
    assert result["errors"] == []


def test_generated_route_blocks_residual_object_when_cuda_release_is_only_noise(monkeypatch):
    module, gguf_object = _load_generated_routes(
        monkeypatch,
        cuda_allocated=[9_588_530_156, 9_588_529_132],
        cuda_reserved=[9_596_567_552, 9_596_567_552],
    )
    monkeypatch.setattr(module.gc, "get_objects", lambda: [gguf_object])

    result = module.unload_gguf_models()

    assert result["safe_to_continue"] is False
    assert result["release_confirmation_reason"] == "gguf_objects_residual"
    assert result["diagnostic_objects"] == ["GGUFModelPatcher"]
    assert result["residual_objects"] == ["GGUFModelPatcher"]


def test_generated_route_blocks_errors_even_after_cuda_release(monkeypatch):
    module, gguf_object = _load_generated_routes(
        monkeypatch,
        cuda_allocated=[9_588_530_156, 1_620_772_680],
        cuda_reserved=[9_596_567_552, 1_711_276_032],
        unload_error=RuntimeError("release failed"),
    )
    monkeypatch.setattr(module.gc, "get_objects", lambda: [gguf_object])

    result = module.unload_gguf_models()

    assert result["safe_to_continue"] is False
    assert result["release_confirmation_reason"] == "gguf_release_errors"
    assert result["residual_objects"] == []
    assert result["errors"] == ["release failed"]


def _load_generated_routes(
    monkeypatch,
    *,
    cuda_allocated: list[int],
    cuda_reserved: list[int],
    unload_error: Exception | None = None,
):
    class _FakeCuda:
        def __init__(self) -> None:
            self._allocated = list(cuda_allocated)
            self._reserved = list(cuda_reserved)

        def is_available(self):
            return True

        def current_device(self):
            return 0

        def memory_allocated(self, _device):
            return self._allocated.pop(0)

        def memory_reserved(self, _device):
            return self._reserved.pop(0)

        def synchronize(self):
            return None

        def empty_cache(self):
            return None

        def ipc_collect(self):
            return None

    class _FakeModelManagement:
        def unload_all_models(self):
            if unload_error is not None:
                raise unload_error

        def soft_empty_cache(self):
            return None

    class _FakeRoutes:
        def get(self, _path):
            return lambda handler: handler

        def post(self, _path):
            return lambda handler: handler

    class GGUFModelPatcher:
        pass

    gguf_object = GGUFModelPatcher()
    torch_module = types.SimpleNamespace(cuda=_FakeCuda())
    comfy_module = types.ModuleType("comfy")
    model_management_module = _FakeModelManagement()
    comfy_module.model_management = model_management_module
    nodes_module = types.ModuleType("custom_nodes.ComfyUI_GGUF.nodes")
    nodes_module.GGUFModelPatcher = GGUFModelPatcher
    server_module = types.SimpleNamespace(
        PromptServer=types.SimpleNamespace(instance=types.SimpleNamespace(routes=_FakeRoutes()))
    )

    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "comfy", comfy_module)
    monkeypatch.setitem(sys.modules, "comfy.model_management", model_management_module)
    monkeypatch.setitem(sys.modules, "custom_nodes.ComfyUI_GGUF.nodes", nodes_module)
    monkeypatch.setitem(sys.modules, "server", server_module)

    spec = importlib.util.spec_from_loader("pixelle_gguf_routes_under_test", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(patch_gguf_plugin.STABLE_PIXELLE_GGUF_ROUTES, module.__dict__)
    monkeypatch.setattr(module.gc, "collect", lambda: 0)
    return module, gguf_object
