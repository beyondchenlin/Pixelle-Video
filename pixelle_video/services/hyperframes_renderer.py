"""
HyperFrames renderer bridge helpers.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

_SAFE_MANIFEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_HYPERFRAMES_BROWSER_ENV = "PRODUCER_HEADLESS_SHELL_PATH"


def _system_browser_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []

    if os.name == "nt":
        for environment_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base_path = os.environ.get(environment_name)
            if not base_path:
                continue
            base = Path(base_path)
            candidates.extend(
                (
                    base / "Google" / "Chrome" / "Application" / "chrome.exe",
                    base / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                )
            )
    elif sys.platform == "darwin":
        candidates.extend(
            (
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            )
        )

    for executable_name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
        "msedge",
    ):
        executable_path = shutil.which(executable_name)
        if executable_path:
            candidates.append(Path(executable_path))

    return tuple(candidates)


def _resolve_browser_executable(environment: dict[str, str]) -> str | None:
    explicitly_configured = environment.get(_HYPERFRAMES_BROWSER_ENV, "").strip()
    if explicitly_configured:
        return explicitly_configured

    seen: set[str] = set()
    for candidate in _system_browser_candidates():
        normalized = str(candidate.resolve(strict=False))
        normalized_key = normalized.casefold()
        if normalized_key in seen:
            continue
        seen.add(normalized_key)
        if candidate.is_file():
            return normalized

    return None


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
    ) -> str:
        project_path = Path(project_dir).resolve()
        has_compiled_entrypoint = self._has_compiled_entrypoint(project_path)
        manifest = self._load_manifest(project_path, required=not has_compiled_entrypoint)
        if not has_compiled_entrypoint:
            if manifest is None:
                raise FileNotFoundError(
                    f"HyperFrames manifest not found: {project_path / 'data' / 'render_manifest.json'}"
                )
            template_id = _validate_manifest_identifier("template_id", manifest.get("template_id"))
            self._materialize_template(project_path, template_id)

        resolved_output_path = (
            Path(output_path).resolve()
            if output_path
            else project_path
            / "renders"
            / f'{self._resolve_task_id(project_path, manifest)}.mp4'
        )
        resolved_output_path.parent.mkdir(parents=True, exist_ok=True)

        render_environment = os.environ.copy()
        browser_executable = _resolve_browser_executable(render_environment)
        if browser_executable:
            render_environment[_HYPERFRAMES_BROWSER_ENV] = browser_executable

        command = [
            self.node_executable,
            str(self.bridge_script),
            "--project-dir",
            str(project_path),
            "--output-path",
            str(resolved_output_path),
        ]
        if browser_executable:
            command.extend(("--chrome-path", browser_executable))

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=str(project_path),
            env=render_environment,
        )

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            detail = stderr or stdout or "unknown error"
            raise RuntimeError(f"HyperFrames bridge failed: {detail}")

        final_output_path = self._parse_output_path(completed.stdout, resolved_output_path)

        if (
            width is not None
            or height is not None
            or expected_duration is not None
            or expect_audio
        ):
            probe = self._probe_output(final_output_path)
            if not probe["has_video"]:
                raise RuntimeError("Rendered HyperFrames output is missing a video stream.")
            if expect_audio and not probe["has_audio"]:
                raise RuntimeError("Rendered HyperFrames output is missing an audio stream.")
            if expected_duration is not None and abs(probe["duration"] - float(expected_duration)) > 0.35:
                raise RuntimeError("Rendered HyperFrames output duration is outside tolerance.")
            if width is not None and probe["width"] != int(width):
                raise RuntimeError("Rendered HyperFrames output width does not match the requested canvas.")
            if height is not None and probe["height"] != int(height):
                raise RuntimeError("Rendered HyperFrames output height does not match the requested canvas.")

        return final_output_path

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

        for source_path in template_dir.rglob("*"):
            relative_path = source_path.relative_to(template_dir)
            target_path = project_dir / relative_path

            if source_path.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)

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
        )
        payload = json.loads(completed.stdout)
        streams = payload.get("streams", [])
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)

        return {
            "has_video": video_stream is not None,
            "has_audio": audio_stream is not None,
            "duration": float(payload.get("format", {}).get("duration", 0.0) or 0.0),
            "width": int(video_stream.get("width", 0)) if video_stream else 0,
            "height": int(video_stream.get("height", 0)) if video_stream else 0,
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
