from dataclasses import replace

import pytest

from pixelle_video.models.article_concretization import (
    ArticleConcretizationRequest,
    DiagramAspectRatio,
)
from pixelle_video.models.article_understanding import (
    ArticleUnderstandingLens,
    ArticleUnderstandingPlan,
    FrameUnderstandingPlan,
    SourceEvidenceSpan,
    SubjectAnchor,
)
from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.final_visual_prompt_contract import (
    FinalVisualPromptContract,
    RenderedMediaPrompt,
)
from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.services.article_concretization_planner import (
    ArticleConcretizationPlanner,
)
from pixelle_video.services.article_concretization_resolution import (
    resolve_article_concretization,
)
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
        series_visual_signature_profile_id="ip_main",
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


def _evidence(evidence_id: str, quote: str) -> SourceEvidenceSpan:
    return SourceEvidenceSpan(
        evidence_id=evidence_id,
        source_id="article-1",
        quote=quote,
        evidence_role="core_claim",
    )


def _subject(subject_id: str, label: str, evidence_id: str) -> SubjectAnchor:
    return SubjectAnchor(
        subject_id=subject_id,
        label=label,
        source_phrase=label,
        evidence_span_ids=(evidence_id,),
        importance="primary",
        visual_presence="required",
        loss_policy="forbidden",
    )


def _article_concretization_plans(plan: StoryboardPlan):
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "cognitive_anchor_kind": "causal_mechanism",
            "explanation_diagram_grammar": "process_flow",
            "diagram_render_style": "editorial_diagram",
            "diagram_visible_text_policy": "approved_labels_only",
            "diagram_approved_labels": ["Cause", "Effect"],
            "diagram_user_intent_hint": "make the feedback loop visible",
        }
    )
    article_evidence = _evidence("article-evidence-1", plan.source_text)
    article_plan = ArticleUnderstandingPlan(
        article_id=plan.plan_id,
        primary_lens=ArticleUnderstandingLens.CAUSAL_MECHANISM,
        core_claim=plan.source_text,
        main_entities=("Cause", "Effect"),
        required_subjects=(
            _subject("article-subject-1", "Cause", article_evidence.evidence_id),
            _subject("article-subject-2", "Effect", article_evidence.evidence_id),
        ),
        source_evidence=(article_evidence,),
    )
    plans = []
    for frame in plan.frames:
        frame_evidence = _evidence(f"{frame.frame_id}-evidence", frame.source_text)
        frame_plan = FrameUnderstandingPlan(
            frame_id=frame.frame_id,
            source_text=frame.source_text,
            frame_claim=frame.visual_goal,
            frame_question=frame.prompt_intent,
            primary_lens=ArticleUnderstandingLens.CAUSAL_MECHANISM,
            required_subjects=(
                _subject(f"{frame.frame_id}-subject-1", "Cause", frame_evidence.evidence_id),
                _subject(f"{frame.frame_id}-subject-2", "Effect", frame_evidence.evidence_id),
            ),
            source_evidence=(frame_evidence,),
            visible_text_policy="free_text_allowed",
        )
        resolution = resolve_article_concretization(
            request=request,
            article_plan=article_plan,
            frame_plan=frame_plan,
            series_visual_signature_profile_id=None,
            template_aspect_ratio=DiagramAspectRatio.VERTICAL_9_16,
            strict_user_mode=False,
        )
        plans.append(
            ArticleConcretizationPlanner().plan(
                resolution=resolution,
                article_plan=article_plan,
                frame_plan=frame_plan,
                source_text=plan.source_text,
            )
        )
    return tuple(plans)


def _styled_batch(
    *,
    prompts: list[str],
    planning_snapshot: dict | None = None,
) -> StyledImagePromptBatch:
    return StyledImagePromptBatch(
        prompts=prompts,
        resolved_style=None,
        negative_prompt=None,
        planning_snapshot=planning_snapshot,
        rendered_prompts=[_rendered_prompt(prompt) for prompt in prompts],
    )


