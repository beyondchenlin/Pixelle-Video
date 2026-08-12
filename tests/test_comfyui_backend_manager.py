import os
import subprocess
from pathlib import Path

import pytest

from pixelle_video.config.schema import ComfyUIBackendProfile
from pixelle_video.services.comfyui_backend_manager import (
    ComfyUIBackendCommandResult,
    ComfyUIBackendState,
    ManagedComfyUIBackend,
)


class _ProbeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def probe_backend(self):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else {"system": {}}
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _QueueClient:
    def __init__(self, events=None, *, error=None, health=None):
        self.events = events if events is not None else []
        self.error = error
        self.health = health if health is not None else {"system": {}}

    async def wait_until_idle(self):
        self.events.append("queue_idle")
        if self.error is not None:
            raise self.error

    async def probe_backend(self):
        if isinstance(self.health, Exception):
            raise self.health
        return self.health


def _state(ownership, *, listener=True, pid_file=False):
    return ComfyUIBackendState(
        ownership=ownership,
        listener_present=listener,
        pid_file_present=pid_file,
        payload={
            "listener_present": listener,
            "listener_is_managed_backend": ownership == "pixelle",
            "pid_file_present": pid_file,
        },
    )


def test_managed_backend_auto_mode_only_manages_local_pixelle_port(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
    )

    monkeypatch.setattr(backend, "_management_runtime_available", lambda: True)
    assert backend.can_manage() is True


def test_managed_backend_auto_mode_does_not_manage_default_desktop_port():
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8188",
        management_mode="auto",
    )

    assert backend.can_manage() is False


def test_managed_backend_required_mode_does_not_take_over_remote_host():
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://192.168.1.10:9000",
        management_mode="required",
    )

    assert backend.can_manage() is False


def test_managed_backend_disabled_mode_never_manages():
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="disabled",
    )

    assert backend.can_manage() is False


def test_managed_backend_profile_managed_false_disables_management(tmp_path):
    profile = ComfyUIBackendProfile(
        url="http://127.0.0.1:8001",
        managed=False,
        data_root=str(tmp_path / "image-data"),
        runtime_dir=str(tmp_path / "runtime" / "image"),
        logs_dir=str(tmp_path / "logs" / "image"),
        database_url=f"sqlite:///{(tmp_path / 'image-data' / 'user' / 'comfyui.db').as_posix()}",
    )
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        profile_name="image",
        profile=profile,
        management_mode="required",
    )

    assert backend.can_manage() is False


@pytest.mark.asyncio
async def test_required_restart_reports_profile_managed_false(tmp_path):
    profile = ComfyUIBackendProfile(
        url="http://127.0.0.1:8001",
        managed=False,
        data_root=str(tmp_path / "image-data"),
        runtime_dir=str(tmp_path / "runtime" / "image"),
        logs_dir=str(tmp_path / "logs" / "image"),
        database_url=f"sqlite:///{(tmp_path / 'image-data' / 'user' / 'comfyui.db').as_posix()}",
    )
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        profile_name="image",
        profile=profile,
        management_mode="required",
    )

    with pytest.raises(RuntimeError, match="profile 'image'.*managed=false"):
        await backend.restart(reason="test-required-mode")


def test_managed_backend_auto_mode_manages_local_profile_ports(tmp_path, monkeypatch):
    for profile_name, port in (("image", 8001), ("tts", 8002)):
        profile = ComfyUIBackendProfile(
            url=f"http://127.0.0.1:{port}",
            data_root=str(tmp_path / f"{profile_name}-data"),
            runtime_dir=str(tmp_path / "runtime" / profile_name),
            logs_dir=str(tmp_path / "logs" / profile_name),
            database_url=f"sqlite:///{(tmp_path / f'{profile_name}-data' / 'user' / 'comfyui.db').as_posix()}",
        )
        backend = ManagedComfyUIBackend(
            repo_root=Path.cwd(),
            profile_name=profile_name,
            profile=profile,
            management_mode="auto",
        )

        monkeypatch.setattr(backend, "_management_runtime_available", lambda: True)
        assert backend.can_manage() is True


def test_managed_backend_auto_mode_skips_unsupported_management_runtime(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
    )
    monkeypatch.setattr(backend, "_management_runtime_available", lambda: False)

    assert backend.can_manage() is False


