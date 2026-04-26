import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.models.element_animation import (
    ElementAnimationBackground,
    ElementAnimationCanvas,
    ElementAnimationManifest,
    ElementAnimationRender,
    ElementAnimationSegmentation,
    ElementAnimationTimeline,
)
from pixelle_video.services.element_motion_materializer import ElementMotionMaterializer


@pytest.mark.asyncio
async def test_element_motion_materializer_writes_manifest_and_python_video(tmp_path):
    manifest = ElementAnimationManifest(
        source_image_path="frame.png",
        canvas=ElementAnimationCanvas(width=1080, height=1920),
        timeline=ElementAnimationTimeline(duration=2.0, fps=30),
        background=ElementAnimationBackground(
            mode="source_image_low_motion",
            image_path="frame.png",
        ),
        segmentation=ElementAnimationSegmentation(
            provider="test",
            workflow="segment.json",
            prompt=None,
            candidate_limit=1,
            selected_count=1,
        ),
        elements=[],
        render=ElementAnimationRender(backend="python_ffmpeg"),
    )

    class FakeSegmentation:
        async def segment_image(self, **kwargs):
            return manifest

    class FakeRenderer:
        def render_video(self, render_manifest, output_path):
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"video")
            return output_path

    materializer = ElementMotionMaterializer(
        segmentation_service=FakeSegmentation(),
        python_renderer=FakeRenderer(),
    )
    frame = SimpleNamespace(index=0, duration=2.0)

    result = await materializer.materialize_frame(
        frame=frame,
        source_image_path="frame.png",
        task_id="task-1",
        output_dir=tmp_path,
        width=1080,
        height=1920,
        fps=30,
        backend="python_ffmpeg",
        selected_count=1,
        candidate_limit=1,
        prompt=None,
        workflow="segment.json",
        intensity="medium",
    )

    assert Path(result.manifest_path).exists()
    assert result.motion_video_path is not None
    assert Path(result.motion_video_path).exists()


@pytest.mark.asyncio
async def test_element_motion_materializer_normalizes_invalid_timing_for_manifest(tmp_path):
    captured = {}

    class FakeSegmentation:
        async def segment_image(self, **kwargs):
            captured.update(kwargs)
            return ElementAnimationManifest(
                source_image_path=kwargs["image_path"],
                canvas=ElementAnimationCanvas(width=kwargs["width"], height=kwargs["height"]),
                timeline=ElementAnimationTimeline(
                    duration=kwargs["duration"],
                    fps=kwargs["fps"],
                ),
                background=ElementAnimationBackground(
                    mode="source_image_low_motion",
                    image_path=kwargs["image_path"],
                ),
                segmentation=ElementAnimationSegmentation(
                    provider="test",
                    workflow=kwargs["workflow"],
                    prompt=kwargs["prompt"],
                    candidate_limit=kwargs["candidate_limit"],
                    selected_count=kwargs["selected_count"],
                ),
                elements=[],
                render=ElementAnimationRender(backend=kwargs["backend"]),
            )

    class UnusedRenderer:
        def render_video(self, render_manifest, output_path):
            raise AssertionError("non-python backends should not render python video")

    materializer = ElementMotionMaterializer(
        segmentation_service=FakeSegmentation(),
        python_renderer=UnusedRenderer(),
    )
    frame = SimpleNamespace(index=0, duration=float("nan"))

    result = await materializer.materialize_frame(
        frame=frame,
        source_image_path="frame.png",
        task_id="task-1",
        output_dir=tmp_path,
        width=1080,
        height=1920,
        fps=0,
        backend="hyperframes_canvas",
        selected_count=1,
        candidate_limit=1,
        prompt=None,
        workflow="segment.json",
        intensity="medium",
    )

    manifest_data = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert captured["duration"] == 0.1
    assert captured["fps"] == 1
    assert manifest_data["timeline"] == {"duration": 0.1, "fps": 1}
    assert result.motion_video_path is None
