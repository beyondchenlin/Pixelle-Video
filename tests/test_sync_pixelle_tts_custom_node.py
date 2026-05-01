import pytest

import tools.sync_pixelle_tts_custom_node as sync_module


def test_sync_tree_replaces_existing_files(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "custom_nodes" / "ComfyUI-Pixelle-TTS"
    (source / "nested").mkdir(parents=True)
    target.mkdir(parents=True)

    (source / "nested" / "plugin.py").write_text("new", encoding="utf-8")
    (target / "old.py").write_text("old", encoding="utf-8")

    sync_module.sync_tree(source, target)

    assert (target / "nested" / "plugin.py").read_text(encoding="utf-8") == "new"
    assert not (target / "old.py").exists()


def test_sync_tree_rejects_custom_nodes_root_target(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "custom_nodes"
    source.mkdir()
    target.mkdir()

    with pytest.raises(ValueError, match="plugin directory"):
        sync_module.sync_tree(source, target)


def test_resolve_target_path_uses_custom_nodes_env(monkeypatch, tmp_path):
    custom_nodes_dir = tmp_path / "custom_nodes"
    monkeypatch.setenv("COMFYUI_CUSTOM_NODES_DIR", str(custom_nodes_dir))
    monkeypatch.delenv("COMFYUI_ROOT", raising=False)

    resolved = sync_module.resolve_target_path(None)

    assert resolved == custom_nodes_dir / "ComfyUI-Pixelle-TTS"


def test_resolve_python_executable_uses_env_override(monkeypatch, tmp_path):
    python_executable = tmp_path / "python.exe"
    python_executable.write_text("", encoding="utf-8")
    monkeypatch.setenv("COMFYUI_PYTHON", str(python_executable))

    resolved = sync_module.resolve_python_executable(None)

    assert resolved == python_executable