def test_managed_backend_uses_profile_runtime_arguments(tmp_path):
    profile = ComfyUIBackendProfile(
        url="http://127.0.0.1:8001",
        data_root=str(tmp_path / "image-data"),
        runtime_dir=str(tmp_path / "runtime" / "image"),
        logs_dir=str(tmp_path / "logs" / "image"),
        database_url=f"sqlite:///{(tmp_path / 'image-data' / 'user' / 'comfyui.db').as_posix()}",
    )
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        profile_name="image",
        profile=profile,
        management_mode="required",
    )

    args = backend._script_args()

    assert "-ProfileName" in args
    assert "image" in args
    assert "-DataRoot" in args
    assert str(tmp_path / "image-data") in args
    assert "-SharedBasePath" in args
    assert str(tmp_path) in args
    assert "-RuntimeDir" in args
    assert str(tmp_path / "runtime" / "image") in args
    assert "-LogsDir" in args
    assert str(tmp_path / "logs" / "image") in args
    assert "-DatabaseUrl" in args
    assert profile.database_url in args
    assert "-Port" in args
    assert "8001" in args
    assert args[args.index("-ResourcePolicy") + 1] == "auto"
    assert "-MinimumFreeCommitGB" not in args


def test_managed_backend_passes_optional_profile_script_arguments(tmp_path):
    python_exe = tmp_path / "venv" / "Scripts" / "python.exe"
    comfyui_root = tmp_path / "ComfyUI"
    frontend_root = comfyui_root / "web_custom_versions" / "desktop_app"
    extra_models_config = tmp_path / "extra_models_config.yaml"
    profile = ComfyUIBackendProfile(
        url="http://localhost:8020",
        python_exe=str(python_exe),
        comfyui_root=str(comfyui_root),
        frontend_root=str(frontend_root),
        extra_models_config=str(extra_models_config),
        data_root=str(tmp_path / "data"),
        runtime_dir=str(tmp_path / "runtime"),
        logs_dir=str(tmp_path / "logs"),
        database_url=f"sqlite:///{(tmp_path / 'data' / 'user' / 'comfyui.db').as_posix()}",
    )
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        profile_name="image",
        profile=profile,
        management_mode="required",
    )

    args = backend._script_args()

    assert "-PythonExe" in args
    assert str(python_exe) in args
    assert "-ComfyUIRoot" in args
    assert str(comfyui_root) in args
    assert "-FrontEndRoot" in args
    assert str(frontend_root) in args
    assert "-ExtraModelsConfig" in args
    assert str(extra_models_config) in args


def test_managed_backend_normalizes_localhost_for_powershell_listener(tmp_path):
    profile = ComfyUIBackendProfile(
        url="http://localhost:8020",
        data_root=str(tmp_path / "data"),
        runtime_dir=str(tmp_path / "runtime"),
        logs_dir=str(tmp_path / "logs"),
    )
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        profile_name="default",
        profile=profile,
        management_mode="required",
    )

    args = backend._script_args()

    assert args[args.index("-HostAddress") + 1] == "127.0.0.1"


@pytest.mark.asyncio
async def test_managed_backend_reads_script_output_from_files(monkeypatch, tmp_path):
    scripts_dir = tmp_path / "scripts" / "comfyui"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "start_backend.ps1").write_text("# test", encoding="utf-8")
    working_directory = tmp_path / "configured-project"
    working_directory.mkdir()
    backend = ManagedComfyUIBackend(
        repo_root=tmp_path,
        working_directory=working_directory,
        comfyui_url="http://127.0.0.1:8001",
        profile=ComfyUIBackendProfile(
            url="http://127.0.0.1:8001",
            data_root=str(tmp_path / "data"),
            runtime_dir=str(tmp_path / "runtime"),
            logs_dir=str(tmp_path / "logs"),
        ),
        management_mode="required",
    )

    def fake_run(command, **kwargs):
        assert kwargs["cwd"] == str(working_directory.resolve())
        assert kwargs.get("capture_output") is not True
        assert kwargs["stdout"] is not subprocess.PIPE
        assert kwargs["stderr"] is not subprocess.PIPE
        kwargs["stdout"].write('{"started":true,"pid":1234}')
        kwargs["stdout"].flush()
        kwargs["stderr"].write("backend warning")
        kwargs["stderr"].flush()
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        "pixelle_video.services.comfyui_backend_manager.subprocess.run",
        fake_run,
    )

    result = await backend.start(reason="test-start")

    assert result.returncode == 0
    assert result.payload == {"started": True, "pid": 1234}
    assert result.stderr == "backend warning"


