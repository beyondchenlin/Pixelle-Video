import pytest

from pixelle_video.utils.prompt_batching import PromptBatch, run_prompt_batches


@pytest.mark.asyncio
async def test_run_prompt_batches_ignores_progress_callback_errors_without_retry():
    calls = 0

    async def run_batch(batch: PromptBatch[str], attempt: int):
        nonlocal calls
        calls += 1
        return list(batch.items)

    def broken_progress_callback(completed: int, total: int, message: str):
        raise RuntimeError("progress sink failed")

    result = await run_prompt_batches(
        items=["scene 1", "scene 2"],
        batch_size=2,
        max_concurrency=1,
        max_retries=3,
        run_batch=run_batch,
        progress_callback=broken_progress_callback,
    )

    assert result.outputs == ["scene 1", "scene 2"]
    assert result.call_count == 1
    assert result.retry_count == 0
    assert calls == 1


@pytest.mark.asyncio
async def test_run_prompt_batches_ignores_progress_message_errors_without_retry():
    calls = 0
    progress_events = []

    async def run_batch(batch: PromptBatch[str], attempt: int):
        nonlocal calls
        calls += 1
        return list(batch.items)

    def broken_progress_message(batch_index: int, batch_total: int):
        raise RuntimeError("progress message failed")

    result = await run_prompt_batches(
        items=["scene 1", "scene 2"],
        batch_size=2,
        max_concurrency=1,
        max_retries=3,
        run_batch=run_batch,
        progress_callback=lambda completed, total, message: progress_events.append(
            (completed, total, message)
        ),
        progress_message=broken_progress_message,
    )

    assert result.outputs == ["scene 1", "scene 2"]
    assert result.call_count == 1
    assert result.retry_count == 0
    assert calls == 1
    assert progress_events == [(2, 2, "Batch 1/1 completed")]
