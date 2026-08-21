import pytest

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.series_visual_signature_identity import (
    SeriesVisualSignatureIdentityContract,
)
from pixelle_video.models.series_visual_signature_profile import SeriesVisualSignatureProfile
from pixelle_video.models.series_visual_signature_request import SeriesVisualSignatureRequest
from pixelle_video.models.series_visual_signature_strategy import SeriesVisualSignatureMode
from pixelle_video.models.visual_expression import VisualExpressionDecision, VisualExpressionMode
from pixelle_video.services.series_visual_signature_prompt_critic import (
    SeriesVisualSignaturePromptCritic,
)
from pixelle_video.services.series_visual_signature_repair_loop import (
    SeriesVisualSignatureRepairFailedError,
    SeriesVisualSignatureRepairLoop,
)
from pixelle_video.services.series_visual_signature_scene_planner import (
    SeriesVisualSignatureScenePlanner,
)


def _brief() -> BaseVisualBrief:
    return BaseVisualBrief(
        frame_id="f1",
        core_message="讲解太阳能原理",
        visual_moment="工程师在实验室展示太阳能板发电流程",
        main_subjects=("工程师", "太阳能板"),
        base_image_prompt="工程师在实验室展示太阳能板发电流程",
    )


def _profile() -> SeriesVisualSignatureProfile:
    return SeriesVisualSignatureProfile(
        profile_id="sparrow",
        display_name="红嘴麻雀",
        identity_kernel=("红嘴麻雀",),
        appearance_traits=("红色鸟嘴", "小型麻雀"),
        action_affordances=("指示", "讲解"),
        primary_role_affordances=("故事行动者",),
        supporting_role_affordances=("信息图指示物", "导览者"),
        forbidden_role_forms=("角标", "水印", "贴纸", "logo", "overlay"),
    )


def _dog_profile() -> SeriesVisualSignatureProfile:
    return SeriesVisualSignatureProfile(
        profile_id="dog_1",
        display_name="Dalmatian guide",
        identity_kernel=("Dalmatian guide",),
        appearance_traits=("black sunglasses", "dalmatian spots"),
        action_affordances=("guide",),
        primary_role_affordances=("protagonist",),
        supporting_role_affordances=("guide",),
        forbidden_role_forms=("corner badge", "watermark", "overlay"),
        identity_contract=SeriesVisualSignatureIdentityContract(
            canonical_identity_name="Dalmatian guide",
            required_identity_traits=("black sunglasses", "dalmatian spots"),
        ),
    )


def _request(**overrides) -> SeriesVisualSignatureRequest:
    payload = {
        "series_visual_signature_enabled": True,
        "series_visual_signature_asset_bible_id": "asset",
        "series_visual_signature_profile_id": "sparrow",
        "series_visual_signature_expression_mode": "explanatory_diagram",
        "series_visual_signature_mode": "supporting_integration",
    }
    payload.update(overrides)
    raw_role = payload.get("series_visual_signature_role", "auto")
    return SeriesVisualSignatureRequest(
        enabled=True,
        asset_bible_id=str(payload["series_visual_signature_asset_bible_id"]),
        profile_id=str(payload["series_visual_signature_profile_id"]),
        role=raw_role,
        role_was_explicit=raw_role not in {None, "", "none", "auto"},
        max_area_ratio=payload.get("series_visual_signature_max_area_ratio"),
        compatibility_options={
            key: value
            for key, value in payload.items()
            if key.startswith("series_visual_signature_")
        },
    )


@pytest.mark.asyncio
async def test_series_visual_signature_scene_planner_supporting_integration_preserves_original_subject():
    plans = await SeriesVisualSignatureScenePlanner().plan_batch(
        base_visual_briefs=(_brief(),),
        series_visual_signature_request=_request(),
        series_visual_signature_profile=_profile(),
        expression_decisions=(VisualExpressionDecision(frame_id="f1", expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM),),
    )

    assert "工程师" in plans[0].integrated_scene_prompt
    assert "红嘴麻雀" in plans[0].integrated_scene_prompt
    assert "角标" not in plans[0].integrated_scene_prompt


