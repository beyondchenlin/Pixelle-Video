from __future__ import annotations

import ctypes
import http.client
import json
import os
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import psutil
import pytest
from pydantic import ValidationError

import scripts.launch_web as launch_web
from api.config import APIConfig
from pixelle_video.platform_defaults import (
    BUILTIN_API_BASE_URL,
    DEFAULT_API_PORT,
    configured_api_base_url,
    configured_api_port,
    is_legacy_local_api_base_url,
    normalize_api_base_url,
    parse_api_port,
)
from pixelle_video.utils.process_lifetime import ProcessLifetimeGuardError
from pixelle_video.utils.project_identity import is_launch_id
from scripts.launch_web import (
    LaunchConfigurationError,
    LocalApiState,
    build_runtime_target,
    probe_local_api,
)

TEST_LAUNCH_ID = "pixelle-launch-v1:" + ("1" * 32)
TEST_API_IDENTITY = launch_web.build_local_api_identity({"PIXELLE_LAUNCH_ID": TEST_LAUNCH_ID})


def _health_payload(**overrides: object) -> bytes:
    payload: dict[str, object] = {
        "status": "healthy",
        "version": "0.1.0",
        "service": "Pixelle-Video API",
        "checkout_root_id": launch_web.EXPECTED_CHECKOUT_ROOT_ID,
        "project_root_id": launch_web.EXPECTED_PROJECT_ROOT_ID,
        "output_root_id": TEST_API_IDENTITY.output_root_id,
        "launch_id": TEST_LAUNCH_ID,
    }
    payload.update(overrides)
    return json.dumps(payload).encode("utf-8")


class _HealthHandler(BaseHTTPRequestHandler):
    payload = _health_payload()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        if self.path != "/health":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class _RedirectHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        self.send_response(302)
        self.send_header("Location", "http://example.test/health")
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _start_health_server(payload: bytes) -> tuple[ThreadingHTTPServer, Thread]:
    handler = type("ConfiguredHealthHandler", (_HealthHandler,), {"payload": payload})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _windows_process_is_running(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel32.WaitForSingleObject.restype = ctypes.c_ulong
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    synchronize = 0x00100000
    wait_timeout = 0x00000102
    handle = kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
    finally:
        kernel32.CloseHandle(handle)


def _unused_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _wait_for_health_payload(
    port: int,
    *,
    launcher: subprocess.Popen[bytes],
    timeout: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if launcher.poll() is not None:
            raise AssertionError(f"web-stack launcher exited with {launcher.returncode}")
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
        try:
            connection.request("GET", "/health")
            response = connection.getresponse()
            if response.status == 200:
                payload = json.loads(response.read())
                if isinstance(payload, dict):
                    return payload
        except (http.client.HTTPException, OSError, TimeoutError):
            pass
        finally:
            connection.close()
        time.sleep(0.1)
    raise AssertionError(f"API on port {port} did not become healthy")


def _wait_for_port_closed(port: int, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                pass
        except OSError:
            return
        time.sleep(0.1)
    raise AssertionError(f"port {port} remained open after launcher exit")


def _wait_for_port_open(
    port: int,
    *,
    launcher: subprocess.Popen[bytes],
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if launcher.poll() is not None:
            raise AssertionError(f"web-stack launcher exited with {launcher.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise AssertionError(f"port {port} did not open")


def test_builtin_api_contract_has_one_python_source_of_truth() -> None:
    assert DEFAULT_API_PORT == 6789
    assert BUILTIN_API_BASE_URL == "http://localhost:6789/api"
    assert APIConfig().port == DEFAULT_API_PORT


def test_api_environment_treats_blank_values_as_defaults() -> None:
    environment = {"PIXELLE_API_PORT": "  ", "PIXELLE_API_BASE_URL": "\t"}

    assert configured_api_port(environment) == DEFAULT_API_PORT
    assert configured_api_base_url(environment) == BUILTIN_API_BASE_URL


@pytest.mark.parametrize("value", ["0", "65536", "not-a-port", "12.5"])
def test_api_port_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match="PIXELLE_API_PORT"):
        parse_api_port(value)


@pytest.mark.parametrize("port", [0, 65_536])
def test_api_config_rejects_out_of_range_ports(port: int) -> None:
    with pytest.raises(ValidationError):
        APIConfig(port=port)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "/api",
        "ftp://localhost:6789/api",
        "http://user:secret@localhost:6789/api",
        "http://localhost:6789/api?token=secret",
        "http://localhost:6789/api#fragment",
        "http://localhost:99999/api",
    ],
)
def test_api_base_url_rejects_unsafe_or_malformed_values(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_api_base_url(value)


def test_api_base_url_preserves_custom_hosts_and_removes_trailing_slashes() -> None:
    assert (
        normalize_api_base_url(" https://api.example.test/proxy/api/// ")
        == "https://api.example.test/proxy/api"
    )


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost:8001/api",
        "http://localhost:8888/api",
        "http://127.0.0.1:8899/api/",
        "http://[::1]:8888/api",
    ],
)
def test_legacy_local_api_defaults_are_identified(value: str) -> None:
    assert is_legacy_local_api_base_url(value) is True


def test_custom_api_port_is_not_mistaken_for_a_legacy_default() -> None:
    assert is_legacy_local_api_base_url("http://localhost:9123/api") is False


class _SessionState(dict[str, object]):
    def __getattr__(self, name: str) -> object:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: object) -> None:
        self[name] = value


