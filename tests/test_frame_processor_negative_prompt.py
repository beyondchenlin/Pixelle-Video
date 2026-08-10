from pathlib import Path

import pytest

from pixelle_video.models.layered_template import LayeredTemplateSpec
from pixelle_video.models.media import MediaResult
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.services.frame_processor import FrameProcessor
from pixelle_video.services.prompt_trace_artifacts import (
    build_workflow_params_trace,
    validate_media_prompt_trace_artifact,
    write_single_media_prompt_trace_context,
)


@pytest.mark.asyncio
async def test_step_generate_media_forwards_media_negative_prompt(monkeypatch, tmp_path):
    captured = {}

    class _FakeCore:
        async def media(self, **kwargs):
            captured.update(kwargs)
            return MediaResult(media_type="image", url="https://example.com/frame.png")

    processor = FrameProcessor(_FakeCore())

    async def fake_download_media(*args, **kwargs):
        return str(tmp_path / "frame.png")

    monkeypatch.setattr(processor, "_download_media", fake_download_media)

    frame = StoryboardFrame(index=0, narration="scene", image_prompt="bird-universe dog sprint")
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
        media_negative_prompt="photo realism",
    )

    await processor._step_generate_media(frame, config)

    assert captured["negative_prompt"] == "photo realism"


@pytest.mark.asyncio
async def test_step_generate_media_forwards_final_frame_prompt_to_media_model(monkeypatch, tmp_path):
    captured = {}

    class _FakeCore:
        async def media(self, **kwargs):
            captured.update(kwargs)
            return MediaResult(media_type="image", url="https://example.com/frame.png")

    processor = FrameProcessor(_FakeCore())

    async def fake_download_media(*args, **kwargs):
        return str(tmp_path / "frame.png")

    monkeypatch.setattr(processor, "_download_media", fake_download_media)

    final_prompt = (
        "A white rabbit guide with a blue tie stands naturally in the morning market, "
        "warm watercolor light, old city gate in the background."
    )
    frame = StoryboardFrame(index=0, narration="scene", image_prompt=final_prompt)
    config = StoryboardConfig(media_width=1024, media_height=1024, task_id="task-1")

    await processor._step_generate_media(frame, config)

    assert captured["prompt"] == final_prompt


@pytest.mark.asyncio
async def test_step_generate_media_uses_video_template_when_workflow_missing(monkeypatch, tmp_path):
    captured = {}

    class _FakeCore:
        async def media(self, **kwargs):
            captured.update(kwargs)
            return MediaResult(media_type="video", url="https://example.com/frame.mp4", duration=2.5)

    processor = FrameProcessor(_FakeCore())

    async def fake_download_media(*args, **kwargs):
        return str(tmp_path / "frame.mp4")

    monkeypatch.setattr(processor, "_download_media", fake_download_media)

    frame = StoryboardFrame(index=0, narration="scene", image_prompt="dynamic bird-world dog sprint", duration=2.0)
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
        frame_template="1080x1920/video_default.html",
        media_workflow=None,
    )

    await processor._step_generate_media(frame, config)

    assert captured["media_type"] == "video"
    assert captured["duration"] == 2.0


@pytest.mark.asyncio
async def test_step_generate_media_records_video_duration_in_trace_artifact(
    monkeypatch,
    tmp_path,
):
    prompt = "dynamic bird-world dog sprint"

    class _FakeCore:
        async def media(self, **kwargs):
            workflow_param_trace = build_workflow_params_trace(
                {
                    "prompt": kwargs["prompt"],
                    "width": kwargs["width"],
                    "height": kwargs["height"],
                    "index": kwargs["index"],
                    "duration": kwargs["duration"],
                },
                prompt=kwargs["prompt"],
            )
            trace_context = kwargs["media_prompt_trace_context"]
            validate_media_prompt_trace_artifact(
                trace_context,
                prompt=kwargs["prompt"],
                resolved_workflow=trace_context["workflow"],
                resolved_workflow_input=trace_context["workflow_input"],
                media_type="video",
                width=kwargs["width"],
                height=kwargs["height"],
                negative_prompt="",
                workflow_param_trace=workflow_param_trace,
            )
            return MediaResult(media_type="video", url="https://example.com/frame.mp4", duration=2.0)

    processor = FrameProcessor(_FakeCore())

    async def fake_download_media(*args, **kwargs):
        return str(tmp_path / "frame.mp4")

    monkeypatch.setattr(processor, "_download_media", fake_download_media)

    frame = StoryboardFrame(index=0, narration="scene", image_prompt=prompt, duration=2.0)
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
        frame_template="1080x1920/video_default.html",
        media_workflow="video_default.json",
        media_prompt_trace_context=write_single_media_prompt_trace_context(
            tmp_path / "trace",
            task_id="task-1",
            prompt=prompt,
            workflow="video_default.json",
            media_type="video",
            source="test",
            media_width=1024,
            media_height=1024,
        ),
    )

    await processor._step_generate_media(frame, config)

    artifact_path = (
        tmp_path
        / "trace"
        / "media_prompt_calls"
        / "frame_001"
        / "prompt_traces"
        / "final_visual_prompts.md"
    )
    artifact_text = artifact_path.read_text(encoding="utf-8")
    assert '"index": "1"' in artifact_text


