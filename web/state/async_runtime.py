import asyncio
import atexit
import sys
import threading
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from loguru import logger

try:
    from streamlit.runtime import exists as streamlit_runtime_exists
    from streamlit.runtime import get_instance as get_streamlit_runtime
    from streamlit.runtime.scriptrunner_utils.script_run_context import (
        add_script_run_ctx,
        get_script_run_ctx,
    )
except Exception:  # pragma: no cover - raw mode or API changes
    add_script_run_ctx = None
    streamlit_runtime_exists = None
    get_streamlit_runtime = None
    get_script_run_ctx = None


DEFAULT_SESSION_KEY = "__default__"
PROCESS_RUNTIME_KEY = "__process_tasks__"
RUNTIME_CLOSE_TIMEOUT_SECONDS = 30


def _create_event_loop() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()


class AsyncRuntime:
    """Run async work on a dedicated, long-lived event loop."""

    def __init__(
        self,
        name: str,
        streamlit_ctx=None,
        *,
        attach_streamlit_context: bool = True,
    ):
        self._name = name
        self._attach_context = attach_streamlit_context
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ready = threading.Event()
        self._stopped = threading.Event()
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
        if not self._attach_context or add_script_run_ctx is None or ctx is None:
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
            self._loop = None
            self._stopped.set()

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

    def close(
        self,
        async_cleanup: Optional[Callable[[], Awaitable[None]]] = None,
        *,
        suppress_logs: bool = False,
    ) -> bool:
        """Stop the runtime after running optional async cleanup on the same loop."""
        with self._close_lock:
            if self._closed:
                return self._stopped.is_set()

            loop = self._loop

            if loop is not None and async_cleanup is not None:
                try:
                    self.run(async_cleanup())
                except Exception as e:
                    if not suppress_logs:
                        logger.warning(f"Async runtime cleanup failed for '{self._name}': {e}")

            self._closed = True
            if loop is not None:
                loop.call_soon_threadsafe(loop.stop)

        self._thread.join(timeout=RUNTIME_CLOSE_TIMEOUT_SECONDS)
        if self._thread.is_alive():
            if not suppress_logs:
                logger.error(
                    f"Async runtime '{self._name}' did not stop within "
                    f"{RUNTIME_CLOSE_TIMEOUT_SECONDS} seconds"
                )
            return False

        return True


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


def session_exists(session_key: str) -> bool:
    """Check whether a Streamlit session still exists, even if temporarily inactive."""
    if session_key == DEFAULT_SESSION_KEY:
        return True

    if streamlit_runtime_exists is None or not streamlit_runtime_exists():
        return False

    try:
        runtime = get_streamlit_runtime()
        if runtime.is_active_session(session_key):
            return True

        session_manager = getattr(runtime, "_session_mgr", None)
        if session_manager is None:
            return False

        get_session_info = getattr(session_manager, "get_session_info", None)
        if get_session_info is None:
            return False

        return get_session_info(session_key) is not None
    except Exception:
        logger.debug(f"Failed to query Streamlit session existence for {session_key}")
        return False


def _close_managed_runtime(
    session_key: str,
    handle: ManagedAsyncRuntime,
    *,
    log: bool = True,
) -> bool:
    if log:
        logger.info(f"Cleaning up async runtime for stale session: {session_key}")
    try:
        return _close_runtime_handle(
            handle.runtime,
            async_cleanup=handle.async_cleanup,
            suppress_logs=not log,
        )
    except Exception as e:
        if log:
            logger.error(f"Failed to close async runtime for session {session_key}: {e}")
        return False


def _close_runtime_handle(
    runtime,
    *,
    async_cleanup: Optional[Callable[[], Awaitable[None]]] = None,
    suppress_logs: bool = False,
) -> bool:
    if suppress_logs and isinstance(runtime, AsyncRuntime):
        return runtime.close(async_cleanup=async_cleanup, suppress_logs=True)
    return runtime.close(async_cleanup=async_cleanup)


def _cleanup_stale_runtimes(current_session_key: str):
    stale_items = []
    with _RUNTIMES_LOCK:
        for session_key, handle in _RUNTIMES.items():
            if session_key in {
                DEFAULT_SESSION_KEY,
                PROCESS_RUNTIME_KEY,
                current_session_key,
            }:
                continue
            if not session_exists(session_key):
                stale_items.append((session_key, handle))

    for session_key, handle in stale_items:
        if not _close_managed_runtime(session_key, handle):
            continue

        with _RUNTIMES_LOCK:
            if _RUNTIMES.get(session_key) is handle:
                _RUNTIMES.pop(session_key, None)


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


def get_process_async_runtime() -> AsyncRuntime:
    """Get the process-scoped runtime used by refresh-resilient background tasks."""
    with _RUNTIMES_LOCK:
        handle = _RUNTIMES.get(PROCESS_RUNTIME_KEY)
        if handle is None:
            handle = ManagedAsyncRuntime(
                runtime=AsyncRuntime(
                    PROCESS_RUNTIME_KEY,
                    attach_streamlit_context=False,
                )
            )
            _RUNTIMES[PROCESS_RUNTIME_KEY] = handle
        return handle.runtime


def register_process_async_cleanup(
    async_cleanup: Callable[[], Awaitable[None]],
) -> None:
    """Register cleanup for process-scoped background task resources."""
    get_process_async_runtime()
    with _RUNTIMES_LOCK:
        _RUNTIMES[PROCESS_RUNTIME_KEY].async_cleanup = async_cleanup


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


def shutdown_all_async_runtimes(*, log: bool = True):
    """Shutdown all managed runtimes. Used by tests and process exit."""
    with _RUNTIMES_LOCK:
        runtime_items = sorted(
            _RUNTIMES.items(),
            key=lambda item: item[0] == PROCESS_RUNTIME_KEY,
        )

    for session_key, handle in runtime_items:
        if not _close_managed_runtime(session_key, handle, log=log):
            continue

        with _RUNTIMES_LOCK:
            if _RUNTIMES.get(session_key) is handle:
                _RUNTIMES.pop(session_key, None)


def _shutdown_all_async_runtimes_at_exit():
    shutdown_all_async_runtimes(log=False)


atexit.register(_shutdown_all_async_runtimes_at_exit)
