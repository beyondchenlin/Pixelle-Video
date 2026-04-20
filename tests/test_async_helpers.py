import asyncio
import sys

import pytest

from web.state.async_runtime import shutdown_all_async_runtimes
from web.utils.async_helpers import run_async


def test_run_async_reuses_the_same_event_loop_across_calls():
    async def get_loop_id():
        return id(asyncio.get_running_loop())

    try:
        first_loop_id = run_async(get_loop_id())
        second_loop_id = run_async(get_loop_id())
    finally:
        shutdown_all_async_runtimes()

    assert first_loop_id == second_loop_id


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific event loop behavior")
def test_run_async_supports_subprocesses_with_selector_policy():
    previous_policy = asyncio.get_event_loop_policy()
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async def spawn_python():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "print('pixelle')",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        return stdout.decode().strip()

    try:
        assert run_async(spawn_python()) == "pixelle"
    finally:
        shutdown_all_async_runtimes()
        asyncio.set_event_loop_policy(previous_policy)
