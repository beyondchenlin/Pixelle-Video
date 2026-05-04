import pytest

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.services.image_prompt_composer import ImagePromptComposer


def _plan():
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text="第一句。第二句。",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="第一句。",
                visual_goal="Show idea one.",
                prompt_intent="Visual metaphor one.",
                source_start=0,
                source_end=4,
            ),
            StoryboardPlanFrame(
                index=2,
                source_text="第二句。",
                visual_goal="Show idea two.",
                prompt_intent="Visual metaphor two.",
                source_start=4,
                source_end=8,
            ),
        ],
    )


def _ip_profile():
    return IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="Zhengding guide",
        identity_lock=("white rabbit mascot", "long ears"),
        identity_anchors=("blue tie",),
        variable_slots=("action", "expression", "position"),
        semantic_boundary=("must not replace historic architecture",),
        negative_constraints=("avoid sticker-like character",),
        visible_text_whitelist=("Changle Gate",),
    )


@pytest.mark.asyncio
async def test_composer_generates_one_prompt_per_plan_frame(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured.update(kwargs)
        return type(
            "Batch",
            (),
            {
                "prompts": ["prompt one", "prompt two"],
                "resolved_style": None,
                "negative_prompt": None,
                "planning_snapshot": {"frames": [{"scene_id": "1"}, {"scene_id": "2"}]},
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    result = await ImagePromptComposer().compose(
        llm_service=object(),
        storyboard_plan=_plan(),
        image_config={},
        prompt_prefix="clean style",
        prompt_language="zh_CN",
    )

    assert captured["narrations"] == ["第一句。", "第二句。"]
    assert captured["prompt_language"] == "zh_CN"
    plan = _plan()
    prompt_contexts = captured["prompt_contexts"]
    assert isinstance(prompt_contexts, PromptContextEnvelope)
    assert prompt_contexts.plan_context["plan_source_text"] == plan.source_text
    assert "plan_source_text" not in prompt_contexts.frame_contexts[0]
    assert prompt_contexts.frame_contexts[0]["frame_source_text"] == plan.frames[0].source_text
    assert "narration_text" not in prompt_contexts.frame_contexts[0]
    assert prompt_contexts.frame_contexts[0]["visual_goal"] == "Show idea one."
    assert prompt_contexts.frame_contexts[1]["prompt_intent"] == "Visual metaphor two."
    assert captured["storyboard_plan"] == plan
    assert result.prompts == ["prompt one", "prompt two"]
    assert result.planning_snapshot["frames"] == [{"scene_id": "1"}, {"scene_id": "2"}]
    assert result.planning_snapshot["storyboard_generation"]["resolved_scene_count"] == 2
    assert "prompt_plan_bundle" not in result.planning_snapshot
    prompt_plan_ref = result.planning_snapshot["prompt_plan_bundle_ref"]
    assert prompt_plan_ref["storyboard_plan_id"] == plan.plan_id
    assert prompt_plan_ref["prompt_plan_count"] == 2
    prompt_plan_bundle = result.prompt_plan_bundle
    assert prompt_plan_bundle is not None
    assert prompt_plan_bundle.storyboard_plan_id == plan.plan_id
    assert [plan.frame_id for plan in prompt_plan_bundle.prompt_plans] == [
        plan.frames[0].frame_id,
        plan.frames[1].frame_id,
    ]
    assert prompt_plan_bundle.prompt_plans[0].final_prompt == "prompt one"
    assert prompt_plan_bundle.image_prompt_drafts[0].prompt_text == "prompt one"


@pytest.mark.asyncio
async def test_composer_passes_ip_controls_without_deciding_ip_adaptation(monkeypatch):
    captured = {}
    plan = _plan()
    profile = _ip_profile()
    scene_casts_by_frame = {plan.frames[0].frame_id: {"character_ids": ["char_guide"]}}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured.update(kwargs)
        return type(
            "Batch",
            (),
            {
                "prompts": ["prompt one", "prompt two"],
                "resolved_style": None,
                "negative_prompt": None,
                "planning_snapshot": {
                    "ip_adaptations_by_frame": {
                        plan.frames[0].frame_id: {
                            "ip_presence_type": "scene_integrated",
                            "image_text_plan": {
                                "summary_text": "Changle Gate",
                                "visible_text_whitelist": ["Changle Gate"],
                            },
                        }
                    }
                },
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    result = await ImagePromptComposer().compose(
        llm_service=object(),
        storyboard_plan=plan,
        image_config={},
        ip_enabled=True,
        ip_profile=profile,
        scene_casts_by_frame=scene_casts_by_frame,
    )

    assert captured["storyboard_plan"] == plan
    assert captured["ip_enabled"] is True
    assert captured["ip_profile"] == profile
    assert captured["scene_casts_by_frame"] == scene_casts_by_frame
    assert "ip_adaptation" not in captured["prompt_contexts"].frame_contexts[0]
    assert result.prompt_plan_bundle.prompt_plans[0].metadata["ip_presence_type"] == (
        "scene_integrated"
    )


@pytest.mark.asyncio
async def test_composer_rejects_ip_enabled_prompt_count_mismatch(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        return type(
            "Batch",
            (),
            {
                "prompts": ["prompt one"],
                "resolved_style": None,
                "negative_prompt": None,
                "planning_snapshot": None,
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    with pytest.raises(ValueError, match="image prompt count must match storyboard frame count"):
        await ImagePromptComposer().compose(
            llm_service=object(),
            storyboard_plan=_plan(),
            image_config={},
            ip_enabled=True,
            ip_profile=_ip_profile(),
            scene_casts_by_frame={},
        )


@pytest.mark.asyncio
async def test_composer_projects_text_rendering_to_prompt_payload(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured.update(kwargs)
        return type(
            "Batch",
            (),
            {
                "prompts": ["prompt one", "prompt two"],
                "resolved_style": None,
                "negative_prompt": None,
                "planning_snapshot": None,
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    await ImagePromptComposer().compose(
        llm_service=object(),
        storyboard_plan=_plan(),
        image_config={},
        text_rendering={
            "title_style": {"font_size": 96},
            "caption_style": {"font_size": 72},
            "overlay_style": {"position": "center"},
            "overlay": {"enabled": False},
            "image_text": {"suppress_embedded_text": True},
        },
    )

    assert captured["text_rendering"] == {
        "overlay": {"enabled": False},
        "image_text": {"suppress_embedded_text": True},
    }


@pytest.mark.asyncio
async def test_composer_rejects_prompt_count_mismatch(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        return type(
            "Batch",
            (),
            {
                "prompts": ["prompt one"],
                "resolved_style": None,
                "negative_prompt": None,
                "planning_snapshot": None,
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    with pytest.raises(ValueError, match="image prompt count must match storyboard frame count"):
        await ImagePromptComposer().compose(
            llm_service=object(),
            storyboard_plan=_plan(),
            image_config={},
        )


@pytest.mark.asyncio
async def test_composer_rejects_legacy_frame_override_identity(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        raise AssertionError("legacy override should be rejected before prompt generation")

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    with pytest.raises(ValueError, match="legacy frame override"):
        await ImagePromptComposer().compose(
            llm_service=object(),
            storyboard_plan=_plan(),
            image_config={},
            frame_overrides=[
                {
                    "scene_id": "scene-1",
                    "snapshot_identity": "snapshot-1",
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
                }
            ],
        )


@pytest.mark.asyncio
async def test_composer_rejects_non_sha256_source_digest_override(monkeypatch):
    plan = _plan()

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        raise AssertionError("malformed override should be rejected before prompt generation")

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    with pytest.raises(ValueError, match="source_digest"):
        await ImagePromptComposer().compose(
            llm_service=object(),
            storyboard_plan=plan,
            image_config={},
            frame_overrides=[
                {
                    "plan_id": plan.plan_id,
                    "plan_revision": plan.revision,
                    "frame_id": plan.frames[0].frame_id,
                    "source_digest": "z" * 64,
                    "locked_fields": ["visual_goal"],
                    "visual_goal": "Locked visual goal.",
                }
            ],
        )


@pytest.mark.asyncio
async def test_composer_applies_new_frame_override_identity_to_prompt_context(monkeypatch):
    captured = {}
    plan = _plan()
    first_frame = plan.frames[0]

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured.update(kwargs)
        return type(
            "Batch",
            (),
            {
                "prompts": ["prompt one", "prompt two"],
                "resolved_style": None,
                "negative_prompt": None,
                "planning_snapshot": {
                    "frame_overrides": list(kwargs["frame_overrides"] or []),
                },
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    await ImagePromptComposer().compose(
        llm_service=object(),
        storyboard_plan=plan,
        image_config={},
        frame_overrides=[
            {
                "plan_id": plan.plan_id,
                "plan_revision": plan.revision,
                "frame_id": first_frame.frame_id,
                "source_digest": plan.source_digest,
                "locked_fields": ["visual_goal", "prompt_intent"],
                "visual_goal": "Locked visual goal.",
                "prompt_intent": "Locked prompt intent.",
            }
        ],
    )

    assert captured["frame_overrides"] == [
        {
            "plan_id": plan.plan_id,
            "plan_revision": plan.revision,
            "frame_id": first_frame.frame_id,
            "source_digest": plan.source_digest,
            "locked_fields": ["visual_goal", "prompt_intent"],
            "visual_goal": "Locked visual goal.",
            "prompt_intent": "Locked prompt intent.",
        }
    ]
    frame_context = captured["prompt_contexts"].frame_contexts[0]
    assert frame_context["locked_fields"] == ["visual_goal", "prompt_intent"]
    assert frame_context["visual_goal"] == "Locked visual goal."
    assert frame_context["prompt_intent"] == "Locked prompt intent."


@pytest.mark.asyncio
async def test_composer_applies_source_text_override_to_frame_source_text(monkeypatch):
    captured = {}
    plan = _plan()
    first_frame = plan.frames[0]

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured.update(kwargs)
        return type(
            "Batch",
            (),
            {
                "prompts": ["prompt one", "prompt two"],
                "resolved_style": None,
                "negative_prompt": None,
                "planning_snapshot": {},
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    await ImagePromptComposer().compose(
        llm_service=object(),
        storyboard_plan=plan,
        image_config={},
        frame_overrides=[
            {
                "plan_id": plan.plan_id,
                "plan_revision": plan.revision,
                "frame_id": first_frame.frame_id,
                "source_digest": plan.source_digest,
                "locked_fields": ["source_text"],
                "source_text": "Locked source fragment.",
            }
        ],
    )

    frame_context = captured["prompt_contexts"].frame_contexts[0]
    assert captured["narrations"][0] == "Locked source fragment."
    assert frame_context["source_text"] == "Locked source fragment."
    assert frame_context["frame_source_text"] == "Locked source fragment."
