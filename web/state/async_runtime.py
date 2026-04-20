import asyncio
import atexit
import sys
import threading
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from loguru import logger

try:
    from streamlit.runtime.scriptrunner_utils.script_run_context import add_script_run_ctx
    from streamlit.runtime import exists as streamlit_runtime_exists
    from streamlit.runtime import get_instance as get_streamlit_runtime
    from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
except Exception:  # pragma: no cover - raw mode or API changes
    add_script_run_ctx = None
    streamlit_runtime_exists = None
    get_streamlit_runtime = None
    get_script_run_ctx = None


DEFAULT_SESSION_KEY = "__default__"


def _create_event_loop() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()


class AsyncRuntime:
    """Run async work on a dedicated, long-lived event loop."""

    def __init__(self, name: str, streamlit_ctx=None):
        self._name = name
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ready = threading.Event()
        self._closed = False
        self._close_lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"PixelleAsyncRuntime-{name}",
            daemon=True,
        )
        self._attach_streamlit_context(streamlit_ctx)
        self._thread.start()
        self._ready.wait()

    def _attach_streamlit_context(self, ctx):
        if add_script_run_ctx is None or ctx is None:
            return
        add_script_run_ctx(self._thread, ctx=ctx)

    def _run_loop(self):
        loop = _create_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()

        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()

            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

            loop.run_until_complete(loop.shutdown_asyncgens())
            if hasattr(loop, "shutdown_default_executor"):
                loop.run_until_complete(loop.shutdown_default_executor())
            loop.close()

    def run(self, coro):
        """Submit a coroutine to the runtime loop and wait for the result."""
        if self._closed or self._loop is None:
            coro.close()
            raise RuntimeError(f"Async runtime '{self._name}' is closed")

        if threading.current_thread() is self._thread:
            coro.close()
            raise RuntimeError("run_async cannot be called from inside the async runtime thread")

        self._attach_streamlit_context(_get_streamlit_context())
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result()
        except Exception:
            if not future.done():
                future.cancel()
            raise

    def close(self, async_cleanup: Optional[Callable[[], Awaitable[None]]] = None):
        """Stop the runtime after running optional async cleanup on the same loop."""
        with self._close_lock:
            if self._closed:
                return

            if self._loop is not None and async_cleanup is not None:
                try:
                    self.run(async_cleanup())
                except Exception as e:
                    logger.warning(f"Async runtime cleanup failed for '{self._name}': {e}")

            self._closed = True
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._loop.stop)

        self._thread.join(timeout=5)
        self._loop = None


@dataclass
class ManagedAsyncRuntime:
    runtime: AsyncRuntime
    async_cleanup: Optional[Callable[[], Awaitable[None]]] = None


_RUNTIMES: dict[str, ManagedAsyncRuntime] = {}
_RUNTIMES_LOCK = threading.Lock()


def _get_streamlit_context():
    if get_script_run_ctx is None:
        return None
    return get_script_run_ctx(suppress_warning=True)


def get_current_session_key() -> str:
    """Return the active Streamlit session ID, or a default key outside Streamlit."""
    ctx = _get_streamlit_context()
    if ctx is None:
        return DEFAULT_SESSION_KEY
    return ctx.session_id


def is_session_active(session_key: str) -> bool:
    """Check whether a Streamlit session is still active."""
    if session_key == DEFAULT_SESSION_KEY:
        return True

    if streamlit_runtime_exists is None or not streamlit_runtime_exists():
        return False

    try:
        return get_streamlit_runtime().is_active_session(session_key)
    except Exception:
        logger.debug(f"Failed to query Streamlit session activity for {session_key}")
        return False


def _cleanup_stale_runtimes(current_session_key: str):
    stale_keys = []
    with _RUNTIMES_LOCK:
        for session_key in _RUNTIMES:
            if session_key in {DEFAULT_SESSION_KEY, current_session_key}:
                continue
            if not is_session_active(session_key):
                stale_keys.append(session_key)

        stale_handles = [(_RUNTIMES.pop(key), key) for key in stale_keys]

    for handle, session_key in stale_handles:
        logger.info(f"Cleaning up async runtime for inactive session: {session_key}")
        handle.runtime.close(async_cleanup=handle.async_cleanup)


def get_async_runtime() -> AsyncRuntime:
    """Get the async runtime for the current Streamlit session."""
    session_key = get_current_session_key()
    _cleanup_stale_runtimes(session_key)

    with _RUNTIMES_LOCK:
        handle = _RUNTIMES.get(session_key)
        if handle is None:
            handle = ManagedAsyncRuntime(
                runtime=AsyncRuntime(session_key, streamlit_ctx=_get_streamlit_context())
            )
            _RUNTIMES[session_key] = handle
        return handle.runtime


def register_async_cleanup(
    async_cleanup: Callable[[], Awaitable[None]],
    session_key: Optional[str] = None,
):
    """Register session-scoped async cleanup to run before the runtime stops."""
    resolved_session_key = session_key or get_current_session_key()
    _cleanup_stale_runtimes(resolved_session_key)

    with _RUNTIMES_LOCK:
        handle = _RUNTIMES.get(resolved_session_key)
        if handle is None:
            handle = ManagedAsyncRuntime(
                runtime=AsyncRuntime(resolved_session_key, streamlit_ctx=_get_streamlit_context())
            )
            _RUNTIMES[resolved_session_key] = handle
        handle.async_cleanup = async_cleanup


def shutdown_all_async_runtimes():
    """Shutdown all managed runtimes. Used by tests and process exit."""
    with _RUNTIMES_LOCK:
        handles = list(_RUNTIMES.values())
        _RUNTIMES.clear()

    for handle in handles:
        handle.runtime.close(async_cleanup=handle.async_cleanup)


atexit.register(shutdown_all_async_runtimes)
