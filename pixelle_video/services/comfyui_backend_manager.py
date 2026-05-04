from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger


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
        management_mode: str = "auto",
        ready_timeout_seconds: int = 90,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()
        self.comfyui_url = str(comfyui_url or "").strip()
        self.management_mode = (management_mode or "auto").strip().lower()
        self.ready_timeout_seconds = ready_timeout_seconds

    @property
    def scripts_dir(self) -> Path:
        return self.repo_root / "scripts" / "comfyui"

    def can_manage(self) -> bool:
        if self.management_mode == "disabled":
            return False
        if self.management_mode == "required":
            return True
        parsed = urlparse(self.comfyui_url)
        host = (parsed.hostname or "").lower()
        return host in {"127.0.0.1", "localhost", "::1"} and self._resolved_port() == 8000

    async def restart(self, *, reason: str) -> bool:
        if not self.can_manage():
            if self.management_mode == "required":
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
        command.extend(self._url_args())
        if extra_args:
            command.extend(extra_args)

        process = await asyncio.to_thread(
            subprocess.run,
            command,
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        payload = self._parse_payload(process.stdout)
        result = ComfyUIBackendCommandResult(
            action=action,
            returncode=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
            payload=payload,
        )
        logger.bind(
            channel="runtime",
            event="comfyui_backend_management",
            action=action,
            reason=reason,
            returncode=result.returncode,
            payload=payload,
            stderr=process.stderr,
        ).info(f"ComfyUI backend {action} command completed")
        if process.returncode != 0:
            raise RuntimeError(
                f"ComfyUI backend {action} command failed with exit code "
                f"{process.returncode}: {process.stderr or process.stdout}"
            )
        return result

    def _url_args(self) -> list[str]:
        parsed = urlparse(self.comfyui_url)
        args: list[str] = []
        if parsed.hostname:
            args.extend(["-HostAddress", parsed.hostname])
        port = self._resolved_port()
        if port:
            args.extend(["-Port", str(port)])
        return args

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
