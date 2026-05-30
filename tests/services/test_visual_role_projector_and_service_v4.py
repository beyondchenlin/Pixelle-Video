import pytest

from pixelle_video.models.visual_role_request import VisualRoleRequest
from pixelle_video.models.visual_role_profile import VisualRoleProfile
from pixelle_video.services.visual_prompt_planning_service import VisualPromptPlanningService
from pixelle_video.services.visual_role_prompt_projector import VisualRolePromptProjectionError, VisualRolePromptProjector
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_expression import VisualExpressionDecision, VisualExpressionMode
from pixelle_video.services.visual_role_scene_planner import VisualRoleScenePlanner
from pixelle_video.models.visual_role_planning import VisualRoleCritique, VisualRolePromptIssue


def _request():
    return VisualRoleRequest.from_mapping({
        "ip_enabled": True,
        "ip_asset_bible_id": "asset",
        "ip_profile_id": "sparrow",
        "visual_expression_mode": "explanatory_diagram",
        "visual_role_mode": "supporting_integration",
    })


def _profile():
    return VisualRoleProfile(
        profile_id="sparrow",
        display_name="红嘴麻雀",
        identity_kernel=("红嘴麻雀",),
        appearance_traits=("红色鸟嘴",),
        action_affordances=("指示",),
        primary_role_affordances=("故事行动者",),
        supporting_role_affordances=("信息图指示物",),
        forbidden_role_forms=("角标", "水印", "贴纸", "logo", "overlay"),
    )


@pytest.mark.asyncio
async def test_visual_prompt_planning_routes_v4_to_visual_role_projector():
    result = await VisualPromptPlanningService().plan_image_prompts(
        base_prompts=("工程师讲解太阳能板发电流程",),
        frame_contexts=({"frame_id": "f1", "source_text": "太阳能发电原理"},),
        visual_role_request=_request(),
        visual_role_profile=_profile(),
    )

    assert len(result.rendered_prompts) == 1
    assert result.visual_role_plans
    assert result.visual_role_critiques[0].passed
    assert "红嘴麻雀" in result.rendered_prompts[0].prompt
    snapshot = result.planning_snapshot()
    assert "visual_role_request" in snapshot
    assert "visual_role_plan_by_frame" in snapshot


def test_v4_projector_raises_when_critic_not_passed():
    brief = BaseVisualBrief(frame_id="f1", core_message="讲解太阳能原理", visual_moment="工程师在实验室展示太阳能板发电流程", main_subjects=("工程师",))
    plan = VisualRoleScenePlanner().plan_frame_rule(
        base_visual_brief=brief,
        visual_role_request=_request(),
        visual_role_profile=_profile(),
        expression_decision=VisualExpressionDecision(frame_id="f1", expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM),
    )
    critique = VisualRoleCritique(frame_id="f1", issues=(VisualRolePromptIssue("role_missing", "blocking", "missing", "repair"),))

    with pytest.raises(VisualRolePromptProjectionError):
        VisualRolePromptProjector().project(
            base_visual_brief=brief,
            visual_role_plan=plan,
            visual_role_critique=critique,
            visual_role_request=_request(),
            visual_role_profile=_profile(),
        )
