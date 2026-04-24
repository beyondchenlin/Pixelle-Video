import asyncio

from loguru import logger

from pixelle_video.utils.logging_util import attach_task_log_sinks


async def _write_task_line(task_dir, task_id, message):
    session = attach_task_log_sinks(task_id=task_id, task_dir=task_dir)
    try:
        logger.bind(channel="runtime").info(message)
        await asyncio.sleep(0)
        logger.bind(channel="ai_creation", stage="title_generation", event="end").info(f"{message} ai")
    finally:
        session.close()


async def _run_parallel_writes(task_a_dir, task_b_dir):
    await asyncio.gather(
        _write_task_line(task_a_dir, "task-a", "only task a"),
        _write_task_line(task_b_dir, "task-b", "only task b"),
    )


def test_parallel_task_log_sessions_do_not_cross_write(tmp_path):
    task_a_dir = tmp_path / "task-a"
    task_b_dir = tmp_path / "task-b"

    asyncio.run(_run_parallel_writes(task_a_dir, task_b_dir))

    task_a_runtime = (task_a_dir / "logs" / "runtime.jsonl").read_text(encoding="utf-8")
    task_b_runtime = (task_b_dir / "logs" / "runtime.jsonl").read_text(encoding="utf-8")
    task_a_ai = (task_a_dir / "logs" / "ai_creation.jsonl").read_text(encoding="utf-8")

    assert "only task a" in task_a_runtime
    assert "only task b" not in task_a_runtime
    assert "only task b" in task_b_runtime
    assert "only task a" not in task_b_runtime
    assert "only task a ai" in task_a_ai
