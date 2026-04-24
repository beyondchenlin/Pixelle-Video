from pathlib import Path

import pytest

from pixelle_video.models.element_animation import (
    ElementAnimation,
    ElementAnimationBackground,
    ElementAnimationCanvas,
    ElementAnimationManifest,
    ElementAnimationRender,
    ElementAnimationSegmentation,
    ElementAnimationTimeline,
    ElementMotionBounds,
    SegmentedElement,
)


def test_manifest_round_trip_preserves_canvas_timeline_and_selection(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    element_a = tmp_path / "element_001.png"
    mask_a = tmp_path / "mask_001.png"
    element_b = tmp_path / "element_002.png"
    mask_b = tmp_path / "mask_002.png"
    element_a.write_bytes(b"png")
    mask_a.write_bytes(b"png")
    element_b.write_bytes(b"png")
    mask_b.write_bytes(b"png")

    manifest = ElementAnimationManifest(
        source_image_path=str(source),
        canvas=ElementAnimationCanvas(width=1024, height=576),
        timeline=ElementAnimationTimeline(duration=3.0, fps=24),
        background=ElementAnimationBackground(
            mode="source_image_low_motion",
            image_path=str(source),
            motion_bounds=ElementMotionBounds(
                translate_px=4,
                rotate_deg=0.4,
                scale_delta=0.01,
            ),
        ),
        segmentation=ElementAnimationSegmentation(
            provider="comfyui_sam31",
            workflow="image_sam31_segment.json",
            prompt="main foreground elements",
            candidate_limit=5,
            selected_count=3,
        ),
        elements=[
            SegmentedElement(
                id="element_002",
                label="cloud",
                image_path=str(element_b),
                mask_path=str(mask_b),
                bbox=[110, 22, 240, 130],
                score=0.84,
                selected=True,
                z_index=2,
                animation=ElementAnimation(
                    preset="pulse",
                    intensity="low",
                    seed=8,
                    motion_bounds=ElementMotionBounds(
                        translate_px=10,
                        rotate_deg=1.0,
                        scale_delta=0.02,
                    ),
                ),
            ),
            SegmentedElement(
                id="element_001",
                label="subject",
                image_path=str(element_a),
                mask_path=str(mask_a),
                bbox=[10, 12, 140, 180],
                score=0.92,
                selected=True,
                z_index=1,
                animation=ElementAnimation(
                    preset="float",
                    intensity="medium",
                    seed=7,
                    motion_bounds=ElementMotionBounds(
                        translate_px=18,
                        rotate_deg=2.0,
                        scale_delta=0.04,
                    ),
                ),
            ),
        ],
        render=ElementAnimationRender(backend="hyperframes_canvas"),
    )

    loaded = ElementAnimationManifest.from_dict(manifest.to_dict())

    assert loaded.canvas.width == 1024
    assert loaded.timeline.fps == 24
    assert loaded.render.backend == "hyperframes_canvas"
    assert [element.id for element in loaded.selected_elements()] == [
        "element_001",
        "element_002",
    ]
    assert "fps" not in loaded.render.to_dict()


def test_manifest_rejects_selected_count_above_candidate_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="selected_count"):
        ElementAnimationSegmentation(
            provider="comfyui_sam31",
            workflow="image_sam31_segment.json",
            prompt=None,
            candidate_limit=2,
            selected_count=3,
        )
