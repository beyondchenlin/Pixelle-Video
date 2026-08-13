from __future__ import annotations

from web import home_editor_prewarm


def _reset_prewarm_state() -> None:
    home_editor_prewarm._PREWARMING_PIPELINES.clear()
    home_editor_prewarm._PREWARMED_PIPELINES.clear()


def test_prewarm_imports_dependencies_and_selected_pipeline(monkeypatch):
    imported = []
    loaded = []
    _reset_prewarm_state()
    monkeypatch.setattr(home_editor_prewarm, "import_module", imported.append)
    monkeypatch.setattr(
        home_editor_prewarm,
        "get_pipeline_ui",
        lambda name: loaded.append(name) or object(),
    )

    home_editor_prewarm._PREWARMING_PIPELINES.add("quick_create")
    home_editor_prewarm._prewarm_home_editor_dependencies(
        "quick_create",
        delay_seconds=0,
    )

    assert imported == list(home_editor_prewarm._EDITOR_DEPENDENCY_MODULES)
    assert loaded == ["quick_create"]
    assert "quick_create" in home_editor_prewarm._PREWARMED_PIPELINES
    assert "quick_create" not in home_editor_prewarm._PREWARMING_PIPELINES


def test_prewarm_schedule_is_deduplicated(monkeypatch):
    started = []
    _reset_prewarm_state()

    class _FakeThread:
        def __init__(self, **kwargs):
            started.append(kwargs)

        def start(self):
            return None

    monkeypatch.setattr(home_editor_prewarm, "Thread", _FakeThread)

    assert home_editor_prewarm.schedule_home_editor_prewarm("quick_create") is True
    assert home_editor_prewarm.schedule_home_editor_prewarm("quick_create") is False
    assert len(started) == 1
    assert started[0]["daemon"] is True
