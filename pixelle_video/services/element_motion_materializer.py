from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pixelle_video.models.element_animation import (
    AnimationIntensity,
    ElementRenderBackend,
)


@dataclass(frozen=True)
class ElementMotionArtifact:
    manifest_path: str
    motion_video_path: str | None


class ElementMotionMaterializer:
    def __init__(self, segmentation_service: Any, python_renderer: Any = None) -> None:
        self.segmentation_service = segmentation_service
        if python_renderer is None:
            from pixelle_video.services.element_animation_renderer import (
                PythonElementAnimationRenderer,
            )

            python_renderer = PythonElementAnimationRenderer()
        self.python_renderer = python_renderer

    async def materialize_frame(
        self,
        *,
        frame: Any,
        source_image_path: str,
        task_id: str,
        output_dir: str | Path,
        width: int,
        height: int,
        fps: int,
        backend: ElementRenderBackend,
        selected_count: int,
        candidate_limit: int,
        prompt: str | None,
        workflow: str,
        intensity: AnimationIntensity,
        audio_path: str | None = None,
    ) -> ElementMotionArtifact:
        frame_index = int(getattr(frame, "index"))
        frame_dir = Path(output_dir) / "element_motion" / f"frame_{frame_index:03d}"
        frame_dir.mkdir(parents=True, exist_ok=True)
        duration = _positive_float(getattr(frame, "duration", 0.0), default=0.1)
        safe_fps = _positive_int(fps, default=1)

        manifest = await self.segmentation_service.segment_image(
            image_path=source_image_path,
            task_id=task_id,
            frame_index=frame_index,
            output_dir=str(frame_dir),
            width=int(width),
            height=int(height),
            duration=duration,
            fps=safe_fps,
            selected_count=int(selected_count),
            candidate_limit=int(candidate_limit),
            prompt=prompt,
            workflow=workflow,
            backend=backend,
            intensity=intensity,
            audio_path=audio_path,
        )

        manifest_path = frame_dir / "element_animation_manifest.json"
        manifest_path.write_text(
            json.dumps(
                manifest.to_dict(),
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            ),
            encoding="utf-8",
        )

        motion_video_path = None
        if backend == "python_ffmpeg":
            motion_output_path = frame_dir / "motion.mp4"
            motion_video_path = self.python_renderer.render_video(
                manifest,
                str(motion_output_path),
            )

        return ElementMotionArtifact(
            manifest_path=str(manifest_path),
            motion_video_path=motion_video_path,
        )


def _positive_float(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number) or number <= 0:
        return default
    return number


def _positive_int(value: Any, *, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if number <= 0:
        return default
    return number
