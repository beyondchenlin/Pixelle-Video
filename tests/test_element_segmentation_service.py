from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
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

    async def execute(
        self,
        workflow_input: object,
        workflow_params: dict[str, object],
    ) -> FakeComfyResult:
        self.calls.append((workflow_input, workflow_params))
        return self.result


class FakeCore:
    def __init__(self, kit: FakeKit, comfyui_url: str = "http://comfy.local") -> None:
        self.kit = kit
        self.comfyui_url = comfyui_url
        self.workflow_calls: list[dict[str, object]] = []

    async def _get_or_create_comfykit(self) -> FakeKit:
        return self.kit

    def _get_comfykit_config(self) -> dict[str, str]:
        return {"comfyui_url": self.comfyui_url}

    async def execute_comfykit_workflow(
        self,
        workflow_input: object,
        workflow_params: dict[str, object],
        **kwargs: object,
    ) -> FakeComfyResult:
        self.workflow_calls.append(
            {
                "workflow_input": workflow_input,
                "workflow_params": dict(workflow_params),
                **kwargs,
            }
        )
        if kwargs.get("media_prompt_trace_context") is None:
            raise ValueError("media_prompt_trace_context is required")
        return await self.kit.execute(workflow_input, workflow_params)


def _png(path: Path, color: tuple[int, int, int, int]) -> None:
    Image.new("RGBA", (32, 32), color).save(path)


def _mask(path: Path, bbox: tuple[int, int, int, int] | None) -> None:
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    if bbox is not None:
        draw = ImageDraw.Draw(image)
        draw.rectangle(bbox, fill=(255, 255, 255, 255))
    image.save(path)


