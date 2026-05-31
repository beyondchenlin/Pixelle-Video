import pytest

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.visual_role_request import VisualRoleRequest
from pixelle_video.services.visual_prompt_planning_service import VisualPromptPlanningService


@pytest.mark.asyncio
async def test_visual_prompt_planning_accepts_visual_role_request_without_enabling_v4():
    result = await VisualPromptPlanningService().plan_image_prompts(
        base_prompts=("工程师讲解太阳能板发电流程",),
        frame_contexts=({"frame_id": "f1", "source_text": "太阳能发电原理"},),
        visual_expression_mode="explanatory_diagram",
        visual_role_request=VisualRoleRequest.disabled(),
    )

    assert len(result.rendered_prompts) == 1
    assert result.rendered_prompts[0].prompt


@pytest.mark.asyncio
async def test_visual_anchor_enabled_without_v4_request_keeps_legacy_anchor_path(monkeypatch):
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
            ip_profile_id="rabbit",
            workspace_id="ws",
            project_id="project",
            name="Rabbit Guide",
            identity_lock=("rabbit",),
            visual_summary="friendly guide rabbit",
        ),
        visual_expression_mode="explanatory_diagram",
        visual_structure_mode="workflow",
        visual_participation_mode="guide_explainer",
    )

    assert planner_calls
    assert result.visual_role_request is None
    assert result.visual_role_plans == ()
    assert len(result.rendered_prompts) == 1