@pytest.mark.asyncio
async def test_managed_backend_script_timeout_reports_context(monkeypatch, tmp_path):
    scripts_dir = tmp_path / "scripts" / "comfyui"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "stop_backend.ps1").write_text("# test", encoding="utf-8")
    backend = ManagedComfyUIBackend(
        repo_root=tmp_path,
        comfyui_url="http://127.0.0.1:8001",
        profile=ComfyUIBackendProfile(
            url="http://127.0.0.1:8001",
            data_root=str(tmp_path / "data"),
            runtime_dir=str(tmp_path / "runtime"),
            logs_dir=str(tmp_path / "logs"),
        ),
        management_mode="required",
        maintenance_client=_QueueClient(),
    )

    def fake_run(command, **kwargs):
        assert kwargs["timeout"] > 0
        kwargs["stdout"].write('{"stopped":false}')
        kwargs["stdout"].flush()
        kwargs["stderr"].write("still waiting")
        kwargs["stderr"].flush()
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(
        "pixelle_video.services.comfyui_backend_manager.subprocess.run",
        fake_run,
    )
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(_state("pixelle", pid_file=True)),
    )

    with pytest.raises(RuntimeError, match="ComfyUI backend stop command timed out"):
        await backend.stop(reason="test-stop")


async def _async_result(value):
    return value


@pytest.mark.asyncio
async def test_auto_mode_reuses_healthy_external_backend_without_starting(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
        maintenance_client=_ProbeClient([{"system": {"comfyui_version": "0.31.0"}}]),
    )
    async def fail_inspection(*, reason):
        raise AssertionError(f"healthy auto mode must not inspect processes: {reason}")

    async def fail_start(*, reason):
        raise AssertionError(f"external backend must not be started: {reason}")

    monkeypatch.setattr(backend, "start", fail_start)
    monkeypatch.setattr(backend, "inspect_state", fail_inspection)

    result = await backend.ensure_ready(reason="pre-workflow")

    assert result.ownership == "unknown"
    assert result.started is False
    assert result.reused_existing is True


@pytest.mark.asyncio
@pytest.mark.parametrize("ownership", ("external", "pixelle"))
async def test_auto_mode_captures_healthy_backend_ownership_when_batch_stop_is_enabled(
    monkeypatch,
    ownership,
):
    profile = ComfyUIBackendProfile(
        url="http://127.0.0.1:8000",
        stop_after_batch=True,
    )
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        profile=profile,
        management_mode="auto",
        maintenance_client=_ProbeClient([{"system": {"comfyui_version": "0.31.0"}}]),
    )
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(_state(ownership)),
    )

    result = await backend.ensure_ready(reason="pre-workflow")

    assert result.ownership == ownership
    assert result.started is False
    assert result.reused_existing is True


@pytest.mark.asyncio
async def test_auto_mode_keeps_healthy_backend_when_ownership_capture_fails(monkeypatch):
    profile = ComfyUIBackendProfile(
        url="http://127.0.0.1:8000",
        stop_after_batch=True,
    )
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        profile=profile,
        management_mode="auto",
        maintenance_client=_ProbeClient([{"system": {"comfyui_version": "0.31.0"}}]),
    )

    async def _fail_inspection(*, reason):
        raise PermissionError(f"inspection denied: {reason}")

    monkeypatch.setattr(backend, "inspect_state", _fail_inspection)

    result = await backend.ensure_ready(reason="pre-workflow")

    assert result.ownership == "unknown"
    assert result.reused_existing is True


@pytest.mark.asyncio
async def test_disabled_mode_reuses_healthy_backend_as_external(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="disabled",
        maintenance_client=_ProbeClient([{"system": {"comfyui_version": "0.31.0"}}]),
    )

    async def fail_lifecycle(*, reason):
        raise AssertionError(f"disabled mode must not inspect or start: {reason}")

    monkeypatch.setattr(backend, "inspect_state", fail_lifecycle)
    monkeypatch.setattr(backend, "start", fail_lifecycle)

    result = await backend.ensure_ready(reason="pre-workflow")

    assert result.ownership == "external"
    assert result.reused_existing is True


