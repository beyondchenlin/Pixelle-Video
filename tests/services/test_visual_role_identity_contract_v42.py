import pytest

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_expression import VisualExpressionDecision, VisualExpressionMode
from pixelle_video.models.visual_role_planning import VisualRoleCritique
from pixelle_video.models.visual_role_profile import VisualRoleProfile
from pixelle_video.models.visual_role_request import VisualRoleRequest
from pixelle_video.services.visual_role_prompt_critic import VisualRolePromptCritic
from pixelle_video.services.visual_role_prompt_projector import (
    VisualRolePromptProjectionError,
    VisualRolePromptProjector,
)
from pixelle_video.services.visual_role_profile_builder import VisualRoleProfileBuilder
from pixelle_video.services.visual_role_scene_planner import VisualRoleScenePlanner


def _ip_profile(**overrides) -> IPProfile:
    payload = {
        "ip_profile_id": "rabbit",
        "workspace_id": "ws",
        "project_id": "prj",
        "name": "正定向导兔",
        "identity_lock": ("兔子", "蓝色领结"),
        "minimal_traits": ("蓝色领结一角",),
        "identity_anchors": ("长耳朵", "亲和向导感"),
        "visual_summary": "亲和的兔子向导形象，带蓝色领结。",
        "negative_constraints": ("不能变成非兔类",),
    }
    payload.update(overrides)
    return IPProfile(**payload)


def _brief() -> BaseVisualBrief:
    return BaseVisualBrief(
        frame_id="f1",
        core_message="讲解太阳能原理",
        visual_moment="工程师在实验室展示太阳能板发电流程",
        main_subjects=("工程师", "太阳能板"),
        base_image_prompt="工程师在实验室展示太阳能板发电流程",
    )


def _request(**overrides) -> VisualRoleRequest:
    payload = {
        "ip_enabled": True,
        "ip_asset_bible_id": "asset",
        "ip_profile_id": "rabbit",
        "visual_expression_mode": "explanatory_diagram",
        "visual_role_mode": "supporting_integration",
    }
    payload.update(overrides)
    return VisualRoleRequest.from_mapping(payload)


def test_identity_contract_required_traits_from_ip_profile():
    profile = VisualRoleProfileBuilder().build(_ip_profile())

    contract = profile.identity_contract

    assert contract.canonical_identity_name == "正定向导兔"
    assert contract.required_identity_traits == ("兔子", "蓝色领结", "蓝色领结一角")
    assert "兔子" in contract.fixed_identity_clause
    assert "蓝色领结" in contract.fixed_identity_clause
    assert "不能变成非兔类" in contract.forbidden_identity_loss_rules
    assert contract.metadata["required_trait_sources"]["兔子"] == "identity_lock"
    assert contract.metadata["required_trait_sources"]["蓝色领结一角"] == "minimal_traits"


def test_identity_contract_does_not_force_blue_bowtie_for_other_ip():
    profile = VisualRoleProfileBuilder().build(
        _ip_profile(
            ip_profile_id="sparrow",
            name="红嘴麻雀",
            identity_lock=("红嘴麻雀", "红色鸟嘴"),
            minimal_traits=(),
            identity_anchors=("小型鸟类",),
            visual_summary="一只小型红嘴麻雀。",
        )
    )

    assert "蓝色领结" not in profile.identity_contract.required_identity_traits
    assert "蓝色领结" not in profile.identity_contract.fixed_identity_clause


@pytest.mark.asyncio
async def test_required_identity_trait_missing_blocks_critic():
    profile = VisualRoleProfileBuilder().build(_ip_profile())
    plan = VisualRoleScenePlanner().plan_frame_rule(
        base_visual_brief=_brief(),
        visual_role_request=_request(),
        visual_role_profile=profile,
        expression_decision=VisualExpressionDecision(
            frame_id="f1",
            expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM,
        ),
    )
    bad_plan = plan.__class__(
        **{
            **plan.to_dict(),
            "integrated_scene_prompt": "工程师展示太阳能板发电流程，正定向导兔在旁边指示重点。",
            "metadata": {},
        }
    )

    critique = await VisualRolePromptCritic().critique(
        plan=bad_plan,
        visual_role_profile=profile,
        visual_role_request=_request(),
        base_visual_brief=_brief(),
    )

    assert not critique.passed
    assert "required_identity_trait_missing" in {issue.code for issue in critique.issues}


def test_fixed_identity_clause_enters_final_prompt_and_positive_only_guard_stays_positive():
    profile = VisualRoleProfileBuilder().build(_ip_profile())
    plan = VisualRoleScenePlanner().plan_frame_rule(
        base_visual_brief=_brief(),
        visual_role_request=_request(),
        visual_role_profile=profile,
        expression_decision=VisualExpressionDecision(
            frame_id="f1",
            expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM,
        ),
    )

    rendered = VisualRolePromptProjector().project(
        base_visual_brief=_brief(),
        visual_role_plan=plan,
        visual_role_critique=VisualRoleCritique(frame_id="f1"),
        visual_role_request=_request(),
        visual_role_profile=profile,
        workflow="z_image",
    )

    assert profile.identity_contract.fixed_identity_clause in rendered.prompt
    assert "不能变成非兔类" in rendered.prompt
    assert rendered.negative_prompt is None
    assert rendered.metadata["projected_prompt_parts"]["projector_validation_passed"] is True


def test_projector_final_validation_rejects_missing_required_trait():
    profile = VisualRoleProfile(
        profile_id="broken",
        display_name="破损角色",
        identity_kernel=("破损角色",),
        appearance_traits=(),
        action_affordances=("指示",),
        primary_role_affordances=("主角",),
        supporting_role_affordances=("讲解者",),
        forbidden_role_forms=(),
        metadata={
            "identity_contract": {
                "canonical_identity_name": "破损角色",
                "required_identity_traits": ["必须保留的徽章"],
                "fixed_identity_clause": "固定 IP 身份：破损角色。",
            }
        },
    )
    plan = VisualRoleScenePlanner().plan_frame_rule(
        base_visual_brief=_brief(),
        visual_role_request=_request(ip_profile_id="broken"),
        visual_role_profile=profile,
        expression_decision=VisualExpressionDecision(
            frame_id="f1",
            expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM,
        ),
    )
    bad_plan = plan.__class__(
        **{
            **plan.to_dict(),
            "integrated_scene_prompt": "The broken role points beside the diagram, but the mandatory trait is absent.",
            "metadata": {},
        }
    )

    with pytest.raises(VisualRolePromptProjectionError, match="required_identity_traits"):
        VisualRolePromptProjector().project(
            base_visual_brief=_brief(),
            visual_role_plan=bad_plan,
            visual_role_critique=VisualRoleCritique(frame_id="f1"),
            visual_role_request=_request(ip_profile_id="broken"),
            visual_role_profile=profile,
        )
