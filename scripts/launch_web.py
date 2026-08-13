from __future__ import annotations

import ctypes
import http.client
import ipaddress
import json
import math
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Mapping
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit

from pixelle_video.platform_defaults import configured_api_base_url, configured_api_port
from pixelle_video.utils.configured_path import resolve_configured_path
from pixelle_video.utils.project_identity import (
    build_path_id,
    build_project_root_id,
    is_path_id,
    is_project_root_id,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CHECKOUT_ROOT_ID = build_project_root_id(PROJECT_ROOT)
EXPECTED_PROJECT_ROOT_ID = EXPECTED_CHECKOUT_ROOT_ID
API_HEALTH_SERVICE = "Pixelle-Video API"
STARTUP_TIMEOUT_SECONDS = 30.0
PROBE_TIMEOUT_SECONDS = 0.75
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_WINDOWS_PROCESS_JOB_HANDLE: int | None = None


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _install_process_lifetime_guard() -> None:
    """Make every child exit when this launcher disappears on Windows."""
    global _WINDOWS_PROCESS_JOB_HANDLE

    if os.name != "nt" or _WINDOWS_PROCESS_JOB_HANDLE is not None:
        return

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        raise ctypes.WinError(ctypes.get_last_error())

    limits = _JobObjectExtendedLimitInformation()
    limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    try:
        if not kernel32.SetInformationJobObject(
            job_handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel32.AssignProcessToJobObject(
            job_handle,
            kernel32.GetCurrentProcess(),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
    except BaseException:
        kernel32.CloseHandle(job_handle)
        raise

    # Keep the only non-inheritable job handle open for the launcher's lifetime.
    # Windows closes it even after an abrupt launcher termination, which then
    # terminates every child that inherited membership in this job.
    _WINDOWS_PROCESS_JOB_HANDLE = int(job_handle)


class LaunchConfigurationError(ValueError):
    pass


class LocalApiState(str, Enum):
    ABSENT = "absent"
    READY = "ready"
    OCCUPIED = "occupied"
    IDENTITY_MISMATCH = "identity_mismatch"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True)
class LocalApiIdentity:
    checkout_root_id: str
    project_root_id: str
    output_root_id: str


@dataclass(frozen=True)
class RuntimeTarget:
    port: int
    web_port: int
    api_base_url: str
    supervise_local_api: bool
    startup_timeout_seconds: float


def build_local_api_identity(environ: Mapping[str, str]) -> LocalApiIdentity:
    try:
        output_root = resolve_configured_path(
            environ.get("PIXELLE_ARTIFACT_BASE_PATH", "output"),
            project_root=PROJECT_ROOT,
            setting_name="PIXELLE_ARTIFACT_BASE_PATH",
        )
    except (OSError, ValueError) as exc:
        raise LaunchConfigurationError(str(exc)) from exc
    return LocalApiIdentity(
        checkout_root_id=EXPECTED_CHECKOUT_ROOT_ID,
        project_root_id=EXPECTED_PROJECT_ROOT_ID,
        output_root_id=build_path_id(output_root),
    )


DEFAULT_LOCAL_API_IDENTITY = build_local_api_identity(os.environ)


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower().rstrip(".")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _api_origin_for_log(api_base_url: str) -> str:
    parsed = urlsplit(api_base_url)
    host = parsed.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{host}{port}"


def build_runtime_target(environ: Mapping[str, str]) -> RuntimeTarget:
    port = configured_api_port(environ)
    try:
        web_port = int(str(environ.get("PIXELLE_WEB_PORT", "8501")).strip(), 10)
    except ValueError as exc:
        raise LaunchConfigurationError(
            "PIXELLE_WEB_PORT must be an integer between 1 and 65535."
        ) from exc
    if not 1 <= web_port <= 65_535:
        raise LaunchConfigurationError("PIXELLE_WEB_PORT must be between 1 and 65535.")

    raw_timeout = str(
        environ.get("PIXELLE_API_READY_TIMEOUT_SECONDS", STARTUP_TIMEOUT_SECONDS)
    ).strip()
    try:
        startup_timeout_seconds = float(raw_timeout)
    except ValueError as exc:
        raise LaunchConfigurationError(
            "PIXELLE_API_READY_TIMEOUT_SECONDS must be a positive finite number."
        ) from exc
    if not math.isfinite(startup_timeout_seconds) or startup_timeout_seconds <= 0:
        raise LaunchConfigurationError(
            "PIXELLE_API_READY_TIMEOUT_SECONDS must be a positive finite number."
        )

    api_base_url = configured_api_base_url(environ)
    parsed = urlsplit(api_base_url)
    host = parsed.hostname or ""
    supervise_local_api = _is_loopback_host(host)

    if supervise_local_api:
        normalized_host = host.lower().rstrip(".")
        if normalized_host not in {"localhost", "127.0.0.1"}:
            raise LaunchConfigurationError(
                "A locally supervised PIXELLE_API_BASE_URL must use localhost or 127.0.0.1."
            )
        effective_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if parsed.scheme != "http":
            raise LaunchConfigurationError(
                "A locally supervised Pixelle API must use http, not https."
            )
        if effective_port != port:
            raise LaunchConfigurationError(
                "PIXELLE_API_BASE_URL and PIXELLE_API_PORT must use the same local port."
            )
        if parsed.path != "/api":
            raise LaunchConfigurationError(
                "A locally supervised PIXELLE_API_BASE_URL must end with /api."
            )
        if port == web_port:
            raise LaunchConfigurationError(
                "PIXELLE_API_PORT and PIXELLE_WEB_PORT must be different."
            )

    return RuntimeTarget(
        port=port,
        web_port=web_port,
        api_base_url=api_base_url,
        supervise_local_api=supervise_local_api,
        startup_timeout_seconds=startup_timeout_seconds,
    )


def probe_local_api(
    port: int,
    *,
    expected_identity: LocalApiIdentity | None = None,
    timeout: float = PROBE_TIMEOUT_SECONDS,
) -> LocalApiState:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            pass
    except OSError:
        return LocalApiState.ABSENT

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", "/health", headers={"Accept": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            return LocalApiState.OCCUPIED
        raw_payload = response.read(65_537)
    except (http.client.HTTPException, OSError, TimeoutError):
        return LocalApiState.OCCUPIED
    finally:
        connection.close()

    if len(raw_payload) > 65_536:
        return LocalApiState.OCCUPIED
    try:
        payload = json.loads(raw_payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return LocalApiState.OCCUPIED
    if not (
        isinstance(payload, dict)
        and payload.get("service") == API_HEALTH_SERVICE
        and payload.get("status") == "healthy"
    ):
        return LocalApiState.OCCUPIED

    expected = expected_identity or DEFAULT_LOCAL_API_IDENTITY
    checkout_root_id = payload.get("checkout_root_id")
    project_root_id = payload.get("project_root_id")
    output_root_id = payload.get("output_root_id")
    if (
        not is_project_root_id(checkout_root_id)
        or not is_project_root_id(project_root_id)
        or not is_path_id(output_root_id)
    ):
        return LocalApiState.INCOMPATIBLE
    if (
        checkout_root_id != expected.checkout_root_id
        or project_root_id != expected.project_root_id
        or output_root_id != expected.output_root_id
    ):
        return LocalApiState.IDENTITY_MISMATCH
    return LocalApiState.READY


def wait_for_local_api(
    port: int,
    *,
    timeout: float,
    process: subprocess.Popen[bytes] | subprocess.Popen[str] | None = None,
    expected_identity: LocalApiIdentity | None = None,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = probe_local_api(port, expected_identity=expected_identity)
        if state is LocalApiState.READY:
            return True
        if state in {LocalApiState.IDENTITY_MISMATCH, LocalApiState.INCOMPATIBLE}:
            return False
        if process is not None and process.poll() is not None:
            return (
                probe_local_api(port, expected_identity=expected_identity)
                is LocalApiState.READY
            )
        time.sleep(0.2)
    return (
        probe_local_api(port, expected_identity=expected_identity) is LocalApiState.READY
    )


def _raise_for_api_identity_conflict(state: LocalApiState, *, port: int) -> None:
    if state is LocalApiState.IDENTITY_MISMATCH:
        raise LaunchConfigurationError(
            f"Port {port} is running {API_HEALTH_SERVICE} for another project root, checkout, "
            "or output root. "
            "Stop that checkout's API or configure this checkout to use a different local port."
        )
    if state is LocalApiState.INCOMPATIBLE:
        raise LaunchConfigurationError(
            f"Port {port} is running {API_HEALTH_SERVICE} without a compatible project identity. "
            "Restart that API with the current code before reusing the port."
        )


def _terminate_process(process: subprocess.Popen[bytes] | subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (AttributeError, OSError, ProcessLookupError):
        process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        if os.name == "nt" and getattr(process, "pid", None):
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
            )
        elif getattr(process, "pid", None):
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def _process_group_options() -> dict[str, object]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _start_process(arguments: list[str], *, environ: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        arguments,
        cwd=PROJECT_ROOT,
        env=environ,
        **_process_group_options(),
    )


def _assert_port_available(port: int, *, service_name: str) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise LaunchConfigurationError(
                f"{service_name} port 127.0.0.1:{port} is already occupied."
            ) from exc


def _prepare_runtime_environment(environ: dict[str, str], target: RuntimeTarget) -> None:
    runtime_root = PROJECT_ROOT / "_runtime"
    temporary_root = runtime_root / "tmp"
    uv_cache = runtime_root / "uv-cache"
    ruff_cache = runtime_root / "ruff-cache"
    for directory in (runtime_root, temporary_root, uv_cache, ruff_cache):
        directory.mkdir(parents=True, exist_ok=True)

    environ.update(
        {
            "PIXELLE_VIDEO_ROOT": str(PROJECT_ROOT),
            "PIXELLE_VIDEO_RUNTIME_ROOT": str(runtime_root),
            "PIXELLE_API_PORT": str(target.port),
            "PIXELLE_WEB_PORT": str(target.web_port),
            "PIXELLE_API_BASE_URL": target.api_base_url,
            "TMP": str(temporary_root),
            "TEMP": str(temporary_root),
            "TMPDIR": str(temporary_root),
            "UV_CACHE_DIR": str(uv_cache),
            "RUFF_CACHE_DIR": str(ruff_cache),
        }
    )


def run_web_stack(environ: dict[str, str] | None = None) -> int:
    child_environ = dict(os.environ if environ is None else environ)
    target = build_runtime_target(child_environ)
    _prepare_runtime_environment(child_environ, target)
    expected_api_identity = build_local_api_identity(child_environ)
    _assert_port_available(target.web_port, service_name="Web UI")

    api_process: subprocess.Popen[bytes] | None = None
    web_process: subprocess.Popen[bytes] | None = None
    try:
        if target.supervise_local_api:
            state = probe_local_api(
                target.port,
                expected_identity=expected_api_identity,
            )
            _raise_for_api_identity_conflict(state, port=target.port)
            if state is LocalApiState.OCCUPIED:
                if wait_for_local_api(
                    target.port,
                    timeout=2.0,
                    expected_identity=expected_api_identity,
                ):
                    state = LocalApiState.READY
                else:
                    state = probe_local_api(
                        target.port,
                        expected_identity=expected_api_identity,
                    )
                    _raise_for_api_identity_conflict(state, port=target.port)
                    raise LaunchConfigurationError(
                        f"Port {target.port} is occupied by a service that is not a healthy "
                        f"{API_HEALTH_SERVICE}. Stop that service or set both "
                        "PIXELLE_API_PORT and PIXELLE_API_BASE_URL explicitly."
                    )

            if state is LocalApiState.READY:
                print(f"Reusing the healthy {API_HEALTH_SERVICE} on port {target.port}.")
            else:
                print(f"Starting {API_HEALTH_SERVICE} on http://127.0.0.1:{target.port} ...")
                api_process = _start_process(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "api.app:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(target.port),
                    ],
                    environ=child_environ,
                )
                if not wait_for_local_api(
                    target.port,
                    timeout=target.startup_timeout_seconds,
                    process=api_process,
                    expected_identity=expected_api_identity,
                ):
                    state = probe_local_api(
                        target.port,
                        expected_identity=expected_api_identity,
                    )
                    _raise_for_api_identity_conflict(state, port=target.port)
                    raise RuntimeError(
                        f"{API_HEALTH_SERVICE} did not become healthy within "
                        f"{target.startup_timeout_seconds:.1f} seconds."
                    )
                if api_process.poll() is not None:
                    api_process = None
                    print(f"Reusing a concurrently started {API_HEALTH_SERVICE}.")
                else:
                    print(f"{API_HEALTH_SERVICE} is healthy.")
        else:
            print(
                "Using the explicitly configured remote API origin: "
                f"{_api_origin_for_log(target.api_base_url)}"
            )

        print(f"Starting Pixelle-Video Web UI on http://127.0.0.1:{target.web_port} ...")
        web_process = _start_process(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "web/app.py",
                "--server.address",
                "127.0.0.1",
                "--server.port",
                str(target.web_port),
            ],
            environ=child_environ,
        )
        while True:
            web_exit_code = web_process.poll()
            if web_exit_code is not None:
                return web_exit_code
            if api_process is not None and api_process.poll() is not None:
                raise RuntimeError(
                    f"The supervised {API_HEALTH_SERVICE} exited while the Web UI was running."
                )
            time.sleep(0.25)
    finally:
        _terminate_process(web_process)
        _terminate_process(api_process)


def main() -> int:
    try:
        _install_process_lifetime_guard()
        return run_web_stack()
    except KeyboardInterrupt:
        return 130
    except (LaunchConfigurationError, RuntimeError, OSError) as exc:
        print(f"Launch failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
