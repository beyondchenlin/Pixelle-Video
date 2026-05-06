import pytest

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.content_world import ContentWorldHintSource, ContentWorldProfile
from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.storyboard_planning import FramePlan
from pixelle_video.models.style_resolution import ResolvedStyleSpec, StyleSourceSpec
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch
from pixelle_video.utils.prompt_helper import apply_no_text_policy, sanitize_visual_prompt_text


def _progress_message_key(message):
    return getattr(message, "key", message)


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


def _storyboard_plan() -> StoryboardPlan:
    frame = StoryboardPlanFrame(
        index=1,
        source_text="从长乐门出发，走进正定古城。",
        visual_goal="表现长乐门作为旅程入口的历史感。",
        prompt_intent="建立古城空间和导览开篇。",
        shot_type="中远景",
        shot_purpose="建立场景",
        primary_subject="长乐门",
        world_elements=("青砖城墙", "晨光"),
    )
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=frame.source_text,
        frames=[frame],
    )


def _storyboard_plan_two_frames() -> StoryboardPlan:
    frames = [
        StoryboardPlanFrame(
            index=1,
            source_text="frame one",
            visual_goal="show frame one",
            prompt_intent="plan frame one",
            primary_subject="gate one",
        ),
        StoryboardPlanFrame(
            index=2,
            source_text="frame two",
            visual_goal="show frame two",
            prompt_intent="plan frame two",
            primary_subject="gate two",
        ),
    ]
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text="frame one frame two",
        frames=frames,
    )


def _ip_profile() -> IPProfile:
    return IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="正定向导兔",
        identity_lock=("白色卡通兔子", "长耳朵"),
        identity_anchors=("蓝色领带",),
        negative_constraints=("避免多余文字", "避免角色贴纸感"),
        visible_text_whitelist=("从长乐门出发", "长乐门"),
    )


def _empty_ip_profile() -> IPProfile:
    return IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="Empty IP",
    )


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_accepts_task3_ip_passthrough_kwargs(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["base scene prompt"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_source",
        lambda image_config, prompt_prefix_override=None: None,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={},
        storyboard_plan=None,
        ip_enabled=False,
        ip_profile=None,
        scene_casts_by_frame=None,
        text_rendering=_suppress_image_text(),
    )

    assert result.prompts == [apply_no_text_policy("base scene prompt")]
    assert result.planning_snapshot is None


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
        + ", photo realism, realistic fur"
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
async def test_generate_styled_image_prompt_batch_rejects_enabled_ip_without_identity_anchors():
    with pytest.raises(ValueError, match="identity anchors|身份锚点"):
        await generate_styled_image_prompt_batch(
            llm_service=object(),
            narrations=["从长乐门出发。"],
            image_config={},
            storyboard_plan=_storyboard_plan(),
            ip_enabled=True,
            ip_profile=_empty_ip_profile(),
        )


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_merges_ip_negative_constraints_for_z_image(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["Zhengding gate prompt"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": False})(),
    )
    plan = _storyboard_plan()

    class _Planner:
        def __init__(self, *args, **kwargs):
            pass
        async def plan_batch(self, **kwargs):
            return [
                type(
                    "Pkg",
                    (),
                    {
                        "frame_id": plan.frames[0].frame_id,
                        "to_dict": lambda self: {
                            "frame_id": plan.frames[0].frame_id,
                            "ip_presence_type": "scene_integrated",
                            "negative_constraints": ["avoid extra text", "avoid sticker-like IP"],
                        },
                    },
                )()
            ]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.IPFrameAppearancePlanner",
        _Planner,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["Start from Changle Gate."],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        storyboard_plan=plan,
        ip_enabled=True,
        ip_profile=_ip_profile(),
    )

    assert result.negative_prompt is None
    assert "avoid extra text" in result.prompts[0]
    assert "avoid sticker-like IP" in result.prompts[0]


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_keeps_per_frame_ip_negative_out_of_batch_negative_prompt(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["frame one prompt", "frame two prompt"]

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
    plan = _storyboard_plan_two_frames()

    class _Planner:
        def __init__(self, *args, **kwargs):
            pass
        async def plan_batch(self, **kwargs):
            return [
                type(
                    "Pkg",
                    (),
                    {
                        "frame_id": plan.frames[0].frame_id,
                        "to_dict": lambda self: {
                            "frame_id": plan.frames[0].frame_id,
                            "ip_presence_type": "scene_integrated",
                            "negative_constraints": ["avoid frame one sticker"],
                        },
                    },
                )(),
                type(
                    "Pkg",
                    (),
                    {
                        "frame_id": plan.frames[1].frame_id,
                        "to_dict": lambda self: {
                            "frame_id": plan.frames[1].frame_id,
                            "ip_presence_type": "scene_integrated",
                            "negative_constraints": ["avoid frame two mascot"],
                        },
                    },
                )(),
            ]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.IPFrameAppearancePlanner",
        _Planner,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["frame one", "frame two"],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_flux.json",
        storyboard_plan=plan,
        ip_enabled=True,
        ip_profile=_ip_profile(),
        text_rendering=_suppress_image_text("letters"),
    )

    assert result.negative_prompt is not None
    assert "photo realism" in result.negative_prompt
    assert "letters" in result.negative_prompt
    assert "avoid frame one sticker" not in result.negative_prompt
    assert "avoid frame two mascot" not in result.negative_prompt


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_merges_all_z_image_constraints_when_negative_prompt_unsupported(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["styled frame prompt"]

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
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": False})(),
    )
    plan = _storyboard_plan()

    class _Planner:
        def __init__(self, *args, **kwargs):
            pass
        async def plan_batch(self, **kwargs):
            return [
                type(
                    "Pkg",
                    (),
                    {
                        "frame_id": plan.frames[0].frame_id,
                        "to_dict": lambda self: {
                            "frame_id": plan.frames[0].frame_id,
                            "ip_presence_type": "scene_integrated",
                            "negative_constraints": ["avoid IP sticker"],
                            "image_text_plan": {
                                "visible_text_whitelist": ["Changle Gate"],
                            },
                        },
                    },
                )()
            ]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.IPFrameAppearancePlanner",
        _Planner,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["frame one"],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        storyboard_plan=plan,
        ip_enabled=True,
        ip_profile=_ip_profile(),
        text_rendering=_suppress_image_text("letters"),
    )

    assert result.negative_prompt is None
    assert "photo realism" in result.prompts[0]
    assert "letters" in result.prompts[0]
    assert "avoid IP sticker" in result.prompts[0]
    assert "Changle Gate" in result.prompts[0]
    assert "only whitelisted text" in result.prompts[0].lower()
    assert result.prompts[0].lower().count("only whitelisted text") == 1


