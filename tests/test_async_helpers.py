import asyncio
import sys
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from types import SimpleNamespace

import pytest
from loguru import logger

from tests.support.async_runner import run_coroutine_in_isolated_thread
from web.state import async_runtime
from web.state import session as session_state
from web.state.async_runtime import shutdown_all_async_runtimes
from web.utils.async_helpers import run_async


def test_isolated_test_runner_preserves_calling_thread_event_loop():
    def verify_loop_ownership() -> int:
        calling_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(calling_loop)
        try:
            result = run_coroutine_in_isolated_thread(asyncio.sleep(0, result=42))
            assert asyncio.get_event_loop() is calling_loop
            return result
        finally:
            asyncio.set_event_loop(None)
            calling_loop.close()

    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(verify_loop_ownership).result() == 42


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


def test_session_exists_returns_true_for_reconnectable_streamlit_sessions(monkeypatch):
    reconnectable_info = SimpleNamespace(session_id="reconnectable")
    fake_runtime = SimpleNamespace(
        is_active_session=lambda session_id: False,
        _session_mgr=SimpleNamespace(
            get_session_info=lambda session_id: reconnectable_info
            if session_id == "reconnectable"
            else None
        ),
    )

    monkeypatch.setattr(async_runtime, "streamlit_runtime_exists", lambda: True)
    monkeypatch.setattr(async_runtime, "get_streamlit_runtime", lambda: fake_runtime)

    assert async_runtime.session_exists("reconnectable") is True


def test_cleanup_stale_runtimes_keeps_reconnectable_sessions(monkeypatch):
    reconnectable_info = SimpleNamespace(session_id="reconnectable")
    fake_runtime_api = SimpleNamespace(
        is_active_session=lambda session_id: session_id == "current",
        _session_mgr=SimpleNamespace(
            get_session_info=lambda session_id: reconnectable_info
            if session_id in {"current", "reconnectable"}
            else None
        ),
    )

    class FakeRuntime:
        def __init__(self):
            self.close_calls = 0

        def close(self, async_cleanup=None):
            self.close_calls += 1
            return True

    current_runtime = FakeRuntime()
    reconnectable_runtime = FakeRuntime()

    monkeypatch.setattr(async_runtime, "streamlit_runtime_exists", lambda: True)
    monkeypatch.setattr(async_runtime, "get_streamlit_runtime", lambda: fake_runtime_api)

    async_runtime._RUNTIMES.clear()
    async_runtime._RUNTIMES.update(
        {
            "current": async_runtime.ManagedAsyncRuntime(runtime=current_runtime),
            "reconnectable": async_runtime.ManagedAsyncRuntime(runtime=reconnectable_runtime),
        }
    )

    try:
        async_runtime._cleanup_stale_runtimes("current")
        assert "reconnectable" in async_runtime._RUNTIMES
    finally:
        async_runtime._RUNTIMES.clear()

    assert reconnectable_runtime.close_calls == 0


def test_cleanup_stale_runtimes_keeps_handles_when_close_fails(monkeypatch):
    fake_runtime_api = SimpleNamespace(
        is_active_session=lambda session_id: session_id == "current",
        _session_mgr=SimpleNamespace(
            get_session_info=lambda session_id: object() if session_id == "current" else None
        ),
    )

    class FakeRuntime:
        def __init__(self, should_close):
            self.should_close = should_close
            self.close_calls = 0

        def close(self, async_cleanup=None):
            self.close_calls += 1
            return self.should_close

    current_runtime = FakeRuntime(True)
    stale_runtime = FakeRuntime(False)

    monkeypatch.setattr(async_runtime, "streamlit_runtime_exists", lambda: True)
    monkeypatch.setattr(async_runtime, "get_streamlit_runtime", lambda: fake_runtime_api)

    async_runtime._RUNTIMES.clear()
    async_runtime._RUNTIMES.update(
        {
            "current": async_runtime.ManagedAsyncRuntime(runtime=current_runtime),
            "stale": async_runtime.ManagedAsyncRuntime(runtime=stale_runtime),
        }
    )

    try:
        async_runtime._cleanup_stale_runtimes("current")
        assert "stale" in async_runtime._RUNTIMES
    finally:
        async_runtime._RUNTIMES.clear()

    assert stale_runtime.close_calls == 1


def test_atexit_async_runtime_shutdown_does_not_log_to_closed_streams(capsys):
    class FakeRuntime:
        def __init__(self):
            self.close_calls = 0

        def close(self, async_cleanup=None):
            self.close_calls += 1
            return True

    closed_stream = StringIO()
    sink_id = logger.add(closed_stream, level="INFO")
    closed_stream.close()
    fake_runtime = FakeRuntime()
    async_runtime._RUNTIMES.clear()
    async_runtime._RUNTIMES[async_runtime.DEFAULT_SESSION_KEY] = (
        async_runtime.ManagedAsyncRuntime(runtime=fake_runtime)
    )

    try:
        async_runtime._shutdown_all_async_runtimes_at_exit()
    finally:
        try:
            logger.remove(sink_id)
        except ValueError:
            pass
        async_runtime._RUNTIMES.clear()

    captured = capsys.readouterr()
    assert fake_runtime.close_calls == 1
    assert "Logging error in Loguru Handler" not in captured.err
    assert "I/O operation on closed file" not in captured.err
    assert "Cleaning up async runtime" not in captured.err


def test_cleanup_stale_pixelle_video_sessions_keeps_reconnectable_sessions(monkeypatch):
    monkeypatch.setattr(session_state, "session_exists", lambda session_id: session_id != "missing")

    current_state = session_state._PixelleVideoSessionState(
        pixelle_video=object(),
        config_hash="current",
    )
    reconnectable_state = session_state._PixelleVideoSessionState(
        pixelle_video=object(),
        config_hash="reconnectable",
    )
    missing_state = session_state._PixelleVideoSessionState(
        pixelle_video=object(),
        config_hash="missing",
    )

    session_state._PIXELLE_VIDEO_SESSIONS.clear()
    session_state._PIXELLE_VIDEO_SESSIONS.update(
        {
            "current": current_state,
            "reconnectable": reconnectable_state,
            "missing": missing_state,
        }
    )

    try:
        session_state._cleanup_stale_pixelle_video_sessions("current")
        assert "reconnectable" in session_state._PIXELLE_VIDEO_SESSIONS
        assert "missing" not in session_state._PIXELLE_VIDEO_SESSIONS
    finally:
        session_state._PIXELLE_VIDEO_SESSIONS.clear()


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
