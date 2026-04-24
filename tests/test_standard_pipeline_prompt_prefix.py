import pytest

from pixelle_video.models.storyboard_planning import FramePlan
from pixelle_video.models.style_resolution import StyledImagePromptBatch, StyleSourceSpec
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch
from pixelle_video.utils.prompt_helper import apply_no_text_policy


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

    async def real_styled_batch_with_capture(**kwargs):
        captured["world_preset_id"] = kwargs["world_preset_id"]
        captured["shot_preset_id"] = kwargs["shot_preset_id"]
        captured["content_mode"] = kwargs["content_mode"]
        captured["consistency_strength"] = kwargs["consistency_strength"]
        captured["role_strategy"] = kwargs["role_strategy"]
        captured["role_locking_strength"] = kwargs["role_locking_strength"]
        captured["shot_strategy"] = kwargs["shot_strategy"]
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
        "pixelle_video.pipelines.standard.generate_styled_image_prompt_batch",
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
    assert ctx.image_prompts == [
        apply_no_text_policy(
            "flat illustration, Neutral Knowledge Storyboard, clean educational illustration, medium_shot, context, strategy board, bird-universe dog sprint"
        )
    ]
    assert ctx.media_negative_prompt is not None
    assert "text" in ctx.media_negative_prompt
    assert "Chinese characters" in ctx.media_negative_prompt
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
        captured["text_rendering_policy"] = kwargs.get("text_rendering_policy")
        return StyledImagePromptBatch(
            prompts=["native prompt"],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={"prompt": "summary"},
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    pipeline = StandardPipeline(_DummyCore({"comfyui": {"image": {}}}))
    ctx = PipelineContext(
        input_text="topic",
        params={
            "frame_template": "1080x1920/image_default.html",
            "media_width": 1024,
            "media_height": 1024,
            "text_layer": {
                "enabled": True,
                "mode": "native_hint",
                "renderer_targets": ["native_prompt"],
                "max_items_per_frame": 1,
            },
        },
    )
    ctx.title = "Text Layer"
    ctx.task_id = "task-1"
    ctx.task_dir = str(tmp_path)
    ctx.narrations = ["把品牌名 Pixelle 放在画面中心。"]

    await pipeline.plan_visuals(ctx)
    await pipeline.initialize_storyboard(ctx)

    assert ctx.creation_package is not None
    assert ctx.creation_package.text_overlay_plan is not None
    assert ctx.creation_package.text_overlay_plan.candidates[0].role == "model_native_hint"
    assert captured["text_rendering_policy"].image_text_mode == "native_hint"
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
    ctx.narrations = ["scene one"]

    await pipeline.plan_visuals(ctx)
    await pipeline.initialize_storyboard(ctx)

    assert ctx.planning_snapshot is None
    assert ctx.storyboard.planning_snapshot is None
    assert ctx.storyboard.config.world_preset_id is None
    assert ctx.storyboard.config.shot_preset_id is None
    assert ctx.storyboard.config.content_mode is None
    assert ctx.storyboard.config.consistency_strength is None
    assert ctx.storyboard.config.role_strategy is None
    assert ctx.storyboard.config.role_locking_strength is None
    assert ctx.storyboard.config.shot_strategy is None