@pytest.mark.asyncio
async def test_repair_context_does_not_pollute_final_prompt():
    plans = await SeriesVisualSignatureScenePlanner().plan_batch(
        base_visual_briefs=(_brief(),),
        series_visual_signature_request=_request(),
        series_visual_signature_profile=_profile(),
        expression_decisions=(VisualExpressionDecision(frame_id="f1", expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM),),
        repair_context_by_frame={"f1": {"issues": [{"code": "forbidden_visual_form", "message": "不要出现角标、水印、overlay"}]}},
    )

    assert "forbidden_visual_form" not in plans[0].integrated_scene_prompt
    assert "overlay" not in plans[0].integrated_scene_prompt.lower()


@pytest.mark.asyncio
async def test_rule_critic_rejects_overlay_like_role():
    plan = SeriesVisualSignatureScenePlanner().plan_frame_rule(
        base_visual_brief=_brief(),
        series_visual_signature_request=_request(),
        series_visual_signature_profile=_profile(),
        expression_decision=VisualExpressionDecision(frame_id="f1", expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM),
    )
    bad_plan = plan.__class__(**{**plan.to_dict(), "integrated_scene_prompt": "工程师展示流程，红嘴麻雀作为 corner badge overlay 出现。", "metadata": {}})
    critique = await SeriesVisualSignaturePromptCritic().critique(
        plan=bad_plan,
        series_visual_signature_profile=_profile(),
        series_visual_signature_request=_request(),
        base_visual_brief=_brief(),
    )
    assert not critique.passed
    assert {issue.code for issue in critique.issues} & {"forbidden_visual_form", "overlay_like_series_visual_signature"}


@pytest.mark.asyncio
async def test_repair_loop_raises_after_repeated_role_missing():
    class BadPlanner(SeriesVisualSignatureScenePlanner):
        async def plan_batch(self, **kwargs):
            plans = await super().plan_batch(**kwargs)
            return tuple(
                plan.__class__(**{**plan.to_dict(), "integrated_scene_prompt": "工程师展示流程，没有配置的视觉签名。", "metadata": {}})
                for plan in plans
            )

    with pytest.raises(SeriesVisualSignatureRepairFailedError):
        await SeriesVisualSignatureRepairLoop(max_repair_attempts=1).run_batch(
            planner=BadPlanner(),
            critic=SeriesVisualSignaturePromptCritic(),
            base_visual_briefs=(_brief(),),
            series_visual_signature_request=_request(),
            series_visual_signature_profile=_profile(),
            expression_decisions=(VisualExpressionDecision(frame_id="f1", expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM),),
        )


