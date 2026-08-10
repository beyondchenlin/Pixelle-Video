from __future__ import annotations

from types import SimpleNamespace

import pytest

from pixelle_video.models.series_visual_signature import SeriesVisualSignatureRequest
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.services import visual_prompt_composer as composer_module
from pixelle_video.services.image_prompt_composer import ImagePromptComposer
from pixelle_video.services.visual_prompt_composer import VisualPromptComposer


def _storyboard_plan() -> StoryboardPlan:
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text="A worker operates a machine.",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="A worker operates a machine.",
                visual_goal="show the production process",
                prompt_intent="explain the bottleneck",
                primary_subject="worker",
                secondary_subjects=("assembly machine",),
                frame_id="frame-1",
            )
        ],
    )


def _ip_profile():
    return SimpleNamespace(
        series_visual_signature_profile_id="dog_1",
        name="Dalmatian",
        identity_lock=(
            "black spots",
            "black sunglasses",
            "red collar",
            "small round ears",
        ),
        minimal_traits=(),
        identity_anchors=(),
        forbidden_elements=(),
        metadata={},
    )


async def _base_batch(**kwargs):
    return StyledImagePromptBatch(
        prompts=["worker beside assembly machine, neutral cinematic scene"],
        negative_prompt="low quality",
        resolved_style=None,
        planning_snapshot={
            "existing": True,
            "base_visual_briefs_by_frame": {
                "frame-1": {
                    "main_subjects": ["worker", "assembly machine"],
                    "base_image_prompt": "worker beside assembly machine, neutral cinematic scene",
                }
            },
        },
    )


def _enabled_request() -> SeriesVisualSignatureRequest:
    return SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "auto",
        }
    )


def test_image_prompt_composer_is_only_a_compatibility_alias() -> None:
    assert ImagePromptComposer is VisualPromptComposer


@pytest.mark.asyncio
async def test_prompt_composer_uses_signature_free_base_then_canonical_projection(
    monkeypatch,
) -> None:
    base_prompt = "worker beside assembly machine, neutral cinematic scene"
    captured_generation = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured_generation.update(kwargs)
        return await _base_batch(**kwargs)

    monkeypatch.setattr(
        composer_module,
        "generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    result = await VisualPromptComposer().compose(
        llm_service=None,
        storyboard_plan=_storyboard_plan(),
        image_config={},
        ip_profile=_ip_profile(),
        series_visual_signature_enabled=True,
        series_visual_signature_request=_enabled_request(),
        visual_story_context={
            "selected_visual_route": {
                "route_id": "content-route",
                "route_name": "Factory process",
                "route_type": "process_map",
                "visual_premise": "show the assembly process",
                "why_it_fits_article": "matches the factory claim",
                "recommended_ip_role": "operator",
                "ip_fit_reason": "legacy IP-specific ranking",
                "scores": {"ip_compatibility": 0.99},
            },
            "frame_visual_plans": [
                {
                    "frame_id": "frame-1",
                    "frame_index": 0,
                    "source_text": "A worker operates a machine.",
                    "local_claim": "show the production process",
                    "visual_task": "process walkthrough",
                    "visual_logic": "follow the factory route",
                    "required_subjects": ["worker", "assembly machine"],
                    "visible_text_policy": "no_visible_text",
                    "cognitive_anchor": "legacy IP anchor",
                    "physical_metaphor": "legacy IP metaphor",
                    "scene_arena": "legacy IP arena",
                    "ip_action_affordance": "legacy IP action",
                    "forbidden_ip_forms": ["sticker"],
                    "content_bound_ip_ready": True,
                }
            ],
            "frame_ip_fusion_plans": [
                {"frame_id": "frame-1", "legacy_identity": "must not reach base"}
            ],
            "visual_story_engine": {
                "selected_visual_route": {"route_id": "content-route"},
                "style_harmonization": {"legacy_ip_style": "must not reach base"},
                "channel_memory_intent": "stable legacy signature",
            },
        },
    )

    assert captured_generation["series_visual_signature_enabled"] is False
    assert captured_generation["series_visual_signature_request"] is None
    assert captured_generation["series_visual_signature_profile"] is None
    assert captured_generation["ip_profile"] is None
    assert captured_generation["scene_casts_by_frame"] is None
    generation_context = captured_generation["prompt_contexts"].frame_contexts[0]
    assert "visual_story_ip_fusion_plan" not in generation_context
    context_text = str(generation_context)
    for forbidden in (
        "legacy_identity",
        "legacy_ip_style",
        "stable legacy signature",
        "legacy IP anchor",
        "legacy IP metaphor",
        "legacy IP arena",
        "legacy IP action",
        "recommended_ip_role",
        "ip_fit_reason",
        "ip_compatibility",
    ):
        assert forbidden not in context_text
    assert generation_context["selected_visual_route"]["route_id"] == "content-route"
    frame_plan = generation_context["visual_story_frame_plan"]
    assert frame_plan["local_claim"] == "show the production process"
    assert frame_plan["required_subjects"] == ["worker", "assembly machine"]

    final_prompt = result.prompts[0]
    assert base_prompt in final_prompt
    assert "Dalmatian" in final_prompt
    assert "black spots" in final_prompt
    assert "black sunglasses" in final_prompt
    assert "red collar" in final_prompt
    assert "small round ears" in final_prompt
    assert "worker" in final_prompt
    assert "assembly machine" in final_prompt
    assert "low quality" in (result.negative_prompt or "")
    assert "recurring visual signature rendered as a watermark" in (
        result.negative_prompt or ""
    )

    snapshot = result.planning_snapshot
    assert snapshot["existing"] is True
    assert "series_visual_signature_shadow_comparison" not in snapshot
    audit = snapshot["series_visual_signature_projection_audit"]
    assert audit["all_frames_passed"] is True
    assert audit["frame_count"] == 1
    frame_audit = audit["frames"][0]
    assert frame_audit["identity_trait_count"] == 4
    assert frame_audit["final_gate_passed"] is True
    assert "positive_prompt" not in frame_audit
    assert "negative_prompt" not in frame_audit
    assert len(frame_audit["positive_prompt_sha256"]) == 64


