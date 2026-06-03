import asyncio

import pytest

from pixelle_video.models.asset_bible import IPProfile, IPRenderingStyle
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_anchor_integration import (
    VisualAnchorIntegrationCandidateResponse,
    VisualAnchorIntegrationPlanResponse,
    VisualAnchorIntegrationResponse,
)
from pixelle_video.models.visual_anchor_planning import AnchorProminence
from pixelle_video.services.series_visual_signature_anchor_planner import (
    VisualAnchorIntegrationPlanner,
)


class ValidSceneBoundLLM:
    async def __call__(self, **kwargs):
        return VisualAnchorIntegrationResponse(
            visual_anchor_integration_plans=[
                VisualAnchorIntegrationPlanResponse(
                    frame_id="f1",
                    candidates=[
                        VisualAnchorIntegrationCandidateResponse(
                            carrier_type="bookplate_or_stamp",
                            anchor_function="material_signature",
                            prominence="embedded_mark",
                            style_relation="blended",
                            placement="attached to the inner paper margin of the open page",
                            support_anchor="打开的书页纸面",
                            contact_relation="压印进纸张纹理",
                            interaction_target="书页",
                            occlusion_relation="主体阅读区域保持清晰",
                            visual_weight_clause="低对比、低存在感，作为纸面材质细节",
                            image_prompt_clause="白色科技兔子轮廓浅压印纹章，带蓝色领结和长耳朵，像安静的藏书票细节",
                            scene_coherence_score=10,
                            disruption_risk=1,
                            identity_preservation_score=9,
                            reason="low disruption",
                        )
                    ],
                    selected_index=0,
                )
            ]
        )


class RejectedOverlayLLM:
    async def __call__(self, **kwargs):
        return {
            "visual_anchor_integration_plans": [
                {
                    "frame_id": "f1",
                    "candidates": [
                        {
                            "carrier_type": "printed_mark",
                            "anchor_function": "material_signature",
                            "prominence": "embedded_mark",
                            "style_relation": "blended",
                            "placement": "画面右下角",
                            "support_anchor": "画面角落",
                            "contact_relation": "悬浮在画面上",
                            "image_prompt_clause": "右下角蓝领结白兔logo角标",
                            "scene_coherence_score": 10,
                            "disruption_risk": 1,
                            "identity_preservation_score": 9,
                            "reason": "bad overlay",
                        }
                    ],
                    "selected_index": 0,
                }
            ]
        }


class MalformedButJsonLLM:
    async def __call__(self, **kwargs):
        return {
            "visual_anchor_integration_plans": [
                {
                    "frame_id": "f1",
                    "affordance": None,
                    "candidates": "selected_index",
                    "selected_index": "0",
                }
            ]
        }


def _profile() -> IPProfile:
    return IPProfile(
        series_visual_signature_profile_id="rabbit",
        workspace_id="ws",
        project_id="prj",
        name="科技兔子",
        rendering_style=IPRenderingStyle.STYLIZED_CHARACTER,
        visual_summary="一只白色科技兔子，蓝色领结，长耳朵，圆润脸型",
    )


def _book_brief() -> BaseVisualBrief:
    return BaseVisualBrief(
        frame_id="f1",
        core_message="书籍介绍",
        visual_moment="一本打开的书页展示家族故事。",
        main_subjects=("《百年孤独》书页",),
        anchor_affordances=("打开的书页纸面",),
        base_image_prompt="一本打开的书页展示家族故事。",
    )


def test_series_visual_signature_anchor_planner_uses_scene_bound_llm_candidate():
    plans = asyncio.run(
        VisualAnchorIntegrationPlanner(llm_service=ValidSceneBoundLLM()).plan_batch(
            base_visual_briefs=(_book_brief(),),
            anchor_profile=_profile(),
        )
    )

    assert plans[0].visible
    assert plans[0].anchor_prominence is AnchorProminence.EMBEDDED_MARK
    assert "白色科技兔子" in plans[0].image_prompt_clause
    assert "蓝色领结" in plans[0].image_prompt_clause
    assert "压印" in plans[0].image_prompt_clause
    assert "角标" not in plans[0].image_prompt_clause
    assert "水印" not in plans[0].image_prompt_clause
    assert plans[0].metadata["source"] == "llm_mandatory_series_visual_signature_integration"


def test_series_visual_signature_anchor_planner_rejects_overlay_candidate_fail_closed():
    with pytest.raises(ValueError, match="forbidden overlay"):
        asyncio.run(
            VisualAnchorIntegrationPlanner(llm_service=RejectedOverlayLLM()).plan_batch(
                base_visual_briefs=(_book_brief(),),
                anchor_profile=_profile(),
            )
        )


def test_series_visual_signature_anchor_planner_repairs_malformed_json_fail_closed():
    with pytest.raises(ValueError, match="candidates must be an array"):
        asyncio.run(
            VisualAnchorIntegrationPlanner(llm_service=MalformedButJsonLLM()).plan_batch(
                base_visual_briefs=(_book_brief(),),
                anchor_profile=_profile(),
            )
        )


def test_series_visual_signature_anchor_planner_rejects_non_callable_llm_service():
    with pytest.raises(ValueError, match="callable llm_service"):
        asyncio.run(
            VisualAnchorIntegrationPlanner(llm_service=object()).plan_batch(
                base_visual_briefs=(_book_brief(),),
                anchor_profile=_profile(),
            )
        )