def test_session_state_migrates_only_known_legacy_local_defaults(monkeypatch) -> None:
    from web.state import session as session_module

    state = _SessionState(
        language="zh_CN",
        workspace_id="workspace_1",
        project_id="project_1",
        api_base_url="http://localhost:8888/api",
    )
    monkeypatch.setattr(session_module.st, "session_state", state)

    session_module.init_session_state()

    assert state["api_base_url"] == "http://localhost:6789/api"


def test_session_state_preserves_an_explicit_custom_api_port(monkeypatch) -> None:
    from web.state import session as session_module

    state = _SessionState(
        language="zh_CN",
        workspace_id="workspace_1",
        project_id="project_1",
        api_base_url="http://localhost:9123/api",
    )
    monkeypatch.setattr(session_module.st, "session_state", state)

    session_module.init_session_state()

    assert state["api_base_url"] == "http://localhost:9123/api"


def test_local_runtime_target_requires_port_and_base_url_to_match() -> None:
    with pytest.raises(LaunchConfigurationError, match="same local port"):
        build_runtime_target(
            {
                "PIXELLE_API_PORT": "6789",
                "PIXELLE_API_BASE_URL": "http://localhost:9123/api",
            }
        )


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"PIXELLE_WEB_PORT": "invalid"}, "PIXELLE_WEB_PORT"),
        ({"PIXELLE_WEB_PORT": "0"}, "PIXELLE_WEB_PORT"),
        (
            {"PIXELLE_API_PORT": "6789", "PIXELLE_WEB_PORT": "6789"},
            "must be different",
        ),
        ({"PIXELLE_API_READY_TIMEOUT_SECONDS": "0"}, "positive finite"),
        ({"PIXELLE_API_READY_TIMEOUT_SECONDS": "nan"}, "positive finite"),
    ],
)
def test_runtime_target_rejects_invalid_web_and_timeout_boundaries(
    environment: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(LaunchConfigurationError, match=message):
        build_runtime_target(environment)


@pytest.mark.parametrize("host", ["127.0.0.2", "[::1]"])
def test_local_runtime_target_rejects_a_loopback_host_the_launcher_does_not_bind(
    host: str,
) -> None:
    with pytest.raises(LaunchConfigurationError, match="localhost or 127.0.0.1"):
        build_runtime_target(
            {
                "PIXELLE_API_PORT": "6789",
                "PIXELLE_API_BASE_URL": f"http://{host}:6789/api",
            }
        )


def test_remote_runtime_target_does_not_start_an_unused_local_api() -> None:
    target = build_runtime_target(
        {
            "PIXELLE_API_PORT": "6789",
            "PIXELLE_API_BASE_URL": "https://api.example.test/pixelle/api",
        }
    )

    assert target.supervise_local_api is False
    assert target.api_base_url == "https://api.example.test/pixelle/api"


def test_remote_api_log_label_does_not_expose_url_paths() -> None:
    assert (
        launch_web._api_origin_for_log("https://api.example.test:9443/tenant-secret/api")
        == "https://api.example.test:9443"
    )


def test_local_probe_only_accepts_the_pixelle_health_identity() -> None:
    server, thread = _start_health_server(_HealthHandler.payload)
    try:
        assert (
            probe_local_api(server.server_port, expected_identity=TEST_API_IDENTITY)
            is LocalApiState.READY
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    ("mismatched_field", "mismatched_value"),
    [
        ("checkout_root_id", "pixelle-root-v1:" + ("0" * 64)),
        ("project_root_id", "pixelle-root-v1:" + ("0" * 64)),
        ("output_root_id", "pixelle-path-v1:" + ("0" * 64)),
    ],
)
def test_local_probe_rejects_a_different_runtime_identity(
    mismatched_field: str,
    mismatched_value: str,
) -> None:
    payload = _health_payload(**{mismatched_field: mismatched_value})
    server, thread = _start_health_server(payload)
    try:
        assert (
            probe_local_api(server.server_port, expected_identity=TEST_API_IDENTITY)
            is LocalApiState.IDENTITY_MISMATCH
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"status":"healthy","service":"Pixelle-Video API"}',
        _health_payload(checkout_root_id="invalid"),
        _health_payload(project_root_id="invalid"),
        _health_payload(output_root_id="invalid"),
        _health_payload(launch_id="invalid"),
    ],
)
def test_local_probe_rejects_an_api_without_a_valid_project_identity(payload: bytes) -> None:
    server, thread = _start_health_server(payload)
    try:
        assert (
            probe_local_api(server.server_port, expected_identity=TEST_API_IDENTITY)
            is LocalApiState.INCOMPATIBLE
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_local_probe_rejects_a_foreign_service_on_the_port() -> None:
    server, thread = _start_health_server(b'{"status":"healthy","service":"other-project"}')
    try:
        assert (
            probe_local_api(server.server_port, expected_identity=TEST_API_IDENTITY)
            is LocalApiState.OCCUPIED
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_local_probe_does_not_follow_a_foreign_service_redirect() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RedirectHealthHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert (
            probe_local_api(server.server_port, expected_identity=TEST_API_IDENTITY)
            is LocalApiState.OCCUPIED
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    "state",
    [
        LocalApiState.IDENTITY_MISMATCH,
        LocalApiState.OWNERSHIP_MISMATCH,
        LocalApiState.INCOMPATIBLE,
    ],
)
def test_local_wait_fails_fast_for_a_definitive_identity_conflict(
    monkeypatch,
    state: LocalApiState,
) -> None:
    monkeypatch.setattr(launch_web, "probe_local_api", lambda _port, **_kwargs: state)
    monkeypatch.setattr(
        launch_web.time,
        "sleep",
        lambda _seconds: pytest.fail("definitive identity conflicts must not be retried"),
    )

    assert (
        launch_web.wait_for_local_api(
            6789,
            timeout=30.0,
            expected_identity=TEST_API_IDENTITY,
        )
        is False
    )


def test_local_probe_rejects_an_api_from_another_launcher() -> None:
    payload = _health_payload(launch_id="pixelle-launch-v1:" + ("2" * 32))
    server, thread = _start_health_server(payload)
    try:
        assert (
            probe_local_api(server.server_port, expected_identity=TEST_API_IDENTITY)
            is LocalApiState.OWNERSHIP_MISMATCH
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("value", ["", "../outside"])
def test_local_api_identity_rejects_unsafe_artifact_paths(value: str) -> None:
    with pytest.raises(LaunchConfigurationError, match="PIXELLE_ARTIFACT_BASE_PATH"):
        launch_web.build_local_api_identity({"PIXELLE_ARTIFACT_BASE_PATH": value})


class _FakeProcess:
    def __init__(self, *, exit_code: int | None = None) -> None:
        self.exit_code = exit_code
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.exit_code

    def terminate(self) -> None:
        self.terminated = True
        self.exit_code = 0

    def kill(self) -> None:
        self.killed = True
        self.exit_code = -9

    def wait(self, *, timeout: float) -> int:
        assert timeout > 0
        assert self.exit_code is not None
        return self.exit_code


def test_main_installs_process_lifetime_guard_before_starting_services(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        launch_web,
        "install_process_tree_lifetime_guard",
        lambda: calls.append("guard"),
    )
    monkeypatch.setattr(
        launch_web,
        "run_web_stack",
        lambda: calls.append("services") or 0,
    )

    assert launch_web.main() == 0
    assert calls == ["guard", "services"]


def test_main_fails_before_starting_services_when_lifetime_guard_is_unavailable(
    monkeypatch,
    capsys,
) -> None:
    def fail_guard() -> None:
        raise ProcessLifetimeGuardError("simulated lifetime guard failure")

    monkeypatch.setattr(launch_web, "install_process_tree_lifetime_guard", fail_guard)
    monkeypatch.setattr(
        launch_web,
        "run_web_stack",
        lambda: pytest.fail("services must not start without a lifetime guard"),
    )

    assert launch_web.main() == 1
    assert "simulated lifetime guard failure" in capsys.readouterr().err


@pytest.mark.skipif(os.name != "nt", reason="Windows job objects are Windows-only")
def test_windows_lifetime_guard_kills_nested_job_tree_after_forced_launcher_exit(
    tmp_path: Path,
) -> None:
    middle_pid_path = tmp_path / "middle.pid"
    grandchild_pid_path = tmp_path / "grandchild.pid"
    middle_source = "\n".join(
        [
            "import subprocess",
            "import sys",
            "import time",
            "from pathlib import Path",
            (
                "from pixelle_video.utils.process_lifetime import "
                "install_process_tree_lifetime_guard"
            ),
            "install_process_tree_lifetime_guard()",
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])",
            f"Path({str(grandchild_pid_path)!r}).write_text(str(child.pid), encoding='ascii')",
            "time.sleep(120)",
        ]
    )
    helper_source = "\n".join(
        [
            "import subprocess",
            "import sys",
            "import time",
            "from pathlib import Path",
            (
                "from pixelle_video.utils.process_lifetime import "
                "install_process_tree_lifetime_guard"
            ),
            "install_process_tree_lifetime_guard()",
            f"child = subprocess.Popen([sys.executable, '-c', {middle_source!r}])",
            f"Path({str(middle_pid_path)!r}).write_text(str(child.pid), encoding='ascii')",
            "time.sleep(120)",
        ]
    )
    launcher = subprocess.Popen(
        [sys.executable, "-c", helper_source],
        cwd=launch_web.PROJECT_ROOT,
    )
    owned_pids: list[int] = []
    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not grandchild_pid_path.exists():
            if launcher.poll() is not None:
                raise AssertionError(f"lifetime-guard helper exited with {launcher.returncode}")
            time.sleep(0.05)
        assert middle_pid_path.is_file()
        assert grandchild_pid_path.is_file()
        owned_pids = [
            int(middle_pid_path.read_text(encoding="ascii")),
            int(grandchild_pid_path.read_text(encoding="ascii")),
        ]
        assert all(_windows_process_is_running(pid) for pid in owned_pids)

        launcher.kill()
        launcher.wait(timeout=10)

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and any(
            _windows_process_is_running(pid) for pid in owned_pids
        ):
            time.sleep(0.05)
        assert not any(_windows_process_is_running(pid) for pid in owned_pids)
    finally:
        if launcher.poll() is None:
            launcher.kill()
            launcher.wait(timeout=10)
        for pid in owned_pids:
            if _windows_process_is_running(pid):
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                    timeout=10,
                )


