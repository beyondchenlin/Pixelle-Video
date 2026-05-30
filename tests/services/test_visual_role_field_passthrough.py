import pytest

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