@pytest.mark.asyncio
async def test_required_mode_refuses_healthy_external_backend(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="required",
        maintenance_client=_ProbeClient([{"system": {"comfyui_version": "0.31.0"}}]),
    )
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(_state("external")),
    )

    with pytest.raises(RuntimeError, match="not owned by Pixelle"):
        await backend.ensure_ready(reason="pre-workflow")


@pytest.mark.asyncio
async def test_required_mode_cleans_started_process_when_ownership_is_unconfirmed(
    monkeypatch,
):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="required",
        maintenance_client=_ProbeClient(
            [ConnectionError("not running"), {"system": {"comfyui_version": "0.31.0"}}]
        ),
    )
    monkeypatch.setattr(backend, "_management_runtime_available", lambda: True)
    states = iter(
        [
            _state("absent", listener=False),
            _state("external", listener=True),
        ]
    )
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(next(states)),
    )

    async def start(*, reason):
        return ComfyUIBackendCommandResult(
            action="start",
            returncode=0,
            stdout="",
            stderr="",
            payload={"started": True},
        )

    cleanup_calls = []

    async def run_script(script_name, action, *, reason, extra_args=None):
        cleanup_calls.append((script_name, action, reason, extra_args))
        return ComfyUIBackendCommandResult(
            action="stop",
            returncode=0,
            stdout="",
            stderr="",
            payload={"stopped": True},
        )

    monkeypatch.setattr(backend, "start", start)
    monkeypatch.setattr(backend, "_run_script", run_script)

    with pytest.raises(RuntimeError, match="ownership could not be confirmed"):
        await backend.ensure_ready(reason="pre-workflow")

    assert cleanup_calls == [
        (
            "stop_backend.ps1",
            "stop",
            "pre-workflow:unconfirmed-ownership",
            None,
        )
    ]


@pytest.mark.asyncio
async def test_auto_mode_starts_absent_backend_and_confirms_api_health(monkeypatch):
    probe = _ProbeClient(
        [
            ConnectionError("not running"),
            {"system": {"comfyui_version": "0.31.0"}},
        ]
    )
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
        maintenance_client=probe,
    )
    monkeypatch.setattr(backend, "_management_runtime_available", lambda: True)
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(_state("absent", listener=False)),
    )

    async def start(*, reason):
        return ComfyUIBackendCommandResult(
            action="start",
            returncode=0,
            stdout="",
            stderr="",
            payload={"started": True},
        )

    monkeypatch.setattr(backend, "start", start)

    result = await backend.ensure_ready(reason="pre-workflow")

    assert result.ownership == "pixelle"
    assert result.started is True
    assert probe.calls == 2


@pytest.mark.asyncio
async def test_auto_mode_cleans_recorded_orphan_before_starting(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
        maintenance_client=_ProbeClient(
            [ConnectionError("not running"), {"system": {"comfyui_version": "0.31.0"}}]
        ),
    )
    monkeypatch.setattr(backend, "_management_runtime_available", lambda: True)
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(
            _state("absent", listener=False, pid_file=True)
        ),
    )
    events = []

    async def stop(*, reason):
        events.append(("stop", reason))
        return ComfyUIBackendCommandResult(
            action="stop",
            returncode=0,
            stdout="",
            stderr="",
            payload={"stopped": True},
        )

    async def start(*, reason):
        events.append(("start", reason))
        return ComfyUIBackendCommandResult(
            action="start",
            returncode=0,
            stdout="",
            stderr="",
            payload={"started": True},
        )

    monkeypatch.setattr(backend, "stop", stop)
    monkeypatch.setattr(backend, "start", start)

    result = await backend.ensure_ready(reason="pre-workflow")

    assert result.started is True
    assert events == [
        ("stop", "pre-workflow:clean-stale-owned-process"),
        ("start", "pre-workflow"),
    ]


