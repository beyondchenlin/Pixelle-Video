from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from pixelle_video.services.element_segmentation import ElementSegmentationService


@dataclass
class FakeComfyImage:
    path: str


@dataclass
class FakeComfyResult:
    images: list[FakeComfyImage]


class FakeKit:
    def __init__(self, result: FakeComfyResult) -> None:
        self.result = result
        self.calls: list[tuple[object, dict[str, object]]] = []

    def execute(
        self,
        workflow_input: object,
        workflow_params: dict[str, object],
    ) -> FakeComfyResult:
        self.calls.append((workflow_input, workflow_params))
        return self.result


class FakeCore:
    def __init__(self, kit: FakeKit) -> None:
        self.kit = kit

    def _get_or_create_comfykit(self) -> FakeKit:
        return self.kit


def _png(path: Path, color: tuple[int, int, int, int]) -> None:
    Image.new("RGBA", (32, 32), color).save(path)


def _mask(path: Path, bbox: tuple[int, int, int, int] | None) -> None:
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    if bbox is not None:
        draw = ImageDraw.Draw(image)
        draw.rectangle(bbox, fill=(255, 255, 255, 255))
    image.save(path)


def test_segment_image_builds_manifest_from_comfy_outputs(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    background = tmp_path / "background.png"
    element_a = tmp_path / "element_a.png"
    mask_a = tmp_path / "mask_a.png"
    element_b = tmp_path / "element_b.png"
    mask_b = tmp_path / "mask_b.png"
    _png(source, (255, 255, 255, 255))
    _png(background, (250, 250, 250, 255))
    _png(element_a, (255, 0, 0, 255))
    _mask(mask_a, (4, 5, 12, 15))
    _png(element_b, (0, 0, 255, 255))
    _mask(mask_b, None)

    kit = FakeKit(
        FakeComfyResult(
            images=[
                FakeComfyImage(str(background)),
                FakeComfyImage(str(element_a)),
                FakeComfyImage(str(mask_a)),
                FakeComfyImage(str(element_b)),
                FakeComfyImage(str(mask_b)),
            ],
        ),
    )
    service = ElementSegmentationService(FakeCore(kit))

    manifest = service.segment_image(
        image_path=str(source),
        task_id="task-1",
        frame_index=0,
        output_dir=str(tmp_path / "out"),
        width=32,
        height=32,
        duration=2.5,
        fps=24,
        selected_count=1,
        candidate_limit=2,
        prompt="main simple drawing subjects",
        workflow="image_sam31_segment.json",
        backend="hyperframes_canvas",
        intensity="medium",
    )

    assert kit.calls == [
        (
            "image_sam31_segment.json",
            {
                "image": str(source),
                "prompt": "main simple drawing subjects",
                "candidate_limit": 2,
                "selected_count": 1,
                "width": 32,
                "height": 32,
            },
        ),
    ]
    output_root = tmp_path / "out" / "element_animation" / "frame_000"
    assert manifest.background.mode == "inpainted"
    assert manifest.background.image_path == str(output_root / "background.png")
    assert manifest.segmentation.selected_count == 1
    assert manifest.segmentation.candidate_limit == 2
    assert manifest.canvas.width == 32
    assert manifest.timeline.fps == 24
    assert manifest.render.backend == "hyperframes_canvas"
    assert len(manifest.elements) == 2
    assert [element.selected for element in manifest.elements] == [True, False]
    assert [element.animation.preset for element in manifest.elements] == ["float", "pulse"]
    assert manifest.elements[0].bbox == [4, 5, 13, 16]
    assert manifest.elements[1].bbox == [0, 0, 32, 32]
    assert Path(manifest.elements[0].image_path) == output_root / "element_001.png"
    assert Path(manifest.elements[0].mask_path) == output_root / "mask_001.png"
    assert (output_root / "background.png").exists()
    assert (output_root / "element_002.png").exists()
    assert (output_root / "mask_002.png").exists()


def test_segment_image_falls_back_to_source_low_motion_when_background_missing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    element = tmp_path / "element.png"
    mask = tmp_path / "mask.png"
    _png(source, (255, 255, 255, 255))
    _png(element, (255, 0, 0, 255))
    _mask(mask, (1, 2, 20, 21))

    kit = FakeKit(
        FakeComfyResult(
            images=[
                FakeComfyImage(str(element)),
                FakeComfyImage(str(mask)),
            ],
        ),
    )
    service = ElementSegmentationService(FakeCore(kit))

    manifest = service.segment_image(
        image_path=str(source),
        task_id="task-1",
        frame_index=0,
        output_dir=str(tmp_path / "out"),
        width=32,
        height=32,
        duration=1.0,
        fps=12,
        selected_count=1,
        candidate_limit=1,
        prompt=None,
        workflow="image_sam31_segment.json",
        backend="python_ffmpeg",
        intensity="high",
    )

    assert kit.calls[0][1]["prompt"] == (
        "main foreground subjects, separated simple drawing elements"
    )
    assert manifest.background.mode == "source_image_low_motion"
    assert manifest.background.motion_bounds.translate_px <= 6
    assert manifest.background.motion_bounds.rotate_deg <= 0.5
    assert manifest.background.motion_bounds.scale_delta <= 0.015
    assert manifest.render.backend == "python_ffmpeg"
    assert Path(manifest.background.image_path).read_bytes() == source.read_bytes()
    assert len(manifest.elements) == 1
    assert manifest.elements[0].selected is True
