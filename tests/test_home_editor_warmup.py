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

    assert imported[:-1] == list(home_editor_warmup._CORE_IMPORT_MODULES)
    assert imported[-1] == "web.pipelines.standard"
    assert snapshot.status is home_editor_warmup.HomeEditorWarmupStatus.SUCCEEDED


def test_core_only_warmup_supports_registered_extensions_without_guessing_imports():
    imported = []

    snapshot = home_editor_warmup._execute_home_editor_warmup(
        None,
        module_importer=lambda name: imported.append(name),
    )

    assert imported == list(home_editor_warmup._CORE_IMPORT_MODULES)
    assert snapshot.target is None
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
        lambda target: home_editor_warmup.HomeEditorWarmupSnapshot(
            target=target,
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


def test_unexpected_execution_failure_does_not_abandon_remaining_queue(monkeypatch):
    executed = []

    def _execute(target):
        executed.append(target)
        if target == "quick_create":
            raise RuntimeError("unexpected worker failure")
        return home_editor_warmup.HomeEditorWarmupSnapshot(
            target=target,
            status=home_editor_warmup.HomeEditorWarmupStatus.SUCCEEDED,
        )

    monkeypatch.setattr(home_editor_warmup, "_execute_home_editor_warmup", _execute)
    home_editor_warmup._WARMUP_QUEUE.extend(["quick_create", "image_to_video"])
    home_editor_warmup._WARMUP_WORKER_RUNNING = True

    home_editor_warmup._run_home_editor_warmup_queue(initial_delay_seconds=0)

    assert executed == ["quick_create", "image_to_video"]
    assert home_editor_warmup._WARMUP_WORKER_RUNNING is False
    assert home_editor_warmup.get_home_editor_warmup_snapshot(
        "quick_create"
    ).status is home_editor_warmup.HomeEditorWarmupStatus.FAILED
    assert home_editor_warmup.get_home_editor_warmup_snapshot(
        "image_to_video"
    ).status is home_editor_warmup.HomeEditorWarmupStatus.SUCCEEDED


def test_worker_start_failure_closes_every_concurrently_queued_target(monkeypatch):
    class _FailingThread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            assert home_editor_warmup.schedule_home_editor_warmup(
                "image_to_video"
            ) is True
            raise RuntimeError("thread unavailable")

    monkeypatch.setattr(home_editor_warmup, "Thread", _FailingThread)

    assert home_editor_warmup.schedule_home_editor_warmup("quick_create") is False
    assert list(home_editor_warmup._WARMUP_QUEUE) == []
    assert home_editor_warmup._WARMUP_WORKER_RUNNING is False
    assert home_editor_warmup.get_home_editor_warmup_snapshot("quick_create") is None
    assert home_editor_warmup.get_home_editor_warmup_snapshot("image_to_video") is None


def test_delay_failure_releases_worker_and_allows_a_retry(monkeypatch):
    home_editor_warmup._WARMUP_QUEUE.append("quick_create")
    home_editor_warmup._WARMUP_SNAPSHOTS["quick_create"] = (
        home_editor_warmup.HomeEditorWarmupSnapshot(
            target="quick_create",
            status=home_editor_warmup.HomeEditorWarmupStatus.PENDING,
        )
    )
    home_editor_warmup._WARMUP_WORKER_RUNNING = True
    monkeypatch.setattr(
        home_editor_warmup.time,
        "sleep",
        lambda _delay: (_ for _ in ()).throw(RuntimeError("sleep failure")),
    )

    home_editor_warmup._run_home_editor_warmup_queue(initial_delay_seconds=0.5)

    assert home_editor_warmup._WARMUP_WORKER_RUNNING is False
    assert list(home_editor_warmup._WARMUP_QUEUE) == []
    assert home_editor_warmup.get_home_editor_warmup_snapshot("quick_create") is None