@pytest.mark.asyncio
async def test_z_image_final_prompt_contains_structured_ip_identity_anchors(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["Zhengding gate prompt"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": False})(),
    )
    hero_frame = StoryboardPlanFrame(
        index=1,
        source_text="IP主角登场，白色卡通兔子引导观众探索古城。",
        visual_goal="IP英雄镜头展示",
        prompt_intent="强IP露出",
        shot_type="中景",
        primary_subject="白色卡通兔子",
    )
    plan = StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=hero_frame.source_text,
        frames=[hero_frame],
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["IP主角登场，白色卡通兔子引导观众探索古城。"],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        storyboard_plan=plan,
        ip_enabled=True,
        ip_profile=IPProfile(
            ip_profile_id="ip_main",
            workspace_id="workspace_1",
            project_id="project_1",
            name="正定向导兔",
            identity_lock=("白色卡通兔子", "长耳朵"),
            identity_anchors=("蓝色领带",),
            semantic_boundary=("不能替代历史建筑",),
            negative_constraints=("避免画成普通人类讲解者",),
        ),
    )

    final_prompt = result.prompts[0]
    # With IP hero frame (STRONG_IDENTITY, weight=0.9 >= threshold 0.7),
    # the IP appearance_description is post-appended
    assert "白色卡通兔子" in final_prompt
    assert "避免画成普通人类讲解者" in final_prompt


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_ignores_stale_ip_adaptation_when_ip_disabled(monkeypatch):
    captured = {}

    async def fake_generate_image_prompts(*args, **kwargs):
        captured["prompt_contexts"] = kwargs["prompt_contexts"]
        return ["base frame prompt"]

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
        narrations=["frame one"],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        ip_enabled=False,
        prompt_contexts=[
            {
                "ip_adaptation": {
                    "negative_constraints": ["stale IP negative"],
                    "image_text_plan": {"visible_text_whitelist": ["Stale Text"]},
                },
            }
        ],
    )

    assert "Stale Text" not in result.prompts[0]
    assert "stale IP negative" not in result.prompts[0]
    assert isinstance(captured["prompt_contexts"], PromptContextEnvelope)
    assert "ip_adaptation" not in captured["prompt_contexts"].frame_contexts[0]
    assert "ip_presence_options" not in captured["prompt_contexts"].frame_contexts[0]
    assert result.planning_snapshot is None


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_does_not_apply_ip_chain_to_video(monkeypatch):
    captured = {}

    async def fake_generate_video_prompts(*args, **kwargs):
        captured["prompt_contexts"] = kwargs["prompt_contexts"]
        return ["video prompt with no IP text"]

    class _Planner:
        def __init__(self, *args, **kwargs):
            pass
        async def plan_batch(self, **kwargs):
            raise AssertionError("IP planner should not run for video prompts")

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_video_prompts",
        fake_generate_video_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.IPFrameAppearancePlanner",
        _Planner,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["frame one"],
        image_config={},
        media_type="video",
        storyboard_plan=_storyboard_plan(),
        ip_enabled=True,
        ip_profile=_ip_profile(),
        prompt_contexts=[
            {
                "visual_goal": "Keep plain video context.",
                "ip_adaptation": {
                    "negative_constraints": ["stale video IP negative"],
                    "image_text_plan": {"visible_text_whitelist": ["Video Stale Text"]},
                },
                "ip_presence_options": ["scene_integrated"],
            }
        ],
    )

    assert isinstance(captured["prompt_contexts"], PromptContextEnvelope)
    assert "ip_adaptation" not in captured["prompt_contexts"].frame_contexts[0]
    assert "ip_presence_options" not in captured["prompt_contexts"].frame_contexts[0]
    assert "only whitelisted text" not in result.prompts[0].lower()
    assert "ip_adaptations_by_frame" not in (result.planning_snapshot or {})