@pytest.mark.asyncio
async def test_repair_loop_retries_planner_exceptions_without_silent_success():
    class FlakyPlanner(SeriesVisualSignatureScenePlanner):
        def __init__(self):
            super().__init__()
            self.calls = 0

        async def plan_batch(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ValueError("LLM series visual signature planner must return integrated_scene_prompt")
            return await super().plan_batch(**kwargs)

    plans, critiques, attempts = await SeriesVisualSignatureRepairLoop(max_repair_attempts=1).run_batch(
        planner=FlakyPlanner(),
        critic=SeriesVisualSignaturePromptCritic(),
        base_visual_briefs=(_brief(),),
        series_visual_signature_request=_request(),
        series_visual_signature_profile=_profile(),
        expression_decisions=(VisualExpressionDecision(frame_id="f1", expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM),),
    )

    assert "planner_error" in attempts["attempt_1"]
    assert critiques[0].passed
    assert "红嘴麻雀" in plans[0].integrated_scene_prompt


@pytest.mark.asyncio
async def test_repair_loop_normalizes_subject_replacement_before_failure():
    async def llm_service(**_kwargs):
        return {
            "role_assignment": "supporting observer",
            "role_location": "beside the original reader",
            "integrated_scene_prompt": (
                "A lonely reader stands near an open book while a Dalmatian guide "
                "watches from the side."
            ),
            "role_action": "observe the scene",
            "role_manifestation": "in-scene guide",
        }

    request = _request(
        series_visual_signature_expression_mode="auto",
        series_visual_signature_mode="auto",
        series_visual_signature_consistency_mode="primary_character",
    )

    plans, critiques, attempts = await SeriesVisualSignatureRepairLoop(max_repair_attempts=1).run_batch(
        planner=SeriesVisualSignatureScenePlanner(llm_service=llm_service),
        critic=SeriesVisualSignaturePromptCritic(),
        base_visual_briefs=(_brief(),),
        series_visual_signature_request=request,
        series_visual_signature_profile=_dog_profile(),
        expression_decisions=(
            VisualExpressionDecision(
                frame_id="f1",
                expression_mode=VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
            ),
        ),
    )

    assert attempts["attempt_1"]["critiques"][0]["passed"]
    assert critiques[0].passed
    assert "subject_replacement_not_primary" not in {issue.code for issue in critiques[0].issues}
    assert "watches from the side" not in plans[0].integrated_scene_prompt.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expression_mode",
    (
        VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
        VisualExpressionMode.PRODUCT_OR_OBJECT_SCENE,
    ),
)
async def test_auto_signature_mode_stays_supporting_for_portrait_and_product_expression(expression_mode):
    request = _request(
        series_visual_signature_expression_mode="auto",
        series_visual_signature_mode="auto",
        series_visual_signature_consistency_mode="off",
    )

    plans = await SeriesVisualSignatureScenePlanner().plan_batch(
        base_visual_briefs=(_brief(),),
        series_visual_signature_request=request,
        series_visual_signature_profile=_profile(),
        expression_decisions=(VisualExpressionDecision(frame_id="f1", expression_mode=expression_mode),),
    )

    assert plans[0].signature_mode is SeriesVisualSignatureMode.SUPPORTING_INTEGRATION
    critique = await SeriesVisualSignaturePromptCritic().critique(
        plan=plans[0],
        series_visual_signature_profile=_profile(),
        series_visual_signature_request=request,
        base_visual_brief=_brief(),
    )
    assert "subject_replacement_not_primary" not in {issue.code for issue in critique.issues}


@pytest.mark.asyncio
async def test_explicit_subject_replacement_still_requires_primary_role():
    request = _request(
        series_visual_signature_mode="subject_replacement",
        series_visual_signature_consistency_mode="off",
    )

    plans = await SeriesVisualSignatureScenePlanner().plan_batch(
        base_visual_briefs=(_brief(),),
        series_visual_signature_request=request,
        series_visual_signature_profile=_profile(),
        expression_decisions=(
            VisualExpressionDecision(
                frame_id="f1",
                expression_mode=VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
            ),
        ),
    )

    assert plans[0].signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT


@pytest.mark.asyncio
async def test_llm_planner_preserves_identity_terms_without_internal_contract_labels():
    async def llm_service(**_kwargs):
        return {
            "integrated_scene_prompt": "An engineer explains the solar workflow with a visible guide beside the panel.",
            "role_action": "guide the viewer through the solar workflow",
            "role_manifestation": "in-scene guide",
        }

    profile = SeriesVisualSignatureProfile(
        profile_id="dog_1",
        display_name="Dalmatian guide",
        identity_kernel=("dalmatian in black sunglasses",),
        appearance_traits=("black sunglasses", "dalmatian spots"),
        action_affordances=("guide",),
        primary_role_affordances=("protagonist",),
        supporting_role_affordances=("guide",),
        forbidden_role_forms=("corner badge", "watermark", "overlay"),
        identity_contract=SeriesVisualSignatureIdentityContract(
            canonical_identity_name="Dalmatian guide",
            required_identity_traits=("black sunglasses", "dalmatian"),
        ),
    )
    request = _request(
        series_visual_signature_expression_mode="auto",
        series_visual_signature_mode="auto",
        series_visual_signature_consistency_mode="off",
    )

    plans = await SeriesVisualSignatureScenePlanner(llm_service=llm_service).plan_batch(
        base_visual_briefs=(_brief(),),
        series_visual_signature_request=request,
        series_visual_signature_profile=profile,
        expression_decisions=(
            VisualExpressionDecision(
                frame_id="f1",
                expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM,
            ),
        ),
    )

    prompt = plans[0].integrated_scene_prompt
    assert "Fixed IP identity" not in prompt
    assert "required identity traits" not in prompt
    assert "Identity kernel" not in prompt
    assert "Scene responsibility" not in prompt
    assert "black sunglasses" in prompt
    assert "dalmatian" in prompt
    assert "dalmatian in black sunglasses" in prompt
    critique = await SeriesVisualSignaturePromptCritic().critique(
        plan=plans[0],
        series_visual_signature_profile=profile,
        series_visual_signature_request=request,
    )
    assert critique.passed


