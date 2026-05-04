import pytest

from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.storyboard_planning import FramePlan
from pixelle_video.models.style_resolution import StyledImagePromptBatch, StyleSourceSpec
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch


class _DummyCore:
    def __init__(self, config: dict):
        self.config = config
        self.llm = object()
        self.tts = None
        self.media = object()
        self.video = None


def _storyboard_plan(narration: str = "scene one") -> StoryboardPlan:
    return StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text=narration,
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text=narration,
                visual_goal="Show the scene clearly.",
                prompt_intent="Keep the generated visual aligned with the storyboard.",
                source_start=0,
                source_end=len(narration),
            )
        ],
    )


@pytest.mark.asyncio
async def test_standard_pipeline_plan_visuals_uses_shared_styled_batch(monkeypatch):
    captured = {}

    async def real_styled_batch_with_capture(**kwargs):
        captured["has_forbid_embedded_text_arg"] = "forbid_embedded_text_in_image" in kwargs
        captured["prompt_contexts"] = kwargs.get("prompt_contexts")
        captured["text_rendering"] = kwargs.get("text_rendering")
        captured["generation_world_hint"] = kwargs.get("generation_world_hint")
        captured["world_preset_id"] = kwargs["world_preset_id"]
        captured["shot_preset_id"] = kwargs["shot_preset_id"]
        captured["content_mode"] = kwargs["content_mode"]
        captured["consistency_strength"] = kwargs["consistency_strength"]
        captured["role_strategy"] = kwargs["role_strategy"]
        captured["role_locking_strength"] = kwargs["role_locking_strength"]
        captured["shot_strategy"] = kwargs["shot_strategy"]
        kwargs.pop("generation_world_hint", None)
        return await generate_styled_image_prompt_batch(**kwargs)

    async def fake_generate_image_prompts(*args, **kwargs):
        return ["bird-universe dog sprint"]

    async def fake_plan_storyboard_batch(**kwargs):
        return type(
            "PlanResult",
            (),
            {
                "frames": (
                    FramePlan(
                        scene_id="scene-1",
                        shot_type="medium_shot",
                        shot_purpose="context",
                        world_elements=("strategy board",),
                        prompt_intent="teach the first relationship",
                    ),
                ),
                "planning_snapshot": {
                    "world_preset_id": "neutral_knowledge_storyboard",
                    "effective_final_shot_preset": "balanced_explainer",
                    "resolved_content_mode": "concept_explainer",
                    "selected_consistency_strength": "strong",
                    "resolved_role_strategy": "stable_explainer_cast",
                    "selected_role_locking_strength": "strong",
                    "selected_shot_strategy": "strict",
                    "world_preset": {
                        "display_name": "Neutral Knowledge Storyboard",
                        "style_core": "clean educational illustration",
                    },
                },
            },
        )()

    async def fake_resolve_style_spec(*args, **kwargs):
        raise RuntimeError("resolver boom")

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        real_styled_batch_with_capture,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.plan_storyboard_batch",
        fake_plan_storyboard_batch,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_source",
        lambda image_config, prompt_prefix_override=None: StyleSourceSpec(
            origin="request",
            raw_content="flat illustration",
            content_hash="hash-123",
            source_identity="request:hash-123",
            item_id=None,
        ),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": True})(),
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
            "generation_world_hint": "古城清晨漫游",
            "content_mode": "concept_explainer",
            "consistency_strength": "strong",
            "role_strategy": "auto",
            "role_locking_strength": "strong",
            "shot_strategy": "strict",
        },
    )
    ctx.title = "Storyboard Title"
    ctx.task_id = "task-1"
    ctx.storyboard_plan = _storyboard_plan()

    await pipeline.plan_visuals(ctx)
    await pipeline.initialize_storyboard(ctx)

    assert captured["world_preset_id"] == "neutral_knowledge_storyboard"
    assert captured["generation_world_hint"] == "古城清晨漫游"
    assert isinstance(captured["prompt_contexts"], PromptContextEnvelope)
    assert captured["prompt_contexts"].frame_contexts[0]["visual_goal"] == "Show the scene clearly."
    assert captured["has_forbid_embedded_text_arg"] is False
    assert captured["text_rendering"] is None
    assert captured["shot_preset_id"] == "balanced_explainer"
    assert captured["content_mode"] == "concept_explainer"
    assert captured["consistency_strength"] == "strong"
    assert captured["role_strategy"] == "auto"
    assert captured["role_locking_strength"] == "strong"
    assert captured["shot_strategy"] == "strict"
    assert ctx.image_prompts == [
        "flat illustration, Neutral Knowledge Storyboard, clean educational illustration, medium_shot, context, strategy board, bird-universe dog sprint"
    ]
    assert ctx.media_negative_prompt is None
    assert ctx.planning_snapshot["world_preset_id"] == "neutral_knowledge_storyboard"
    assert ctx.planning_snapshot["frames"][0]["shot_type"] == "medium_shot"
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
        captured["batch_size"] = kwargs.get("batch_size")
        captured["max_concurrency"] = kwargs.get("max_concurrency")
        captured["text_rendering"] = kwargs.get("text_rendering")
        captured["has_forbid_embedded_text_arg"] = "forbid_embedded_text_in_image" in kwargs
        return StyledImagePromptBatch(
            prompts=["override prompt"],
            negative_prompt=None,
            resolved_style=None,
        )

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    pipeline = StandardPipeline(_DummyCore({"comfyui": {"image": {"prompt_prefix": "legacy"}}}))
    ctx = PipelineContext(
        input_text="topic",
        params={
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": "explicit override",
            "llm_prompt_batch_size": 8,
            "llm_prompt_batch_concurrent_limit": 3,
            "text_rendering": {
                "title_style": {"font_size": 96},
                "caption_style": {"font_size": 72},
                "overlay_style": {"font_size": 88},
                "overlay": {"enabled": False},
                "image_text": {
                    "suppress_embedded_text": True,
                    "positive_prompt": "avoid generated lettering",
                    "negative_prompt": "signage",
                }
            },
        },
    )
    ctx.storyboard_plan = _storyboard_plan()

    await pipeline.plan_visuals(ctx)

    assert captured["prompt_prefix"] == "explicit override"
    assert captured["batch_size"] == 8
    assert captured["max_concurrency"] == 3
    assert captured["text_rendering"] == {
        "overlay": {"enabled": False},
        "image_text": {
            "suppress_embedded_text": True,
            "positive_prompt": "avoid generated lettering",
            "negative_prompt": "signage",
        },
    }
    assert captured["has_forbid_embedded_text_arg"] is False
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
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
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
    ctx.storyboard_plan = _storyboard_plan()

    await pipeline.plan_visuals(ctx)

    assert captured["image_config"] == config["comfyui"]["video"]
    assert captured["media_type"] == "video"
    assert ctx.image_prompts == ["dynamic video prompt"]
    assert ctx.media_negative_prompt == "washed out frames"


