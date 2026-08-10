from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.series_visual_signature_presentation import (
    SeriesVisualSignaturePresentationPolicy,
)
from pixelle_video.models.visual_anchor_planning import AnchorCarrierType
from pixelle_video.services.visual_signature_fallback_planner import (
    VisualSignatureFallbackPlanner,
    fallback_ledger_from_plans,
)


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
        core_message="主角在书桌前思考孤独与记忆",
        visual_moment="室内书桌旁的沉思场景",
        setting="室内房间，书桌，书本",
        spatial_layout="主体在中央，桌边和前景留白",
        base_image_prompt="一个人在书桌旁思考，前景有地面和桌边",
        key_props_symbols=("书桌", "书本"),
    )


def test_visible_supporting_character_fallback_keeps_identity_and_real_character():
    policy = SeriesVisualSignaturePresentationPolicy.from_mapping(
        {"series_visual_signature_presentation_mode": "visible_supporting_character"}
    )
    plans = VisualSignatureFallbackPlanner(
        anchor_profile=_profile(),
        presentation_policy=policy,
        identity_kernel=("黑色墨镜", "斑点狗", "戴黑色墨镜的斑点狗"),
    ).plan_failed_frames(
        base_visual_briefs=(_brief("frame_1"),),
        failed_frame_ids=("frame_1",),
        failure_reasons_by_frame={"frame_1": ["missing carrier"]},
    )

    assert len(plans) == 1
    plan = plans[0]
    assert plan.anchor_carrier_type is AnchorCarrierType.MINOR_SUPPORTING_CHARACTER
    assert "斑点狗" in plan.image_prompt_clause
    assert "黑色墨镜" in plan.image_prompt_clause
    assert "不替代主体" in plan.image_prompt_clause
    assert plan.metadata["fallback_applied"] is True


def test_fallback_ledger_records_frame_level_fallback():
    policy = SeriesVisualSignaturePresentationPolicy.from_mapping(
        {"series_visual_signature_presentation_mode": "visible_supporting_character"}
    )
    plans = VisualSignatureFallbackPlanner(
        anchor_profile=_profile(),
        presentation_policy=policy,
    ).plan_failed_frames(
        base_visual_briefs=(_brief("frame_1"), _brief("frame_2")),
        failed_frame_ids=("frame_2",),
        failure_reasons_by_frame={"frame_2": ["supporting_integration requires a concrete in-scene carrier"]},
    )

    ledger = fallback_ledger_from_plans(plans)
    assert ledger["fallback_applied"] is True
    assert ledger["fallback_count"] == 1
    assert ledger["entries"][0]["frame_id"] == "frame_2"