@pytest.mark.asyncio
async def test_compose_frame_html_uses_caption_punctuation_mode_for_subtitle_text(monkeypatch, tmp_path):
    captured = {}

    class _FakeHTMLFrameGenerator:
        width = 1024
        height = 1024

        def __init__(self, template_path, canvas_width=None, canvas_height=None):
            captured["template_path"] = template_path
            captured["canvas_width"] = canvas_width
            captured["canvas_height"] = canvas_height

        async def generate_frame(self, **kwargs):
            captured.update(kwargs)
            return kwargs["output_path"]

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        _FakeHTMLFrameGenerator,
    )
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)

    processor = FrameProcessor(None)
    config = StoryboardConfig(
        canvas_width=1280,
        canvas_height=720,
        media_width=768,
        media_height=768,
        task_id="task-1",
        frame_template="1080x1920/image_life_insights_light.html",
        template_text_policy="template_body",
    )
    frame = StoryboardFrame(
        index=0,
        narration="\u4f60\u597d\uff0c\u4e16\u754c\uff01",
        image_prompt="prompt",
        image_path=str(tmp_path / "frame.png"),
        media_type="image",
    )
    storyboard = Storyboard(title="测试标题", config=config, frames=[frame])

    result = await processor._compose_frame_html(
        frame=frame,
        storyboard=storyboard,
        config=config,
        output_path=str(tmp_path / "composed.png"),
    )

    assert result == str(tmp_path / "composed.png")
    assert captured["text"] == "\u4f60\u597d\u4e16\u754c"
    assert captured["canvas_width"] == 1280
    assert captured["canvas_height"] == 720
    assert frame.template_visual_path == str(tmp_path / "composed.png")


@pytest.mark.asyncio
async def test_compose_frame_html_forwards_layered_template_spec_to_materializer(
    monkeypatch,
    tmp_path,
):
    captured = {}

    class _FakeMaterializer:
        async def materialize_frame(self, **kwargs):
            captured.update(kwargs)

            class _Asset:
                path = str(tmp_path / "layered.png")

            Path(_Asset.path).write_bytes(b"png")
            return _Asset()

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.TemplateVisualMaterializer",
        _FakeMaterializer,
    )
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)

    spec = {
        "version": "layered_template.v1",
        "template_id": "user:portrait_news",
        "template_name": "Portrait News",
        "template_type": "image",
        "canvas_width": 720,
        "canvas_height": 1280,
        "media_width": 640,
        "media_height": 960,
        "safe_area": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
        "layers": [
            {
                "id": "layer_background",
                "type": "background",
                "name": "Background",
                "rect": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
                "z_index": 0,
                "opacity": 1.0,
                "rotation": 0.0,
                "locked": False,
                "enabled": True,
                "source": None,
                "style": {"background_color": "#FFFFFF"},
            }
        ],
        "metadata": {"source_kind": "user"},
    }
    processor = FrameProcessor(None)
    config = StoryboardConfig(
        canvas_width=720,
        canvas_height=1280,
        media_width=640,
        media_height=960,
        task_id="task-1",
        frame_template="1080x1920/image_default.html",
        layered_template_spec=spec,
    )
    frame = StoryboardFrame(
        index=0,
        narration="caption",
        image_prompt="prompt",
        image_path=str(tmp_path / "frame.png"),
        media_type="image",
    )
    storyboard = Storyboard(title="Layered title", config=config, frames=[frame])

    await processor._compose_frame_html(
        frame=frame,
        storyboard=storyboard,
        config=config,
        output_path=str(tmp_path / "composed.png"),
    )

    assert captured["layered_template_spec"] == LayeredTemplateSpec.from_dict(spec).to_dict()
    assert captured["caption_text"] == "caption"
    assert captured["text_rendering"] == {}


