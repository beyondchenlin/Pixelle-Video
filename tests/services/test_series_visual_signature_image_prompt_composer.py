from __future__ import annotations

from types import SimpleNamespace

import pytest

from pixelle_video.models.series_visual_signature import SeriesVisualSignatureRequest
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.services import image_prompt_composer as composer_module
from pixelle_video.services.image_prompt_composer import ImagePromptComposer


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
        identity_lock=("black spots", "black sunglasses", "red collar", "small round ears"),
        minimal_traits=(),
        identity_anchors=(),
        forbidden_elements=(),
        metadata={},
    )


@pytest.mark.asyncio
async def test_prompt_composer_uses_signature_free_base_then_canonical_projection(
    monkeypatch,
) -> None:
    base_prompt = "worker beside assembly machine, neutral cinematic scene"
    captured_generation = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured_generation.update(kwargs)
        return StyledImagePromptBatch(
            prompts=[base_prompt],
            negative_prompt="low quality",
            resolved_style=None,
            planning_snapshot={
                "existing": True,
                "base_visual_briefs_by_frame": {
                    "frame-1": {
                        "main_subjects": ["worker", "assembly machine"],
                        "base_image_prompt": base_prompt,
                    }
                },
            },
        )

    monkeypatch.setattr(
        composer_module,
        "generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    request = SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "auto",
        }
    )
    result = await ImagePromptComposer().compose(
        llm_service=None,
        storyboard_plan=_storyboard_plan(),
        image_config={},
        ip_profile=_ip_profile(),
        series_visual_signature_enabled=True,
        series_visual_signature_request=request,
        visual_story_context={
            "selected_visual_route": {"route_id": "content-route"},
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
    assert "legacy_identity" not in str(generation_context)
    assert "legacy_ip_style" not in str(generation_context)
    assert "stable legacy signature" not in str(generation_context)
    assert generation_context["selected_visual_route"]["route_id"] == "content-route"

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
