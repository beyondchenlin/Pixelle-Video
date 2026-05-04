import importlib.util
import sys
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
    assert '"safe_to_continue": safe_to_continue' in routes_text
    assert "cuda_allocated_after <= _SAFE_CUDA_ALLOCATED_BYTES" in routes_text
    assert "256 * 1024 * 1024" in routes_text
    assert '"diagnostic_objects": diagnostic_objects' in routes_text
    assert '"residual_objects": [] if safe_to_continue else diagnostic_objects' in routes_text


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
