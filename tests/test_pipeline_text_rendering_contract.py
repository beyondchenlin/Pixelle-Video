from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.models.asset_script import AssetScriptSceneResponse
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig
from pixelle_video.pipelines.asset_based import AssetBasedPipeline
from pixelle_video.services.text_rendering_contract_summary import (
    build_text_rendering_result_metadata,
)


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


def test_build_text_rendering_result_metadata_centralizes_public_summaries():
    observability = {
        "caption_rendering_summary": {
            "enabled": True,
            "artifacts": {"subtitle_only_ass": "text_layer/subtitle_only.ass"},
        },
        "text_layer_summary": {"enabled": False, "fallbacks": []},
        "image_text_policy_summary": {
            "status": "not_applicable",
            "suppress_embedded_text": False,
        },
    }

    result_metadata = build_text_rendering_result_metadata(
        observability,
        text_render_package_path="text_render_package.json",
    )

    assert result_metadata == {
        "caption_rendering_summary": observability["caption_rendering_summary"],
        "text_layer_summary": observability["text_layer_summary"],
        "image_text_policy_summary": observability["image_text_policy_summary"],
        "text_render_package_path": "text_render_package.json",
    }
    observability["caption_rendering_summary"]["artifacts"][
        "subtitle_only_ass"
    ] = "changed.ass"
    assert result_metadata["caption_rendering_summary"]["artifacts"][
        "subtitle_only_ass"
    ] == "text_layer/subtitle_only.ass"


def test_build_text_rendering_result_metadata_omits_artifact_path_without_contract():
    result_metadata = build_text_rendering_result_metadata(
        {},
        text_render_package_path="text_render_package.json",
    )

    assert result_metadata == {
        "caption_rendering_summary": None,
        "text_layer_summary": None,
        "image_text_policy_summary": None,
    }


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
    assert metadata["result"]["text_render_package_path"] == "text_render_package.json"


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
