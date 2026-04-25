from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.models.asset_script import AssetScriptSceneResponse
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig
from pixelle_video.pipelines.asset_based import AssetBasedPipeline
from pixelle_video.pipelines.custom import CustomPipeline


class _RecordingPersistence:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.saved_metadata = None

    def get_task_runtime_log_path(self, task_id):
        return self.tmp_path / task_id / "logs" / "runtime.jsonl"

    async def save_task_metadata(self, task_id, metadata):
        self.saved_metadata = metadata

    async def save_storyboard(self, task_id, storyboard):
        return None


class _MinimalCore:
    config = {"render": {"backend": "legacy"}}
    llm = object()
    tts = object()
    media = object()
    video = object()


def test_custom_pipeline_direct_contract_summary_honors_disabled_reason():
    pipeline = CustomPipeline(_MinimalCore())
    ctx = SimpleNamespace(observability={})

    pipeline._record_text_rendering_contract_summary(
        ctx,
        text_rendering={
            "caption_style": {"font_size": 72},
            "overlay": {"enabled": True, "renderer_targets": ["ass"]},
        },
        supported_overlay=False,
        disabled_reason="custom_pipeline_overlay_not_supported",
    )

    assert ctx.observability["caption_rendering_summary"]["style_profile_id"] == (
        "caption-default"
    )
    assert ctx.observability["text_layer_summary"]["enabled"] is False
    assert ctx.observability["text_layer_summary"]["disabled_reason"] == (
        "custom_pipeline_overlay_not_supported"
    )


def test_asset_based_direct_contract_summary_honors_disabled_reason():
    pipeline = AssetBasedPipeline(_MinimalCore())
    ctx = SimpleNamespace(
        request={
            "text_rendering": {
                "caption_style": {"primary_color": "#FFFF00"},
                "overlay": {"enabled": False},
            }
        },
        observability={},
    )

    pipeline._record_text_rendering_contract_summary(
        ctx,
        supported_overlay=False,
        disabled_reason="asset_based_overlay_disabled",
    )

    assert ctx.observability["caption_rendering_summary"]["style_profile_id"] == (
        "caption-default"
    )
    assert ctx.observability["text_layer_summary"]["disabled_reason"] == (
        "asset_based_overlay_disabled"
    )


@pytest.mark.asyncio
async def test_custom_pipeline_records_contract_when_overlay_unsupported(
    monkeypatch,
    tmp_path,
):
    task_dir = tmp_path / "task-custom"
    task_dir.mkdir()
    final_path = task_dir / "final.mp4"
    persistence = _RecordingPersistence(tmp_path)

    class _FakeHTMLFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1080, 1920

    class _FakeVideoService:
        def concat_videos(self, videos, output, **kwargs):
            Path(output).write_bytes(b"video")
            return output

    class _FakeFrameProcessor:
        async def __call__(
            self,
            frame,
            storyboard,
            config,
            total_frames,
            progress_callback=None,
        ):
            frame.duration = 1.0
            segment_path = task_dir / f"segment_{frame.index}.mp4"
            segment_path.write_bytes(b"segment")
            frame.video_segment_path = str(segment_path)
            return frame

    class _FakeCore:
        def __init__(self):
            self.config = {
                "template": {"default_template": "1080x1920/static_default.html"},
                "render": {"backend": "legacy"},
            }
            self.llm = object()
            self.tts = object()
            self.media = object()
            self.video = object()
            self.frame_processor = _FakeFrameProcessor()
            self.persistence = persistence

    async def fake_generate_title(*args, **kwargs):
        return "Custom Title"

    monkeypatch.setattr(
        "pixelle_video.utils.os_util.create_task_output_dir",
        lambda: (str(task_dir), "task-custom"),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.os_util.get_task_final_video_path",
        lambda task_id: str(final_path),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_title",
        fake_generate_title,
    )
    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeHTMLFrameGenerator,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda template_name: "static",
    )
    monkeypatch.setattr("pixelle_video.services.video.VideoService", _FakeVideoService)

    pipeline = CustomPipeline(_FakeCore())

    await pipeline(
        text="line one",
        text_rendering={
            "overlay": {"enabled": True, "renderer_targets": ["ass"]},
            "caption_style": {"primary_color": "#ffff00"},
            "overlay_style": {"primary_color": "#00ff00"},
            "image_text": {"suppress_embedded_text": True},
        },
    )

    metadata = persistence.saved_metadata
    assert metadata is not None
    observability = metadata["observability"]
    assert observability["caption_rendering_summary"]["style_profile_id"] == (
        "caption-default"
    )
    assert observability["text_layer_summary"] == {
        "enabled": False,
        "renderer": "disabled",
        "track_count": 0,
        "cue_count": 0,
        "native_prompt_hint_count": 0,
        "style_profile_ids": ["overlay-default"],
        "artifacts": {},
        "fallbacks": [],
        "targets": ["ass"],
        "disabled_reason": "overlay_unsupported",
    }
    assert observability["image_text_policy_summary"]["status"] == "not_applicable"
    assert metadata["result"]["text_layer_summary"] == observability[
        "text_layer_summary"
    ]
    assert metadata["result"]["caption_rendering_summary"] == observability[
        "caption_rendering_summary"
    ]
    assert metadata["result"]["image_text_policy_summary"] == observability[
        "image_text_policy_summary"
    ]
    assert "caption_style" not in observability["caption_rendering_summary"]
    assert "overlay_style" not in observability["text_layer_summary"]


