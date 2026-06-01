import pytest

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_expression import VisualExpressionDecision, VisualExpressionMode
from pixelle_video.models.visual_role_identity import VisualRoleIdentityContract
from pixelle_video.models.visual_role_profile import VisualRoleProfile
from pixelle_video.models.visual_role_request import VisualRoleRequest
from pixelle_video.models.visual_role_strategy import VisualRoleMode
from pixelle_video.services.visual_role_prompt_critic import VisualRolePromptCritic
from pixelle_video.services.visual_role_repair_loop import (
    VisualRoleRepairFailedError,
    VisualRoleRepairLoop,
)
from pixelle_video.services.visual_role_scene_planner import VisualRoleScenePlanner


def _brief() -> BaseVisualBrief:
    return BaseVisualBrief(
        frame_id="f1",
        core_message="讲解太阳能原理",
        visual_moment="工程师在实验室展示太阳能板发电流程",
        main_subjects=("工程师", "太阳能板"),
        base_image_prompt="工程师在实验室展示太阳能板发电流程",
    )


def _profile() -> VisualRoleProfile:
    return VisualRoleProfile(
        profile_id="sparrow",
        display_name="红嘴麻雀",
        identity_kernel=("红嘴麻雀",),
        appearance_traits=("红色鸟嘴", "小型麻雀"),
        action_affordances=("指示", "讲解"),
        primary_role_affordances=("故事行动者",),
        supporting_role_affordances=("信息图指示物", "导览者"),
        forbidden_role_forms=("角标", "水印", "贴纸", "logo", "overlay"),
    )


def _request(**overrides) -> VisualRoleRequest:
    payload = {
        "ip_enabled": True,
        "ip_asset_bible_id": "asset",
        "ip_profile_id": "sparrow",
        "visual_expression_mode": "explanatory_diagram",
        "visual_role_mode": "supporting_integration",
    }
    payload.update(overrides)
    return VisualRoleRequest.from_mapping(payload)


@pytest.mark.asyncio
async def test_visual_role_scene_planner_supporting_integration_preserves_original_subject():
    plans = await VisualRoleScenePlanner().plan_batch(
        base_visual_briefs=(_brief(),),
        visual_role_request=_request(),
        visual_role_profile=_profile(),
        expression_decisions=(VisualExpressionDecision(frame_id="f1", expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM),),
    )

    assert "工程师" in plans[0].integrated_scene_prompt
    assert "红嘴麻雀" in plans[0].integrated_scene_prompt
    assert "角标" not in plans[0].integrated_scene_prompt


@pytest.mark.asyncio
async def test_repair_context_does_not_pollute_final_prompt():
    plans = await VisualRoleScenePlanner().plan_batch(
        base_visual_briefs=(_brief(),),
        visual_role_request=_request(),
        visual_role_profile=_profile(),
        expression_decisions=(VisualExpressionDecision(frame_id="f1", expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM),),
        repair_context_by_frame={"f1": {"issues": [{"code": "forbidden_visual_form", "message": "不要出现角标、水印、overlay"}]}},
    )

    assert "forbidden_visual_form" not in plans[0].integrated_scene_prompt
    assert "overlay" not in plans[0].integrated_scene_prompt.lower()


@pytest.mark.asyncio
async def test_rule_critic_rejects_overlay_like_role():
    plan = VisualRoleScenePlanner().plan_frame_rule(
        base_visual_brief=_brief(),
        visual_role_request=_request(),
        visual_role_profile=_profile(),
        expression_decision=VisualExpressionDecision(frame_id="f1", expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM),
    )
    bad_plan = plan.__class__(**{**plan.to_dict(), "integrated_scene_prompt": "工程师展示流程，红嘴麻雀作为 corner badge overlay 出现。", "metadata": {}})
    critique = await VisualRolePromptCritic().critique(
        plan=bad_plan,
        visual_role_profile=_profile(),
        visual_role_request=_request(),
        base_visual_brief=_brief(),
    )
    assert not critique.passed
    assert {issue.code for issue in critique.issues} & {"forbidden_visual_form", "overlay_like_visual_role"}


@pytest.mark.asyncio
async def test_repair_loop_raises_after_repeated_role_missing():
    class BadPlanner(VisualRoleScenePlanner):
        async def plan_batch(self, **kwargs):
            plans = await super().plan_batch(**kwargs)
            return tuple(
                plan.__class__(**{**plan.to_dict(), "integrated_scene_prompt": "工程师展示流程，没有配置的视觉角色。", "metadata": {}})
                for plan in plans
            )

    with pytest.raises(VisualRoleRepairFailedError):
        await VisualRoleRepairLoop(max_repair_attempts=1).run_batch(
            planner=BadPlanner(),
            critic=VisualRolePromptCritic(),
            base_visual_briefs=(_brief(),),
            visual_role_request=_request(),
            visual_role_profile=_profile(),
            expression_decisions=(VisualExpressionDecision(frame_id="f1", expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM),),
        )


