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
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured["world_preset_id"] = kwargs["world_preset_id"]
        captured["shot_preset_id"] = kwargs["shot_preset_id"]
        captured["content_mode"] = kwargs["content_mode"]
        captured["consistency_strength"] = kwargs["consistency_strength"]
        captured["role_strategy"] = kwargs["role_strategy"]
        captured["role_locking_strength"] = kwargs["role_locking_strength"]
        captured["shot_strategy"] = kwargs["shot_strategy"]
        return StyledImagePromptBatch(
            prompts=["bird-universe dog sprint"],
            negative_prompt="photo realism",
            resolved_style=None,
            planning_snapshot={
                "world_preset_id": "neutral_knowledge_storyboard",
                "effective_final_shot_preset": "balanced_explainer",
                "resolved_content_mode": "concept_explainer",
                "selected_consistency_strength": "strong",
                "resolved_role_strategy": "stable_explainer_cast",
                "selected_role_locking_strength": "strong",
                "selected_shot_strategy": "strict",
                "frames": [
                    {
                        "shot_type": "medium_shot",
                        "shot_purpose": "context",
                        "frame_source": "planner_generated",
                    }
                ],
            },
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
        params={
            "frame_template": "1080x1920/image_default.html",
            "media_width": 1024,
            "media_height": 1024,
            "world_preset_id": "neutral_knowledge_storyboard",
            "shot_preset_id": "balanced_explainer",
            "content_mode": "concept_explainer",
            "consistency_strength": "strong",
            "role_strategy": "auto",
            "role_locking_strength": "strong",
            "shot_strategy": "strict",
        },
    )
    ctx.title = "Storyboard Title"
    ctx.task_id = "task-1"
    ctx.narrations = ["scene one"]

    await pipeline.plan_visuals(ctx)
    await pipeline.initialize_storyboard(ctx)

    assert captured["world_preset_id"] == "neutral_knowledge_storyboard"
    assert captured["shot_preset_id"] == "balanced_explainer"
    assert captured["content_mode"] == "concept_explainer"
    assert captured["consistency_strength"] == "strong"
    assert captured["role_strategy"] == "auto"
    assert captured["role_locking_strength"] == "strong"
    assert captured["shot_strategy"] == "strict"
    assert ctx.image_prompts == ["bird-universe dog sprint"]
    assert ctx.media_negative_prompt == "photo realism"
    assert ctx.planning_snapshot["world_preset_id"] == "neutral_knowledge_storyboard"
    assert ctx.storyboard.planning_snapshot["world_preset_id"] == "neutral_knowledge_storyboard"
    assert ctx.storyboard.config.world_preset_id == "neutral_knowledge_storyboard"
    assert ctx.storyboard.config.shot_preset_id == "balanced_explainer"
    assert ctx.storyboard.config.content_mode == "concept_explainer"
    assert ctx.storyboard.config.consistency_strength == "strong"
    assert ctx.storyboard.config.role_strategy == "stable_explainer_cast"
    assert ctx.storyboard.config.role_locking_strength == "strong"
    assert ctx.storyboard.config.shot_strategy == "strict"
    assert ctx.storyboard.frames[0].shot_type == "medium_shot"
    assert ctx.storyboard.frames[0].shot_purpose == "context"
    assert ctx.storyboard.frames[0].frame_source == "planner_generated"


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
