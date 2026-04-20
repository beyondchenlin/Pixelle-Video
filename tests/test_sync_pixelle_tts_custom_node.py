from tools.sync_pixelle_tts_custom_node import sync_tree


def test_sync_tree_replaces_existing_files(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    (source / "nested").mkdir(parents=True)
    target.mkdir()

    (source / "nested" / "plugin.py").write_text("new", encoding="utf-8")
    (target / "old.py").write_text("old", encoding="utf-8")

    sync_tree(source, target)

    assert (target / "nested" / "plugin.py").read_text(encoding="utf-8") == "new"
    assert not (target / "old.py").exists()
