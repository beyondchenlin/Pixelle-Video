from pathlib import Path

from tools import install_pixelle_release_protocol as installer


def test_installer_accepts_existing_directory_link_that_resolves_to_source(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "source"
    source.mkdir()
    custom_nodes = tmp_path / "custom_nodes"
    custom_nodes.mkdir()
    plugin_link = custom_nodes / "ComfyUI-Pixelle-Release-Protocol"
    plugin_link.mkdir()
    original_resolve = Path.resolve

    def _resolve(path, *args, **kwargs):
        if path == plugin_link:
            return original_resolve(source, *args, **kwargs)
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(installer, "PIXELLE_PLUGIN", source)
    monkeypatch.setattr(Path, "resolve", _resolve)

    assert installer.install_pixelle_plugin(custom_nodes) is True


def test_installer_rejects_existing_directory_with_different_target(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "source"
    source.mkdir()
    custom_nodes = tmp_path / "custom_nodes"
    custom_nodes.mkdir()
    (custom_nodes / "ComfyUI-Pixelle-Release-Protocol").mkdir()
    monkeypatch.setattr(installer, "PIXELLE_PLUGIN", source)

    assert installer.install_pixelle_plugin(custom_nodes) is False
