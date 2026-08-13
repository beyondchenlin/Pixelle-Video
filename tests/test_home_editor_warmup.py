from __future__ import annotations

import pytest

from web import home_editor_warmup


@pytest.fixture(autouse=True)
def _isolated_warmup_state():
    with home_editor_warmup._WARMUP_LOCK:
        home_editor_warmup._WARMUP_QUEUE.clear()
        home_editor_warmup._WARMUP_SNAPSHOTS.clear()
        home_editor_warmup._WARMUP_WORKER_RUNNING = False
    yield
    with home_editor_warmup._WARMUP_LOCK:
        home_editor_warmup._WARMUP_QUEUE.clear()
        home_editor_warmup._WARMUP_SNAPSHOTS.clear()
        home_editor_warmup._WARMUP_WORKER_RUNNING = False


def test_warmup_imports_only_allowlisted_modules():
    imported = []

    snapshot = home_editor_warmup._execute_home_editor_warmup(
        "quick_create",
        module_importer=lambda name: imported.append(name),
    )

    assert imported[0] == "web.pipelines.standard"
    assert imported[1:] == list(home_editor_warmup._CORE_IMPORT_MODULES)
    assert snapshot.status is home_editor_warmup.HomeEditorWarmupStatus.SUCCEEDED


def test_unknown_pipeline_is_rejected_without_imports():
    imported = []

    snapshot = home_editor_warmup._execute_home_editor_warmup(
        "../../untrusted",
        module_importer=lambda name: imported.append(name),
    )

    assert imported == []
    assert snapshot.status is home_editor_warmup.HomeEditorWarmupStatus.FAILED
    assert home_editor_warmup.schedule_home_editor_warmup("../../untrusted") is False


def test_warmup_schedule_is_deduplicated_and_uses_one_daemon_worker(monkeypatch):
    started = []

    class _FakeThread:
        def __init__(self, **kwargs):
            started.append(kwargs)

        def start(self):
            return None

    monkeypatch.setattr(home_editor_warmup, "Thread", _FakeThread)

    assert home_editor_warmup.schedule_home_editor_warmup("quick_create") is True
    assert home_editor_warmup.schedule_home_editor_warmup("quick_create") is False
    assert home_editor_warmup.schedule_home_editor_warmup("image_to_video") is True
    assert len(started) == 1
    assert started[0]["daemon"] is True
    assert list(home_editor_warmup._WARMUP_QUEUE) == [
        "quick_create",
        "image_to_video",
    ]


def test_failed_warmup_is_not_retried_on_every_rerun(monkeypatch):
    monkeypatch.setattr(
        home_editor_warmup,
        "_execute_home_editor_warmup",
        lambda pipeline_name: home_editor_warmup.HomeEditorWarmupSnapshot(
            pipeline_name=pipeline_name,
            status=home_editor_warmup.HomeEditorWarmupStatus.FAILED,
        ),
    )
    home_editor_warmup._WARMUP_QUEUE.append("quick_create")
    home_editor_warmup._WARMUP_WORKER_RUNNING = True

    home_editor_warmup._run_home_editor_warmup_queue(initial_delay_seconds=0)

    snapshot = home_editor_warmup.get_home_editor_warmup_snapshot("quick_create")
    assert snapshot is not None
    assert snapshot.status is home_editor_warmup.HomeEditorWarmupStatus.FAILED
    assert home_editor_warmup.schedule_home_editor_warmup("quick_create") is False
