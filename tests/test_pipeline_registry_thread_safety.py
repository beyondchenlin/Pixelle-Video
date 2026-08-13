from __future__ import annotations

from threading import Event, Thread

from web.pipelines import base


def test_registration_waits_for_registry_write_lock(monkeypatch):
    monkeypatch.setattr(base, "_pipeline_uis", {})
    instance_created = Event()

    class _ConcurrentPipeline(base.PipelineUI):
        name = "concurrent"

        def __init__(self):
            instance_created.set()

    worker = Thread(target=base.register_pipeline_ui, args=(_ConcurrentPipeline,))
    with base._pipeline_uis_lock:
        worker.start()
        assert instance_created.wait(timeout=1)
        assert "concurrent" not in base._pipeline_uis

    worker.join(timeout=1)
    assert not worker.is_alive()
    assert base.get_pipeline_ui("concurrent") is not None


def test_registry_readers_receive_stable_snapshots(monkeypatch):
    monkeypatch.setattr(base, "_pipeline_uis", {})

    class _FirstPipeline(base.PipelineUI):
        name = "first"

    class _SecondPipeline(base.PipelineUI):
        name = "second"

    base.register_pipeline_ui(_FirstPipeline)
    snapshot = base.get_all_pipeline_uis()
    base.register_pipeline_ui(_SecondPipeline)

    assert [pipeline.name for pipeline in snapshot] == ["first"]
    assert [pipeline.name for pipeline in base.get_all_pipeline_uis()] == [
        "first",
        "second",
    ]