def test_sanitize_visual_prompt_text_removes_short_long_and_quoted_field_labels():
    prompt = sanitize_visual_prompt_text(
        '"summary_text": Start, \'title_hex\': #FFF, "scene_text": Gate, color #FFFFFFFF'
    )

    assert "#FFF" not in prompt
    assert "#FFFFFFFF" not in prompt
    assert "summary_text" not in prompt
    assert "title_hex" not in prompt
    assert "scene_text" not in prompt


def test_sanitize_visual_prompt_text_removes_full_width_colon_field_labels():
    prompt = sanitize_visual_prompt_text(
        '"summary_text"： Start, visible_text_whitelist： Gate'
    )

    assert "summary_text" not in prompt
    assert "visible_text_whitelist" not in prompt
    assert "Start" in prompt
    assert "Gate" in prompt


def test_sanitize_visual_prompt_text_removes_world_profile_field_labels():
    prompt = sanitize_visual_prompt_text(
        "generation_world_profile: city, story_constraints: protect gate, "
        "ip_integration_guidance: low intrusion, ip_adaptation: guide"
    )

    assert "generation_world_profile" not in prompt
    assert "story_constraints" not in prompt
    assert "ip_integration_guidance" not in prompt
    assert "ip_adaptation" not in prompt
    assert "city" in prompt
    assert "protect gate" in prompt


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_plans_ip_after_storyboard_and_style_resolution(monkeypatch):
    planner_calls = {}

    async def fake_generate_image_prompts(*args, **kwargs):
        planner_calls["prompt_contexts"] = kwargs["prompt_contexts"]
        return ["正定长乐门晨光画面，白色兔子自然陪伴在城墙边。"]

    plan = _storyboard_plan()

    class _Planner:
        def __init__(self, *args, **kwargs):
            pass
        async def plan_batch(self, **kwargs):
            planner_calls["resolved_style"] = kwargs["resolved_style"]
            planner_calls["storyboard_plan"] = kwargs["storyboard_plan"]
            planner_calls["scene_casts_by_frame"] = kwargs["scene_casts_by_frame"]
            planner_calls["generation_world_profile"] = kwargs["generation_world_profile"]
            return [
                type(
                    "Pkg",
                    (),
                    {
                        "frame_id": plan.frames[0].frame_id,
                        "to_dict": lambda self: {
                            "frame_id": plan.frames[0].frame_id,
                            "ip_presence_type": "scene_integrated",
                            "presence_mode": "support",
                            "image_text_plan": {
                                "summary_text": "从长乐门出发",
                                "visible_text_whitelist": ["从长乐门出发", "长乐门"],
                            },
                            "negative_constraints": ["避免角色贴纸感"],
                        },
                    },
                )()
            ]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.IPFrameAppearancePlanner",
        _Planner,
    )

    async def fake_resolve_style_spec(*args, **kwargs):
        return _resolved_ip_world()

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )

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
                        world_elements=("长乐门",),
                        prompt_intent="建立古城空间",
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
        "pixelle_video.utils.content_generators.plan_storyboard_batch",
        fake_plan_storyboard_batch,
    )

    class _WorldPlanner:
        async def plan(self, **kwargs):
            return ContentWorldProfile(
                summary="正定古城清晨漫游",
                story_constraints="不能替代长乐门",
                ip_integration_guidance="IP 作为低侵入陪伴式向导",
            )

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.ContentWorldPlanner",
        lambda: _WorldPlanner(),
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["从长乐门出发。"],
        image_config={"prompt_prefix": "古城旅行纪录片风格"},
        storyboard_plan=plan,
        world_preset_id="neutral_knowledge_storyboard",
        generation_world_hint="古城清晨漫游，低侵入陪伴。",
        ip_enabled=True,
        ip_profile=_ip_profile(),
        scene_casts_by_frame={"frame_1": {"ip_presence_type": "scene_integrated"}},
    )

    assert planner_calls["resolved_style"] is not None
    assert planner_calls["storyboard_plan"] is plan
    assert planner_calls["scene_casts_by_frame"] == {"frame_1": {"ip_presence_type": "scene_integrated"}}
    assert planner_calls["generation_world_profile"].summary == "正定古城清晨漫游"
    assert isinstance(planner_calls["prompt_contexts"], PromptContextEnvelope)
    assert (
        planner_calls["prompt_contexts"].frame_contexts[0]["ip_adaptation"]["ip_presence_type"]
        == "scene_integrated"
    )
    assert "ip_presence_options" in planner_calls["prompt_contexts"].frame_contexts[0]
    assert "style_context" in planner_calls["prompt_contexts"].frame_contexts[0]
    assert result.planning_snapshot["ip_adaptations_by_frame"][plan.frames[0].frame_id][
        "ip_presence_type"
    ] == "scene_integrated"


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_never_leaks_hex_codes_or_field_names(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["summary_text: 从长乐门出发，title_hex: #5A2A12，白色兔子。"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["从长乐门出发。"],
        image_config={},
        prompt_contexts=[
            {
                "frame_source_text": "从长乐门出发。",
                "ip_adaptation": {
                    "identity_color_terms": ["纯白色身体", "鲜明宝蓝色领带"],
                    "image_text_plan": {
                        "summary_text": "从长乐门出发",
                        "visible_text_whitelist": ["从长乐门出发"],
                    },
                },
            }
        ],
    )

    assert "#5A2A12" not in result.prompts[0]
    assert "summary_text" not in result.prompts[0]
    assert "title_hex" not in result.prompts[0]


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_uses_visible_text_whitelist_for_ip_text_plan(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["Changle Gate wall with white guide rabbit."]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    plan = _storyboard_plan()

    class _Planner:
        def __init__(self, *args, **kwargs):
            pass
        async def plan_batch(self, **kwargs):
            return [
                type(
                    "Pkg",
                    (),
                    {
                        "frame_id": plan.frames[0].frame_id,
                        "to_dict": lambda self: {
                            "frame_id": plan.frames[0].frame_id,
                            "ip_presence_type": "scene_integrated",
                            "image_text_plan": {
                                "summary_text": "Start from Changle Gate",
                                "scene_text": ["Changle Gate"],
                                "visible_text_whitelist": ["Start from Changle Gate", "Changle Gate"],
                            },
                        },
                    },
                )()
            ]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.IPFrameAppearancePlanner",
        _Planner,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["Start from Changle Gate."],
        image_config={},
        storyboard_plan=plan,
        ip_enabled=True,
        ip_profile=_ip_profile(),
    )

    assert "Start from Changle Gate" in result.prompts[0]
    assert "Changle Gate" in result.prompts[0]
    assert "only whitelisted text" in result.prompts[0].lower()
    assert "no visible text" not in result.prompts[0]


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
        captured["prompt_language"] = kwargs["prompt_language"]
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
        prompt_language="zh_CN",
        prompt_prefix="Angry Birds style",
        text_rendering=_suppress_image_text(),
    )

    assert captured["style_profile"]["style_kind"] == "ip_world"
    assert captured["prompt_language"] == "zh_CN"
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
        captured["prompt_language"] = kwargs["prompt_language"]
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
        prompt_language="zh_CN",
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
    assert captured["planner_kwargs"]["prompt_language"] == "zh_CN"
    assert captured["planner_kwargs"]["shot_strategy"] == "strict"
    assert captured["prompt_language"] == "zh_CN"
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
async def test_generate_styled_image_prompt_batch_builds_generation_world_profile(monkeypatch):
    captured = {}

    class FakePlanner:
        async def plan(self, **kwargs):
            captured["world_planner_kwargs"] = kwargs
            return ContentWorldProfile(
                summary="正定古城清晨漫游",
                story_constraints="不能替代长乐门",
                ip_integration_guidance="IP 作为陪伴式向导",
                hint_source=ContentWorldHintSource.MANUAL,
            )

    async def fake_plan_storyboard_batch(**kwargs):
        captured["storyboard_kwargs"] = kwargs
        return type(
            "PlanResult",
            (),
            {
                "frames": (
                    FramePlan(
                        scene_id="scene-1",
                        shot_type="medium_shot",
                        shot_purpose="context",
                        world_elements=("青砖城墙",),
                        prompt_intent="建立古城漫游开篇",
                    ),
                ),
                "planning_snapshot": {
                    "world_preset_id": "neutral_knowledge_storyboard",
                    "world_preset": {
                        "display_name": "Neutral Knowledge Storyboard",
                    },
                },
            },
        )()

    async def fake_generate_image_prompts(*args, **kwargs):
        captured["image_contexts"] = kwargs["prompt_contexts"]
        return ["base prompt"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.ContentWorldPlanner",
        lambda: FakePlanner(),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.plan_storyboard_batch",
        fake_plan_storyboard_batch,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["从长乐门出发，这是正定的南大门。"],
        image_config={},
        world_preset_id="neutral_knowledge_storyboard",
        generation_world_hint="古城清晨漫游，IP 是陪伴式向导。",
        text_rendering=_suppress_image_text(),
    )

    assert captured["world_planner_kwargs"]["generation_world_hint"] == "古城清晨漫游，IP 是陪伴式向导。"
    assert captured["storyboard_kwargs"]["generation_world_profile"].summary == "正定古城清晨漫游"
    assert captured["image_contexts"].plan_context["generation_world_profile"]["summary"] == "正定古城清晨漫游"
    assert result.planning_snapshot["generation_world_profile"]["summary"] == "正定古城清晨漫游"
    assert result.planning_snapshot["generation_world_hint"] == "古城清晨漫游，IP 是陪伴式向导。"
    assert result.planning_snapshot["generation_world_hint_source"] == "manual"


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_passes_generation_world_profile_to_real_prompt_builder(
    monkeypatch,
):
    captured = {}

    class _WorldPlanner:
        async def plan(self, **kwargs):
            return ContentWorldProfile(
                summary="正定古城清晨漫游",
                story_constraints="不能替代长乐门",
                ip_integration_guidance="IP 作为低侵入陪伴式向导",
                hint_source=ContentWorldHintSource.MANUAL,
            )

    async def fake_llm_service(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return type("Resp", (), {"image_prompts": ["base scene prompt"]})()

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.ContentWorldPlanner",
        lambda: _WorldPlanner(),
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=fake_llm_service,
        narrations=["从长乐门出发，这是正定的南大门。"],
        image_config={},
        generation_world_hint="古城清晨漫游，IP 是陪伴式向导。",
        text_rendering=_suppress_image_text(),
    )

    assert "generation_world_profile" in captured["prompt"]
    assert "正定古城清晨漫游" in captured["prompt"]
    assert result.planning_snapshot["generation_world_profile"]["summary"] == "正定古城清晨漫游"


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_passes_prompt_contexts_to_storyboard_planner(monkeypatch):
    captured = {}
    prompt_contexts = [
        {
            "plan_source_text": "Full script with connected ideas.",
            "frame_source_text": "First idea in the connected script.",
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

    planner_contexts = captured["planner_kwargs"]["prompt_contexts"]
    assert isinstance(planner_contexts, PromptContextEnvelope)
    assert planner_contexts.plan_context["plan_source_text"] == "Full script with connected ideas."
    assert "plan_source_text" not in planner_contexts.frame_contexts[0]
    assert planner_contexts.frame_contexts[0]["visual_goal"] == "Show the first idea as part of the whole story."


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

    class FailWorldPlanner:
        async def plan(self, **kwargs):
            raise AssertionError("world planner should not run without world signals")

    async def fake_generate_image_prompts(*args, **kwargs):
        return ["base scene prompt"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.ContentWorldPlanner",
        lambda: FailWorldPlanner(),
    )
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
                "visual_goal": "Show idea one.",
                "prompt_intent": "Visual metaphor one.",
            }
        ],
        image_config={"prompt_prefix": "", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
    )

    assert isinstance(captured["prompt_contexts"], PromptContextEnvelope)
    assert captured["prompt_contexts"].frame_contexts == (
        {
            "visual_goal": "Show idea one.",
            "prompt_intent": "Visual metaphor one.",
        },
    )
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

    assert [_progress_message_key(message) for _, _, message in progress_events] == [
        "progress.detail.style_resolution",
        "progress.detail.storyboard_planning",
        "base_prompt_generation",
        "progress.detail.prompt_assembly",
    ]
