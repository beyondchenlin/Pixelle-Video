import pytest

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.series_visual_signature_presentation import SeriesVisualSignaturePresentationPolicy
from pixelle_video.models.visual_anchor_planning import AnchorCarrierType
from pixelle_video.services.series_visual_signature_anchor_planner import VisualAnchorIntegrationPlanner


class _FakePartialLLM:
    async def __call__(self, **kwargs):
        return {
            "visual_anchor_integration_plans": [
                {
                    "frame_id": "frame_2",
                    "carrier_type": "minor_supporting_character",
                    "anchor_function": "co_present_support",
                    "prominence": "small_side_character",
                    "style_relation": "blended",
                    "placement": "主体旁边的前景地面",
                    "support_anchor": "前景地面",
                    "contact_relation": "站在地面上",
                    "interaction_target": "主角",
                    "occlusion_relation": "main subject remains readable",
                    "visual_weight_clause": "visible but subordinate",
                    "image_prompt_clause": "一只戴黑色墨镜的斑点狗站在主体旁边的前景地面上，不替代主体。",
                    "integrated_scene_prompt": "一只戴黑色墨镜的斑点狗站在主体旁边的前景地面上，不替代主体。",
                    "integration_strategy": "supporting_integration",
                }
            ]
        }


def _profile() -> IPProfile:
    return IPProfile(
        series_visual_signature_profile_id="dog_1",
        workspace_id="workspace_1",
        project_id="project_1",
        name="戴黑色墨镜的斑点狗",
        visual_summary="戴黑色墨镜的斑点狗",
        identity_lock=("黑色墨镜", "斑点狗"),
        identity_anchors=("戴黑色墨镜的斑点狗",),
        minimal_traits=("斑点狗", "黑色墨镜"),
    )


def _brief(frame_id: str) -> BaseVisualBrief:
    return BaseVisualBrief(
        frame_id=frame_id,
        core_message="主角在书桌前思考",
        visual_moment="室内书桌旁的沉思场景",
        setting="室内房间，书桌，书本",
        spatial_layout="主体在中央，桌边和前景留白",
        base_image_prompt="一个人在书桌旁思考，前景有地面和桌边",
        key_props_symbols=("书桌", "书本"),
    )


@pytest.mark.asyncio
async def test_planner_preserves_valid_frame_and_fallbacks_only_failed_frame():
    policy = SeriesVisualSignaturePresentationPolicy.from_mapping(
        {"series_visual_signature_presentation_mode": "visible_supporting_character"}
    )
    plans = await VisualAnchorIntegrationPlanner(
        llm_service=_FakePartialLLM(),
        presentation_policy=policy,
        max_repair_attempts=0,
    ).plan_batch(
        base_visual_briefs=(_brief("frame_1"), _brief("frame_2")),
        anchor_profile=_profile(),
    )

    assert [plan.frame_id for plan in plans] == ["frame_1", "frame_2"]
    assert plans[0].metadata.get("fallback_applied") is True
    assert plans[1].metadata.get("fallback_applied") is not True
    assert plans[0].anchor_carrier_type is AnchorCarrierType.MINOR_SUPPORTING_CHARACTER
    assert "斑点狗" in plans[0].image_prompt_clause
