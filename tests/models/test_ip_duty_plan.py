from pixelle_video.models.ip_duty import (
    IPDutyPreset,
    IPPresentationForm,
    build_default_ip_duty_plan,
    compact_ip_duty_payload,
    duty_from_route_type,
)
from pixelle_video.models.visual_story_engine import FrameIPFusionPlan


def test_route_to_duty_keeps_rich_preset():
    assert duty_from_route_type("archive_investigation") is IPDutyPreset.EVIDENCE_CURATOR
    assert duty_from_route_type("emotional_theater") is IPDutyPreset.EMOTIONAL_PROXY
    assert duty_from_route_type("mechanical_cutaway") is IPDutyPreset.MECHANIC_REPAIRER


def test_unknown_route_defaults_to_background_signature():
    assert duty_from_route_type(None) is IPDutyPreset.BACKGROUND_SIGNATURE
    assert duty_from_route_type("unclassified_route") is IPDutyPreset.BACKGROUND_SIGNATURE


def test_default_duty_plan_has_source_of_truth_fields():
    plan = build_default_ip_duty_plan(
        frame_id="f1",
        route_type="process_map",
        local_claim="戴黑色墨镜的斑点狗轮廓参与流程说明",
    )
    assert plan.duty_preset is IPDutyPreset.OPERATOR_DEMONSTRATOR
    assert plan.action_verb
    assert plan.interaction_target
    assert plan.scene_binding
    assert plan.presentation_form is not IPPresentationForm.AUTO
    payload = compact_ip_duty_payload(plan)
    assert payload["ip_duty_preset"] == "operator_demonstrator"
    assert payload["action_verb"] == plan.action_verb


def test_frame_ip_fusion_plan_round_trips_duty_fields():
    plan = FrameIPFusionPlan.deterministic(
        frame_id="f2",
        route_type="archive_investigation",
        ip_role="guide_explainer",
        risk_text="真实人物 纪实",
    )
    payload = plan.to_dict()
    assert payload["ip_duty_preset"] == "background_signature"
    assert payload["action_verb"]
    assert payload["interaction_target"]
    assert payload["scene_binding"]
    restored = FrameIPFusionPlan.from_mapping(payload)
    assert restored.ip_duty_preset == "background_signature"
    assert restored.channel_identity_removal_test
