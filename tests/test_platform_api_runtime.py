from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

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
from scripts.launch_web import (
    LaunchConfigurationError,
    LocalApiState,
    build_runtime_target,
    probe_local_api,
)


def _health_payload(**overrides: object) -> bytes:
    payload: dict[str, object] = {
        "status": "healthy",
        "version": "0.1.0",
        "service": "Pixelle-Video API",
        "checkout_root_id": launch_web.EXPECTED_CHECKOUT_ROOT_ID,
        "project_root_id": launch_web.EXPECTED_PROJECT_ROOT_ID,
        "output_root_id": launch_web.DEFAULT_LOCAL_API_IDENTITY.output_root_id,
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
        assert probe_local_api(server.server_port) is LocalApiState.READY
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
        assert probe_local_api(server.server_port) is LocalApiState.IDENTITY_MISMATCH
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
    ],
)
def test_local_probe_rejects_an_api_without_a_valid_project_identity(payload: bytes) -> None:
    server, thread = _start_health_server(payload)
    try:
        assert probe_local_api(server.server_port) is LocalApiState.INCOMPATIBLE
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_local_probe_rejects_a_foreign_service_on_the_port() -> None:
    server, thread = _start_health_server(b'{"status":"healthy","service":"other-project"}')
    try:
        assert probe_local_api(server.server_port) is LocalApiState.OCCUPIED
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_local_probe_does_not_follow_a_foreign_service_redirect() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RedirectHealthHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert probe_local_api(server.server_port) is LocalApiState.OCCUPIED
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    "state",
    [LocalApiState.IDENTITY_MISMATCH, LocalApiState.INCOMPATIBLE],
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

    assert launch_web.wait_for_local_api(6789, timeout=30.0) is False


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


def test_supervisor_cleans_up_only_the_api_process_it_started(monkeypatch) -> None:
    api_process = _FakeProcess()
    web_process = _FakeProcess(exit_code=0)
    started: list[list[str]] = []

    def fake_start(arguments: list[str], *, environ: dict[str, str]) -> _FakeProcess:
        assert environ["PIXELLE_API_PORT"] == "6789"
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


def test_supervisor_reuses_a_healthy_existing_api_without_owning_it(monkeypatch) -> None:
    web_process = _FakeProcess(exit_code=0)
    started: list[list[str]] = []

    def fake_start(arguments: list[str], *, environ: dict[str, str]) -> _FakeProcess:
        started.append(arguments)
        return web_process

    monkeypatch.setattr(
        launch_web,
        "probe_local_api",
        lambda _port, **_kwargs: LocalApiState.READY,
    )
    monkeypatch.setattr(launch_web, "_start_process", fake_start)
    monkeypatch.setattr(launch_web, "_assert_port_available", lambda *_args, **_kwargs: None)

    assert launch_web.run_web_stack({}) == 0
    assert len(started) == 1
    assert "streamlit" in started[0]


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


@pytest.mark.parametrize(
    ("state", "message"),
    [
        (LocalApiState.IDENTITY_MISMATCH, "another project root, checkout, or output root"),
        (LocalApiState.INCOMPATIBLE, "project identity"),
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
    web_process = _FakeProcess(exit_code=0)
    captured: dict[str, object] = {}

    def fake_start(arguments: list[str], *, environ: dict[str, str]) -> _FakeProcess:
        captured["arguments"] = arguments
        captured["environment"] = environ
        return web_process

    monkeypatch.setattr(
        launch_web,
        "probe_local_api",
        lambda _port, **_kwargs: LocalApiState.READY,
    )
    monkeypatch.setattr(launch_web, "_start_process", fake_start)
    monkeypatch.setattr(launch_web, "_assert_port_available", lambda *_args, **_kwargs: None)

    assert launch_web.run_web_stack({"PIXELLE_WEB_PORT": "8512"}) == 0

    arguments = captured["arguments"]
    environment = captured["environment"]
    assert isinstance(arguments, list)
    assert arguments[-1] == "8512"
    assert isinstance(environment, dict)
    assert environment["PIXELLE_WEB_PORT"] == "8512"
    assert environment["PIXELLE_API_BASE_URL"] == "http://localhost:6789/api"
    assert environment["TMP"].endswith("_runtime\\tmp")