@pytest.mark.asyncio
async def test_compose_frame_html_uses_canvas_media_layout_when_media_syncs(monkeypatch, tmp_path):
    captured = {}

    class _FakeHTMLFrameGenerator:
        width = 1280
        height = 720

        def __init__(self, template_path, canvas_width=None, canvas_height=None):
            captured["template_path"] = template_path

        async def generate_frame(self, **kwargs):
            captured.update(kwargs)
            return kwargs["output_path"]

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        _FakeHTMLFrameGenerator,
    )
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)

    processor = FrameProcessor(None)
    config = StoryboardConfig(
        canvas_width=1280,
        canvas_height=720,
        media_width=1280,
        media_height=720,
        sync_media_size_to_canvas=True,
        media_placement={"scale_percent": 90, "anchor": "right"},
        task_id="task-1",
        frame_template="1920x1080/image_landscape_minimal.html",
    )
    frame = StoryboardFrame(
        index=0,
        narration="text",
        image_prompt="prompt",
        image_path=str(tmp_path / "frame.png"),
        media_type="image",
    )
    storyboard = Storyboard(title="Test title", config=config, frames=[frame])

    await processor._compose_frame_html(
        frame=frame,
        storyboard=storyboard,
        config=config,
        output_path=str(tmp_path / "composed.png"),
    )

    assert captured["ext"]["media_layout_mode"] == "canvas"
    assert captured["media_placement"].to_dict() == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 90,
        "offset_x": 0,
        "offset_y": 0,
    }
    assert captured["media_type"] == "image"
    assert (captured["media_width"], captured["media_height"]) == (1280, 720)


@pytest.mark.asyncio
async def test_compose_frame_html_allows_blank_template_body_text_for_shell_only_render(monkeypatch, tmp_path):
    captured = {}

    class _FakeHTMLFrameGenerator:
        width = 1024
        height = 1024

        def __init__(self, template_path, canvas_width=None, canvas_height=None):
            captured["template_path"] = template_path

        async def generate_frame(self, **kwargs):
            captured.update(kwargs)
            return kwargs["output_path"]

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        _FakeHTMLFrameGenerator,
    )
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)

    processor = FrameProcessor(None)
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
        frame_template="1080x1920/image_life_insights_light.html",
    )
    frame = StoryboardFrame(
        index=0,
        narration="Original subtitle text.",
        image_prompt="prompt",
        image_path=str(tmp_path / "frame.png"),
        media_type="image",
    )
    storyboard = Storyboard(title="Test title", config=config, frames=[frame])

    await processor._compose_frame_html(
        frame=frame,
        storyboard=storyboard,
        config=config,
        output_path=str(tmp_path / "shell-only.png"),
        template_body_text="",
    )

    assert captured["text"] == ""
    assert frame.template_visual_path == str(tmp_path / "shell-only.png")


@pytest.mark.asyncio
async def test_compose_frame_html_uses_nonempty_template_body_text(monkeypatch, tmp_path):
    captured = {}

    class _FakeHTMLFrameGenerator:
        width = 1024
        height = 1024

        def __init__(self, template_path, canvas_width=None, canvas_height=None):
            captured["template_path"] = template_path

        async def generate_frame(self, **kwargs):
            captured.update(kwargs)
            return kwargs["output_path"]

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        _FakeHTMLFrameGenerator,
    )
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)

    processor = FrameProcessor(None)
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
        frame_template="1080x1920/image_life_insights_light.html",
    )
    frame = StoryboardFrame(
        index=0,
        narration="Original subtitle text.",
        image_prompt="prompt",
        image_path=str(tmp_path / "frame.png"),
        media_type="image",
    )
    storyboard = Storyboard(title="Test title", config=config, frames=[frame])

    await processor._compose_frame_html(
        frame=frame,
        storyboard=storyboard,
        config=config,
        output_path=str(tmp_path / "override.png"),
        template_body_text="Override subtitle.",
    )

    assert captured["text"] == "Override subtitle"


