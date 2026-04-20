import pytest

from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


class _DummyCore:
    def __init__(self, config: dict):
        self.config = config
        self.llm = object()
        self.tts = None
        self.media = None
        self.video = None


@pytest.mark.asyncio
async def test_standard_pipeline_plan_visuals_uses_active_library_prefix_when_no_override(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["base scene prompt"]

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.generate_image_prompts",
        fake_generate_image_prompts,
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
                                {
                                    "id": "custom-flat",
                                    "name": "Flat",
                                    "content": "flat illustration, simple shapes",
                                    "style_category_id": "flat_illustration",
                                    "scene_category_id": "knowledge_sharing",
                                    "source": "manual",
                                    "is_builtin": False,
                                }
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

    assert ctx.image_prompts == ["flat illustration, simple shapes, base scene prompt"]


@pytest.mark.asyncio
async def test_standard_pipeline_plan_visuals_honors_explicit_prompt_prefix_override(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["base scene prompt"]

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.generate_image_prompts",
        fake_generate_image_prompts,
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
                                {
                                    "id": "custom-flat",
                                    "name": "Flat",
                                    "content": "flat illustration, simple shapes",
                                    "style_category_id": "flat_illustration",
                                    "scene_category_id": "knowledge_sharing",
                                    "source": "manual",
                                    "is_builtin": False,
                                }
                            ],
                        },
                    }
                }
            }
        )
    )
    ctx = PipelineContext(
        input_text="topic",
        params={
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": "explicit override",
        },
    )
    ctx.narrations = ["scene one"]

    await pipeline.plan_visuals(ctx)

    assert ctx.image_prompts == ["explicit override, base scene prompt"]
