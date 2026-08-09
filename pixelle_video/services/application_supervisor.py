from __future__ import annotations

import math
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping
from urllib.error import URLError
from urllib.request import urlopen


class ApplicationSupervisorError(RuntimeError):
    """Raised when the local application stack cannot be supervised safely."""


@dataclass(frozen=True)
class ApplicationRuntime:
    environment: dict[str, str]
    api_port: int
    web_port: int
    api_ready_timeout_seconds: float


def _parse_port(value: str, *, field_name: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise ApplicationSupervisorError(f"{field_name} must be an integer: {value}") from exc
    if not 1 <= port <= 65535:
        raise ApplicationSupervisorError(f"{field_name} must be between 1 and 65535: {port}")
    return port


def build_application_runtime(
    repo_root: Path,
    source_environment: Mapping[str, str] | None = None,
) -> ApplicationRuntime:
    environment = dict(os.environ if source_environment is None else source_environment)

    api_port = _parse_port(environment.get("PIXELLE_API_PORT", "8888"), field_name="API port")
    web_port = _parse_port(environment.get("PIXELLE_WEB_PORT", "8501"), field_name="Web port")
    if api_port == web_port:
        raise ApplicationSupervisorError("API port and Web port must be different")

    raw_timeout = environment.get("PIXELLE_API_READY_TIMEOUT_SECONDS", "60")
    try:
        ready_timeout = float(raw_timeout)
    except ValueError as exc:
        raise ApplicationSupervisorError(
            f"API readiness timeout must be a positive number: {raw_timeout}"
        ) from exc
    if not math.isfinite(ready_timeout) or ready_timeout <= 0:
        raise ApplicationSupervisorError("API readiness timeout must be a positive finite number")

    runtime_root = repo_root / "_runtime"
    temporary_root = runtime_root / "tmp"
    for directory in (
        runtime_root,
        temporary_root,
        runtime_root / "uv-cache",
        runtime_root / "ruff-cache",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    environment.update(
        {
            "PIXELLE_VIDEO_ROOT": str(repo_root),
            "PIXELLE_VIDEO_RUNTIME_ROOT": str(runtime_root),
            "TMP": str(temporary_root),
            "TEMP": str(temporary_root),
            "TMPDIR": str(temporary_root),
            "UV_CACHE_DIR": str(runtime_root / "uv-cache"),
            "RUFF_CACHE_DIR": str(runtime_root / "ruff-cache"),
            "PIXELLE_API_PORT": str(api_port),
            "PIXELLE_WEB_PORT": str(web_port),
            "PIXELLE_API_BASE_URL": f"http://127.0.0.1:{api_port}/api",
        }
    )
    return ApplicationRuntime(
        environment=environment,
        api_port=api_port,
        web_port=web_port,
        api_ready_timeout_seconds=ready_timeout,
    )


class ApplicationSupervisor:
    def __init__(
        self,
        *,
        repo_root: str | Path,
        source_environment: Mapping[str, str] | None = None,
        process_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.runtime = build_application_runtime(self.repo_root, source_environment)
        self.process_factory = process_factory
        self._stop_requested = False
        self._processes: list[tuple[str, subprocess.Popen]] = []

    def run(self) -> int:
        self._assert_port_available(self.runtime.api_port, "API")
        self._assert_port_available(self.runtime.web_port, "Web")
        previous_handlers = self._install_signal_handlers()
        try:
            api_process = self._start_process("API", self._api_command())
            self._wait_for_api(api_process)
            web_process = self._start_process("Web", self._web_command())
            return self._monitor(api_process, web_process)
        finally:
            self._shutdown_all()
            self._restore_signal_handlers(previous_handlers)

    def _api_command(self) -> list[str]:
        return [
            sys.executable,
            "-m",
            "uvicorn",
            "api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.runtime.api_port),
        ]

    def _web_command(self) -> list[str]:
        return [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "web/app.py",
            "--server.address",
            "127.0.0.1",
            "--server.port",
            str(self.runtime.web_port),
        ]

    def _start_process(self, name: str, command: list[str]) -> subprocess.Popen:
        print(f"[Pixelle] Starting {name}...", flush=True)
        process = self.process_factory(
            command,
            cwd=str(self.repo_root),
            env=self.runtime.environment,
            **self._process_group_kwargs(),
        )
        self._processes.append((name, process))
        return process

    def _wait_for_api(self, process: subprocess.Popen) -> None:
        health_url = f"http://127.0.0.1:{self.runtime.api_port}/health"
        deadline = time.monotonic() + self.runtime.api_ready_timeout_seconds
        while time.monotonic() < deadline:
            returncode = process.poll()
            if returncode is not None:
                raise ApplicationSupervisorError(
                    f"API process exited before readiness with code {returncode}"
                )
            if self._stop_requested:
                raise ApplicationSupervisorError("Application startup was interrupted")
            try:
                with urlopen(health_url, timeout=1.0) as response:
                    if response.status == 200:
                        return
            except (OSError, URLError):
                pass
            time.sleep(0.2)
        raise ApplicationSupervisorError(
            "API did not become healthy within "
            f"{self.runtime.api_ready_timeout_seconds:.1f} seconds: {health_url}"
        )

    def _monitor(self, api_process: subprocess.Popen, web_process: subprocess.Popen) -> int:
        while not self._stop_requested:
            api_returncode = api_process.poll()
            if api_returncode is not None:
                raise ApplicationSupervisorError(
                    f"API process exited while Web was running with code {api_returncode}"
                )
            web_returncode = web_process.poll()
            if web_returncode is not None:
                return int(web_returncode)
            time.sleep(0.2)
        return 130

    def _assert_port_available(self, port: int, service_name: str) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise ApplicationSupervisorError(
                    f"{service_name} port 127.0.0.1:{port} is already in use; "
                    "refusing to attach to an unknown or stale process"
                ) from exc

    def _process_group_kwargs(self) -> dict[str, object]:
        if os.name == "nt":
            return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        return {"start_new_session": True}

    def _shutdown_all(self) -> None:
        for _, process in reversed(self._processes):
            self._terminate_process(process)
        self._processes.clear()

    def _terminate_process(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=8)
            return
        except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
            pass

        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
            )
        else:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    def _install_signal_handlers(self) -> dict[int, object]:
        previous_handlers: dict[int, object] = {}

        def request_stop(_signum, _frame) -> None:
            self._stop_requested = True

        for signal_number in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signal_number] = signal.getsignal(signal_number)
            signal.signal(signal_number, request_stop)
        return previous_handlers

    def _restore_signal_handlers(self, previous_handlers: Mapping[int, object]) -> None:
        for signal_number, previous_handler in previous_handlers.items():
            signal.signal(signal_number, previous_handler)


def run_application_stack(repo_root: str | Path) -> int:
    return ApplicationSupervisor(repo_root=repo_root).run()