@pytest.mark.asyncio
async def test_subject_replacement_llm_payload_is_normalized_to_primary_contract():
    async def llm_service(**_kwargs):
        return {
            "role_assignment": "supporting observer",
            "role_location": "beside the original reader",
            "integrated_scene_prompt": (
                "A lonely reader stands near an open book while a Dalmatian guide "
                "watches from the side."
            ),
            "role_action": "observe the scene",
            "role_manifestation": "in-scene guide",
        }

    profile = _dog_profile()
    request = _request(
        series_visual_signature_expression_mode="auto",
        series_visual_signature_mode="auto",
        series_visual_signature_consistency_mode="primary_character",
    )

    plans = await SeriesVisualSignatureScenePlanner(llm_service=llm_service).plan_batch(
        base_visual_briefs=(_brief(),),
        series_visual_signature_request=request,
        series_visual_signature_profile=profile,
        expression_decisions=(
            VisualExpressionDecision(
                frame_id="f1",
                expression_mode=VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
            ),
        ),
    )

    assert plans[0].signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT
    assert "primary" in plans[0].role_assignment.lower()
    assert "primary" in plans[0].role_location.lower()
    assert "beside" not in plans[0].role_location.lower()
    assert "primary" in plans[0].integrated_scene_prompt.lower()
    assert "watches from the side" not in plans[0].integrated_scene_prompt.lower()
    critique = await SeriesVisualSignaturePromptCritic().critique(
        plan=plans[0],
        series_visual_signature_profile=profile,
        series_visual_signature_request=request,
        base_visual_brief=_brief(),
    )
    assert critique.passed
    assert "subject_replacement_not_primary" not in {issue.code for issue in critique.issues}


@pytest.mark.asyncio
async def test_subject_replacement_critic_rejects_negated_primary_language():
    profile = _dog_profile()
    request = _request(
        series_visual_signature_mode="subject_replacement",
        series_visual_signature_consistency_mode="off",
    )
    plan = SeriesVisualSignatureScenePlanner().plan_frame_rule(
        base_visual_brief=_brief(),
        series_visual_signature_request=request,
        series_visual_signature_profile=profile,
        expression_decision=VisualExpressionDecision(
            frame_id="f1",
            expression_mode=VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
        ),
    )
    bad_plan = plan.__class__(
        **{
            **plan.to_dict(),
            "role_assignment": "not the primary subject",
            "role_location": "beside the original reader",
            "integrated_scene_prompt": (
                "Dalmatian guide is not the primary subject; it stays beside the "
                "reader with black sunglasses and dalmatian spots."
            ),
            "metadata": {},
        }
    )

    critique = await SeriesVisualSignaturePromptCritic().critique(
        plan=bad_plan,
        series_visual_signature_profile=profile,
        series_visual_signature_request=request,
        base_visual_brief=_brief(),
    )

    assert not critique.passed
    assert "subject_replacement_not_primary" in {issue.code for issue in critique.issues}


@pytest.mark.asyncio
async def test_subject_replacement_critic_rejects_side_observer_prompt_even_with_primary_fields():
    profile = _dog_profile()
    request = _request(
        series_visual_signature_mode="subject_replacement",
        series_visual_signature_consistency_mode="off",
    )
    plan = SeriesVisualSignatureScenePlanner().plan_frame_rule(
        base_visual_brief=_brief(),
        series_visual_signature_request=request,
        series_visual_signature_profile=profile,
        expression_decision=VisualExpressionDecision(
            frame_id="f1",
            expression_mode=VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
        ),
    )
    bad_plan = plan.__class__(
        **{
            **plan.to_dict(),
            "role_assignment": "primary protagonist",
            "role_location": "primary focus area",
            "integrated_scene_prompt": (
                "Dalmatian guide is the primary protagonist, but it watches from "
                "the side beside the original reader with black sunglasses and "
                "dalmatian spots."
            ),
            "metadata": {},
        }
    )

    critique = await SeriesVisualSignaturePromptCritic().critique(
        plan=bad_plan,
        series_visual_signature_profile=profile,
        series_visual_signature_request=request,
        base_visual_brief=_brief(),
    )

    assert not critique.passed
    assert "subject_replacement_not_primary" in {issue.code for issue in critique.issues}


