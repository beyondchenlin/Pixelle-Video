# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared async batch runner for LLM prompt generation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, Sequence, TypeVar

from loguru import logger

from pixelle_video.models.progress import ProgressI18nMessage

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


@dataclass(frozen=True)
class PromptBatch(Generic[TInput]):
    """One indexed input batch."""

    index: int
    start_index: int
    items: list[TInput]


@dataclass(frozen=True)
class PromptBatchRunResult(Generic[TOutput]):
    """Ordered outputs and observability counters from a batch run."""

    outputs: list[TOutput]
    call_count: int
    retry_count: int
    batch_total: int


class PromptBatchRunError(RuntimeError):
    """Batch execution failed after retries; includes partial run metrics."""

    def __init__(
        self,
        message: str,
        *,
        call_count: int,
        retry_count: int,
        batch_total: int,
        failed_batch_index: int,
    ):
        super().__init__(message)
        self.call_count = call_count
        self.retry_count = retry_count
        self.batch_total = batch_total
        self.failed_batch_index = failed_batch_index


BatchRunner = Callable[[PromptBatch[TInput], int], Awaitable[Sequence[TOutput]]]
ProgressCallback = Callable[[int, int, ProgressI18nMessage], None]
ProgressMessageFactory = Callable[[int, int], ProgressI18nMessage]


def _default_progress_message(batch_index: int, batch_total: int) -> ProgressI18nMessage:
    return ProgressI18nMessage(
        key="progress.batch_completed",
        params={"current": batch_index, "total": batch_total},
        fallback=f"Batch {batch_index}/{batch_total} completed",
    )


def _normalize_progress_message(message: Any) -> ProgressI18nMessage:
    if isinstance(message, ProgressI18nMessage):
        return message

    text = str(message or "").strip()
    if not text:
        return ProgressI18nMessage(key="", fallback="")
    return ProgressI18nMessage(key=text, fallback=text)


def chunk_prompt_batches(items: Sequence[TInput], batch_size: int) -> list[PromptBatch[TInput]]:
    """Split inputs into indexed batches while preserving global positions."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    normalized = list(items)
    return [
        PromptBatch(
            index=batch_number,
            start_index=start_index,
            items=normalized[start_index:start_index + batch_size],
        )
        for batch_number, start_index in enumerate(
            range(0, len(normalized), batch_size),
            start=1,
        )
    ]


def normalize_prompt_concurrency(max_concurrency: int | None) -> int:
    """Normalize optional concurrency settings to a safe minimum."""
    if max_concurrency is None:
        return 1
    return max(1, int(max_concurrency))


async def run_prompt_batches(
    *,
    items: Sequence[TInput],
    batch_size: int,
    max_concurrency: int | None,
    max_retries: int,
    run_batch: BatchRunner[TInput, TOutput],
    progress_callback: ProgressCallback | None = None,
    progress_message: ProgressMessageFactory | None = None,
) -> PromptBatchRunResult[TOutput]:
    """Run prompt batches with bounded concurrency, retry, cancellation, and stable output order."""
    if max_retries < 1:
        raise ValueError("max_retries must be at least 1")

    batches = chunk_prompt_batches(items, batch_size)
    if not batches:
        return PromptBatchRunResult(outputs=[], call_count=0, retry_count=0, batch_total=0)

    concurrency = normalize_prompt_concurrency(max_concurrency)
    total_items = len(items)
    completed_items = 0
    call_count = 0
    retry_count = 0
    state_lock = asyncio.Lock()

    async def execute_batch(batch: PromptBatch[TInput]) -> tuple[int, list[TOutput]]:
        nonlocal completed_items, call_count, retry_count

        for attempt in range(1, max_retries + 1):
            try:
                async with state_lock:
                    call_count += 1
                    if attempt > 1:
                        retry_count += 1

                outputs = list(await run_batch(batch, attempt))
                if len(outputs) != len(batch.items):
                    raise ValueError(
                        f"Batch {batch.index} prompt count mismatch: "
                        f"expected {len(batch.items)}, got {len(outputs)}"
                    )

                async with state_lock:
                    completed_items += len(outputs)
                    completed_count = completed_items
                if progress_callback is not None:
                    message = _default_progress_message(batch.index, len(batches))
                    if progress_message is not None:
                        try:
                            message = _normalize_progress_message(
                                progress_message(batch.index, len(batches))
                            )
                        except Exception as exc:
                            logger.warning(f"Prompt batch progress message failed: {exc}")
                    try:
                        progress_callback(completed_count, total_items, message)
                    except Exception as exc:
                        logger.warning(f"Prompt batch progress callback failed: {exc}")

                return batch.start_index, outputs
            except Exception as exc:
                if attempt >= max_retries:
                    async with state_lock:
                        failed_call_count = call_count
                        failed_retry_count = retry_count
                    raise PromptBatchRunError(
                        str(exc),
                        call_count=failed_call_count,
                        retry_count=failed_retry_count,
                        batch_total=len(batches),
                        failed_batch_index=batch.index,
                    ) from exc

        raise RuntimeError("unreachable prompt batch retry state")

    if concurrency <= 1:
        results = [await execute_batch(batch) for batch in batches]
    else:
        semaphore = asyncio.Semaphore(concurrency)

        async def execute_with_semaphore(batch: PromptBatch[TInput]) -> tuple[int, list[TOutput]]:
            async with semaphore:
                return await execute_batch(batch)

        tasks = [
            asyncio.create_task(execute_with_semaphore(batch))
            for batch in batches
        ]
        try:
            results = await asyncio.gather(*tasks)
        except Exception:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    ordered_outputs = [
        output
        for _, outputs in sorted(results, key=lambda item: item[0])
        for output in outputs
    ]
    return PromptBatchRunResult(
        outputs=ordered_outputs,
        call_count=call_count,
        retry_count=retry_count,
        batch_total=len(batches),
    )