async def test_segment_image_builds_manifest_from_comfy_outputs(tmp_path: Path) -> None:
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
    core = FakeCore(kit)
    service = ElementSegmentationService(core)

    manifest = await service.segment_image(
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
    assert core.workflow_calls[0]["media_type"] == "image"
    trace_context = core.workflow_calls[0]["media_prompt_trace_context"]
    assert isinstance(trace_context, dict)
    assert trace_context["prompt"] == "main simple drawing subjects"
    assert Path(str(trace_context["artifact_path"])).is_file()
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


async def test_segment_image_falls_back_to_source_low_motion_when_background_missing(
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
    core = FakeCore(kit)
    service = ElementSegmentationService(core)

    manifest = await service.segment_image(
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
    trace_context = core.workflow_calls[0]["media_prompt_trace_context"]
    artifact_text = Path(str(trace_context["artifact_path"])).read_text(encoding="utf-8")
    assert '"prompt_id": "element_segmentation"' in artifact_text
    assert manifest.background.mode == "source_image_low_motion"
    assert manifest.background.motion_bounds.translate_px <= 6
    assert manifest.background.motion_bounds.rotate_deg <= 0.5
    assert manifest.background.motion_bounds.scale_delta <= 0.015
    assert manifest.render.backend == "python_ffmpeg"
    assert Path(manifest.background.image_path).read_bytes() == source.read_bytes()
    assert len(manifest.elements) == 1
    assert manifest.elements[0].selected is True


async def test_segment_image_downloads_url_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.png"
    element = tmp_path / "element.png"
    mask = tmp_path / "mask.png"
    _png(source, (255, 255, 255, 255))
    _png(element, (255, 0, 0, 255))
    _mask(mask, (1, 2, 20, 21))

    downloaded: list[tuple[str, Path]] = []

    async def fake_download(self, url: str, target: Path) -> None:
        downloaded.append((url, target))
        _png(target, (10, 20, 30, 255))

    monkeypatch.setattr(ElementSegmentationService, "_download_url", fake_download)
    kit = FakeKit(
        FakeComfyResult(
            images=[
                FakeComfyImage("https://cdn.example/background.png"),
                FakeComfyImage("/view?filename=element.png&type=output"),
                FakeComfyImage(str(mask)),
            ],
        ),
    )
    service = ElementSegmentationService(FakeCore(kit, comfyui_url="http://127.0.0.1:8188"))

    manifest = await service.segment_image(
        image_path=str(source),
        task_id="task-1",
        frame_index=3,
        output_dir=str(tmp_path / "out"),
        width=32,
        height=32,
        duration=1.0,
        fps=12,
        selected_count=1,
        candidate_limit=1,
        prompt=None,
        workflow="image_sam31_segment.json",
        backend="hyperframes_canvas",
        intensity="medium",
    )

    assert downloaded == [
        (
            "https://cdn.example/background.png",
            tmp_path / "out" / "element_animation" / "frame_003" / "background.png",
        ),
        (
            "http://127.0.0.1:8188/view?filename=element.png&type=output",
            tmp_path / "out" / "element_animation" / "frame_003" / "element_001.png",
        ),
    ]
    assert Path(manifest.background.image_path).exists()
    assert Path(manifest.elements[0].image_path).exists()


async def test_segment_image_rejects_odd_element_mask_output_count(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    element = tmp_path / "element.png"
    mask = tmp_path / "mask.png"
    dangling = tmp_path / "dangling.png"
    _png(source, (255, 255, 255, 255))
    _png(element, (255, 0, 0, 255))
    _mask(mask, (1, 2, 20, 21))
    _png(dangling, (0, 0, 255, 255))

    kit = FakeKit(
        FakeComfyResult(
            images=[
                FakeComfyImage(str(element)),
                FakeComfyImage(str(mask)),
                FakeComfyImage(str(dangling)),
            ],
        ),
    )
    service = ElementSegmentationService(FakeCore(kit))

    with pytest.raises(ValueError, match="expected .*actual 3"):
        await service.segment_image(
            image_path=str(source),
            task_id="task-1",
            frame_index=0,
            output_dir=str(tmp_path / "out"),
            width=32,
            height=32,
            duration=1.0,
            fps=12,
            selected_count=1,
            candidate_limit=2,
            prompt=None,
            workflow="image_sam31_segment.json",
            backend="python_ffmpeg",
            intensity="medium",
        )


async def test_segment_image_ignores_extra_pairs_after_background_candidate_limit(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    background = tmp_path / "background.png"
    element_a = tmp_path / "element_a.png"
    mask_a = tmp_path / "mask_a.png"
    element_b = tmp_path / "element_b.png"
    mask_b = tmp_path / "mask_b.png"
    _png(source, (255, 255, 255, 255))
    _png(background, (250, 250, 250, 255))
    _png(element_a, (255, 0, 0, 255))
    _mask(mask_a, (1, 2, 20, 21))
    _png(element_b, (0, 0, 255, 255))
    _mask(mask_b, (4, 5, 12, 15))

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

    manifest = await service.segment_image(
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
        intensity="medium",
    )

    assert len(manifest.elements) == 1
    assert manifest.elements[0].image_path.endswith("element_001.png")


async def test_segment_image_ignores_odd_trailing_output_after_background_candidate_limit(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    background = tmp_path / "background.png"
    element = tmp_path / "element.png"
    mask = tmp_path / "mask.png"
    diagnostic = tmp_path / "diagnostic.png"
    _png(source, (255, 255, 255, 255))
    _png(background, (250, 250, 250, 255))
    _png(element, (255, 0, 0, 255))
    _mask(mask, (1, 2, 20, 21))
    _png(diagnostic, (0, 0, 255, 255))

    kit = FakeKit(
        FakeComfyResult(
            images=[
                FakeComfyImage(str(background)),
                FakeComfyImage(str(element)),
                FakeComfyImage(str(mask)),
                FakeComfyImage(str(diagnostic)),
            ],
        ),
    )
    service = ElementSegmentationService(FakeCore(kit))

    manifest = await service.segment_image(
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
        intensity="medium",
    )

    assert len(manifest.elements) == 1
    assert manifest.elements[0].selected is True


async def test_segment_image_does_not_select_empty_mask_candidate(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    element = tmp_path / "element.png"
    empty_mask = tmp_path / "empty_mask.png"
    _png(source, (255, 255, 255, 255))
    _png(element, (255, 0, 0, 255))
    _mask(empty_mask, None)

    kit = FakeKit(
        FakeComfyResult(
            images=[
                FakeComfyImage(str(element)),
                FakeComfyImage(str(empty_mask)),
            ],
        ),
    )
    service = ElementSegmentationService(FakeCore(kit))

    manifest = await service.segment_image(
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
        intensity="medium",
    )

    assert manifest.elements[0].bbox == [0, 0, 32, 32]
    assert manifest.elements[0].selected is False


async def test_segment_image_selects_first_usable_elements_after_empty_mask(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    element_a = tmp_path / "element_a.png"
    empty_mask = tmp_path / "empty_mask.png"
    element_b = tmp_path / "element_b.png"
    mask_b = tmp_path / "mask_b.png"
    _png(source, (255, 255, 255, 255))
    _png(element_a, (255, 0, 0, 255))
    _mask(empty_mask, None)
    _png(element_b, (0, 0, 255, 255))
    _mask(mask_b, (4, 5, 12, 15))

    kit = FakeKit(
        FakeComfyResult(
            images=[
                FakeComfyImage(str(element_a)),
                FakeComfyImage(str(empty_mask)),
                FakeComfyImage(str(element_b)),
                FakeComfyImage(str(mask_b)),
            ],
        ),
    )
    service = ElementSegmentationService(FakeCore(kit))

    manifest = await service.segment_image(
        image_path=str(source),
        task_id="task-1",
        frame_index=0,
        output_dir=str(tmp_path / "out"),
        width=32,
        height=32,
        duration=1.0,
        fps=12,
        selected_count=1,
        candidate_limit=2,
        prompt=None,
        workflow="image_sam31_segment.json",
        backend="python_ffmpeg",
        intensity="medium",
    )

    assert [element.selected for element in manifest.elements] == [False, True]