@pytest.mark.asyncio
async def test_subject_replacement_critic_allows_primary_subject_side_view_framing():
    profile = _dog_profile()
    request = _request(
        series_visual_signature_mode="subject_replacement",
        series_visual_signature_consistency_mode="off",
    )
    plan = SeriesVisualSignatureScenePlanner().plan_frame_rule(
        base_visual_brief=_brief(),
        series_visual_signature_request=request,
        series_visual_signature_profile=profile,
        expression_decision=VisualExpressionDecision(
            frame_id="f1",
            expression_mode=VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
        ),
    )
    side_view_plan = plan.__class__(
        **{
            **plan.to_dict(),
            "role_assignment": "primary protagonist",
            "role_location": "primary focus area",
            "integrated_scene_prompt": (
                "Dalmatian guide is the primary protagonist and central visual subject, "
                "viewed from the side as it carries the main scene action with black "
                "sunglasses and dalmatian spots."
            ),
            "metadata": {},
        }
    )

    critique = await SeriesVisualSignaturePromptCritic().critique(
        plan=side_view_plan,
        series_visual_signature_profile=profile,
        series_visual_signature_request=request,
        base_visual_brief=_brief(),
    )

    assert critique.passed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "primary_action_clause",
    (
        "observes the solar workflow, viewed from the side",
        "stands by the console, viewed from the side",
    ),
)
async def test_subject_replacement_critic_allows_primary_action_with_side_view_framing(
    primary_action_clause,
):
    profile = _dog_profile()
    request = _request(
        series_visual_signature_mode="subject_replacement",
        series_visual_signature_consistency_mode="off",
    )
    plan = SeriesVisualSignatureScenePlanner().plan_frame_rule(
        base_visual_brief=_brief(),
        series_visual_signature_request=request,
        series_visual_signature_profile=profile,
        expression_decision=VisualExpressionDecision(
            frame_id="f1",
            expression_mode=VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
        ),
    )
    side_view_plan = plan.__class__(
        **{
            **plan.to_dict(),
            "role_assignment": "primary protagonist",
            "role_location": "primary focus area",
            "integrated_scene_prompt": (
                "Dalmatian guide is the primary protagonist and central visual subject; "
                f"it {primary_action_clause} with black sunglasses and dalmatian spots."
            ),
            "metadata": {},
        }
    )

    critique = await SeriesVisualSignaturePromptCritic().critique(
        plan=side_view_plan,
        series_visual_signature_profile=profile,
        series_visual_signature_request=request,
        base_visual_brief=_brief(),
    )

    assert critique.passed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "observer_clause",
    (
        "observes from the side",
        "observing from the side",
        "watches from the side",
        "watching from the side",
        "looks on from the side",
        "looking on from the side",
        "stands by from the side",
        "standing by from the side",
        "guides quietly from the side",
        "guiding quietly from the side",
    ),
)
async def test_subject_replacement_critic_rejects_observer_action_from_side(observer_clause):
    profile = _dog_profile()
    request = _request(
        series_visual_signature_mode="subject_replacement",
        series_visual_signature_consistency_mode="off",
    )
    plan = SeriesVisualSignatureScenePlanner().plan_frame_rule(
        base_visual_brief=_brief(),
        series_visual_signature_request=request,
        series_visual_signature_profile=profile,
        expression_decision=VisualExpressionDecision(
            frame_id="f1",
            expression_mode=VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
        ),
    )
    bad_plan = plan.__class__(
        **{
            **plan.to_dict(),
            "role_assignment": "primary protagonist",
            "role_location": "primary focus area",
            "integrated_scene_prompt": (
                f"Dalmatian guide is the primary protagonist, but it {observer_clause} "
                "while the original reader carries the scene, with black sunglasses "
                "and dalmatian spots."
            ),
            "metadata": {},
        }
    )

    critique = await SeriesVisualSignaturePromptCritic().critique(
        plan=bad_plan,
        series_visual_signature_profile=profile,
        series_visual_signature_request=request,
        base_visual_brief=_brief(),
    )

    assert not critique.passed
    assert "subject_replacement_not_primary" in {issue.code for issue in critique.issues}


