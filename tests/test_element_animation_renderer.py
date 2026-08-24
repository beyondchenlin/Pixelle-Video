from pathlib import Path

from PIL import Image

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
from pixelle_video.services.element_animation_renderer import (
    PythonElementAnimationRenderer,
)


def _png(
    path: Path,
    color: tuple[int, int, int, int],
    size: tuple[int, int] = (4, 4),
) -> None:
    Image.new("RGBA", size, color).save(path)


def _mask(path: Path) -> None:
    mask = Image.new("L", (4, 4), 0)
    for x in (1, 2):
        for y in (1, 2):
            mask.putpixel((x, y), 255)
    mask.save(path)


def _manifest(
    tmp_path: Path,
    *,
    selected: bool = True,
    audio_path: str | None = None,
    duration: float = 1.0,
    fps: int = 12,
) -> ElementAnimationManifest:
    background = tmp_path / "background.png"
    element = tmp_path / "element.png"
    mask = tmp_path / "mask.png"
    _png(background, (10, 20, 30, 255))
    _png(element, (220, 30, 40, 255))
    _mask(mask)

    zero_bounds = ElementMotionBounds(translate_px=0, rotate_deg=0, scale_delta=0)
    return ElementAnimationManifest(
        source_image_path=str(background),
        canvas=ElementAnimationCanvas(width=4, height=4),
        timeline=ElementAnimationTimeline(duration=duration, fps=fps),
        background=ElementAnimationBackground(
            mode="inpainted",
            image_path=str(background),
            motion_bounds=zero_bounds,
        ),
        segmentation=ElementAnimationSegmentation(
            provider="test",
            workflow="test.json",
            prompt=None,
            candidate_limit=1,
            selected_count=1,
        ),
        elements=[
            SegmentedElement(
                id="element_001",
                label="subject",
                image_path=str(element),
                mask_path=str(mask),
                bbox=[0, 0, 4, 4],
                score=1.0,
                selected=selected,
                z_index=0,
                animation=ElementAnimation(
                    preset="float",
                    intensity="medium",
                    seed=3,
                    motion_bounds=zero_bounds,
                ),
            )
        ],
        render=ElementAnimationRender(backend="python_ffmpeg"),
        audio_path=audio_path,
    )


def test_render_frame_composites_selected_element_over_background(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)

    frame = PythonElementAnimationRenderer().render_frame(manifest, time=0)

    assert frame.mode == "RGB"
    assert frame.size == (4, 4)
    assert frame.getpixel((1, 1)) == (220, 30, 40)
    assert frame.getpixel((0, 0)) == (10, 20, 30)


def test_render_frame_skips_unselected_elements(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, selected=False)

    frame = PythonElementAnimationRenderer().render_frame(manifest, time=0)

    assert frame.getpixel((1, 1)) == (10, 20, 30)


def test_render_video_muxes_audio_bounded_to_animation_duration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    manifest = _manifest(tmp_path, audio_path=str(audio), duration=0.4, fps=5)
    rendered_times: list[float] = []
    encoder_calls: list[dict[str, object]] = []

    class FakeEncoder:
        def encode_png_sequence(self, **kwargs) -> str:
            encoder_calls.append(kwargs)
            return str(kwargs["output_path"])

    renderer = PythonElementAnimationRenderer(video_encoder=FakeEncoder())

    def fake_render_frame(
        frame_manifest: ElementAnimationManifest,
        *,
        time: float,
    ) -> Image.Image:
        assert frame_manifest is manifest
        rendered_times.append(time)
        return Image.new("RGB", (2, 2), (1, 2, 3))

    monkeypatch.setattr(renderer, "render_frame", fake_render_frame)

    output_path = tmp_path / "rendered.mp4"
    result = renderer.render_video(manifest, str(output_path))

    assert result == str(output_path)
    assert len(rendered_times) == 2
    assert len(encoder_calls) == 1
    assert encoder_calls[0]["fps"] == 5
    assert encoder_calls[0]["duration"] == 0.4
    assert encoder_calls[0]["audio_path"] == str(audio)
    assert encoder_calls[0]["output_path"] == output_path
