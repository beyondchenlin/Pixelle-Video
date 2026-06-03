import json
from dataclasses import replace

import pytest

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.series_visual_signature_planning import (
    SeriesVisualSignatureCritique,
    SeriesVisualSignaturePromptIssue,
)
from pixelle_video.models.series_visual_signature_profile import SeriesVisualSignatureProfile
from pixelle_video.models.series_visual_signature_request import (
    SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION,
    SeriesVisualSignatureRequest,
)
from pixelle_video.models.visual_expression import VisualExpressionDecision, VisualExpressionMode
from pixelle_video.services.series_visual_signature_prompt_projector import (
    SeriesVisualSignaturePromptProjectionError,
    SeriesVisualSignaturePromptProjector,
)
from pixelle_video.services.series_visual_signature_scene_planner import (
    SeriesVisualSignatureScenePlanner,
)
from pixelle_video.services.visual_prompt_planning_service import VisualPromptPlanningService


def _request():
    return SeriesVisualSignatureRequest.from_mapping({
        "series_visual_signature_enabled": True,
        "series_visual_signature_asset_bible_id": "asset",
        "series_visual_signature_profile_id": "sparrow",
        "series_visual_signature_expression_mode": "explanatory_diagram",
        "series_visual_signature_structure_mode": "workflow",
        "series_visual_signature_participation_mode": "guide_explainer",
        "series_visual_signature_mode": "supporting_integration",
    })


def _profile():
    return SeriesVisualSignatureProfile(
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
async def test_visual_prompt_planning_routes_v4_to_series_visual_signature_projector():
    result = await VisualPromptPlanningService().plan_image_prompts(
        base_prompts=("工程师讲解太阳能板发电流程",),
        frame_contexts=({"frame_id": "f1", "source_text": "太阳能发电原理"},),
        series_visual_signature_request=_request(),
        series_visual_signature_profile=_profile(),
    )

    assert len(result.rendered_prompts) == 1
    assert result.series_visual_signature_plans == ()
    assert result.series_visual_signature_critiques == ()
    assert result.rendered_prompts[0].renderer_id == "provider_prompt_projector_z_image"
    snapshot = result.planning_snapshot()
    assert "series_visual_signature_request" in snapshot
    assert "series_visual_signature_profile" in snapshot
    assert "series_visual_signature_plan_by_frame" not in snapshot
    assert snapshot["series_visual_signature_request"][
        "series_visual_signature_structure_mode"
    ] == "workflow"
    assert snapshot["series_visual_signature_request"][
        "series_visual_signature_participation_mode"
    ] == "guide_explainer"
    json.dumps(snapshot, ensure_ascii=False)


@pytest.mark.asyncio
async def test_visual_prompt_planning_keeps_legacy_pipeline_version_on_v4_route():
    result = await VisualPromptPlanningService().plan_image_prompts(
        base_prompts=("legacy series visual signature route",),
        frame_contexts=({"frame_id": "f1", "source_text": "legacy request"},),
        series_visual_signature_request=replace(
            _request(),
            pipeline_version=SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION,
        ),
        series_visual_signature_profile=_profile(),
    )

    assert result.series_visual_signature_plans == ()
    assert result.rendered_prompts[0].renderer_id == "provider_prompt_projector_z_image"
    assert result.planning_snapshot()["series_visual_signature_request"][
        "pipeline_version"
    ] == SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION


def test_v4_projector_raises_when_critic_not_passed():
    brief = BaseVisualBrief(frame_id="f1", core_message="讲解太阳能原理", visual_moment="工程师在实验室展示太阳能板发电流程", main_subjects=("工程师",))
    plan = SeriesVisualSignatureScenePlanner().plan_frame_rule(
        base_visual_brief=brief,
        series_visual_signature_request=_request(),
        series_visual_signature_profile=_profile(),
        expression_decision=VisualExpressionDecision(frame_id="f1", expression_mode=VisualExpressionMode.EXPLANATORY_DIAGRAM),
    )
    critique = SeriesVisualSignatureCritique(frame_id="f1", issues=(SeriesVisualSignaturePromptIssue("role_missing", "blocking", "missing", "repair"),))

    with pytest.raises(SeriesVisualSignaturePromptProjectionError):
        SeriesVisualSignaturePromptProjector().project(
            base_visual_brief=brief,
            series_visual_signature_plan=plan,
            series_visual_signature_critique=critique,
            series_visual_signature_request=_request(),
            series_visual_signature_profile=_profile(),
        )