@pytest.mark.asyncio
async def test_subject_replacement_critic_rejects_negated_central_subject_language():
    profile = _dog_profile()
    request = _request(
        series_visual_signature_mode="subject_replacement",
        series_visual_signature_consistency_mode="off",
    )
    plan = SeriesVisualSignatureScenePlanner().plan_frame_rule(
        base_visual_brief=_brief(),
        series_visual_signature_request=request,
        series_visual_signature_profile=profile,
        expression_decision=VisualExpressionDecision(
            frame_id="f1",
            expression_mode=VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
        ),
    )
    bad_plan = plan.__class__(
        **{
            **plan.to_dict(),
            "role_assignment": "not the central visual subject",
            "role_location": "beside the original reader",
            "integrated_scene_prompt": (
                "Dalmatian guide is not the central visual subject; it remains "
                "beside the reader with black sunglasses and dalmatian spots."
            ),
            "metadata": {},
        }
    )

    critique = await SeriesVisualSignaturePromptCritic().critique(
        plan=bad_plan,
        series_visual_signature_profile=profile,
        series_visual_signature_request=request,
        base_visual_brief=_brief(),
    )

    assert not critique.passed
    assert "subject_replacement_not_primary" in {issue.code for issue in critique.issues}


@pytest.mark.asyncio
async def test_subject_replacement_planner_repairs_negated_primary_prompt():
    async def llm_service(**_kwargs):
        return {
            "role_assignment": "not the primary subject",
            "role_location": "beside the original reader",
            "integrated_scene_prompt": (
                "Dalmatian guide is not the primary subject; it stays beside the "
                "reader with black sunglasses and dalmatian spots."
            ),
            "role_action": "observe the scene",
            "role_manifestation": "in-scene guide",
        }

    profile = _dog_profile()
    request = _request(
        series_visual_signature_expression_mode="auto",
        series_visual_signature_mode="auto",
        series_visual_signature_consistency_mode="primary_character",
    )

    plans = await SeriesVisualSignatureScenePlanner(llm_service=llm_service).plan_batch(
        base_visual_briefs=(_brief(),),
        series_visual_signature_request=request,
        series_visual_signature_profile=profile,
        expression_decisions=(
            VisualExpressionDecision(
                frame_id="f1",
                expression_mode=VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
            ),
        ),
    )

    prompt = plans[0].integrated_scene_prompt.lower()
    assert "not the primary" not in prompt
    critique = await SeriesVisualSignaturePromptCritic().critique(
        plan=plans[0],
        series_visual_signature_profile=profile,
        series_visual_signature_request=request,
        base_visual_brief=_brief(),
    )
    assert critique.passed


@pytest.mark.asyncio
async def test_subject_replacement_planner_repairs_short_negated_primary_prompt():
    async def llm_service(**_kwargs):
        return {
            "role_assignment": "not the primary",
            "role_location": "primary focus area",
            "integrated_scene_prompt": (
                "Dalmatian guide is not the primary; it carries black sunglasses "
                "and dalmatian spots into the main scene."
            ),
            "role_action": "observe the scene",
            "role_manifestation": "in-scene guide",
        }

    profile = _dog_profile()
    request = _request(
        series_visual_signature_expression_mode="auto",
        series_visual_signature_mode="auto",
        series_visual_signature_consistency_mode="primary_character",
    )

    plans = await SeriesVisualSignatureScenePlanner(llm_service=llm_service).plan_batch(
        base_visual_briefs=(_brief(),),
        series_visual_signature_request=request,
        series_visual_signature_profile=profile,
        expression_decisions=(
            VisualExpressionDecision(
                frame_id="f1",
                expression_mode=VisualExpressionMode.PORTRAIT_OR_HOST_SCENE,
            ),
        ),
    )

    prompt = plans[0].integrated_scene_prompt.lower()
    assert "not the primary" not in prompt
    critique = await SeriesVisualSignaturePromptCritic().critique(
        plan=plans[0],
        series_visual_signature_profile=profile,
        series_visual_signature_request=request,
        base_visual_brief=_brief(),
    )
    assert critique.passed