@pytest.mark.skipif(os.name != "nt", reason="Windows job objects are Windows-only")
def test_real_windows_web_stack_releases_api_and_web_ports_after_forced_exit() -> None:
    api_port = _unused_loopback_port()
    web_port = _unused_loopback_port()
    while web_port == api_port:
        web_port = _unused_loopback_port()

    environment = dict(os.environ)
    environment.update(
        {
            "PIXELLE_API_PORT": str(api_port),
            "PIXELLE_API_BASE_URL": f"http://localhost:{api_port}/api",
            "PIXELLE_WEB_PORT": str(web_port),
            "STREAMLIT_SERVER_HEADLESS": "true",
        }
    )
    launcher = subprocess.Popen(
        [sys.executable, "-m", "scripts.launch_web"],
        cwd=launch_web.PROJECT_ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    descendants: list[psutil.Process] = []
    try:
        payload = _wait_for_health_payload(api_port, launcher=launcher, timeout=30.0)
        assert is_launch_id(payload.get("launch_id"))
        _wait_for_port_open(web_port, launcher=launcher, timeout=30.0)

        root_process = psutil.Process(launcher.pid)
        descendants = root_process.children(recursive=True)
        assert len(descendants) >= 2

        launcher.kill()
        launcher.wait(timeout=10)
        _, alive = psutil.wait_procs(descendants, timeout=10)

        assert alive == []
        _wait_for_port_closed(api_port, timeout=10.0)
        _wait_for_port_closed(web_port, timeout=10.0)
    finally:
        if launcher.poll() is None:
            try:
                known_pids = {process.pid for process in descendants}
                descendants.extend(
                    process
                    for process in psutil.Process(launcher.pid).children(recursive=True)
                    if process.pid not in known_pids
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
        for process in descendants:
            try:
                process.kill()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
        if launcher.poll() is None:
            launcher.kill()
            launcher.wait(timeout=10)


def test_supervisor_cleans_up_only_the_api_process_it_started(monkeypatch) -> None:
    api_process = _FakeProcess()
    web_process = _FakeProcess(exit_code=0)
    started: list[list[str]] = []

    def fake_start(arguments: list[str], *, environ: dict[str, str]) -> _FakeProcess:
        assert environ["PIXELLE_API_PORT"] == "6789"
        assert is_launch_id(environ["PIXELLE_LAUNCH_ID"])
        started.append(arguments)
        return api_process if "uvicorn" in arguments else web_process

    monkeypatch.setattr(
        launch_web,
        "probe_local_api",
        lambda _port, **_kwargs: LocalApiState.ABSENT,
    )
    monkeypatch.setattr(launch_web, "wait_for_local_api", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(launch_web, "_start_process", fake_start)
    monkeypatch.setattr(launch_web, "_assert_port_available", lambda *_args, **_kwargs: None)

    assert launch_web.run_web_stack({}) == 0
    assert any("uvicorn" in arguments for arguments in started)
    assert any("streamlit" in arguments for arguments in started)
    assert api_process.terminated is True
    assert api_process.killed is False


def test_supervisor_refuses_a_healthy_api_owned_by_another_launcher(monkeypatch) -> None:
    monkeypatch.setattr(
        launch_web,
        "probe_local_api",
        lambda _port, **_kwargs: LocalApiState.OWNERSHIP_MISMATCH,
    )
    monkeypatch.setattr(
        launch_web,
        "_start_process",
        lambda *_args, **_kwargs: pytest.fail("an unowned API must not start the web process"),
    )
    monkeypatch.setattr(launch_web, "_assert_port_available", lambda *_args, **_kwargs: None)

    with pytest.raises(LaunchConfigurationError, match="another launcher"):
        launch_web.run_web_stack({})


def test_supervisor_refuses_to_launch_web_against_a_foreign_local_service(monkeypatch) -> None:
    monkeypatch.setattr(
        launch_web,
        "probe_local_api",
        lambda _port, **_kwargs: LocalApiState.OCCUPIED,
    )
    monkeypatch.setattr(launch_web, "wait_for_local_api", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(launch_web, "_assert_port_available", lambda *_args, **_kwargs: None)

    with pytest.raises(LaunchConfigurationError, match="occupied"):
        launch_web.run_web_stack({})


def test_explicit_remote_api_is_not_probed_started_or_terminated(monkeypatch) -> None:
    web_process = _FakeProcess(exit_code=0)
    started: list[list[str]] = []

    def fake_start(arguments: list[str], *, environ: dict[str, str]) -> _FakeProcess:
        assert environ["PIXELLE_API_BASE_URL"] == "https://api.example.test/pixelle/api"
        started.append(arguments)
        return web_process

    monkeypatch.setattr(
        launch_web,
        "probe_local_api",
        lambda *_args, **_kwargs: pytest.fail("an explicit remote API must not be probed"),
    )
    monkeypatch.setattr(launch_web, "_start_process", fake_start)
    monkeypatch.setattr(launch_web, "_assert_port_available", lambda *_args, **_kwargs: None)

    assert (
        launch_web.run_web_stack({"PIXELLE_API_BASE_URL": "https://api.example.test/pixelle/api"})
        == 0
    )
    assert len(started) == 1
    assert "streamlit" in started[0]
    assert web_process.terminated is False


@pytest.mark.parametrize(
    ("state", "message"),
    [
        (LocalApiState.IDENTITY_MISMATCH, "another project root, checkout, or output root"),
        (LocalApiState.OWNERSHIP_MISMATCH, "another launcher"),
        (LocalApiState.INCOMPATIBLE, "outdated or incompatible"),
    ],
)
def test_supervisor_refuses_to_reuse_an_unmatched_pixelle_api(
    monkeypatch,
    state: LocalApiState,
    message: str,
) -> None:
    monkeypatch.setattr(launch_web, "probe_local_api", lambda _port, **_kwargs: state)
    monkeypatch.setattr(
        launch_web,
        "_start_process",
        lambda *_args, **_kwargs: pytest.fail("an unmatched API must not start the web process"),
    )
    monkeypatch.setattr(launch_web, "_assert_port_available", lambda *_args, **_kwargs: None)

    with pytest.raises(LaunchConfigurationError, match=message):
        launch_web.run_web_stack({})


def test_supervisor_passes_explicit_web_port_and_runtime_environment(monkeypatch) -> None:
    api_process = _FakeProcess()
    web_process = _FakeProcess(exit_code=0)
    captured: list[tuple[list[str], dict[str, str]]] = []

    def fake_start(arguments: list[str], *, environ: dict[str, str]) -> _FakeProcess:
        captured.append((arguments, environ))
        return api_process if "uvicorn" in arguments else web_process

    monkeypatch.setattr(
        launch_web,
        "probe_local_api",
        lambda _port, **_kwargs: LocalApiState.ABSENT,
    )
    monkeypatch.setattr(launch_web, "wait_for_local_api", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(launch_web, "_start_process", fake_start)
    monkeypatch.setattr(launch_web, "_assert_port_available", lambda *_args, **_kwargs: None)

    assert (
        launch_web.run_web_stack(
            {
                "PIXELLE_WEB_PORT": "8512",
                "PIXELLE_LAUNCH_ID": TEST_LAUNCH_ID,
            }
        )
        == 0
    )

    assert len(captured) == 2
    arguments, environment = captured[-1]
    assert arguments[-1] == "8512"
    assert environment["PIXELLE_WEB_PORT"] == "8512"
    assert environment["PIXELLE_API_BASE_URL"] == "http://localhost:6789/api"
    assert is_launch_id(environment["PIXELLE_LAUNCH_ID"])
    assert environment["PIXELLE_LAUNCH_ID"] != TEST_LAUNCH_ID
    assert environment["TMP"].endswith("_runtime\\tmp")
