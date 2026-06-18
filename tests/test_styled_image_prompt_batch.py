import pytest

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.content_world import ContentWorldHintSource, ContentWorldProfile
from pixelle_video.models.llm_interaction_trace import LLMTraceContext, LLMTraceRecordingError
from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.storyboard_planning import FramePlan
from pixelle_video.models.style_resolution import ResolvedStyleSpec, StyleSourceSpec
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch
from pixelle_video.utils.prompt_helper import (
    apply_no_text_policy,
    sanitize_visual_prompt_text,
)


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


def _assert_old_storyboard_block_tokens_absent(prompt: str, *tokens: str) -> None:
    assert "Neutral Knowledge Storyboard" not in prompt
    for token in tokens:
        assert token not in prompt


def _assert_final_prompt_contract(prompt: str, scene_fragment: str) -> None:
    assert prompt.startswith("[Scene] ")
    assert scene_fragment in prompt
    assert "[Composition]" in prompt
    assert "[Style Assignment]" in prompt
    assert "[Character Layer Style]" in prompt
    assert "[World Layer Style]" in prompt
    assert "[Integration and Priority]" in prompt


def _assert_final_prompt_snapshot(snapshot: dict | None) -> None:
    assert snapshot is not None
    assert "base_visual_briefs_by_frame" in snapshot
    assert "visual_anchor_placement_by_frame" in snapshot
    assert snapshot["final_visual_prompt_template"]["prompt_id"] == "final_visual_prompt"


