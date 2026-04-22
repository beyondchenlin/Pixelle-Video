import pytest

from pixelle_video.models.storyboard_planning import FramePlan
from pixelle_video.models.style_resolution import ResolvedStyleSpec, StyleSourceSpec
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch


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
    )

    assert result.prompts == [
        "rounded geometric dog sprinting across playful wooden obstacles, same playful bird-universe silhouette"
    ]
    assert "Angry Birds style" not in result.prompts[0]
    assert result.negative_prompt == "photo realism, realistic fur"


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
    )

    assert result.prompts == ["flat illustration, base scene prompt"]
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
    )

    assert result.prompts == ["Angry Birds style, base scene prompt"]


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
    )

    assert result.prompts == [
        "base scene prompt, same playful bird-universe silhouette"
    ]
    assert result.negative_prompt is None


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
    )

    assert captured["style_profile"]["style_kind"] == "ip_world"
    assert result.prompts == [
        "dynamic dog sprinting through playful wooden obstacles, same playful bird-universe silhouette"
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
    )

    assert captured["planner_kwargs"]["world_preset_id"] == "neutral_knowledge_storyboard"
    assert captured["planner_kwargs"]["shot_preset_id"] == "balanced_explainer"
    assert captured["planner_kwargs"]["shot_strategy"] == "strict"
    assert captured["style_profile"]["style_kind"] == "visual_only"
    assert result.planning_snapshot["world_preset_id"] == "neutral_knowledge_storyboard"
    assert "Neutral Knowledge Storyboard" in result.prompts[0]
    assert "medium_shot" in result.prompts[0]


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
    )

    assert result.prompts == ["flat illustration, base scene prompt"]
    assert result.planning_snapshot is None
