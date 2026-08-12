from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from loguru import logger

from pixelle_video.config.schema import ComfyUIBackendProfile
from pixelle_video.services.comfyui_errors import looks_like_memory_exhaustion
from pixelle_video.services.comfyui_maintenance import ComfyUIMaintenanceClient


@dataclass(frozen=True)
class ComfyUIBackendCommandResult:
    action: str
    returncode: int
    stdout: str
    stderr: str
    payload: dict[str, Any]


ComfyUIBackendOwnership = Literal["pixelle", "external", "absent", "unknown"]


@dataclass(frozen=True)
class ComfyUIBackendState:
    ownership: ComfyUIBackendOwnership
    listener_present: bool
    pid_file_present: bool
    payload: dict[str, Any]

    @property
    def owned_by_pixelle(self) -> bool:
        return self.ownership == "pixelle"


@dataclass(frozen=True)
class ComfyUIBackendReadyResult:
    ownership: ComfyUIBackendOwnership
    started: bool
    reused_existing: bool
    health: dict[str, Any]


class ComfyUIBackendController:
    """Connects to existing ComfyUI or manages a process Pixelle actually owns."""

    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        working_directory: str | Path | None = None,
        comfyui_url: str | None = None,
        profile_name: str = "default",
        profile: ComfyUIBackendProfile | None = None,
        management_mode: str = "auto",
        ready_timeout_seconds: int = 90,
        command_timeout_seconds: int | None = None,
        maintenance_client: ComfyUIMaintenanceClient | None = None,
    ) -> None:
        self.repo_root = (Path(repo_root) if repo_root else Path.cwd()).resolve()
        self.working_directory = (
            Path(working_directory).resolve()
            if working_directory is not None
            else self.repo_root
        )
        self.profile_name = (profile_name or "default").strip() or "default"
        self.profile = profile or ComfyUIBackendProfile(url=comfyui_url)
        self.comfyui_url = str(self.profile.url or comfyui_url or "").strip()
        self.management_mode = (management_mode or "auto").strip().lower()
        self.ready_timeout_seconds = ready_timeout_seconds
        self.command_timeout_seconds = command_timeout_seconds
        self.maintenance_client = maintenance_client or ComfyUIMaintenanceClient(
            self.comfyui_url
        )

    @property
    def scripts_dir(self) -> Path:
        return self.repo_root / "scripts" / "comfyui"

    def can_manage(self) -> bool:
        if not self.profile.managed:
            return False
        if self.management_mode == "disabled":
            return False
        if not self._management_runtime_available():
            return False
        parsed = urlparse(self.comfyui_url)
        host = (parsed.hostname or "").lower()
        port = self._resolved_port()
        if host not in {"127.0.0.1", "localhost", "::1"} or port is None:
            return False
        if port == 8000:
            return True
        return bool(
            self.profile.data_root
            and self.profile.runtime_dir
            and self.profile.logs_dir
            and port != 8188
        )

    def can_inspect_local_process(self) -> bool:
        parsed = urlparse(self.comfyui_url)
        host = (parsed.hostname or "").lower()
        return bool(
            host in {"127.0.0.1", "localhost", "::1"}
            and self._resolved_port() is not None
            and self._management_runtime_available()
            and (self.scripts_dir / "check_backend.ps1").exists()
        )

    def _management_runtime_available(self) -> bool:
        return os.name == "nt" and shutil.which("powershell") is not None

    async def inspect_state(self, *, reason: str) -> ComfyUIBackendState:
        if not self.can_inspect_local_process():
            return ComfyUIBackendState(
                ownership="unknown",
                listener_present=False,
                pid_file_present=False,
                payload={"reason": "local_process_inspection_unavailable"},
            )

        result = await self.check(reason=reason)
        payload = result.payload or {}
        listener_present = bool(payload.get("listener_present"))
        pid_file_present = bool(payload.get("pid_file_present"))
        if listener_present and payload.get("listener_is_managed_backend"):
            ownership: ComfyUIBackendOwnership = "pixelle"
        elif listener_present:
            ownership = "external"
        else:
            ownership = "absent"
        return ComfyUIBackendState(
            ownership=ownership,
            listener_present=listener_present,
            pid_file_present=pid_file_present,
            payload=payload,
        )

    async def ensure_ready(self, *, reason: str) -> ComfyUIBackendReadyResult:
        health, health_error = await self._probe_backend_safely()
        if health is not None:
            ownership: ComfyUIBackendOwnership = "unknown"
            if self.management_mode == "required":
                state = await self.inspect_state(reason=f"{reason}:strict-ownership-check")
                if not state.owned_by_pixelle:
                    raise RuntimeError(
                        "ComfyUI backend management is required, but the healthy backend at "
                        f"{self.comfyui_url} is not owned by Pixelle"
                    )
                ownership = "pixelle"
            elif self.management_mode == "disabled" or not self.profile.managed:
                ownership = "external"
            elif self.profile.stop_after_batch:
                state, state_error = await self._inspect_state_safely(
                    reason=f"{reason}:capture-task-start-ownership"
                )
                if state is not None:
                    ownership = state.ownership
                elif state_error:
                    logger.warning(
                        "Could not capture ComfyUI task-start process ownership; "
                        "cleanup will re-check and fail safe: "
                        f"role='{self.profile_name}', error='{state_error}'"
                    )
            logger.info(
                "Reusing healthy existing ComfyUI backend without changing its process "
                f"lifecycle at {self.comfyui_url} ({reason})"
            )
            return ComfyUIBackendReadyResult(
                ownership=ownership,
                started=False,
                reused_existing=True,
                health=health,
            )

        if not self.can_manage():
            detail = health_error or "health probe failed"
            raise RuntimeError(
                f"ComfyUI backend at {self.comfyui_url} is unavailable and Pixelle "
                f"is not allowed to start it: {detail}"
            )

        state, state_error = await self._inspect_state_safely(
            reason=f"{reason}:unhealthy-listener-check"
        )
        if state is not None and state.listener_present:
            if not state.owned_by_pixelle and state.pid_file_present:
                await self.stop(reason=f"{reason}:clean-owned-orphan")
            try:
                recovered_health = await self._wait_for_backend_health(
                    timeout_seconds=min(max(1, self.ready_timeout_seconds), 10)
                )
            except TimeoutError as exc:
                if not state.owned_by_pixelle:
                    raise RuntimeError(
                        f"Port for ComfyUI backend {self.comfyui_url} is already occupied "
                        "by a process Pixelle does not own, and the ComfyUI API health "
                        f"check failed: {health_error or exc}"
                    ) from exc
                logger.warning(
                    "Restarting an API-unhealthy ComfyUI backend whose process ownership "
                    f"was verified ({reason})"
                )
                await self.stop(reason=f"{reason}:api-unhealthy")
            else:
                if self.management_mode == "required" and not state.owned_by_pixelle:
                    raise RuntimeError(
                        "ComfyUI backend management is required, but the backend that "
                        f"became healthy at {self.comfyui_url} is not owned by Pixelle"
                    )
                return ComfyUIBackendReadyResult(
                    ownership=state.ownership,
                    started=False,
                    reused_existing=True,
                    health=recovered_health,
                )
        elif state is not None and state.pid_file_present:
            await self.stop(reason=f"{reason}:clean-stale-owned-process")
        elif state is None:
            logger.warning(
                "Could not inspect local ComfyUI process ownership before startup; "
                "the start script will enforce listener and ownership safety: "
                f"{state_error}"
            )

        try:
            start_result = await self.start(reason=reason)
        except RuntimeError:
            # Close the check/start race without taking ownership of the process that won it.
            raced_health, _ = await self._probe_backend_safely()
            if raced_health is None or self.management_mode == "required":
                raise
            logger.info(
                "Reusing healthy ComfyUI backend that became ready during startup "
                f"at {self.comfyui_url} ({reason})"
            )
            return ComfyUIBackendReadyResult(
                ownership="unknown",
                started=False,
                reused_existing=True,
                health=raced_health,
            )

        try:
            health = await self._wait_for_backend_health()
        except Exception:
            await self._cleanup_after_start_failure(
                reason=f"{reason}:failed-health-check"
            )
            raise

        if self.management_mode == "required":
            try:
                state = await self.inspect_state(reason=f"{reason}:started-backend")
            except Exception:
                await self._cleanup_after_start_failure(
                    reason=f"{reason}:failed-ownership-check"
                )
                raise
            if not state.owned_by_pixelle:
                await self._cleanup_after_start_failure(
                    reason=f"{reason}:unconfirmed-ownership"
                )
                raise RuntimeError(
                    "ComfyUI backend started but Pixelle ownership could not be confirmed: "
                    f"{state.payload}"
                )
        return ComfyUIBackendReadyResult(
            ownership="pixelle",
            started=bool(start_result.payload.get("started")),
            reused_existing=bool(start_result.payload.get("already_running")),
            health=health,
        )

    async def restart(self, *, reason: str) -> bool:
        if not self.can_manage():
            if self.management_mode == "required":
                if not self.profile.managed:
                    raise RuntimeError(
                        "Pixelle-managed ComfyUI backend restart is required but "
                        f"profile '{self.profile_name}' has managed=false: {self.comfyui_url}"
                    )
                raise RuntimeError(
                    "Pixelle-managed ComfyUI backend restart is required but the "
                    f"configured URL is not manageable: {self.comfyui_url}"
                )
            logger.info(
                "Skipping Pixelle-managed ComfyUI backend restart because backend "
                f"management is not active for {self.comfyui_url} ({reason})"
            )
            return False

        state = await self.inspect_state(reason=f"{reason}:restart-check")
        if state.ownership in {"external", "unknown"}:
            if state.ownership == "external" and state.pid_file_present:
                await self.stop(reason=f"{reason}:clean-owned-orphan")
            message = (
                "Skipping ComfyUI backend restart because Pixelle ownership of the "
                f"running process is not established ({reason})"
            )
            if self.management_mode == "required":
                raise RuntimeError(message)
            logger.info(message)
            return False

        logger.warning(f"Restarting Pixelle-owned ComfyUI backend ({reason})")
        stop_result = await self.stop(reason=reason)

        if not _backend_result_allows_restart(stop_result):
            message = (
                "Pixelle-managed ComfyUI backend restart was skipped because process stop "
                f"was not confirmed ({reason}): {stop_result.payload}"
            )
            if self.management_mode == "required":
                raise RuntimeError(message)
            logger.warning(message)
            return False

        await self.start(reason=reason)
        await self._wait_for_backend_health()
        return True

    async def start(self, *, reason: str) -> ComfyUIBackendCommandResult:
        return await self._run_script(
            "start_backend.ps1",
            "start",
            reason=reason,
            extra_args=[
                "-ReadyTimeoutSeconds",
                str(self.ready_timeout_seconds),
            ],
        )

    def diagnose_recent_failure(self, *, max_age_seconds: float = 120.0) -> str | None:
        """Classify a bounded, recent managed-backend log tail without exposing it."""
        logs_dir = str(self.profile.logs_dir or "").strip()
        if not logs_dir:
            return None
        log_path = Path(logs_dir)
        if not log_path.is_absolute():
            log_path = self.working_directory / log_path
        stderr_path = log_path / "comfyui-backend.stderr.log"
        try:
            age_seconds = max(0.0, time.time() - stderr_path.stat().st_mtime)
            if age_seconds > max_age_seconds:
                return None
            with stderr_path.open("rb") as stream:
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                stream.seek(max(0, size - 256 * 1024), os.SEEK_SET)
                tail = stream.read().decode("utf-8", errors="replace")
        except OSError:
            return None
        if looks_like_memory_exhaustion(tail):
            return "memory_exhaustion"
        return None

    async def stop(self, *, reason: str) -> ComfyUIBackendCommandResult:
        state = await self.inspect_state(reason=f"{reason}:stop-check")
        if state.ownership == "external" and state.pid_file_present:
            return await self._run_script("stop_backend.ps1", "stop", reason=reason)
        if state.ownership in {"external", "unknown"}:
            logger.info(
                "Skipping ComfyUI backend stop because Pixelle does not own the "
                f"running process ({reason})"
            )
            return self._skipped_result(
                "stop",
                reason="external_backend_not_owned",
                payload=state.payload,
            )
        if state.ownership == "absent" and not state.pid_file_present:
            return self._skipped_result(
                "stop",
                reason="backend_absent",
                payload=state.payload,
            )
        # Only a live Pixelle-owned listener can have queued work. A crashed
        # service may still have a recorded supervisor that must be terminated,
        # but its HTTP queue is no longer available to inspect.
        if state.owned_by_pixelle and state.listener_present:
            try:
                await self.maintenance_client.wait_until_idle()
            except Exception as exc:
                health, _health_error = await self._probe_backend_safely()
                if health is not None:
                    raise RuntimeError(
                        "ComfyUI queue could not be confirmed idle before stopping the "
                        f"Pixelle-owned backend '{self.profile_name}'"
                    ) from exc
                logger.warning(
                    "Stopping an API-unhealthy Pixelle-owned ComfyUI backend even though "
                    "its queue is unreachable; process ownership remains verified: "
                    f"profile='{self.profile_name}', reason='{reason}'"
                )
        return await self._run_script("stop_backend.ps1", "stop", reason=reason)

    async def check(self, *, reason: str) -> ComfyUIBackendCommandResult:
        return await self._run_script("check_backend.ps1", "check", reason=reason)

    async def _probe_backend_safely(self) -> tuple[dict[str, Any] | None, str]:
        try:
            return await self.maintenance_client.probe_backend(), ""
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            return None, detail

    async def _inspect_state_safely(
        self, *, reason: str
    ) -> tuple[ComfyUIBackendState | None, str]:
        try:
            return await self.inspect_state(reason=reason), ""
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            return None, detail

    async def _cleanup_after_start_failure(self, *, reason: str) -> None:
        try:
            await self._run_script("stop_backend.ps1", "stop", reason=reason)
        except Exception as stop_exc:
            logger.warning(
                "Failed to clean up a ComfyUI process after startup validation failed: "
                f"{stop_exc}"
            )

    async def _wait_for_backend_health(
        self, *, timeout_seconds: int | None = None
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        timeout = max(
            1,
            self.ready_timeout_seconds if timeout_seconds is None else timeout_seconds,
        )
        deadline = loop.time() + timeout
        last_error = "health probe failed"
        while True:
            health, last_error = await self._probe_backend_safely()
            if health is not None:
                return health
            if loop.time() >= deadline:
                raise TimeoutError(
                    f"ComfyUI backend at {self.comfyui_url} did not become API-ready "
                    f"within {timeout}s: {last_error}"
                )
            await asyncio.sleep(0.5)

    def _skipped_result(
        self,
        action: str,
        *,
        reason: str,
        payload: dict[str, Any] | None = None,
    ) -> ComfyUIBackendCommandResult:
        return ComfyUIBackendCommandResult(
            action=action,
            returncode=0,
            stdout="",
            stderr="",
            payload={
                **(payload or {}),
                "stopped": False,
                "skipped": True,
                "reason": reason,
            },
        )

    async def _run_script(
        self,
        script_name: str,
        action: str,
        *,
        reason: str,
        extra_args: list[str] | None = None,
    ) -> ComfyUIBackendCommandResult:
        script_path = self.scripts_dir / script_name
        if not script_path.exists():
            raise RuntimeError(f"ComfyUI backend script does not exist: {script_path}")

        powershell_executable = shutil.which("powershell")
        if powershell_executable is None:
            raise RuntimeError(
                "Pixelle-managed ComfyUI lifecycle requires Windows PowerShell. "
                "Set backend_management_mode=disabled when ComfyUI is managed externally."
            )
        command = [
            powershell_executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-Json",
        ]
        command.extend(self._script_args())
        if extra_args:
            command.extend(extra_args)

        timeout_seconds = self._command_timeout_seconds(action)
        temp_dir = Path(tempfile.mkdtemp(prefix=f"pixelle-comfyui-{action}-"))
        stdout_path = temp_dir / "stdout.txt"
        stderr_path = temp_dir / "stderr.txt"
        try:
            try:
                process = await asyncio.to_thread(
                    self._run_command_to_files,
                    command,
                    stdout_path,
                    stderr_path,
                    timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                stdout = self._read_script_output(stdout_path)
                stderr = self._read_script_output(stderr_path)
                payload = self._parse_payload(stdout)
                logger.bind(
                    channel="runtime",
                    event="comfyui_backend_management_timeout",
                    action=action,
                    reason=reason,
                    timeout_seconds=timeout_seconds,
                    payload=payload,
                    stderr=stderr,
                ).error(f"ComfyUI backend {action} command timed out")
                detail = stderr or stdout or str(exc)
                raise RuntimeError(
                    f"ComfyUI backend {action} command timed out after "
                    f"{timeout_seconds} seconds: {detail}"
                ) from exc
            stdout = self._read_script_output(stdout_path)
            stderr = self._read_script_output(stderr_path)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        payload = self._parse_payload(stdout)
        result = ComfyUIBackendCommandResult(
            action=action,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            payload=payload,
        )
        logger.bind(
            channel="runtime",
            event="comfyui_backend_management",
            action=action,
            reason=reason,
            returncode=result.returncode,
            payload=payload,
            stderr=stderr,
        ).info(f"ComfyUI backend {action} command completed")
        if process.returncode != 0:
            raise RuntimeError(
                f"ComfyUI backend {action} command failed with exit code "
                f"{process.returncode}: {stderr or stdout}"
            )
        return result

    def _run_command_to_files(
        self,
        command: list[str],
        stdout_path: Path,
        stderr_path: Path,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_file:
            with stderr_path.open("w", encoding="utf-8", errors="replace") as stderr_file:
                return subprocess.run(
                    command,
                    cwd=str(self.working_directory),
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    check=False,
                    timeout=timeout_seconds,
                )

    def _command_timeout_seconds(self, action: str) -> int:
        if self.command_timeout_seconds is not None:
            return max(1, int(self.command_timeout_seconds))
        if action == "start":
            return max(30, int(self.ready_timeout_seconds) + 30)
        return 60

    def _read_script_output(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    def _script_args(self) -> list[str]:
        parsed = urlparse(self.comfyui_url)
        args: list[str] = ["-ProfileName", self.profile_name]
        if parsed.hostname:
            host_address = "127.0.0.1" if parsed.hostname.lower() == "localhost" else parsed.hostname
            args.extend(["-HostAddress", host_address])
        port = self._resolved_port()
        if port:
            args.extend(["-Port", str(port)])
        self._append_profile_arg(args, "-DataRoot", self.profile.data_root)
        shared_base_path = self.profile.shared_base_path
        if not shared_base_path and self.profile.data_root:
            shared_base_path = str(Path(self.profile.data_root).parent)
        self._append_profile_arg(args, "-SharedBasePath", shared_base_path)
        self._append_profile_arg(args, "-RuntimeDir", self.profile.runtime_dir)
        self._append_profile_arg(args, "-LogsDir", self.profile.logs_dir)
        self._append_profile_arg(args, "-DatabaseUrl", self.profile.database_url)
        self._append_profile_arg(args, "-PythonExe", self.profile.python_exe)
        self._append_profile_arg(args, "-ComfyUIRoot", self.profile.comfyui_root)
        self._append_profile_arg(args, "-ExtraModelsConfig", self.profile.extra_models_config)
        self._append_profile_arg(args, "-FrontEndRoot", self.profile.frontend_root)
        args.extend(["-ResourcePolicy", self.profile.resource_policy])
        if self.profile.minimum_free_commit_gb is not None:
            args.extend(
                [
                    "-MinimumFreeCommitGB",
                    f"{self.profile.minimum_free_commit_gb:g}",
                ]
            )
        return args

    def _append_profile_arg(
        self,
        args: list[str],
        name: str,
        value: str | None,
    ) -> None:
        if value and value.strip():
            args.extend([name, value])

    def _resolved_port(self) -> int | None:
        parsed = urlparse(self.comfyui_url)
        if parsed.port:
            return parsed.port
        if parsed.scheme == "https":
            return 443
        if parsed.scheme == "http":
            return 80
        return None

    def _parse_payload(self, stdout: str) -> dict[str, Any]:
        stripped = (stdout or "").strip()
        if not stripped:
            return {}
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return {"raw_stdout": stripped}
        return payload if isinstance(payload, dict) else {"raw_stdout": payload}


def _backend_result_allows_restart(result: ComfyUIBackendCommandResult) -> bool:
    payload = result.payload or {}
    if payload.get("stopped"):
        return True
    return payload.get("reason") in {"backend_absent", "process_missing"}


# Backward-compatible import name for integrations that imported the old class.
ManagedComfyUIBackend = ComfyUIBackendController