def _skip_series_visual_signature_anchor_planning(monkeypatch) -> None:
    async def fake_plan_batch(self, **kwargs):
        return ()

    def fake_plan_failed_frames(self, **kwargs):
        return ()

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_planning_service.VisualAnchorIntegrationPlanner.plan_batch",
        fake_plan_batch,
    )
    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_planning_service.VisualSignatureFallbackPlanner.plan_failed_frames",
        fake_plan_failed_frames,
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
        series_visual_signature_profile_id="ip_main",
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
        series_visual_signature_profile_id="ip_main",
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
        series_visual_signature_enabled=False,
        ip_profile=None,
        scene_casts_by_frame=None,
        text_rendering=_suppress_image_text(),
    )

    _assert_final_prompt_contract(result.prompts[0], "base scene prompt")
    assert "no visible text" in result.prompts[0]
    _assert_final_prompt_snapshot(result.planning_snapshot)


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_records_prompt_generation_trace_refs_by_index(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        await kwargs["trace_recorder"].record_interaction(
            context=LLMTraceContext(
                workspace_id="workspace_1",
                task_id="task_1",
                operation="visual_prompt_planning",
                stage="image_prompt_batch",
                metadata={
                    "batch_index": 1,
                    "batch_start_index": 0,
                    "batch_size": 2,
                },
            ),
            provider="fake",
            model="fake-model",
            request_payload={"prompt": "request"},
            response_payload={"image_prompts": ["base one", "base two"]},
            status="success",
        )
        return ["base one", "base two"]

    class _FakeTraceRecorder:
        async def record_interaction(self, **kwargs):
            return type(
                "Trace",
                (),
                {
                    "trace_id": "trace_image_prompt_batch_1",
                    "context": kwargs["context"],
                    "status": kwargs["status"],
                },
            )()

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
        narrations=["scene one", "scene two"],
        image_config={},
        trace_context=LLMTraceContext(
            workspace_id="workspace_1",
            task_id="task_1",
            operation="visual_prompt_planning",
        ),
        trace_recorder=_FakeTraceRecorder(),
    )

    assert result.planning_snapshot["prompt_generation_trace_refs_by_index"] == [
        {
            "prompt_index": 0,
            "trace_id": "trace_image_prompt_batch_1",
            "stage": "image_prompt_batch",
        },
        {
            "prompt_index": 1,
            "trace_id": "trace_image_prompt_batch_1",
            "stage": "image_prompt_batch",
        },
    ]


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_records_upstream_llm_trace_refs(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        await kwargs["trace_recorder"].record_interaction(
            context=LLMTraceContext(
                workspace_id="workspace_1",
                task_id="task_1",
                operation="visual_prompt_planning",
                stage="image_prompt_batch",
                metadata={"batch_start_index": 0, "batch_size": 1},
            ),
            provider="fake",
            model="fake-model",
            request_payload={"prompt": "request"},
            response_payload={"image_prompts": ["base one"]},
            status="success",
        )
        return ["base one"]

    class _FakeTraceRecorder:
        def __init__(self):
            self.count = 0

        async def record_interaction(self, **kwargs):
            self.count += 1
            return type(
                "Trace",
                (),
                {
                    "trace_id": f"trace_{self.count}",
                    "context": kwargs["context"],
                    "status": kwargs["status"],
                },
            )()

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={},
        upstream_llm_trace_refs=[
            {"trace_id": "trace_narration_1", "stage": "api_narration_generation"}
        ],
        trace_context=LLMTraceContext(
            workspace_id="workspace_1",
            task_id="task_1",
            operation="visual_prompt_planning",
        ),
        trace_recorder=_FakeTraceRecorder(),
    )

    assert result.planning_snapshot["llm_trace_refs"] == [
        {"trace_id": "trace_narration_1", "stage": "api_narration_generation"},
        {"trace_id": "trace_1", "stage": "image_prompt_batch"},
    ]


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

    prompt = result.prompts[0]
    _assert_final_prompt_contract(
        prompt,
        "rounded geometric dog sprinting across playful wooden obstacles",
    )
    assert "rounded geometric cartoon forms" in prompt
    assert "destructible wooden obstacles" in prompt
    assert "all frames belong to the same playful bird universe" in prompt
    assert "no visible text" in prompt
    assert "Angry Birds style" not in result.prompts[0]
    assert result.negative_prompt is not None
    assert "photo realism" in prompt
    assert "realistic fur" in prompt
    assert "text" in result.negative_prompt
    assert "Chinese characters" in result.negative_prompt


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_stops_when_style_resolution_fails(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        raise AssertionError("image prompt generation should not run after style resolution fails")

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

    with pytest.raises(RuntimeError, match="resolver boom"):
        await generate_styled_image_prompt_batch(
            llm_service=object(),
            narrations=["scene one"],
            image_config={
                "prompt_prefix": "flat illustration",
                "prompt_prefix_library": {"active_prefix_id": None, "items": []},
            },
            media_service=None,
            prompt_prefix="flat illustration",
            text_rendering=_suppress_image_text(),
        )


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_propagates_style_trace_recording_failure(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        raise AssertionError("image prompt generation should not run after trace failure")

    async def fake_resolve_style_spec(*args, **kwargs):
        raise LLMTraceRecordingError("style trace store down")

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )

    with pytest.raises(LLMTraceRecordingError, match="style trace store down"):
        await generate_styled_image_prompt_batch(
            llm_service=object(),
            narrations=["scene one"],
            image_config={
                "prompt_prefix": "flat illustration",
                "prompt_prefix_library": {"active_prefix_id": None, "items": []},
            },
            media_service=None,
            prompt_prefix="flat illustration",
            text_rendering=_suppress_image_text(),
        )


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_uses_structured_style_when_template_missing(monkeypatch):
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

    prompt = result.prompts[0]
    _assert_final_prompt_contract(prompt, "base scene prompt")
    assert "rounded geometric cartoon forms" in prompt
    assert "destructible wooden obstacles" in prompt
    assert "all frames belong to the same playful bird universe" in prompt
    assert "Angry Birds style" not in prompt
    assert prompt == apply_no_text_policy(prompt)


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

    prompt = result.prompts[0]
    _assert_final_prompt_contract(prompt, "base scene prompt")
    assert "rounded geometric cartoon forms" in prompt
    assert "all frames belong to the same playful bird universe" in prompt
    assert "no visible text" in prompt
    assert "photo realism" in prompt
    assert "realistic fur" in prompt
    assert result.negative_prompt is None


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_appends_no_text_policy_when_negative_prompt_unsupported(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["base scene prompt"]

    async def fake_resolve_style_spec(*args, **kwargs):
        return ResolvedStyleSpec(
            style_kind="visual_only",
            prompt_template="flat illustration treatment: {prompt}",
            negative_prompt="",
            style_profile={
                "style_kind": "visual_only",
                "subject_policy": "preserve_subject_semantics",
                "shape_language": "flat geometry",
                "material": "matte illustration",
                "palette": "warm muted colors",
                "lighting": "soft studio light",
                "world_elements": "",
                "consistency_anchor": "flat illustration treatment",
                "negative_rules": "",
            },
            content_hash="hash-flat",
            resolver_version="2026-04-21-v1",
            source_identity="request:hash-flat",
            raw_content="flat illustration",
        )

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
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
            series_visual_signature_enabled=True,
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
                        "appearance_description": "",
                        "negative_constraints": ("avoid extra text", "avoid sticker-like IP"),
                        "image_text_plan": None,
                        "to_dict": lambda self: {
                            "frame_id": plan.frames[0].frame_id,
                            "ip_presence_type": "scene_integrated",
                            "negative_constraints": ["avoid extra text", "avoid sticker-like IP"],
                            "visual_identity": "白色卡通兔子, 长耳朵",
                        },
                    },
                )()
            ]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.IPFrameAppearancePlanner",
        _Planner,
    )
    _skip_series_visual_signature_anchor_planning(monkeypatch)

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["Start from Changle Gate."],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        storyboard_plan=plan,
        series_visual_signature_enabled=True,
        ip_profile=_ip_profile(),
    )

    assert result.negative_prompt is None
    assert "avoid extra text" in result.prompts[0]
    assert "avoid sticker-like IP" in result.prompts[0]


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_merges_per_frame_ip_negative_into_batch_negative_prompt(monkeypatch):
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
                        "appearance_description": "",
                        "negative_constraints": ("avoid frame one sticker",),
                        "image_text_plan": None,
                        "to_dict": lambda self: {
                            "frame_id": plan.frames[0].frame_id,
                            "ip_presence_type": "scene_integrated",
                            "negative_constraints": ["avoid frame one sticker"],
                            "visual_identity": "白色卡通兔子, 长耳朵",
                        },
                    },
                )(),
                type(
                    "Pkg",
                    (),
                    {
                        "frame_id": plan.frames[1].frame_id,
                        "appearance_description": "",
                        "negative_constraints": ("avoid frame two mascot",),
                        "image_text_plan": None,
                        "to_dict": lambda self: {
                            "frame_id": plan.frames[1].frame_id,
                            "ip_presence_type": "scene_integrated",
                            "negative_constraints": ["avoid frame two mascot"],
                            "visual_identity": "白色卡通兔子, 长耳朵",
                        },
                    },
                )(),
            ]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.IPFrameAppearancePlanner",
        _Planner,
    )
    _skip_series_visual_signature_anchor_planning(monkeypatch)

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["frame one", "frame two"],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_flux.json",
        storyboard_plan=plan,
        series_visual_signature_enabled=True,
        ip_profile=_ip_profile(),
        text_rendering=_suppress_image_text("letters"),
    )

    assert result.negative_prompt is not None
    assert "photo realism" in result.negative_prompt
    assert "letters" in result.negative_prompt
    assert "avoid frame one sticker" in result.negative_prompt
    assert "avoid frame two mascot" in result.negative_prompt


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
                        "appearance_description": "",
                        "negative_constraints": ("avoid IP sticker",),
                        "image_text_plan": type(
                            "ITP", (),
                            {
                                "to_dict": lambda self: {
                                    "summary_text": None,
                                    "scene_text": [],
                                    "visible_text_whitelist": ["Changle Gate"],
                                    "text_safety_rules": [],
                                },
                            },
                        )(),
                        "to_dict": lambda self: {
                            "frame_id": plan.frames[0].frame_id,
                            "ip_presence_type": "scene_integrated",
                            "negative_constraints": ["avoid IP sticker"],
                            "visual_identity": "白色卡通兔子, 长耳朵",
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
    _skip_series_visual_signature_anchor_planning(monkeypatch)

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["frame one"],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        storyboard_plan=plan,
        series_visual_signature_enabled=True,
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

    captured_contexts = {}

    async def capturing_generate_image_prompts(*args, **kwargs):
        captured_contexts["prompt_contexts"] = kwargs.get("prompt_contexts")
        return ["Zhengding gate prompt"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        capturing_generate_image_prompts,
    )
    _skip_series_visual_signature_anchor_planning(monkeypatch)

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["IP主角登场，白色卡通兔子引导观众探索古城。"],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        storyboard_plan=plan,
        series_visual_signature_enabled=True,
        ip_profile=IPProfile(
            series_visual_signature_profile_id="ip_main",
            workspace_id="workspace_1",
            project_id="project_1",
            name="正定向导兔",
            identity_lock=("白色卡通兔子", "长耳朵"),
            identity_anchors=("蓝色领带",),
            semantic_boundary=("不能替代历史建筑",),
            negative_constraints=("避免画成普通人类讲解者",),
        ),
    )

    # Verify ip_scene_description is set in prompt context (pre-integrated, not post-appended)
    ctx_envelope = captured_contexts.get("prompt_contexts")
    if ctx_envelope is not None and hasattr(ctx_envelope, "frame_contexts"):
        fc = ctx_envelope.frame_contexts[0]
        assert "ip_scene_description" in fc
        assert "白色卡通兔子" in fc["ip_scene_description"]

    # Negative constraints still flow through system-level post-processing
    final_prompt = result.prompts[0]
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
        series_visual_signature_enabled=False,
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
    _assert_final_prompt_snapshot(result.planning_snapshot)
    assert "ip_adaptations_by_frame" not in result.planning_snapshot


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
    _skip_series_visual_signature_anchor_planning(monkeypatch)

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["frame one"],
        image_config={},
        media_type="video",
        storyboard_plan=_storyboard_plan(),
        series_visual_signature_enabled=True,
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
        "ip_integration_guidance: low intrusion"
    )

    assert "generation_world_profile" not in prompt
    assert "story_constraints" not in prompt
    assert "ip_integration_guidance" not in prompt
    assert "city" in prompt
    assert "protect gate" in prompt


