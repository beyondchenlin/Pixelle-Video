import socket
from pathlib import Path

import pytest

from pixelle_video.services.application_supervisor import (
    ApplicationSupervisor,
    ApplicationSupervisorError,
    build_application_runtime,
)


class _FakeProcess:
    def __init__(self, *, returncode=None):
        self.returncode = returncode
        self.pid = 12345

    def poll(self):
        return self.returncode


def test_build_application_runtime_owns_consistent_local_endpoints(tmp_path):
    runtime = build_application_runtime(
        tmp_path,
        {
            "PIXELLE_API_PORT": "8890",
            "PIXELLE_WEB_PORT": "8510",
            "PIXELLE_API_BASE_URL": "http://stale.invalid/api",
        },
    )

    assert runtime.api_port == 8890
    assert runtime.web_port == 8510
    assert runtime.environment["PIXELLE_API_BASE_URL"] == "http://127.0.0.1:8890/api"
    assert Path(runtime.environment["TMP"]).is_dir()


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"PIXELLE_API_PORT": "abc"}, "must be an integer"),
        ({"PIXELLE_API_PORT": "0"}, "between 1 and 65535"),
        ({"PIXELLE_API_PORT": "8501", "PIXELLE_WEB_PORT": "8501"}, "must be different"),
        ({"PIXELLE_API_READY_TIMEOUT_SECONDS": "0"}, "positive finite number"),
        ({"PIXELLE_API_READY_TIMEOUT_SECONDS": "nan"}, "positive finite number"),
    ],
)
def test_build_application_runtime_rejects_invalid_boundaries(tmp_path, environment, message):
    with pytest.raises(ApplicationSupervisorError, match=message):
        build_application_runtime(tmp_path, environment)


def test_supervisor_refuses_port_owned_by_existing_process(tmp_path):
    supervisor = ApplicationSupervisor(repo_root=tmp_path)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        with pytest.raises(ApplicationSupervisorError, match="already in use"):
            supervisor._assert_port_available(port, "API")


def test_supervisor_cleans_api_when_web_exits(tmp_path, monkeypatch):
    api_process = _FakeProcess()
    web_process = _FakeProcess(returncode=0)
    processes = iter((api_process, web_process))
    supervisor = ApplicationSupervisor(
        repo_root=tmp_path,
        process_factory=lambda *args, **kwargs: next(processes),
    )
    terminated = []
    monkeypatch.setattr(supervisor, "_assert_port_available", lambda *args: None)
    monkeypatch.setattr(supervisor, "_wait_for_api", lambda process: None)
    monkeypatch.setattr(supervisor, "_install_signal_handlers", lambda: {})
    monkeypatch.setattr(supervisor, "_restore_signal_handlers", lambda handlers: None)
    monkeypatch.setattr(supervisor, "_terminate_process", terminated.append)

    returncode = supervisor.run()

    assert returncode == 0
    assert terminated == [web_process, api_process]


def test_supervisor_cleans_started_api_when_readiness_fails(tmp_path, monkeypatch):
    api_process = _FakeProcess(returncode=7)
    supervisor = ApplicationSupervisor(
        repo_root=tmp_path,
        source_environment={"PIXELLE_API_READY_TIMEOUT_SECONDS": "0.2"},
        process_factory=lambda *args, **kwargs: api_process,
    )
    terminated = []
    monkeypatch.setattr(supervisor, "_assert_port_available", lambda *args: None)
    monkeypatch.setattr(supervisor, "_install_signal_handlers", lambda: {})
    monkeypatch.setattr(supervisor, "_restore_signal_handlers", lambda handlers: None)
    monkeypatch.setattr(supervisor, "_terminate_process", terminated.append)

    with pytest.raises(ApplicationSupervisorError, match="exited before readiness with code 7"):
        supervisor.run()

    assert terminated == [api_process]


def test_supervisor_uses_current_interpreter_and_explicit_ports(tmp_path):
    supervisor = ApplicationSupervisor(
        repo_root=tmp_path,
        source_environment={"PIXELLE_API_PORT": "8891", "PIXELLE_WEB_PORT": "8511"},
    )

    assert supervisor._api_command()[-1] == "8891"
    assert supervisor._web_command()[-1] == "8511"
    assert "uvicorn" in supervisor._api_command()
    assert "streamlit" in supervisor._web_command()
