import pytest

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.series_visual_signature_request import SeriesVisualSignatureRequest
from pixelle_video.models.visual_anchor_planning import AnchorCarrierType
from pixelle_video.services.visual_prompt_planning_service import VisualPromptPlanningService


class UnprojectableSupportingLLM:
    async def __call__(self, **kwargs):
        return {
            "visual_anchor_integration_plans": [
                {
                    "frame_id": "f1",
                    "carrier_type": "minor_supporting_character",
                    "anchor_function": "co_present_support",
                    "prominence": "small_side_character",
                    "style_relation": "blended",
                    "placement": "beside the main subject",
                    "support_anchor": "main subject side",
                    "contact_relation": "near the main subject without a physical carrier",
                    "interaction_target": "main subject",
                    "occlusion_relation": "does not cover the main subject",
                    "visual_weight_clause": "visible but subordinate",
                    "image_prompt_clause": "戴黑色墨镜的斑点狗 beside the main subject",
                    "integrated_scene_prompt": "戴黑色墨镜的斑点狗 beside the main subject",
                    "integration_strategy": "supporting_integration",
                    "anchor_manifestation": {
                        "form": "small character",
                        "location": "main subject side",
                        "visibility": "clear",
                        "relationship": "near the main subject",
                    },
                    "scene_coherence_score": 8,
                    "disruption_risk": 1,
                    "identity_preservation_score": 9,
                    "reason": "looks like a side character but lacks physical scene binding",
                }
            ]
        }


@pytest.mark.asyncio
async def test_visual_prompt_planning_accepts_series_visual_signature_request_without_enabling_v4():
    result = await VisualPromptPlanningService().plan_image_prompts(
        base_prompts=("工程师讲解太阳能板发电流程",),
        frame_contexts=({"frame_id": "f1", "source_text": "太阳能发电原理"},),
        series_visual_signature_expression_mode="explanatory_diagram",
        series_visual_signature_request=SeriesVisualSignatureRequest.disabled(),
    )

    assert len(result.rendered_prompts) == 1
    assert result.rendered_prompts[0].prompt
    assert result.rendered_prompts[0].prompt_contract.metadata["ip_present"] is False
    assert result.rendered_prompts[0].prompt_contract.metadata["mandatory_ip_final_gate"]["reason"] == "not_mandatory"


@pytest.mark.asyncio
async def test_visual_prompt_planning_does_not_apply_mandatory_gate_when_anchor_is_disabled():
    result = await VisualPromptPlanningService().plan_image_prompts(
        base_prompts=("plain source-only scene",),
        frame_contexts=({"frame_id": "f1", "source_text": "plain source"},),
        visual_anchor_enabled=False,
        anchor_profile=None,
    )

    assert result.visual_anchor_plans == ()
    assert len(result.rendered_prompts) == 1
    assert result.rendered_prompts[0].prompt_contract.metadata["ip_present"] is False
    assert result.rendered_prompts[0].prompt_contract.metadata["mandatory_ip_final_gate"]["reason"] == "not_mandatory"


@pytest.mark.asyncio
async def test_visual_anchor_enabled_without_v4_request_uses_deterministic_soft_anchor_path(monkeypatch):
    planner_calls = []

    async def fake_plan_batch(self, **kwargs):
        planner_calls.append(kwargs)
        return ()

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_planning_service.VisualAnchorIntegrationPlanner.plan_batch",
        fake_plan_batch,
    )

    result = await VisualPromptPlanningService().plan_image_prompts(
        base_prompts=("base scene prompt",),
        frame_contexts=({"frame_id": "f1", "source_text": "scene source"},),
        visual_anchor_enabled=True,
        anchor_profile=IPProfile(
            series_visual_signature_profile_id="rabbit",
            workspace_id="ws",
            project_id="project",
            name="Rabbit Guide",
            identity_lock=("rabbit",),
            visual_summary="friendly guide rabbit",
        ),
        series_visual_signature_expression_mode="explanatory_diagram",
        series_visual_signature_structure_mode="workflow",
        series_visual_signature_participation_mode="guide_explainer",
    )

    assert not planner_calls
    assert len(result.visual_anchor_plans) == 1
    assert result.series_visual_signature_fallback is not None
    assert result.series_visual_signature_request is None
    assert result.series_visual_signature_plans == ()
    assert len(result.rendered_prompts) == 1


@pytest.mark.asyncio
async def test_visual_prompt_planning_repairs_unprojectable_llm_anchor_at_planner_source():
    result = await VisualPromptPlanningService().plan_image_prompts(
        base_prompts=("旅行者在桌面上查看地图，桌边和前景地面清晰可见",),
        frame_contexts=({"frame_id": "f1", "source_text": "地图发现"},),
        visual_anchor_enabled=True,
        anchor_profile=IPProfile(
            series_visual_signature_profile_id="rabbit",
            workspace_id="ws",
            project_id="project",
            name="戴黑色墨镜的斑点狗",
            identity_lock=("戴黑色墨镜的斑点狗", "黑色墨镜", "斑点狗"),
            visual_summary="戴黑色墨镜的斑点狗",
        ),
        llm_service=UnprojectableSupportingLLM(),
        series_visual_signature_mode="supporting_integration",
        series_visual_signature_consistency_mode="supporting_character",
    )

    repaired_plan = result.visual_anchor_plans[0]
    assert repaired_plan.anchor_carrier_type is AnchorCarrierType.MINOR_SUPPORTING_CHARACTER
    assert repaired_plan.metadata["fallback_applied"] is True
    assert repaired_plan.metadata["fallback_level"] == "visible_supporting_character"
    assert result.series_visual_signature_fallback is not None
    assert result.rendered_prompts[0].prompt_contract.metadata["mandatory_ip_final_gate"]["passed"] is True
    assert "戴黑色墨镜的斑点狗" in result.rendered_prompts[0].prompt


@pytest.mark.asyncio
async def test_visual_anchor_visible_character_strategy_requires_llm_service():
    with pytest.raises(ValueError, match="requires llm_service"):
        await VisualPromptPlanningService().plan_image_prompts(
            base_prompts=("base scene prompt",),
            frame_contexts=({"frame_id": "f1", "source_text": "scene source"},),
            visual_anchor_enabled=True,
            anchor_profile=IPProfile(
                series_visual_signature_profile_id="rabbit",
                workspace_id="ws",
                project_id="project",
                name="Rabbit Guide",
                identity_lock=("rabbit",),
                visual_summary="friendly guide rabbit",
            ),
            series_visual_signature_mode="supporting_integration",
            series_visual_signature_consistency_mode="supporting_character",
        )