@pytest.mark.asyncio
async def test_auto_mode_waits_for_existing_listener_to_recover(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
        maintenance_client=_ProbeClient(
            [ConnectionError("temporarily busy"), {"system": {"comfyui_version": "0.31.0"}}]
        ),
    )
    monkeypatch.setattr(backend, "_management_runtime_available", lambda: True)
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(_state("external")),
    )

    async def fail_start(*, reason):
        raise AssertionError(f"an occupied listener must not trigger startup: {reason}")

    monkeypatch.setattr(backend, "start", fail_start)

    result = await backend.ensure_ready(reason="pre-workflow")

    assert result.ownership == "external"
    assert result.reused_existing is True


@pytest.mark.asyncio
async def test_auto_mode_refuses_to_start_over_unhealthy_external_listener(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
        maintenance_client=_ProbeClient([ConnectionError("incompatible endpoint")]),
    )
    monkeypatch.setattr(backend, "_management_runtime_available", lambda: True)
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(_state("external")),
    )

    async def fail_health_wait(*, timeout_seconds=None):
        raise TimeoutError(f"not healthy after {timeout_seconds}s")

    async def fail_start(*, reason):
        raise AssertionError(f"external listener must not trigger startup: {reason}")

    monkeypatch.setattr(backend, "_wait_for_backend_health", fail_health_wait)
    monkeypatch.setattr(backend, "start", fail_start)

    with pytest.raises(RuntimeError, match="already occupied.*does not own"):
        await backend.ensure_ready(reason="pre-workflow")


@pytest.mark.asyncio
async def test_stop_preserves_external_backend(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
    )
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(_state("external")),
    )

    result = await backend.stop(reason="resource-release")

    assert result.payload["stopped"] is False
    assert result.payload["reason"] == "external_backend_not_owned"


@pytest.mark.asyncio
async def test_stop_waits_for_idle_queue_before_stopping_owned_listener(monkeypatch):
    events = []
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
        maintenance_client=_QueueClient(events),
    )
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(_state("pixelle", pid_file=True)),
    )

    async def run_script(script_name, action, *, reason, extra_args=None):
        events.append("stop")
        return ComfyUIBackendCommandResult(
            action=action,
            returncode=0,
            stdout="",
            stderr="",
            payload={"stopped": True},
        )

    monkeypatch.setattr(backend, "_run_script", run_script)

    result = await backend.stop(reason="batch-stop")

    assert result.payload["stopped"] is True
    assert events == ["queue_idle", "stop"]


@pytest.mark.asyncio
async def test_stop_fails_closed_when_owned_listener_queue_is_unknown(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
        maintenance_client=_QueueClient(error=TimeoutError("queue unavailable")),
    )
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(_state("pixelle", pid_file=True)),
    )

    async def fail_script(*args, **kwargs):
        raise AssertionError("unknown queue state must not stop a live listener")

    monkeypatch.setattr(backend, "_run_script", fail_script)

    with pytest.raises(RuntimeError, match="queue could not be confirmed idle"):
        await backend.stop(reason="batch-stop")


@pytest.mark.asyncio
async def test_stop_cleans_crashed_owned_process_without_queue_probe(monkeypatch):
    events = []
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
        maintenance_client=_QueueClient(events, error=AssertionError("must not probe")),
    )
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(
            _state("absent", listener=False, pid_file=True)
        ),
    )

    async def run_script(script_name, action, *, reason, extra_args=None):
        events.append("stop")
        return ComfyUIBackendCommandResult(
            action=action,
            returncode=0,
            stdout="",
            stderr="",
            payload={"stopped": True},
        )

    monkeypatch.setattr(backend, "_run_script", run_script)

    result = await backend.stop(reason="crash-cleanup")

    assert result.payload["stopped"] is True
    assert events == ["stop"]


@pytest.mark.asyncio
async def test_stop_cleans_api_unhealthy_owned_listener_when_queue_is_unreachable(
    monkeypatch,
):
    events = []
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
        maintenance_client=_QueueClient(
            events,
            error=TimeoutError("queue unavailable"),
            health=ConnectionError("backend unavailable"),
        ),
    )
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(_state("pixelle", pid_file=True)),
    )

    async def run_script(script_name, action, *, reason, extra_args=None):
        events.append("stop")
        return ComfyUIBackendCommandResult(
            action=action,
            returncode=0,
            stdout="",
            stderr="",
            payload={"stopped": True},
        )

    monkeypatch.setattr(backend, "_run_script", run_script)

    result = await backend.stop(reason="api-unhealthy")

    assert result.payload["stopped"] is True
    assert events == ["queue_idle", "stop"]


