import pytest

from pixelle_video.models.llm_interaction_trace import LLMTraceRecordingError
from pixelle_video.models.progress import ProgressI18nMessage
from pixelle_video.utils.prompt_batching import PromptBatch, run_prompt_batches


@pytest.mark.asyncio
async def test_run_prompt_batches_ignores_progress_callback_errors_without_retry():
    calls = 0

    async def run_batch(batch: PromptBatch[str], attempt: int):
        nonlocal calls
        calls += 1
        return list(batch.items)

    def broken_progress_callback(completed: int, total: int, message: ProgressI18nMessage):
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
async def test_run_prompt_batches_does_not_retry_or_wrap_trace_recording_errors():
    calls = 0
    trace_error = LLMTraceRecordingError("trace persistence failed")

    async def run_batch(batch: PromptBatch[str], attempt: int):
        nonlocal calls
        calls += 1
        raise trace_error

    with pytest.raises(LLMTraceRecordingError) as exc_info:
        await run_prompt_batches(
            items=["scene 1"],
            batch_size=1,
            max_concurrency=1,
            max_retries=3,
            run_batch=run_batch,
        )

    assert exc_info.value is trace_error
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
    assert progress_events == [
        (
            2,
            2,
            ProgressI18nMessage(
                key="progress.batch_completed",
                params={"current": 1, "total": 1},
                fallback="Batch 1/1 completed",
            ),
        )
    ]


@pytest.mark.asyncio
async def test_run_prompt_batches_accepts_custom_structured_progress_message():
    progress_events = []

    async def run_batch(batch: PromptBatch[str], attempt: int):
        return list(batch.items)

    result = await run_prompt_batches(
        items=["scene 1", "scene 2"],
        batch_size=2,
        max_concurrency=1,
        max_retries=2,
        run_batch=run_batch,
        progress_callback=lambda completed, total, message: progress_events.append(
            (completed, total, message)
        ),
        progress_message=lambda batch_index, batch_total: ProgressI18nMessage(
            key="progress.custom_batch",
            params={"batch": batch_index, "total": batch_total},
            fallback=f"Custom {batch_index}/{batch_total}",
        ),
    )

    assert result.outputs == ["scene 1", "scene 2"]
    assert progress_events == [
        (
            2,
            2,
            ProgressI18nMessage(
                key="progress.custom_batch",
                params={"batch": 1, "total": 1},
                fallback="Custom 1/1",
            ),
        )
    ]


@pytest.mark.asyncio
async def test_run_prompt_batches_keeps_legacy_string_progress_message_compatible():
    progress_events = []

    async def run_batch(batch: PromptBatch[str], attempt: int):
        return list(batch.items)

    result = await run_prompt_batches(
        items=["scene 1", "scene 2"],
        batch_size=2,
        max_concurrency=1,
        max_retries=2,
        run_batch=run_batch,
        progress_callback=lambda completed, total, message: progress_events.append(
            (completed, total, message)
        ),
        progress_message=lambda batch_index, batch_total: f"Legacy {batch_index}/{batch_total}",
    )

    assert result.outputs == ["scene 1", "scene 2"]
    assert progress_events == [
        (
            2,
            2,
            ProgressI18nMessage(
                key="Legacy 1/1",
                params={},
                fallback="Legacy 1/1",
            ),
        )
    ]
