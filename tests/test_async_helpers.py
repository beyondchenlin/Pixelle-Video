import asyncio
import sys
from types import SimpleNamespace

import pytest

from web.state import async_runtime
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


def test_run_async_attaches_streamlit_context_to_runtime_thread(monkeypatch):
    captured = []
    fake_ctx = SimpleNamespace(session_id="test-session")

    def fake_add_script_run_ctx(thread, ctx=None):
        captured.append((thread.name, ctx))
        return thread

    monkeypatch.setattr(async_runtime, "get_script_run_ctx", lambda suppress_warning=True: fake_ctx)
    monkeypatch.setattr(async_runtime, "add_script_run_ctx", fake_add_script_run_ctx, raising=False)

    async def get_value():
        return 42

    try:
        assert run_async(get_value()) == 42
    finally:
        shutdown_all_async_runtimes()

    assert captured
    assert captured[-1][1] is fake_ctx


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
