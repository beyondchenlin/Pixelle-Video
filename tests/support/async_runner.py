from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

ResultT = TypeVar("ResultT")


def run_coroutine_in_isolated_thread(
    coroutine: Coroutine[Any, Any, ResultT],
) -> ResultT:
    """Run a synchronous-adapter coroutine without changing the test thread's loop."""

    with ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="pixelle-test-async-runner",
    ) as executor:
        return executor.submit(asyncio.run, coroutine).result()
