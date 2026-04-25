import pytest

from pixelle_video.models.storyboard_planning import FramePlan
from pixelle_video.models.style_resolution import ResolvedStyleSpec, StyleSourceSpec
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch
from pixelle_video.utils.prompt_helper import apply_no_text_policy


def _suppress_image_text(negative_prompt: str | None = None) -> dict:
    image_text = {"suppress_embedded_text": True}
    if negative_prompt is not None:
        image_text["negative_prompt"] = negative_prompt
    return {"image_text": image_text}


def _resolved_ip_world() -> ResolvedStyleSpec:
    return ResolvedStyleSpec(
        style_kind="ip_world",
        prompt_template="{prompt}, same playful bird-universe silhouette",
        negative_prompt="photo realism, realistic fur",
        style_profile={
            "style_kind": "ip_world",
            "subject_policy": "keep_subject_semantics_but_restyle_into_world",
            "shape_language": "rounded geometric cartoon forms",
            "material": "clean game-like cartoon surface",
            "palette": "high saturation reds and yellows",
            "lighting": "bright playful lighting",
            "world_elements": "destructible wooden obstacles and game-like props",
            "consistency_anchor": "all frames belong to the same playful bird universe",
            "negative_rules": "do not revert to realistic anatomy",
        },
        content_hash="hash-123",
        resolver_version="2026-04-21-v1",
        source_identity="request:hash-123",
        raw_content="Angry Birds style",
    )


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_blocks_raw_fallback_for_ip_world(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        assert kwargs["style_profile"]["style_kind"] == "ip_world"
        return ["rounded geometric dog sprinting across playful wooden obstacles"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_source",
        lambda image_config, prompt_prefix_override=None: StyleSourceSpec(
            origin="request",
            raw_content="Angry Birds style",
            content_hash="hash-123",
            source_identity="request:hash-123",
            item_id=None,
        ),
    )

    async def fake_resolve_style_spec(*args, **kwargs):
        return _resolved_ip_world()

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": True})(),
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["一只小狗在奔跑"],
        image_config={"prompt_prefix": "", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        prompt_prefix="Angry Birds style",
        text_rendering=_suppress_image_text("text, Chinese characters"),
    )

    assert result.prompts == [
        apply_no_text_policy(
            "rounded geometric dog sprinting across playful wooden obstacles, same playful bird-universe silhouette"
        )
    ]
    assert "Angry Birds style" not in result.prompts[0]
    assert result.negative_prompt is not None
    assert "photo realism" in result.negative_prompt
    assert "realistic fur" in result.negative_prompt
    assert "text" in result.negative_prompt
    assert "Chinese characters" in result.negative_prompt


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_falls_back_to_legacy_prefix_when_resolver_fails(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        assert kwargs["style_profile"] is None
        return ["base scene prompt"]

    async def fake_resolve_style_spec(*args, **kwargs):
        raise RuntimeError("resolver boom")

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={"prompt_prefix": "flat illustration", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        media_service=None,
        prompt_prefix=None,
        text_rendering=_suppress_image_text(),
    )

    assert result.prompts == [apply_no_text_policy("flat illustration, base scene prompt")]
    assert result.negative_prompt is None


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_preserves_raw_ip_world_prefix_when_template_missing(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["base scene prompt"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_source",
        lambda image_config, prompt_prefix_override=None: StyleSourceSpec(
            origin="request",
            raw_content="Angry Birds style",
            content_hash="hash-123",
            source_identity="request:hash-123",
            item_id=None,
        ),
    )

    async def fake_resolve_style_spec(*args, **kwargs):
        return ResolvedStyleSpec(
            style_kind="ip_world",
            prompt_template="",
            negative_prompt="",
            style_profile=_resolved_ip_world().style_profile,
            content_hash="hash-123",
            resolver_version="2026-04-21-v1",
            source_identity="request:hash-123",
            raw_content="Angry Birds style",
        )

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["一只小狗在奔跑"],
        image_config={"prompt_prefix": "", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        media_service=None,
        prompt_prefix="Angry Birds style",
        text_rendering=_suppress_image_text(),
    )

    assert result.prompts == [apply_no_text_policy("Angry Birds style, base scene prompt")]


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_ignores_capability_probe_failures(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["base scene prompt"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_source",
        lambda image_config, prompt_prefix_override=None: StyleSourceSpec(
            origin="request",
            raw_content="Angry Birds style",
            content_hash="hash-123",
            source_identity="request:hash-123",
            item_id=None,
        ),
    )

    async def fake_resolve_style_spec(*args, **kwargs):
        return _resolved_ip_world()

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("workflow missing")),
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["一只小狗在奔跑"],
        image_config={"prompt_prefix": "", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        media_service=object(),
        workflow="missing.json",
        prompt_prefix="Angry Birds style",
        text_rendering=_suppress_image_text(),
    )

    assert result.prompts == [
        apply_no_text_policy("base scene prompt, same playful bird-universe silhouette")
    ]
    assert result.negative_prompt is None


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_appends_no_text_policy_when_negative_prompt_unsupported(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["base scene prompt"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": False})(),
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={"prompt_prefix": "flat illustration", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        text_rendering=_suppress_image_text(),
    )

    assert result.negative_prompt is None
    assert "no visible text" in result.prompts[0]
    assert "no Chinese characters" in result.prompts[0]
    assert "no English letters" in result.prompts[0]


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_merges_no_text_negative_prompt_when_supported(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["rounded geometric dog sprinting across playful wooden obstacles"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_source",
        lambda image_config, prompt_prefix_override=None: StyleSourceSpec(
            origin="request",
            raw_content="Angry Birds style",
            content_hash="hash-123",
            source_identity="request:hash-123",
            item_id=None,
        ),
    )

    async def fake_resolve_style_spec(*args, **kwargs):
        return _resolved_ip_world()

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": True})(),
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={"prompt_prefix": "", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        media_service=object(),
        workflow="selfhost/image_flux.json",
        prompt_prefix="Angry Birds style",
        text_rendering=_suppress_image_text("text, Chinese characters"),
    )

    assert "no visible text" in result.prompts[0]
    assert result.negative_prompt is not None
    assert "photo realism" in result.negative_prompt
    assert "realistic fur" in result.negative_prompt
    assert "text" in result.negative_prompt
    assert "Chinese characters" in result.negative_prompt


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_uses_video_prompt_generator_for_video_media(monkeypatch):
    captured = {}

    async def fail_generate_image_prompts(*args, **kwargs):
        raise AssertionError("image prompt generator should not be used for video media")

    async def fake_generate_video_prompts(*args, **kwargs):
        captured["style_profile"] = kwargs["style_profile"]
        return ["dynamic dog sprinting through playful wooden obstacles"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fail_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_video_prompts",
        fake_generate_video_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_source",
        lambda image_config, prompt_prefix_override=None: StyleSourceSpec(
            origin="request",
            raw_content="Angry Birds style",
            content_hash="hash-123",
            source_identity="request:hash-123",
            item_id=None,
        ),
    )

    async def fake_resolve_style_spec(*args, **kwargs):
        return _resolved_ip_world()

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["一只小狗在奔跑"],
        image_config={"prompt_prefix": "", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        media_service=None,
        media_type="video",
        prompt_prefix="Angry Birds style",
        text_rendering=_suppress_image_text(),
    )

    assert captured["style_profile"]["style_kind"] == "ip_world"
    assert result.prompts == [
        apply_no_text_policy(
            "dynamic dog sprinting through playful wooden obstacles, same playful bird-universe silhouette"
        )
    ]


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_returns_planning_snapshot_for_storyboard_controls(monkeypatch):
    captured = {}

    async def fake_generate_image_prompts(*args, **kwargs):
        captured["style_profile"] = kwargs["style_profile"]
        return ["base scene prompt"]

    async def fake_plan_storyboard_batch(**kwargs):
        captured["planner_kwargs"] = kwargs
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
                    "world_preset": {
                        "display_name": "Neutral Knowledge Storyboard",
                        "style_core": "clean educational illustration",
                    },
                },
            },
        )()

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
            raw_content="Angry Birds style",
            content_hash="hash-123",
            source_identity="request:hash-123",
            item_id=None,
        ),
    )

    async def fake_resolve_style_spec(*args, **kwargs):
        return _resolved_ip_world()

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={"prompt_prefix": "", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        world_preset_id="neutral_knowledge_storyboard",
        shot_preset_id="balanced_explainer",
        consistency_strength="strong",
        content_mode="concept_explainer",
        role_strategy="auto",
        role_locking_strength="strong",
        shot_strategy="strict",
        frame_overrides=[{"scene_id": "scene-1", "locked_fields": ["shot_type"], "shot_type": "medium_shot"}],
        text_rendering=_suppress_image_text(),
    )

    assert captured["planner_kwargs"]["world_preset_id"] == "neutral_knowledge_storyboard"
    assert captured["planner_kwargs"]["shot_preset_id"] == "balanced_explainer"
    assert captured["planner_kwargs"]["shot_strategy"] == "strict"
    assert captured["style_profile"]["style_kind"] == "visual_only"
    assert result.planning_snapshot["world_preset_id"] == "neutral_knowledge_storyboard"
    assert result.planning_snapshot["frames"] == [
        {
            "scene_id": "scene-1",
            "narration_fragment": "",
            "knowledge_goal": "",
            "shot_type": "medium_shot",
            "shot_purpose": "context",
            "primary_subject": "",
            "secondary_subjects": [],
            "world_elements": ["strategy board"],
            "continuity_anchors": [],
            "focus_detail": "",
            "prompt_intent": "teach the first relationship",
            "locked_fields": [],
            "override_source": None,
            "frame_source": "planner_generated",
            "replan_scope": "local",
            "planner_version": "1.0",
        }
    ]
    assert "Neutral Knowledge Storyboard" in result.prompts[0]
    assert "medium_shot" in result.prompts[0]
    assert "no visible text" in result.prompts[0]


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_passes_prompt_contexts_to_storyboard_planner(monkeypatch):
    captured = {}
    prompt_contexts = [
        {
            "plan_source_text": "Full script with connected ideas.",
            "frame_source_text": "First idea in the connected script.",
            "narration_text": "First idea narration.",
            "visual_goal": "Show the first idea as part of the whole story.",
            "prompt_intent": "Keep continuity with the complete script.",
        }
    ]

    async def fake_generate_image_prompts(*args, **kwargs):
        return ["base scene prompt"]

    async def fake_plan_storyboard_batch(**kwargs):
        captured["planner_kwargs"] = kwargs
        return type(
            "PlanResult",
            (),
            {
                "frames": (
                    FramePlan(
                        scene_id="1",
                        shot_type="medium_shot",
                        shot_purpose="context",
                        world_elements=("strategy board",),
                        prompt_intent="teach the first relationship",
                    ),
                ),
                "planning_snapshot": {
                    "world_preset_id": "neutral_knowledge_storyboard",
                    "world_preset": {
                        "display_name": "Neutral Knowledge Storyboard",
                        "style_core": "clean educational illustration",
                    },
                },
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.plan_storyboard_batch",
        fake_plan_storyboard_batch,
    )

    await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["First idea narration."],
        prompt_contexts=prompt_contexts,
        image_config={},
        world_preset_id="neutral_knowledge_storyboard",
    )

    assert captured["planner_kwargs"]["prompt_contexts"] == prompt_contexts


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_storyboard_falls_back_to_legacy_prefix_when_resolver_fails(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        assert kwargs["style_profile"] is None
        return ["base scene prompt"]

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
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.plan_storyboard_batch",
        fake_plan_storyboard_batch,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={"prompt_prefix": "flat illustration", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        world_preset_id="neutral_knowledge_storyboard",
        text_rendering=_suppress_image_text(),
    )

    assert result.prompts == [
        apply_no_text_policy(
            "flat illustration, Neutral Knowledge Storyboard, clean educational illustration, medium_shot, context, strategy board, base scene prompt"
        )
    ]
    assert result.planning_snapshot["world_preset_id"] == "neutral_knowledge_storyboard"


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_storyboard_keeps_compatible_template_semantics(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        assert kwargs["style_profile"]["style_kind"] == "visual_only"
        return ["base scene prompt"]

    async def fake_plan_storyboard_batch(**kwargs):
        return type(
            "PlanResult",
            (),
            {
                "frames": (
                    FramePlan(
                        scene_id="scene-1",
                        shot_type="close_up",
                        shot_purpose="detail_focus",
                        world_elements=("lab bench",),
                        prompt_intent="show the apparatus clearly",
                    ),
                ),
                "planning_snapshot": {
                    "world_preset_id": "neutral_knowledge_storyboard",
                    "world_preset": {
                        "display_name": "Neutral Knowledge Storyboard",
                        "style_core": "clean educational illustration",
                    },
                },
            },
        )()

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
            raw_content="editorial line art",
            content_hash="hash-789",
            source_identity="request:hash-789",
            item_id=None,
        ),
    )

    async def fake_resolve_style_spec(*args, **kwargs):
        return ResolvedStyleSpec(
            style_kind="visual_only",
            prompt_template="editorial line art treatment, {prompt}, with etched crosshatching",
            negative_prompt="",
            style_profile={
                "style_kind": "visual_only",
                "subject_policy": "preserve_subject",
                "shape_language": "",
                "material": "",
                "palette": "",
                "lighting": "",
                "world_elements": "",
                "consistency_anchor": "",
                "negative_rules": "",
            },
            content_hash="hash-789",
            resolver_version="2026-04-21-v1",
            source_identity="request:hash-789",
            raw_content="editorial line art",
        )

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={"prompt_prefix": "", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        world_preset_id="neutral_knowledge_storyboard",
        text_rendering=_suppress_image_text(),
    )

    assert result.prompts == [
        apply_no_text_policy(
            "editorial line art treatment, Neutral Knowledge Storyboard, clean educational illustration, close_up, detail_focus, lab bench, base scene prompt, with etched crosshatching"
        )
    ]


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_keeps_legacy_prompt_path_when_storyboard_controls_disabled(monkeypatch):
    async def fail_plan_storyboard_batch(**kwargs):
        raise AssertionError("storyboard planner should not run without storyboard controls")

    async def fake_generate_image_prompts(*args, **kwargs):
        return ["base scene prompt"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.plan_storyboard_batch",
        fail_plan_storyboard_batch,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={"prompt_prefix": "flat illustration", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        text_rendering=_suppress_image_text(),
    )

    assert result.prompts == [apply_no_text_policy("flat illustration, base scene prompt")]
    assert result.planning_snapshot is None


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_forwards_prompt_contexts(monkeypatch):
    captured = {}

    async def fake_generate_image_prompts(*args, **kwargs):
        captured["prompt_contexts"] = kwargs.get("prompt_contexts")
        return ["base scene prompt"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["第一句。"],
        prompt_contexts=[
            {
                "narration_text": "第一句。",
                "visual_goal": "Show idea one.",
                "prompt_intent": "Visual metaphor one.",
            }
        ],
        image_config={"prompt_prefix": "", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
    )

    assert captured["prompt_contexts"] == [
        {
            "narration_text": "第一句。",
            "visual_goal": "Show idea one.",
            "prompt_intent": "Visual metaphor one.",
        }
    ]
    assert result.prompts == ["base scene prompt"]


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_reports_substage_progress_messages(monkeypatch):
    progress_events = []

    async def fake_generate_image_prompts(*args, **kwargs):
        progress_callback = kwargs["progress_callback"]
        progress_callback(1, 1, "base_prompt_generation")
        return ["base scene prompt"]

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
                    "world_preset": {
                        "display_name": "Neutral Knowledge Storyboard",
                        "style_core": "clean educational illustration",
                    },
                },
            },
        )()

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
            raw_content="Angry Birds style",
            content_hash="hash-123",
            source_identity="request:hash-123",
            item_id=None,
        ),
    )

    async def fake_resolve_style_spec(*args, **kwargs):
        return _resolved_ip_world()

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )

    await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={"prompt_prefix": "", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        world_preset_id="neutral_knowledge_storyboard",
        progress_callback=lambda completed, total, message: progress_events.append(
            (completed, total, message)
        ),
    )

    assert [message for _, _, message in progress_events] == [
        "progress.detail.style_resolution",
        "progress.detail.storyboard_planning",
        "base_prompt_generation",
        "progress.detail.prompt_assembly",
    ]