@pytest.mark.asyncio
async def test_video_prompt_path_uses_same_canonical_visual_signature_projection(
    monkeypatch,
) -> None:
    captured_generation = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured_generation.update(kwargs)
        return await _base_batch(**kwargs)

    monkeypatch.setattr(
        composer_module,
        "generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    result = await VisualPromptComposer().compose(
        llm_service=None,
        storyboard_plan=_storyboard_plan(),
        image_config={},
        media_type="video",
        ip_profile=_ip_profile(),
        series_visual_signature_enabled=True,
        series_visual_signature_request=_enabled_request(),
    )

    assert captured_generation["media_type"] == "video"
    assert captured_generation["series_visual_signature_enabled"] is False
    assert "Dalmatian" in result.prompts[0]
    assert result.planning_snapshot[
        "series_visual_signature_projection_audit"
    ]["all_frames_passed"] is True


@pytest.mark.asyncio
async def test_explicit_disabled_canonical_request_never_falls_back_to_legacy_runtime(
    monkeypatch,
) -> None:
    captured_generation = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured_generation.update(kwargs)
        return await _base_batch(**kwargs)

    monkeypatch.setattr(
        composer_module,
        "generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    result = await VisualPromptComposer().compose(
        llm_service=None,
        storyboard_plan=_storyboard_plan(),
        image_config={},
        ip_profile=_ip_profile(),
        series_visual_signature_enabled=True,
        series_visual_signature_request=SeriesVisualSignatureRequest.disabled(),
        series_visual_signature_expression_mode="literal_character",
        series_visual_signature_structure_mode="global",
        series_visual_signature_participation_mode="mandatory",
    )

    assert result.prompts == [
        "worker beside assembly machine, neutral cinematic scene"
    ]
    assert captured_generation["series_visual_signature_enabled"] is False
    assert captured_generation["series_visual_signature_request"] is None
    assert captured_generation["ip_profile"] is None
    assert "series_visual_signature_projection_audit" not in result.planning_snapshot