@pytest.mark.asyncio
async def test_frame_processor_call_forwards_template_body_text_to_shell_only_render(monkeypatch, tmp_path):
    captured = {}

    class _FakeCore:
        async def media(self, **kwargs):
            return MediaResult(media_type="image", url="https://example.com/frame.png")

    processor = FrameProcessor(_FakeCore())

    async def fake_generate_audio(frame, config):
        frame.audio_path = str(tmp_path / "audio.mp3")
        frame.duration = 1.0

    async def fake_generate_media(frame, config):
        frame.image_path = str(tmp_path / "frame.png")
        frame.media_type = "image"

    async def fake_compose_frame(frame, storyboard, config, *, template_body_text=None):
        captured["template_body_text"] = template_body_text
        frame.composed_image_path = str(tmp_path / "composed.png")

    async def fake_create_video_segment(frame, config):
        frame.video_segment_path = str(tmp_path / "segment.mp4")

    monkeypatch.setattr(processor, "_step_generate_audio", fake_generate_audio)
    monkeypatch.setattr(processor, "_step_generate_media", fake_generate_media)
    monkeypatch.setattr(processor, "_step_compose_frame", fake_compose_frame)
    monkeypatch.setattr(processor, "_step_create_video_segment", fake_create_video_segment)

    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
    )
    frame = StoryboardFrame(index=0, narration="Original subtitle text.", image_prompt="prompt")
    storyboard = Storyboard(title="Test title", config=config, frames=[frame])

    result = await processor(
        frame=frame,
        storyboard=storyboard,
        config=config,
        template_body_text="",
    )

    assert result is frame
    assert captured["template_body_text"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured_fps", "expected_fps"),
    [
        (30, 90),
        (120, 120),
    ],
)
async def test_step_create_video_segment_uses_high_precision_fps_for_image_frames(
    monkeypatch,
    tmp_path,
    configured_fps,
    expected_fps,
):
    captured = {}

    class _FakeVideoService:
        def create_video_from_image(self, **kwargs):
            captured.update(kwargs)
            output = tmp_path / "segment.mp4"
            output.write_text("segment", encoding="utf-8")
            return str(output)

    monkeypatch.setattr("pixelle_video.services.video.VideoService", _FakeVideoService)
    monkeypatch.setattr(
        "pixelle_video.utils.os_util.get_task_frame_path",
        lambda task_id, index, kind: str(tmp_path / f"{index:02d}_{kind}"),
    )

    processor = FrameProcessor(None)
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
        video_fps=configured_fps,
    )
    frame = StoryboardFrame(
        index=0,
        narration="场景",
        image_prompt="prompt",
        audio_path=str(tmp_path / "audio.mp3"),
        composed_image_path=str(tmp_path / "composed.png"),
        media_type="image",
    )

    await processor._step_create_video_segment(frame, config)

    assert captured["fps"] == expected_fps


@pytest.mark.asyncio
async def test_step_create_video_segment_uses_element_motion_video_when_present(
    monkeypatch,
    tmp_path,
):
    captured = {}

    class _FakeVideoService:
        def merge_audio_video(self, **kwargs):
            captured.update(kwargs)
            Path(kwargs["output"]).write_text("segment", encoding="utf-8")
            return kwargs["output"]

        def create_video_from_image(self, **kwargs):
            raise AssertionError("element motion video should bypass image segment creation")

    monkeypatch.setattr("pixelle_video.services.video.VideoService", _FakeVideoService)
    monkeypatch.setattr(
        "pixelle_video.utils.os_util.get_task_frame_path",
        lambda task_id, index, kind: str(tmp_path / f"{index:02d}_{kind}.mp4"),
    )

    processor = FrameProcessor(None)
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
    )
    frame = StoryboardFrame(
        index=0,
        narration="scene",
        image_prompt="prompt",
        audio_path=str(tmp_path / "audio.mp3"),
        image_path=str(tmp_path / "frame.png"),
        composed_image_path=str(tmp_path / "composed.png"),
        element_motion_video_path=str(tmp_path / "motion.mp4"),
        media_type="image",
    )

    await processor._step_create_video_segment(frame, config)

    assert captured == {
        "video": str(tmp_path / "motion.mp4"),
        "audio": str(tmp_path / "audio.mp3"),
        "output": str(tmp_path / "00_segment.mp4"),
        "replace_audio": True,
        "audio_volume": 1.0,
    }
    assert frame.video_segment_path == str(tmp_path / "00_segment.mp4")


@pytest.mark.asyncio
async def test_step_create_video_segment_copies_element_motion_video_without_audio(
    monkeypatch,
    tmp_path,
):
    class _FakeVideoService:
        def merge_audio_video(self, **kwargs):
            raise AssertionError("missing audio should bypass merge_audio_video")

        def create_video_from_image(self, **kwargs):
            raise AssertionError("element motion video should bypass image segment creation")

    monkeypatch.setattr("pixelle_video.services.video.VideoService", _FakeVideoService)
    monkeypatch.setattr(
        "pixelle_video.utils.os_util.get_task_frame_path",
        lambda task_id, index, kind: str(tmp_path / f"{index:02d}_{kind}.mp4"),
    )

    motion_path = tmp_path / "motion.mp4"
    motion_path.write_bytes(b"motion")
    processor = FrameProcessor(None)
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
    )
    frame = StoryboardFrame(
        index=0,
        narration="scene",
        image_prompt="prompt",
        image_path=str(tmp_path / "frame.png"),
        composed_image_path=str(tmp_path / "composed.png"),
        element_motion_video_path=str(motion_path),
        media_type="image",
    )

    await processor._step_create_video_segment(frame, config)

    assert frame.video_segment_path == str(tmp_path / "00_segment.mp4")
    assert Path(frame.video_segment_path).read_bytes() == b"motion"