def test_sanitize_visual_prompt_text_removes_expanded_ip_internal_keys():
    prompt = sanitize_visual_prompt_text(
        "ip_adaptation: white rabbit guide, "
        "identity_anchors_visible: blue tie, "
        "identity_anchors_suppressed: plastic mascot duplicate, "
        "generation_world_profile: morning market, "
        "semantic_reason: keeps character continuity, "
        "image_text_plan: hand-painted wayfinding sign, "
        "must_not_replace: white rabbit guide, "
        "title_hex: #FFFFFF"
    )

    assert "ip_adaptation" not in prompt
    assert "identity_anchors_visible" not in prompt
    assert "identity_anchors_suppressed" not in prompt
    assert "generation_world_profile" not in prompt
    assert "semantic_reason" not in prompt
    assert "image_text_plan" not in prompt
    assert "must_not_replace" not in prompt
    assert "#FFFFFF" not in prompt
    assert "white rabbit guide" in prompt
    assert "blue tie" in prompt
    assert "morning market" in prompt


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
                        "appearance_description": "白色卡通兔子作为场景中的陪伴角色，低侵入融入画面",
                        "negative_constraints": ("避免角色贴纸感",),
                        "image_text_plan": type(
                            "ITP", (),
                            {
                                "to_dict": lambda self: {
                                    "summary_text": "从长乐门出发",
                                    "scene_text": [],
                                    "visible_text_whitelist": ["从长乐门出发", "长乐门"],
                                    "text_safety_rules": [],
                                },
                            },
                        )(),
                        "to_dict": lambda self: {
                            "frame_id": plan.frames[0].frame_id,
                            "ip_presence_type": "scene_integrated",
                            "presence_mode": "support",
                            "visual_identity": "白色卡通兔子, 长耳朵",
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
    _skip_series_visual_signature_anchor_planning(monkeypatch)

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["从长乐门出发。"],
        image_config={"prompt_prefix": "古城旅行纪录片风格"},
        prompt_prefix="structured test style",
        storyboard_plan=plan,
        world_preset_id="neutral_knowledge_storyboard",
        generation_world_hint="古城清晨漫游，低侵入陪伴。",
        series_visual_signature_enabled=True,
        ip_profile=_ip_profile(),
        scene_casts_by_frame={"frame_1": {"ip_presence_type": "scene_integrated"}},
    )

    assert planner_calls["resolved_style"] is not None
    assert planner_calls["storyboard_plan"] is plan
    assert planner_calls["scene_casts_by_frame"] == {"frame_1": {"ip_presence_type": "scene_integrated"}}
    assert planner_calls["generation_world_profile"].summary == "正定古城清晨漫游"
    assert isinstance(planner_calls["prompt_contexts"], PromptContextEnvelope)
    assert (
        "白色卡通兔子"
        in planner_calls["prompt_contexts"].frame_contexts[0].get("ip_scene_description", "")
    )
    assert isinstance(
        planner_calls["prompt_contexts"].frame_contexts[0].get("ip_negative_constraints"),
        list,
    )
    assert "style_context" in planner_calls["prompt_contexts"].frame_contexts[0]
    assert result.planning_snapshot["ip_adaptations_by_frame"][plan.frames[0].frame_id][
        "ip_presence_type"
    ] == "scene_integrated"


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_never_leaks_hex_codes_or_field_names(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return [
            "summary_text: white rabbit guide, title_hex: #5A2A12, "
            "identity_anchors_visible: blue tie, "
            "identity_anchors_suppressed: plastic mascot duplicate, "
            "generation_world_profile: morning market, "
            "semantic_reason: keeps character continuity, "
            "image_text_plan: hand-painted wayfinding sign, "
            "must_not_replace: white rabbit guide, "
            "ip_adaptation: natural guide pose"
        ]

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
    assert "identity_anchors_visible" not in result.prompts[0]
    assert "identity_anchors_suppressed" not in result.prompts[0]
    assert "generation_world_profile" not in result.prompts[0]
    assert "semantic_reason" not in result.prompts[0]
    assert "image_text_plan" not in result.prompts[0]
    assert "must_not_replace" not in result.prompts[0]
    assert "ip_adaptation" not in result.prompts[0]
    assert "white rabbit guide" in result.prompts[0]
    assert "blue tie" in result.prompts[0]
    assert "morning market" in result.prompts[0]


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
                        "appearance_description": "",
                        "negative_constraints": (),
                        "image_text_plan": type(
                            "ITP", (),
                            {
                                "to_dict": lambda self: {
                                    "summary_text": "Start from Changle Gate",
                                    "scene_text": ["Changle Gate"],
                                    "visible_text_whitelist": ["Start from Changle Gate", "Changle Gate"],
                                    "text_safety_rules": [],
                                },
                            },
                        )(),
                        "to_dict": lambda self: {
                            "frame_id": plan.frames[0].frame_id,
                            "ip_presence_type": "scene_integrated",
                            "visual_identity": "白色卡通兔子, 长耳朵",
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
    _skip_series_visual_signature_anchor_planning(monkeypatch)

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["Start from Changle Gate."],
        image_config={},
        storyboard_plan=plan,
        series_visual_signature_enabled=True,
        ip_profile=_ip_profile(),
        text_rendering={
            "image_text": {
                "suppress_embedded_text": True,
                "positive_prompt": "render only approved gate lettering",
            }
        },
    )

    assert "Start from Changle Gate" in result.prompts[0]
    assert "Changle Gate" in result.prompts[0]
    assert "only whitelisted text" in result.prompts[0].lower()
    assert "render only approved gate lettering" in result.prompts[0]
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
    prompt = result.prompts[0]
    _assert_final_prompt_contract(
        prompt,
        "dynamic dog sprinting through playful wooden obstacles",
    )
    assert "no visible text" in prompt


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
    prompt = result.prompts[0]
    _assert_final_prompt_contract(prompt, "base scene prompt")
    assert "clean educational illustration" in prompt
    assert "strategy board" in prompt
    assert "no visible text" in prompt
    _assert_old_storyboard_block_tokens_absent(prompt, "medium_shot")


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
async def test_generate_styled_image_prompt_batch_storyboard_stops_when_style_resolution_fails(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        raise AssertionError("image prompt generation should not run after style resolution fails")

    async def fake_plan_storyboard_batch(**kwargs):
        raise AssertionError("storyboard planning should not run after style resolution fails")

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

    with pytest.raises(RuntimeError, match="resolver boom"):
        await generate_styled_image_prompt_batch(
            llm_service=object(),
            narrations=["scene one"],
            image_config={
                "prompt_prefix": "flat illustration",
                "prompt_prefix_library": {"active_prefix_id": None, "items": []},
            },
            prompt_prefix="flat illustration",
            world_preset_id="neutral_knowledge_storyboard",
            text_rendering=_suppress_image_text(),
        )


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

    prompt = result.prompts[0]
    _assert_final_prompt_contract(prompt, "base scene prompt")
    assert "clean educational illustration" in prompt
    assert "editorial line art treatment" in prompt
    assert "etched crosshatching" in prompt
    assert "close up" in prompt
    assert "detail focus" in prompt
    assert "lab bench" in prompt
    assert "no visible text" in prompt
    _assert_old_storyboard_block_tokens_absent(
        prompt,
        "close_up",
        "detail_focus",
    )


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_uses_resolved_style_when_storyboard_controls_disabled(monkeypatch):
    async def fail_plan_storyboard_batch(**kwargs):
        raise AssertionError("storyboard planner should not run without storyboard controls")

    class FailWorldPlanner:
        async def plan(self, **kwargs):
            raise AssertionError("world planner should not run without world signals")

    async def fake_generate_image_prompts(*args, **kwargs):
        assert kwargs["style_profile"]["style_kind"] == "visual_only"
        return ["base scene prompt"]

    async def fake_resolve_style_spec(*args, **kwargs):
        return ResolvedStyleSpec(
            style_kind="visual_only",
            prompt_template="flat illustration treatment: {prompt}",
            negative_prompt="",
            style_profile={
                "style_kind": "visual_only",
                "subject_policy": "preserve_subject_semantics",
                "shape_language": "flat geometry",
                "material": "matte illustration",
                "palette": "warm muted colors",
                "lighting": "soft studio light",
                "world_elements": "",
                "consistency_anchor": "flat illustration treatment",
                "negative_rules": "",
            },
            content_hash="hash-flat",
            resolver_version="2026-04-21-v1",
            source_identity="request:hash-flat",
            raw_content="flat illustration",
        )

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
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={"prompt_prefix": "flat illustration", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        prompt_prefix="flat illustration",
        text_rendering=_suppress_image_text(),
    )

    prompt = result.prompts[0]
    _assert_final_prompt_contract(prompt, "base scene prompt")
    assert "flat geometry" in prompt
    assert "matte illustration" in prompt
    assert "warm muted colors" in prompt
    assert "soft studio light" in prompt
    assert "flat illustration treatment" in prompt
    assert "no visible text" in prompt
    _assert_final_prompt_snapshot(result.planning_snapshot)


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
    assert "base scene prompt" in result.prompts[0]
    _assert_final_prompt_snapshot(result.planning_snapshot)


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