@pytest.mark.asyncio
async def test_stop_cleans_owned_record_without_touching_external_listener(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
    )
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(_state("external", pid_file=True)),
    )
    calls = []

    async def run_script(script_name, action, *, reason, extra_args=None):
        calls.append((script_name, action, reason, extra_args))
        return ComfyUIBackendCommandResult(
            action="stop",
            returncode=0,
            stdout="",
            stderr="",
            payload={
                "stopped": True,
                "preserved_external_listener": True,
            },
        )

    monkeypatch.setattr(backend, "_run_script", run_script)

    result = await backend.stop(reason="shutdown")

    assert result.payload["stopped"] is True
    assert result.payload["preserved_external_listener"] is True
    assert calls == [("stop_backend.ps1", "stop", "shutdown", None)]


@pytest.mark.asyncio
async def test_restart_skips_when_process_ownership_is_unknown(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
    )
    monkeypatch.setattr(backend, "can_manage", lambda: True)
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(_state("unknown", listener=False)),
    )

    async def fail_lifecycle(*, reason):
        raise AssertionError(f"unknown ownership must not mutate lifecycle: {reason}")

    monkeypatch.setattr(backend, "stop", fail_lifecycle)
    monkeypatch.setattr(backend, "start", fail_lifecycle)

    assert await backend.restart(reason="memory-release") is False


@pytest.mark.asyncio
async def test_restart_does_not_start_when_stop_is_unconfirmed(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
    )
    monkeypatch.setattr(backend, "can_manage", lambda: True)
    monkeypatch.setattr(
        backend,
        "inspect_state",
        lambda **_kwargs: _async_result(_state("pixelle", pid_file=True)),
    )

    async def stop(*, reason):
        return ComfyUIBackendCommandResult(
            action="stop",
            returncode=0,
            stdout="",
            stderr="",
            payload={
                "stopped": False,
                "reason": "ownership_record_missing_or_mismatch",
            },
        )

    async def fail_start(*, reason):
        raise AssertionError(f"unconfirmed stop must not be followed by start: {reason}")

    monkeypatch.setattr(backend, "stop", stop)
    monkeypatch.setattr(backend, "start", fail_start)

    assert await backend.restart(reason="memory-release") is False


@pytest.mark.asyncio
async def test_start_command_includes_typed_resource_contract(monkeypatch):
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        profile=ComfyUIBackendProfile(
            url="http://127.0.0.1:8000",
            resource_policy="memory_safe",
            minimum_free_commit_gb=12.5,
        ),
    )

    captured = {}

    async def _run_script(script_name, action, *, reason, extra_args=None):
        captured["extra_args"] = extra_args
        return ComfyUIBackendCommandResult(
            action=action,
            returncode=0,
            stdout="",
            stderr="",
            payload={"started": True},
        )

    monkeypatch.setattr(backend, "_run_script", _run_script)

    script_args = backend._script_args()
    await backend.start(reason="test")

    assert script_args[script_args.index("-ResourcePolicy") + 1] == "memory_safe"
    assert script_args[script_args.index("-MinimumFreeCommitGB") + 1] == "12.5"
    assert captured["extra_args"] == [
        "-ReadyTimeoutSeconds",
        "90",
    ]


def test_recent_failure_diagnostic_classifies_only_fresh_bounded_memory_log(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    stderr_log = logs_dir / "comfyui-backend.stderr.log"
    stderr_log.write_text(
        "fatal : Memory allocation failure\nCUDA error: CUBLAS_STATUS_EXECUTION_FAILED",
        encoding="utf-8",
    )
    backend = ManagedComfyUIBackend(
        repo_root=tmp_path,
        working_directory=tmp_path,
        profile=ComfyUIBackendProfile(
            url="http://127.0.0.1:8000",
            logs_dir=str(logs_dir),
        ),
    )

    assert backend.diagnose_recent_failure() == "memory_exhaustion"

    old_timestamp = stderr_log.stat().st_mtime - 300
    os.utime(stderr_log, (old_timestamp, old_timestamp))
    assert backend.diagnose_recent_failure() is None
