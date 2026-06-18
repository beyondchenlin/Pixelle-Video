import pytest

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.series_visual_signature_request import SeriesVisualSignatureRequest
from pixelle_video.services.visual_prompt_planning_service import VisualPromptPlanningService


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
