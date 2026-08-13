import json
from datetime import datetime

import pytest
from loguru import logger

from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.services.history_manager import HistoryManager
from pixelle_video.services.persistence import PersistenceService
from pixelle_video.utils.logging_util import (
    attach_task_log_sinks,
    log_exception_once,
    setup_logging,
    teardown_logging,
)


def test_persistence_service_exposes_task_log_paths(tmp_path):
    persistence = PersistenceService(output_dir=str(tmp_path))

    assert persistence.get_task_logs_dir("task-1") == tmp_path / "task-1" / "logs"
    assert persistence.get_task_runtime_log_path("task-1") == tmp_path / "task-1" / "logs" / "runtime.jsonl"
    assert persistence.get_task_ai_creation_log_path("task-1") == tmp_path / "task-1" / "logs" / "ai_creation.jsonl"


def test_attach_task_log_sinks_stops_writing_after_close(tmp_path):
    task_dir = tmp_path / "task-1"
    task_dir.mkdir(parents=True, exist_ok=True)

    session = attach_task_log_sinks(task_id="task-1", task_dir=task_dir)
    try:
        logger.bind(channel="runtime").info("first task line")
    finally:
        session.close()

    logger.bind(task_id="task-2", channel="runtime").info("later task line")

    contents = (task_dir / "logs" / "runtime.jsonl").read_text(encoding="utf-8")
    assert "first task line" in contents
    assert "later task line" not in contents


def test_task_exception_log_remains_one_json_object_per_line(tmp_path):
    global_log_dir = tmp_path / "global"
    global_sinks = setup_logging(
        service_name="web",
        config={
            "enabled": True,
            "level": "INFO",
            "log_dir": str(global_log_dir),
            "rotation_mb": 50,
            "retention_days": 14,
        },
    )
    task_dir = tmp_path / "task-exception"
    session = attach_task_log_sinks(task_id="task-exception", task_dir=task_dir)
    try:
        try:
            raise RuntimeError("render failed")
        except RuntimeError as error:
            log_exception_once(error, "task generation failed")
    finally:
        session.close()
        teardown_logging(global_sinks)

    lines = (task_dir / "logs" / "runtime.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["exception_type"] == "RuntimeError"
    assert payload["exception_message"] == "<redacted>"
    assert "render failed" not in lines[0]
    assert "RuntimeError" in payload["exception_traceback"]


@pytest.mark.asyncio
async def test_standard_pipeline_setup_environment_binds_task_observability(monkeypatch, tmp_path):
    task_dir = tmp_path / "task-3"
    persistence = PersistenceService(output_dir=str(tmp_path))
    core = type(
        "Core",
        (),
        {
            "llm": None,
            "tts": None,
            "media": None,
            "video": None,
            "persistence": persistence,
        },
    )()
    pipeline = StandardPipeline(core)
    ctx = PipelineContext(
        input_text="demo",
        params={"request_id": "req_1234", "session_id": "sess_5678", "api_task_id": "api-task-1"},
        request_id="req_1234",
        session_id="sess_5678",
        api_task_id="api-task-1",
    )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.create_task_output_dir",
        lambda: (str(task_dir), "task-3"),
    )

    await pipeline.setup_environment(ctx)
    try:
        logger.bind(channel="runtime").info("standard setup line")
    finally:
        ctx.task_log_session.close()

    assert ctx.observability["request_id"] == "req_1234"
    assert ctx.observability["session_id"] == "sess_5678"
    assert ctx.observability["api_task_id"] == "api-task-1"
    assert ctx.observability["task_id"] == "task-3"
    assert (task_dir / "logs" / "runtime.jsonl").exists()
    assert "standard setup line" in (task_dir / "logs" / "runtime.jsonl").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_history_manager_task_detail_includes_observability(tmp_path):
    persistence = PersistenceService(output_dir=str(tmp_path))
    history = HistoryManager(persistence)

    await persistence.save_task_metadata(
        "task-2",
        {
            "created_at": datetime.now(),
            "status": "completed",
            "input": {"text": "demo"},
            "result": {"video_path": "output/final.mp4"},
            "config": {},
            "observability": {
                "version": "v1",
                "ai_creation": {"slowest_stage": "storyboard_planning"},
            },
        },
    )

    detail = await history.get_task_detail("task-2")

    assert detail["observability"]["ai_creation"]["slowest_stage"] == "storyboard_planning"
