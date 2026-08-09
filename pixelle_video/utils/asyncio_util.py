from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

_T = TypeVar("_T")


async def await_cancel_safe_cleanup(awaitable: Awaitable[_T]) -> _T:
    """Finish mandatory cleanup before propagating an outer cancellation."""

    cleanup_task = asyncio.ensure_future(awaitable)
    cancellation_requested = False
    while True:
        try:
            result = await asyncio.shield(cleanup_task)
            break
        except asyncio.CancelledError:
            if cleanup_task.cancelled():
                raise
            cancellation_requested = True

    if cancellation_requested:
        raise asyncio.CancelledError
    return result


__all__ = ["await_cancel_safe_cleanup"]