@pytest.mark.asyncio
async def test_asset_based_pipeline_records_contract_when_overlay_disabled(tmp_path):
    persistence = _RecordingPersistence(tmp_path)

    class _FakeCore:
        def __init__(self):
            self.config = {"render": {"backend": "legacy"}}
            self.llm = object()
            self.tts = object()
            self.media = object()
            self.video = object()
            self.persistence = persistence

    pipeline = AssetBasedPipeline(_FakeCore())
    ctx = await _build_asset_context(
        pipeline,
        tmp_path,
        text_rendering={
            "overlay": {"enabled": False, "renderer_targets": ["ass"]},
            "caption_style": {"primary_color": "#ffff00"},
            "overlay_style": {"primary_color": "#00ff00"},
        },
    )

    assert ctx.text_render_package.text_style_profiles[0].primary_color == "#FFFF00"
    assert ctx.text_render_package.diagnostics["frame_count"] == 1
    assert ctx.observability["caption_rendering_summary"]["style_profile_id"] == (
        "caption-default"
    )
    assert ctx.observability["text_layer_summary"]["enabled"] is False
    assert ctx.observability["text_layer_summary"]["targets"] == []
    assert ctx.observability["text_layer_summary"]["disabled_reason"] == "overlay_disabled"
    assert ctx.observability["text_layer_summary"]["style_profile_ids"] == [
        "overlay-default"
    ]
    assert ctx.observability["image_text_policy_summary"]["status"] == "not_applicable"
    assert "caption_style" not in ctx.observability["caption_rendering_summary"]
    assert "overlay_style" not in ctx.observability["text_layer_summary"]

    final_path = Path(ctx.task_dir) / "final.mp4"
    final_path.write_bytes(b"video")
    ctx.final_video_path = str(final_path)
    await pipeline._persist_task_data(ctx)

    metadata = persistence.saved_metadata
    assert metadata["input"]["text_rendering"] == ctx.request["text_rendering"]
    assert metadata["result"]["text_layer_summary"] == ctx.observability[
        "text_layer_summary"
    ]
    assert metadata["result"]["caption_rendering_summary"] == ctx.observability[
        "caption_rendering_summary"
    ]
    assert metadata["result"]["image_text_policy_summary"] == ctx.observability[
        "image_text_policy_summary"
    ]


@pytest.mark.asyncio
async def test_asset_based_caption_style_is_independent_from_overlay_support(tmp_path):
    class _FakeCore:
        def __init__(self):
            self.config = {"render": {"backend": "legacy"}}
            self.llm = object()
            self.tts = object()
            self.media = object()
            self.video = object()

    pipeline = AssetBasedPipeline(_FakeCore())
    ctx = await _build_asset_context(
        pipeline,
        tmp_path,
        text_rendering={
            "overlay": {"enabled": True, "renderer_targets": ["ass"]},
            "caption_style": {"font_size": 72, "primary_color": "#ffff00"},
        },
    )

    assert ctx.text_render_package.text_style_profiles[0].font_size == 72
    assert ctx.text_render_package.text_style_profiles[0].primary_color == "#FFFF00"
    assert ctx.observability["text_layer_summary"]["disabled_reason"] == (
        "overlay_unsupported"
    )
    assert ctx.observability["caption_rendering_summary"]["style_profile_id"] == (
        "caption-default"
    )


async def _build_asset_context(pipeline, tmp_path, *, text_rendering):
    from pixelle_video.pipelines.linear import PipelineContext

    ctx = PipelineContext(
        input_text="Promote sale",
        params={"template_params": {}, "text_rendering": text_rendering},
    )
    ctx.request = ctx.params
    ctx.task_id = "task-asset"
    ctx.task_dir = str(tmp_path / "task-asset")
    ctx.title = "Sale"
    ctx.script = [
        AssetScriptSceneResponse(
            scene_number=1,
            asset_id="asset_001",
            narrations=["Welcome to our sale.", "Everything is discounted."],
            duration=8,
        ).model_dump()
        | {
            "asset_path": str(tmp_path / "asset.png"),
            "asset_name": "asset.png",
            "asset_type": "image",
        }
    ]
    ctx.matched_scenes = [
        {
            **ctx.script[0],
            "matched_asset_id": "asset_001",
            "matched_asset": str(tmp_path / "asset.png"),
        }
    ]
    pipeline.asset_index = {
        "asset_001": {
            "asset_id": "asset_001",
            "path": str(tmp_path / "asset.png"),
            "type": "image",
            "name": "asset.png",
            "description": "A shop asset",
        }
    }
    ctx.storyboard = Storyboard(
        title="Sale",
        config=StoryboardConfig(task_id="task-asset", media_width=1080, media_height=1920),
    )

    await pipeline.initialize_storyboard(ctx)
    return ctx