@pytest.mark.asyncio
async def test_standard_pipeline_plan_visuals_builds_text_package_and_native_hints(
    monkeypatch,
    tmp_path,
):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured["native_prompt_hints_by_frame"] = kwargs.get(
            "native_prompt_hints_by_frame"
        )
        captured["text_rendering"] = kwargs.get("text_rendering")
        captured["has_text_rendering_policy_arg"] = "text_rendering_policy" in kwargs
        captured["has_forbid_embedded_text_arg"] = "forbid_embedded_text_in_image" in kwargs
        return StyledImagePromptBatch(
            prompts=["native prompt"],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={"prompt": "summary"},
        )

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    pipeline = StandardPipeline(_DummyCore({"comfyui": {"image": {}}}))
    ctx = PipelineContext(
        input_text="topic",
        params={
            "frame_template": "1080x1920/image_default.html",
            "media_width": 1024,
            "media_height": 1024,
            "text_rendering": {
                "title_style": {"font_size": 90},
                "caption_style": {"font_size": 64},
                "overlay_style": {"position": "center"},
                "overlay": {
                    "enabled": True,
                    "mode": "native_hint",
                    "renderer_targets": ["hyperframes", "native_prompt"],
                    "max_items_per_frame": 1,
                }
            },
        },
    )
    ctx.title = "Text Layer"
    ctx.task_id = "task-1"
    ctx.task_dir = str(tmp_path)
    ctx.storyboard_plan = _storyboard_plan("把品牌名 Pixelle 放在画面中心。")

    await pipeline.plan_visuals(ctx)
    await pipeline.initialize_storyboard(ctx)

    assert ctx.creation_package is not None
    assert ctx.creation_package.text_overlay_plan is not None
    assert ctx.creation_package.text_overlay_plan.candidates[0].role == "model_native_hint"
    assert captured["text_rendering"] == {
        "overlay": {
            "enabled": True,
            "mode": "native_hint",
            "renderer_targets": ["hyperframes", "native_prompt"],
            "max_items_per_frame": 1,
        }
    }
    assert captured["has_text_rendering_policy_arg"] is False
    assert captured["has_forbid_embedded_text_arg"] is False
    assert captured["native_prompt_hints_by_frame"][0][0].source_candidate_ids == (
        "text-1-1",
    )
    assert (tmp_path / "text_overlay_plan.json").exists()


@pytest.mark.asyncio
async def test_standard_pipeline_static_path_does_not_persist_pseudo_resolved_planning_fields(monkeypatch):
    monkeypatch.setattr("pixelle_video.pipelines.standard.get_template_type", lambda template_name: "static")

    pipeline = StandardPipeline(_DummyCore({}))
    ctx = PipelineContext(
        input_text="topic",
        params={
            "frame_template": "1080x1920/default.html",
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
    ctx.title = "Static Storyboard"
    ctx.task_id = "task-static"
    ctx.storyboard_plan = _storyboard_plan()

    await pipeline.plan_visuals(ctx)
    await pipeline.initialize_storyboard(ctx)

    assert ctx.planning_snapshot["storyboard_generation"]["resolved_scene_count"] == 1
    assert ctx.storyboard.planning_snapshot["storyboard_generation"]["resolved_scene_count"] == 1
    assert ctx.storyboard.config.world_preset_id is None
    assert ctx.storyboard.config.shot_preset_id is None
    assert ctx.storyboard.config.content_mode is None
    assert ctx.storyboard.config.consistency_strength is None
    assert ctx.storyboard.config.role_strategy is None
    assert ctx.storyboard.config.role_locking_strength is None
    assert ctx.storyboard.config.shot_strategy is None
