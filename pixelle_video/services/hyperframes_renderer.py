"""
HyperFrames renderer bridge helpers.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional


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

    def render(self, project_dir: str, output_path: Optional[str] = None) -> str:
        project_path = Path(project_dir).resolve()
        manifest = self._load_manifest(project_path)
        self._materialize_template(project_path, manifest["template_id"])

        resolved_output_path = (
            Path(output_path).resolve()
            if output_path
            else project_path / "renders" / f'{manifest["task_id"]}.mp4'
        )
        resolved_output_path.parent.mkdir(parents=True, exist_ok=True)

        completed = subprocess.run(
            [
                self.node_executable,
                str(self.bridge_script),
                "--project-dir",
                str(project_path),
                "--output-path",
                str(resolved_output_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(project_path),
        )

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            detail = stderr or stdout or "unknown error"
            raise RuntimeError(f"HyperFrames bridge failed: {detail}")

        return self._parse_output_path(completed.stdout, resolved_output_path)

    def _load_manifest(self, project_dir: Path) -> dict[str, Any]:
        manifest_path = project_dir / "data" / "render_manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"HyperFrames manifest not found: {manifest_path}")

        with open(manifest_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

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
