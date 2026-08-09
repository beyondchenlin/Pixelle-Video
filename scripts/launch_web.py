from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit

from pixelle_video.platform_defaults import configured_api_base_url, configured_api_port

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_HEALTH_SERVICE = "Pixelle-Video API"
STARTUP_TIMEOUT_SECONDS = 30.0
PROBE_TIMEOUT_SECONDS = 0.75


class LaunchConfigurationError(ValueError):
    pass


class LocalApiState(str, Enum):
    ABSENT = "absent"
    READY = "ready"
    OCCUPIED = "occupied"


@dataclass(frozen=True)
class RuntimeTarget:
    port: int
    api_base_url: str
    supervise_local_api: bool


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

    return RuntimeTarget(
        port=port,
        api_base_url=api_base_url,
        supervise_local_api=supervise_local_api,
    )


def probe_local_api(port: int, *, timeout: float = PROBE_TIMEOUT_SECONDS) -> LocalApiState:
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
    if (
        isinstance(payload, dict)
        and payload.get("service") == API_HEALTH_SERVICE
        and payload.get("status") == "healthy"
    ):
        return LocalApiState.READY
    return LocalApiState.OCCUPIED


def wait_for_local_api(
    port: int,
    *,
    timeout: float,
    process: subprocess.Popen[bytes] | subprocess.Popen[str] | None = None,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if probe_local_api(port) is LocalApiState.READY:
            return True
        if process is not None and process.poll() is not None:
            return probe_local_api(port) is LocalApiState.READY
        time.sleep(0.2)
    return probe_local_api(port) is LocalApiState.READY


def _terminate_process(process: subprocess.Popen[bytes] | subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return


def _start_process(arguments: list[str], *, environ: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(arguments, cwd=PROJECT_ROOT, env=environ)


def run_web_stack(environ: dict[str, str] | None = None) -> int:
    child_environ = dict(os.environ if environ is None else environ)
    target = build_runtime_target(child_environ)
    child_environ["PIXELLE_API_PORT"] = str(target.port)
    child_environ["PIXELLE_API_BASE_URL"] = target.api_base_url

    api_process: subprocess.Popen[bytes] | None = None
    web_process: subprocess.Popen[bytes] | None = None
    try:
        if target.supervise_local_api:
            state = probe_local_api(target.port)
            if state is LocalApiState.OCCUPIED:
                if wait_for_local_api(target.port, timeout=2.0):
                    state = LocalApiState.READY
                else:
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
                    timeout=STARTUP_TIMEOUT_SECONDS,
                    process=api_process,
                ):
                    raise RuntimeError(
                        f"{API_HEALTH_SERVICE} did not become healthy within "
                        f"{STARTUP_TIMEOUT_SECONDS:.0f} seconds."
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

        print("Starting Pixelle-Video Web UI on http://localhost:8501 ...")
        web_process = _start_process(
            [sys.executable, "-m", "streamlit", "run", "web/app.py"],
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
        return run_web_stack()
    except KeyboardInterrupt:
        return 130
    except (LaunchConfigurationError, RuntimeError, OSError) as exc:
        print(f"Launch failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