def _rendered_prompt(prompt: str) -> RenderedMediaPrompt:
    contract = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style assignment",
        character_layer_style="character layer",
        world_layer_style="world layer",
        integration_priority="priority",
    )
    return RenderedMediaPrompt(
        prompt=prompt,
        negative_prompt=None,
        prompt_contract=contract,
        renderer_id="test",
        renderer_version="v1",
    )


@pytest.mark.asyncio
async def test_composer_generates_one_prompt_per_plan_frame(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured.update(kwargs)
        return _styled_batch(
            prompts=["prompt one", "prompt two"],
            planning_snapshot={
                "frames": [{"scene_id": "1"}, {"scene_id": "2"}],
                "prompt_generation_trace_refs_by_index": [
                    {"prompt_index": 0, "trace_id": "trace_prompt_batch_1"},
                    {"prompt_index": 1, "trace_id": "trace_prompt_batch_1"},
                ],
            },
        )

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
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
    assert prompt_plan_bundle.source_trace_id == "trace_prompt_batch_1"
    assert prompt_plan_bundle.prompt_plans[0].source_trace_id == "trace_prompt_batch_1"
    assert prompt_plan_bundle.image_prompt_drafts[0].source_trace_id == "trace_prompt_batch_1"


@pytest.mark.asyncio
async def test_composer_injects_article_concretization_plans_into_prompt_contexts_and_snapshot(
    monkeypatch,
):
    captured = {}
    plan = _plan()
    article_plans = _article_concretization_plans(plan)

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured.update(kwargs)
        return _styled_batch(prompts=["prompt one", "prompt two"], planning_snapshot={})

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    result = await ImagePromptComposer().compose(
        llm_service=object(),
        storyboard_plan=plan,
        image_config={},
        article_concretization_plans=article_plans,
    )

    prompt_contexts = captured["prompt_contexts"]
    first_context = prompt_contexts.frame_contexts[0]
    assert first_context["article_concretization_plan"]["plan_id"] == (
        article_plans[0].plan_id
    )
    assert first_context["article_concretization_plan"]["diagram"]["visible_text"][
        "allowed_visible_text"
    ] == ["Cause", "Effect"]
    assert result.planning_snapshot["article_concretization_by_frame"] == {
        plan.frames[0].frame_id: article_plans[0].to_dict(),
        plan.frames[1].frame_id: article_plans[1].to_dict(),
    }


@pytest.mark.asyncio
async def test_composer_rejects_article_concretization_plan_frame_mismatch(monkeypatch):
    plan = _plan()
    article_plans = list(_article_concretization_plans(plan))
    article_plans[0] = replace(article_plans[0], frame_id="wrong-frame")

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        raise AssertionError("frame mismatch should fail before prompt generation")

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    with pytest.raises(ValueError, match="article_concretization_plans must match storyboard frame ids"):
        await ImagePromptComposer().compose(
            llm_service=object(),
            storyboard_plan=plan,
            image_config={},
            article_concretization_plans=tuple(article_plans),
        )


@pytest.mark.asyncio
async def test_composer_carries_all_upstream_llm_trace_ids_into_prompt_plan_metadata(monkeypatch):
    plan = _plan()

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        return _styled_batch(
            prompts=["prompt one", "prompt two"],
            planning_snapshot={
                "llm_trace_refs": [
                    {"trace_id": "trace_world", "stage": "content_world_planning"},
                    {"trace_id": "trace_style", "stage": "style_resolution"},
                    {"trace_id": "trace_storyboard", "stage": "storyboard_planning"},
                    {"trace_id": "trace_ip", "stage": "ip_role_selection"},
                ],
                "prompt_generation_trace_refs_by_index": [
                    {"prompt_index": 0, "trace_id": "trace_prompt_batch_1", "stage": "image_prompt_batch"},
                    {"prompt_index": 1, "trace_id": "trace_prompt_batch_1", "stage": "image_prompt_batch"},
                ],
            },
        )

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    result = await ImagePromptComposer().compose(
        llm_service=object(),
        storyboard_plan=plan,
        image_config={},
        upstream_llm_trace_refs=[
            {"trace_id": "trace_smart_storyboard", "stage": "smart_storyboard_generation"}
        ],
    )

    bundle = result.prompt_plan_bundle
    trace_ids = [ref["trace_id"] for ref in bundle.metadata["llm_trace_refs"]]
    assert trace_ids == [
        "trace_smart_storyboard",
        "trace_world",
        "trace_style",
        "trace_storyboard",
        "trace_ip",
        "trace_prompt_batch_1",
    ]
    assert bundle.prompt_plans[0].metadata["llm_trace_refs"] == bundle.metadata["llm_trace_refs"]
    assert bundle.image_prompt_drafts[0].metadata["llm_trace_refs"] == bundle.metadata["llm_trace_refs"]


@pytest.mark.asyncio
async def test_composer_passes_generation_world_hint_to_styled_batch(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured.update(kwargs)
        return _styled_batch(prompts=["prompt one", "prompt two"])

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    await ImagePromptComposer().compose(
        llm_service=object(),
        storyboard_plan=_plan(),
        image_config={},
        generation_world_hint="古城清晨漫游",
    )

    assert captured["generation_world_hint"] == "古城清晨漫游"


@pytest.mark.asyncio
async def test_composer_passes_ip_controls_without_deciding_ip_adaptation(monkeypatch):
    captured = {}
    plan = _plan()
    profile = _ip_profile()
    scene_casts_by_frame = {plan.frames[0].frame_id: {"character_ids": ["char_guide"]}}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured.update(kwargs)
        return _styled_batch(
            prompts=["prompt one", "prompt two"],
            planning_snapshot={
                "base_visual_briefs_by_frame": {
                    frame.frame_id: {
                        "main_subjects": [frame.source_text],
                        "base_image_prompt": prompt,
                    }
                    for frame, prompt in zip(
                        plan.frames,
                        ("prompt one", "prompt two"),
                    )
                }
            },
        )

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    result = await ImagePromptComposer().compose(
        llm_service=object(),
        storyboard_plan=plan,
        image_config={},
        series_visual_signature_enabled=True,
        ip_profile=profile,
        scene_casts_by_frame=scene_casts_by_frame,
    )

    assert captured["storyboard_plan"] == plan
    assert captured["series_visual_signature_enabled"] is False
    assert captured["ip_profile"] is None
    assert captured["scene_casts_by_frame"] is None
    assert "ip_scene_description" not in captured["prompt_contexts"].frame_contexts[0]
    assert "Zhengding guide" in result.prompts[0]
    assert result.planning_snapshot["visual_anchor_single_pass_prompt_policy"][
        "visual_model_call_count"
    ] == 1


@pytest.mark.asyncio
async def test_composer_rejects_series_visual_signature_enabled_prompt_count_mismatch(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        return _styled_batch(prompts=["prompt one"])

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    with pytest.raises(ValueError, match="visual prompt count must match storyboard frame count"):
        await ImagePromptComposer().compose(
            llm_service=object(),
            storyboard_plan=_plan(),
            image_config={},
            series_visual_signature_enabled=True,
            ip_profile=_ip_profile(),
            scene_casts_by_frame={},
        )


@pytest.mark.asyncio
async def test_composer_projects_text_rendering_to_prompt_payload(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured.update(kwargs)
        return _styled_batch(prompts=["prompt one", "prompt two"])

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
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
        return _styled_batch(prompts=["prompt one"])

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    with pytest.raises(ValueError, match="visual prompt count must match storyboard frame count"):
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
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
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
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
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
        return _styled_batch(
            prompts=["prompt one", "prompt two"],
            planning_snapshot={
                "frame_overrides": list(kwargs["frame_overrides"] or []),
            },
        )

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
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
        return _styled_batch(prompts=["prompt one", "prompt two"], planning_snapshot={})

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
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
