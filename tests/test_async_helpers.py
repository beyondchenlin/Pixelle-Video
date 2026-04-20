import asyncio
import sys

import pytest

from web.utils.async_helpers import run_async


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
        asyncio.set_event_loop_policy(previous_policy)