@pytest.mark.asyncio
async def test_repair_loop_retries_planner_exceptions_without_silent_success():
    class FlakyPlanner(VisualRoleScenePlanner):
        def __init__(self):
            super().__init__()
            self.calls = 0

        async def plan_batch(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ValueError("LLM visual role planner must return integrated_scene_prompt")
            return await super().plan_batch(**kwargs)

    plans, critiques, attempts = await VisualRoleRepairLoop(max_repair_attempts=1).run_batch(
        planner=FlakyPlanner(),
        critic=VisualRolePromptCritic(),
        base_visual_briefs=(_brief(),),
        visual_role_request=_request(),
        visual_role_profile=_profile(),
        expression_decisions=(VisualExpressionDecision(frame_id="f1", expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM),),
    )

    assert "planner_error" in attempts["attempt_1"]
    assert critiques[0].passed
    assert "红嘴麻雀" in plans[0].integrated_scene_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expression_mode",
    (
        VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
        VisualExpressionMode.PRODUCT_OR_OBJECT_SCENE,
    ),
)
async def test_auto_role_mode_stays_supporting_for_portrait_and_product_expression(expression_mode):
    request = _request(
        visual_expression_mode="auto",
        visual_role_mode="auto",
        visual_consistency_mode="off",
    )

    plans = await VisualRoleScenePlanner().plan_batch(
        base_visual_briefs=(_brief(),),
        visual_role_request=request,
        visual_role_profile=_profile(),
        expression_decisions=(VisualExpressionDecision(frame_id="f1", expression_mode=expression_mode),),
    )

    assert plans[0].role_mode is VisualRoleMode.SUPPORTING_INTEGRATION
    critique = await VisualRolePromptCritic().critique(
        plan=plans[0],
        visual_role_profile=_profile(),
        visual_role_request=request,
        base_visual_brief=_brief(),
    )
    assert "subject_replacement_not_primary" not in {issue.code for issue in critique.issues}


@pytest.mark.asyncio
async def test_explicit_subject_replacement_still_requires_primary_role():
    request = _request(
        visual_role_mode="subject_replacement",
        visual_consistency_mode="off",
    )

    plans = await VisualRoleScenePlanner().plan_batch(
        base_visual_briefs=(_brief(),),
        visual_role_request=request,
        visual_role_profile=_profile(),
        expression_decisions=(
            VisualExpressionDecision(
                frame_id="f1",
                expression_mode=VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
            ),
        ),
    )

    assert plans[0].role_mode is VisualRoleMode.SUBJECT_REPLACEMENT


@pytest.mark.asyncio
async def test_llm_planner_preserves_required_identity_terms_before_critique():
    async def llm_service(**_kwargs):
        return {
            "integrated_scene_prompt": "An engineer explains the solar workflow with a visible guide beside the panel.",
            "role_action": "guide the viewer through the solar workflow",
            "role_manifestation": "in-scene guide",
        }

    profile = VisualRoleProfile(
        profile_id="dog_1",
        display_name="Dalmatian guide",
        identity_kernel=("dalmatian in black sunglasses",),
        appearance_traits=("black sunglasses", "dalmatian spots"),
        action_affordances=("guide",),
        primary_role_affordances=("protagonist",),
        supporting_role_affordances=("guide",),
        forbidden_role_forms=("corner badge", "watermark", "overlay"),
        identity_contract=VisualRoleIdentityContract(
            canonical_identity_name="Dalmatian guide",
            required_identity_traits=("black sunglasses", "dalmatian"),
        ),
    )
    request = _request(
        visual_expression_mode="auto",
        visual_role_mode="auto",
        visual_consistency_mode="off",
    )

    plans = await VisualRoleScenePlanner(llm_service=llm_service).plan_batch(
        base_visual_briefs=(_brief(),),
        visual_role_request=request,
        visual_role_profile=profile,
        expression_decisions=(
            VisualExpressionDecision(
                frame_id="f1",
                expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM,
            ),
        ),
    )

    prompt = plans[0].integrated_scene_prompt
    assert "Fixed IP identity: Dalmatian guide" in prompt
    assert "black sunglasses" in prompt
    assert "dalmatian" in prompt
    assert "dalmatian in black sunglasses" in prompt
    critique = await VisualRolePromptCritic().critique(
        plan=plans[0],
        visual_role_profile=profile,
        visual_role_request=request,
    )
    assert critique.passed
