import pytest

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.series_visual_signature_planning import SeriesVisualSignatureCritique
from pixelle_video.models.series_visual_signature_profile import SeriesVisualSignatureProfile
from pixelle_video.models.series_visual_signature_request import SeriesVisualSignatureRequest
from pixelle_video.models.visual_expression import VisualExpressionDecision, VisualExpressionMode
from pixelle_video.services.series_visual_signature_profile_builder import (
    SeriesVisualSignatureProfileBuilder,
)
from pixelle_video.services.series_visual_signature_prompt_critic import (
    SeriesVisualSignaturePromptCritic,
)
from pixelle_video.services.series_visual_signature_prompt_projector import (
    SeriesVisualSignaturePromptProjector,
)
from pixelle_video.services.series_visual_signature_scene_planner import (
    SeriesVisualSignatureScenePlanner,
)


def _ip_profile(**overrides) -> IPProfile:
    payload = {
        "series_visual_signature_profile_id": "rabbit",
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


def _leaky_style_brief() -> BaseVisualBrief:
    return BaseVisualBrief(
        frame_id="f2",
        core_message="Explain how solitude changes self-understanding",
        visual_moment="A reader studies an open book beside a rainy city window",
        main_subjects=("reader", "open book"),
        base_image_prompt="A reader studies an open book beside a rainy city window.",
        style_surface=(
            "flat monochrome illustration, non-IP world layer, non-IP animals, props, "
            "background, and environment: flat monochrome illustration, elegant, "
            "minimal line art with clean contours, lots of negative space"
        ),
    )


def _dalmatian_profile(**contract_overrides) -> SeriesVisualSignatureProfile:
    identity_contract = {
        "canonical_identity_name": "Dalmatian guide",
        "required_identity_traits": ["black sunglasses", "dalmatian spots"],
        "fixed_identity_clause": (
            "Fixed IP identity: Dalmatian guide; required identity traits: "
            "black sunglasses, dalmatian spots."
        ),
        "forbidden_identity_loss_rules": [
            "Do not turn the IP into a logo, watermark, sticker, corner badge, floating icon, or UI overlay.",
            "Do not hide, suppress, replace, or genericize the configured IP identity.",
        ],
    }
    identity_contract.update(contract_overrides)
    return SeriesVisualSignatureProfile(
        profile_id="dalmatian",
        display_name="Dalmatian guide",
        identity_kernel=("Dalmatian guide",),
        appearance_traits=("black sunglasses", "dalmatian spots"),
        action_affordances=("observe and guide",),
        primary_role_affordances=("protagonist",),
        supporting_role_affordances=("in-scene guide",),
        forbidden_role_forms=("logo", "watermark", "sticker", "corner badge", "UI overlay"),
        metadata={"identity_contract": identity_contract},
    )


def _request(**overrides) -> SeriesVisualSignatureRequest:
    payload = {
        "series_visual_signature_enabled": True,
        "series_visual_signature_asset_bible_id": "asset",
        "series_visual_signature_profile_id": "rabbit",
        "series_visual_signature_expression_mode": "explanatory_diagram",
        "series_visual_signature_mode": "supporting_integration",
    }
    payload.update(overrides)
    return SeriesVisualSignatureRequest.from_mapping(payload)


def _assert_no_internal_prompt_tokens(prompt: str) -> None:
    forbidden_tokens = (
        "Fixed IP identity",
        "required identity traits",
        "Identity kernel",
        "Scene responsibility",
        "Identity protection rules",
        "action responsibility",
        "non-IP world layer",
        "non-IP animals",
        "non-IP",
        "Do not",
        "forbidden_identity_loss_rules",
        "identity_contract_clause",
    )
    for token in forbidden_tokens:
        assert token not in prompt


def test_identity_contract_required_traits_from_ip_profile():
    profile = SeriesVisualSignatureProfileBuilder().build(_ip_profile())

    contract = profile.identity_contract

    assert contract.canonical_identity_name == "正定向导兔"
    assert contract.required_identity_traits == ("兔子", "蓝色领结", "蓝色领结一角")
    assert "兔子" in contract.fixed_identity_clause
    assert "蓝色领结" in contract.fixed_identity_clause
    assert "不能变成非兔类" in contract.forbidden_identity_loss_rules
    assert contract.metadata["required_trait_sources"]["兔子"] == "identity_lock"
    assert contract.metadata["required_trait_sources"]["蓝色领结一角"] == "minimal_traits"


def test_identity_contract_does_not_force_blue_bowtie_for_other_ip():
    profile = SeriesVisualSignatureProfileBuilder().build(
        _ip_profile(
            series_visual_signature_profile_id="sparrow",
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
    profile = SeriesVisualSignatureProfileBuilder().build(_ip_profile())
    plan = SeriesVisualSignatureScenePlanner().plan_frame_rule(
        base_visual_brief=_brief(),
        series_visual_signature_request=_request(),
        series_visual_signature_profile=profile,
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

    critique = await SeriesVisualSignaturePromptCritic().critique(
        plan=bad_plan,
        series_visual_signature_profile=profile,
        series_visual_signature_request=_request(),
        base_visual_brief=_brief(),
    )

    assert not critique.passed
    assert "required_identity_trait_missing" in {issue.code for issue in critique.issues}


def test_projector_compiles_image_facing_prompt_without_internal_contract_labels():
    profile = _dalmatian_profile()
    brief = _leaky_style_brief()
    plan = SeriesVisualSignatureScenePlanner().plan_frame_rule(
        base_visual_brief=brief,
        series_visual_signature_request=_request(series_visual_signature_profile_id="dalmatian"),
        series_visual_signature_profile=profile,
        expression_decision=VisualExpressionDecision(
            frame_id="f2",
            expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM,
        ),
    )

    rendered = SeriesVisualSignaturePromptProjector().project(
        base_visual_brief=brief,
        series_visual_signature_plan=plan,
        series_visual_signature_critique=SeriesVisualSignatureCritique(frame_id="f2"),
        series_visual_signature_request=_request(series_visual_signature_profile_id="dalmatian"),
        series_visual_signature_profile=profile,
        workflow="z_image",
    )

    assert profile.display_name in rendered.prompt
    assert "black sunglasses" in rendered.prompt
    assert "dalmatian spots" in rendered.prompt
    _assert_no_internal_prompt_tokens(rendered.prompt)
    assert rendered.prompt.count("flat monochrome illustration") <= 1
    assert rendered.negative_prompt is None
    assert rendered.metadata["projected_prompt_parts"]["projector_validation_passed"] is True


def test_projector_injects_structured_required_traits_without_raw_fixed_clause():
    profile = _dalmatian_profile(required_identity_traits=["black sunglasses", "single ear patch"])
    brief = _leaky_style_brief()
    plan = SeriesVisualSignatureScenePlanner().plan_frame_rule(
        base_visual_brief=brief,
        series_visual_signature_request=_request(series_visual_signature_profile_id="dalmatian"),
        series_visual_signature_profile=profile,
        expression_decision=VisualExpressionDecision(
            frame_id="f2",
            expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM,
        ),
    )
    plan_without_required_trait = plan.__class__(
        **{
            **plan.to_dict(),
            "integrated_scene_prompt": "A guide points beside the diagram, but the specific visual trait is absent.",
            "metadata": {},
        }
    )

    rendered = SeriesVisualSignaturePromptProjector().project(
        base_visual_brief=brief,
        series_visual_signature_plan=plan_without_required_trait,
        series_visual_signature_critique=SeriesVisualSignatureCritique(frame_id="f2"),
        series_visual_signature_request=_request(series_visual_signature_profile_id="dalmatian"),
        series_visual_signature_profile=profile,
    )

    assert "black sunglasses" in rendered.prompt
    assert "single ear patch" in rendered.prompt
    assert profile.identity_contract.fixed_identity_clause not in rendered.prompt
    _assert_no_internal_prompt_tokens(rendered.prompt)
