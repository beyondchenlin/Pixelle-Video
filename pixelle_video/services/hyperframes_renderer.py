"""
HyperFrames renderer bridge helpers.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Optional

from loguru import logger

_SAFE_MANIFEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_REMOTE_SCRIPT_RE = re.compile(
    r"<script\b[^>]*\bsrc\s*=\s*(['\"])\s*https?://",
    re.IGNORECASE,
)
_REMOTE_LINK_RE = re.compile(
    r"<link\b[^>]*\bhref\s*=\s*(['\"])\s*https?://",
    re.IGNORECASE,
)
_MAX_DIAGNOSTIC_BYTES = 64 * 1024
_DEFAULT_RENDER_TIMEOUT_SECONDS = 300.0
_RENDER_TIMEOUT_BASE_SECONDS = 120.0
_RENDER_TIMEOUT_PER_MEDIA_SECOND = 30.0
_MAX_RENDER_TIMEOUT_SECONDS = 6 * 60 * 60.0


@dataclass(frozen=True)
class _RenderRequest:
    project_path: Path
    output_path: Path
    command: tuple[str, ...]
    environment: dict[str, str]
    stdout_log: Path
    stderr_log: Path
    timeout_seconds: float
    width: Optional[int]
    height: Optional[int]
    fps: Optional[int]
    expected_duration: Optional[float]
    expect_audio: bool


def _validate_manifest_identifier(field_name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Invalid {field_name}: expected non-empty string")

    candidate = value.strip()
    if not candidate:
        raise ValueError(f"Invalid {field_name}: expected non-empty string")

    if not _SAFE_MANIFEST_ID_RE.fullmatch(candidate):
        raise ValueError(
            f"Invalid {field_name}: {value!r}. "
            "Expected letters, numbers, hyphens, or underscores only.",
        )

    return candidate


class HyperFramesRenderer:
    """Invoke the Node HyperFrames bridge for a task-local project."""

    def __init__(
        self,
        config: Optional[dict[str, Any]] = None,
        *,
        node_executable: str = "node",
        bridge_script: Optional[str] = None,
        template_root: Optional[str] = None,
        runtime_root: Optional[str] = None,
        render_timeout_seconds: Optional[float] = None,
        use_gpu: Optional[bool] = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]

        self.config = config or {}
        self.node_executable = node_executable
        self.bridge_script = (
            Path(bridge_script).resolve()
            if bridge_script
            else repo_root / "tools" / "hyperframes_bridge" / "src" / "render.mjs"
        )
        self.template_root = (
            Path(template_root).resolve()
            if template_root
            else repo_root / "resources" / "hyperframes" / "templates"
        )
        self.runtime_root = (
            Path(runtime_root).resolve()
            if runtime_root
            else repo_root / "resources" / "hyperframes" / "runtime"
        )
        self.render_timeout_seconds = render_timeout_seconds
        self.use_gpu = self._resolve_use_gpu(use_gpu)

    @staticmethod
    def _resolve_use_gpu(explicit: Optional[bool]) -> bool:
        if explicit is not None:
            return explicit
        env_value = os.environ.get("PIXELLE_HYPERFRAMES_USE_GPU", "").strip().lower()
        if env_value in ("0", "false", "no", "off"):
            return False
        if env_value in ("1", "true", "yes", "on"):
            return True
        if env_value:
            logger.warning(
                "Unrecognized PIXELLE_HYPERFRAMES_USE_GPU value {!r}, defaulting to True",
                env_value,
            )
        return True

    def render(
        self,
        project_dir: str,
        output_path: Optional[str] = None,
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
        expected_duration: Optional[float] = None,
        expect_audio: bool = False,
        use_gpu: Optional[bool] = None,
    ) -> str:
        request = self._prepare_render_request(
            project_dir,
            output_path=output_path,
            width=width,
            height=height,
            fps=fps,
            expected_duration=expected_duration,
            expect_audio=expect_audio,
            use_gpu=use_gpu,
        )
        returncode = self._run_bridge_sync(request)
        return self._finalize_render(request, returncode)

    async def render_async(
        self,
        project_dir: str,
        output_path: Optional[str] = None,
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
        expected_duration: Optional[float] = None,
        expect_audio: bool = False,
        use_gpu: Optional[bool] = None,
    ) -> str:
        """Render without blocking the service event loop.

        Cancellation and timeout both terminate the complete bridge process tree,
        including browser and encoder descendants.
        """
        request = self._prepare_render_request(
            project_dir,
            output_path=output_path,
            width=width,
            height=height,
            fps=fps,
            expected_duration=expected_duration,
            expect_audio=expect_audio,
            use_gpu=use_gpu,
        )
        returncode = await self._run_bridge_async(request)
        return await asyncio.to_thread(self._finalize_render, request, returncode)

    def _prepare_render_request(
        self,
        project_dir: str,
        output_path: Optional[str],
        *,
        width: Optional[int],
        height: Optional[int],
        fps: Optional[int],
        expected_duration: Optional[float],
        expect_audio: bool,
        use_gpu: Optional[bool] = None,
    ) -> _RenderRequest:
        self._validate_render_contract(
            width=width,
            height=height,
            fps=fps,
            expected_duration=expected_duration,
        )
        resolved_use_gpu = use_gpu if use_gpu is not None else self.use_gpu

        project_path = Path(project_dir).resolve()
        if not project_path.is_dir():
            raise FileNotFoundError(f"HyperFrames project directory not found: {project_path}")

        has_compiled_entrypoint = self._has_compiled_entrypoint(project_path)
        manifest = self._load_manifest(project_path, required=not has_compiled_entrypoint)
        if not has_compiled_entrypoint:
            if manifest is None:
                raise FileNotFoundError(
                    f"HyperFrames manifest not found: {project_path / 'data' / 'render_manifest.json'}"
                )
            template_id = _validate_manifest_identifier("template_id", manifest.get("template_id"))
            self._materialize_template(project_path, template_id)

        self._assert_local_executable_dependencies(project_path)

        resolved_output_path = (
            Path(output_path).resolve()
            if output_path
            else project_path
            / "renders"
            / f'{self._resolve_task_id(project_path, manifest)}.mp4'
        )
        resolved_output_path.parent.mkdir(parents=True, exist_ok=True)

        render_environment = os.environ.copy()
        command = [
            self.node_executable,
            str(self.bridge_script),
            "--project-dir",
            str(project_path),
            "--output-path",
            str(resolved_output_path),
        ]
        if resolved_use_gpu:
            command.append("--use-gpu")
        if fps is not None:
            command.extend(("--fps", str(int(fps))))

        logs_dir = project_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return _RenderRequest(
            project_path=project_path,
            output_path=resolved_output_path,
            command=tuple(command),
            environment=render_environment,
            stdout_log=logs_dir / "hyperframes_bridge.stdout.log",
            stderr_log=logs_dir / "hyperframes_bridge.stderr.log",
            timeout_seconds=self._resolve_render_timeout(expected_duration),
            width=width,
            height=height,
            fps=fps,
            expected_duration=expected_duration,
            expect_audio=expect_audio,
        )

    def _finalize_render(self, request: _RenderRequest, returncode: int) -> str:
        stdout = self._read_log_tail(request.stdout_log)
        stderr = self._read_log_tail(request.stderr_log)
        if returncode != 0:
            detail = stderr.strip() or stdout.strip() or "unknown error"
            raise RuntimeError(
                "HyperFrames bridge failed: "
                f"{detail}\nLogs: {request.stdout_log} ; {request.stderr_log}"
            )

        final_output_path = self._parse_output_path(stdout, request.output_path)
        if not Path(final_output_path).is_file():
            raise RuntimeError(
                "HyperFrames bridge reported success but the output file is missing: "
                f"{final_output_path}. Logs: {request.stdout_log} ; {request.stderr_log}"
            )

        if (
            request.width is not None
            or request.height is not None
            or request.fps is not None
            or request.expected_duration is not None
            or request.expect_audio
        ):
            probe = self._probe_output(final_output_path)
            if not probe["has_video"]:
                raise RuntimeError("Rendered HyperFrames output is missing a video stream.")
            if request.expect_audio and not probe["has_audio"]:
                raise RuntimeError("Rendered HyperFrames output is missing an audio stream.")
            if (
                request.expected_duration is not None
                and abs(probe["duration"] - float(request.expected_duration)) > 0.35
            ):
                raise RuntimeError("Rendered HyperFrames output duration is outside tolerance.")
            if request.width is not None and probe["width"] != int(request.width):
                raise RuntimeError("Rendered HyperFrames output width does not match the requested canvas.")
            if request.height is not None and probe["height"] != int(request.height):
                raise RuntimeError("Rendered HyperFrames output height does not match the requested canvas.")
            if request.fps is not None and abs(probe["fps"] - float(request.fps)) > 0.1:
                raise RuntimeError("Rendered HyperFrames output frame rate does not match the request.")

        return final_output_path

    def _run_bridge_sync(self, request: _RenderRequest) -> int:
        process: subprocess.Popen[str] | None = None
        with request.stdout_log.open("w", encoding="utf-8", errors="replace") as stdout_file:
            with request.stderr_log.open("w", encoding="utf-8", errors="replace") as stderr_file:
                try:
                    process = subprocess.Popen(
                        request.command,
                        cwd=str(request.project_path),
                        env=request.environment,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        text=True,
                        **self._process_group_kwargs(),
                    )
                    return process.wait(timeout=request.timeout_seconds)
                except subprocess.TimeoutExpired as exc:
                    if process is not None:
                        self._terminate_process_tree(process.pid)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                    raise self._render_timeout_error(request) from exc
                except BaseException:
                    if process is not None and process.poll() is None:
                        self._terminate_process_tree(process.pid)
                    raise

    async def _run_bridge_async(self, request: _RenderRequest) -> int:
        process: asyncio.subprocess.Process | None = None
        with request.stdout_log.open("w", encoding="utf-8", errors="replace") as stdout_file:
            with request.stderr_log.open("w", encoding="utf-8", errors="replace") as stderr_file:
                try:
                    process = await asyncio.create_subprocess_exec(
                        *request.command,
                        cwd=str(request.project_path),
                        env=request.environment,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        **self._process_group_kwargs(),
                    )
                    await asyncio.wait_for(process.wait(), timeout=request.timeout_seconds)
                    return int(process.returncode or 0)
                except TimeoutError as exc:
                    if process is not None and process.returncode is None:
                        await asyncio.to_thread(self._terminate_process_tree, process.pid)
                        await self._wait_for_async_process_exit(process)
                    raise self._render_timeout_error(request) from exc
                except BaseException:
                    if process is not None and process.returncode is None:
                        await asyncio.to_thread(self._terminate_process_tree, process.pid)
                        await self._wait_for_async_process_exit(process)
                    raise

    async def _wait_for_async_process_exit(self, process: asyncio.subprocess.Process) -> None:
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except TimeoutError:
            process.kill()
            await process.wait()

    def _render_timeout_error(self, request: _RenderRequest) -> RuntimeError:
        stderr = self._read_log_tail(request.stderr_log).strip()
        detail = f" Last error: {stderr}" if stderr else ""
        return RuntimeError(
            "HyperFrames bridge timed out after "
            f"{request.timeout_seconds:.1f} seconds.{detail} "
            f"Logs: {request.stdout_log} ; {request.stderr_log}"
        )

    def _resolve_render_timeout(self, expected_duration: Optional[float]) -> float:
        if self.render_timeout_seconds is not None:
            timeout = float(self.render_timeout_seconds)
        else:
            configured = os.environ.get("PIXELLE_HYPERFRAMES_RENDER_TIMEOUT_SECONDS", "").strip()
            if configured:
                try:
                    timeout = float(configured)
                except ValueError as exc:
                    raise ValueError(
                        "PIXELLE_HYPERFRAMES_RENDER_TIMEOUT_SECONDS must be a positive number"
                    ) from exc
            elif expected_duration is None:
                timeout = _DEFAULT_RENDER_TIMEOUT_SECONDS
            else:
                timeout = max(
                    _DEFAULT_RENDER_TIMEOUT_SECONDS,
                    _RENDER_TIMEOUT_BASE_SECONDS
                    + float(expected_duration) * _RENDER_TIMEOUT_PER_MEDIA_SECOND,
                )

        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("HyperFrames render timeout must be a positive finite number")
        return min(timeout, _MAX_RENDER_TIMEOUT_SECONDS)

    def _validate_render_contract(
        self,
        *,
        width: Optional[int],
        height: Optional[int],
        fps: Optional[int],
        expected_duration: Optional[float],
    ) -> None:
        for field_name, value in (("width", width), ("height", height)):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise ValueError(f"HyperFrames {field_name} must be a positive integer")
        if fps is not None and (
            isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 120
        ):
            raise ValueError("HyperFrames fps must be an integer between 1 and 120")
        if expected_duration is not None and (
            not math.isfinite(float(expected_duration)) or float(expected_duration) <= 0
        ):
            raise ValueError("HyperFrames expected duration must be a positive finite number")

    def _process_group_kwargs(self) -> dict[str, Any]:
        if os.name == "nt":
            return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        return {"start_new_session": True}

    def _terminate_process_tree(self, process_id: int) -> None:
        if process_id <= 0:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process_id), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
            )
            return

        try:
            process_group_id = os.getpgid(process_id)
        except ProcessLookupError:
            return
        try:
            os.killpg(process_group_id, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                os.killpg(process_group_id, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        os.killpg(process_group_id, signal.SIGKILL)

    def _read_log_tail(self, path: Path) -> str:
        try:
            with path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - _MAX_DIAGNOSTIC_BYTES))
                return handle.read().decode("utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    def _load_manifest(
        self,
        project_dir: Path,
        *,
        required: bool = True,
    ) -> dict[str, Any] | None:
        manifest_path = project_dir / "data" / "render_manifest.json"
        if not manifest_path.exists():
            if required:
                raise FileNotFoundError(f"HyperFrames manifest not found: {manifest_path}")
            return None

        with open(manifest_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _resolve_task_id(
        self,
        project_dir: Path,
        manifest: dict[str, Any] | None,
    ) -> str:
        if manifest is not None and manifest.get("task_id") is not None:
            return _validate_manifest_identifier("task_id", manifest.get("task_id"))

        return _validate_manifest_identifier("task_id", project_dir.parent.name)

    def _materialize_template(self, project_dir: Path, template_id: str) -> None:
        template_dir = self.template_root / template_id
        if not template_dir.exists():
            raise FileNotFoundError(f"HyperFrames template not found: {template_dir}")

        self._copy_tree_contents(template_dir, project_dir)
        if self.runtime_root.is_dir():
            self._copy_tree_contents(self.runtime_root, project_dir / "runtime")

    def _copy_tree_contents(self, source_root: Path, target_root: Path) -> None:
        for source_path in source_root.rglob("*"):
            relative_path = source_path.relative_to(source_root)
            target_path = target_root / relative_path
            if source_path.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)

    def _assert_local_executable_dependencies(self, project_dir: Path) -> None:
        for html_path in project_dir.rglob("*.html"):
            content = html_path.read_text(encoding="utf-8", errors="replace")
            if _REMOTE_SCRIPT_RE.search(content) or _REMOTE_LINK_RE.search(content):
                raise RuntimeError(
                    "HyperFrames projects may not load executable scripts or stylesheets "
                    f"from remote origins: {html_path}"
                )

    def _has_compiled_entrypoint(self, project_dir: Path) -> bool:
        return (
            (project_dir / "index.html").exists()
            and (project_dir / "compositions" / "captions.html").exists()
        )

    def _probe_output(self, output_path: str) -> dict[str, Any]:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                output_path,
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        payload = json.loads(completed.stdout)
        streams = payload.get("streams", [])
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)

        frame_rate_raw = "0/1"
        if video_stream:
            frame_rate_raw = str(
                video_stream.get("avg_frame_rate")
                or video_stream.get("r_frame_rate")
                or "0/1"
            )
        try:
            frame_rate = float(Fraction(frame_rate_raw))
        except (ValueError, ZeroDivisionError):
            frame_rate = 0.0

        return {
            "has_video": video_stream is not None,
            "has_audio": audio_stream is not None,
            "duration": float(payload.get("format", {}).get("duration", 0.0) or 0.0),
            "width": int(video_stream.get("width", 0)) if video_stream else 0,
            "height": int(video_stream.get("height", 0)) if video_stream else 0,
            "fps": frame_rate,
        }

    def _parse_output_path(self, stdout: str, fallback_output_path: Path) -> str:
        for raw_line in reversed(stdout.splitlines()):
            line = raw_line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            output_path = payload.get("output_path")
            if isinstance(output_path, str) and output_path.strip():
                return output_path

        return str(fallback_output_path)
