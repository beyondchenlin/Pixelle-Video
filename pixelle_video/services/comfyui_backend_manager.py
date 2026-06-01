from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger

from pixelle_video.config.schema import ComfyUIBackendProfile


@dataclass(frozen=True)
class ComfyUIBackendCommandResult:
    action: str
    returncode: int
    stdout: str
    stderr: str
    payload: dict[str, Any]


class ManagedComfyUIBackend:
    """Runs the Pixelle-managed ComfyUI backend scripts behind a small async API."""

    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        comfyui_url: str | None = None,
        profile_name: str = "default",
        profile: ComfyUIBackendProfile | None = None,
        management_mode: str = "auto",
        ready_timeout_seconds: int = 90,
        command_timeout_seconds: int | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()
        self.profile_name = (profile_name or "default").strip() or "default"
        self.profile = profile or ComfyUIBackendProfile(url=comfyui_url)
        self.comfyui_url = str(self.profile.url or comfyui_url or "").strip()
        self.management_mode = (management_mode or "auto").strip().lower()
        self.ready_timeout_seconds = ready_timeout_seconds
        self.command_timeout_seconds = command_timeout_seconds

    @property
    def scripts_dir(self) -> Path:
        return self.repo_root / "scripts" / "comfyui"

    def can_manage(self) -> bool:
        if not self.profile.managed:
            return False
        if self.management_mode == "disabled":
            return False
        if self.management_mode == "required":
            return True
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

        logger.warning(f"Restarting Pixelle-managed ComfyUI backend ({reason})")
        await self.stop(reason=reason)
        await self.start(reason=reason)
        return True

    async def start(self, *, reason: str) -> ComfyUIBackendCommandResult:
        return await self._run_script(
            "start_backend.ps1",
            "start",
            reason=reason,
            extra_args=["-ReadyTimeoutSeconds", str(self.ready_timeout_seconds)],
        )

    async def stop(self, *, reason: str) -> ComfyUIBackendCommandResult:
        return await self._run_script("stop_backend.ps1", "stop", reason=reason)

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

        command = [
            "powershell",
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
                    cwd=str(self.repo_root),
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
            args.extend(["-HostAddress", parsed.hostname])
        port = self._resolved_port()
        if port:
            args.extend(["-Port", str(port)])
        self._append_profile_arg(args, "-DataRoot", self.profile.data_root)
        self._append_profile_arg(args, "-RuntimeDir", self.profile.runtime_dir)
        self._append_profile_arg(args, "-LogsDir", self.profile.logs_dir)
        self._append_profile_arg(args, "-DatabaseUrl", self.profile.database_url)
        self._append_profile_arg(args, "-PythonExe", self.profile.python_exe)
        self._append_profile_arg(args, "-ComfyUIRoot", self.profile.comfyui_root)
        self._append_profile_arg(args, "-ExtraModelsConfig", self.profile.extra_models_config)
        self._append_profile_arg(args, "-FrontEndRoot", self.profile.frontend_root)
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
