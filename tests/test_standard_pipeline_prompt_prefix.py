import pytest

from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


class _DummyCore:
    def __init__(self, config: dict):
        self.config = config
        self.llm = object()
        self.tts = None
        self.media = object()
        self.video = None


@pytest.mark.asyncio
async def test_standard_pipeline_plan_visuals_uses_shared_styled_batch(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        return StyledImagePromptBatch(
            prompts=["bird-universe dog sprint"],
            negative_prompt="photo realism",
            resolved_style=None,
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    pipeline = StandardPipeline(
        _DummyCore(
            {
                "comfyui": {
                    "image": {
                        "prompt_prefix": "legacy prefix",
                        "prompt_prefix_library": {
                            "active_prefix_id": "custom-flat",
                            "items": [
                                {"id": "custom-flat", "content": "flat illustration"}
                            ],
                        },
                    }
                }
            }
        )
    )
    ctx = PipelineContext(
        input_text="topic",
        params={"frame_template": "1080x1920/image_default.html"},
    )
    ctx.narrations = ["scene one"]

    await pipeline.plan_visuals(ctx)

    assert ctx.image_prompts == ["bird-universe dog sprint"]
    assert ctx.media_negative_prompt == "photo realism"


@pytest.mark.asyncio
async def test_standard_pipeline_plan_visuals_passes_explicit_override(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured["prompt_prefix"] = kwargs["prompt_prefix"]
        return StyledImagePromptBatch(
            prompts=["override prompt"],
            negative_prompt=None,
            resolved_style=None,
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    pipeline = StandardPipeline(_DummyCore({"comfyui": {"image": {"prompt_prefix": "legacy"}}}))
    ctx = PipelineContext(
        input_text="topic",
        params={
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": "explicit override",
        },
    )
    ctx.narrations = ["scene one"]

    await pipeline.plan_visuals(ctx)

    assert captured["prompt_prefix"] == "explicit override"
    assert ctx.image_prompts == ["override prompt"]


@pytest.mark.asyncio
async def test_standard_pipeline_plan_visuals_uses_video_config_and_media_type(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured["image_config"] = kwargs["image_config"]
        captured["media_type"] = kwargs["media_type"]
        return StyledImagePromptBatch(
            prompts=["dynamic video prompt"],
            negative_prompt="washed out frames",
            resolved_style=None,
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    config = {
        "comfyui": {
            "image": {"prompt_prefix": "image legacy"},
            "video": {"prompt_prefix": "video legacy"},
        }
    }
    pipeline = StandardPipeline(_DummyCore(config))
    ctx = PipelineContext(
        input_text="topic",
        params={"frame_template": "1080x1920/video_default.html"},
    )
    ctx.narrations = ["scene one"]

    await pipeline.plan_visuals(ctx)

    assert captured["image_config"] == config["comfyui"]["video"]
    assert captured["media_type"] == "video"
    assert ctx.image_prompts == ["dynamic video prompt"]
    assert ctx.media_negative_prompt == "washed out frames"
