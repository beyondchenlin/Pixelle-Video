import json

import pytest

from pixelle_video.models import mode_resolution
from pixelle_video.models.article_understanding import (
    ArticleUnderstandingLens,
    ArticleUnderstandingMode,
)
from pixelle_video.models.mode_resolution import (
    ArticleVisualPlanningPreflight,
    ArticleVisualPlanningRequest,
    VisualPlanningRouteDecision,
    should_use_v42_compatibility_path,
)
from pixelle_video.models.visual_planning_mode import (
    PrimaryVisualTask,
    VisualPlanningMode,
)
from pixelle_video.models.visual_role_strategy import VisualRoleStrategy


def test_request_normalizes_invalid_and_visual_role_terms():
    request = ArticleVisualPlanningRequest.from_mapping(
        {
            "article_understanding_mode": "not_a_mode",
            "visual_planning_mode": "host_explainer",
            "visual_role_strategy": "observer_guide",
            "user_intent_hint": "  explain policy change  ",
            "allow_mixed_lenses": "false",
            "strict_user_mode": "true",
            "force_v44_planning": 1,
        }
    )

    assert request.article_understanding_mode is ArticleUnderstandingMode.AUTO
    assert request.visual_planning_mode is VisualPlanningMode.AUTO
    assert request.visual_role_strategy is VisualRoleStrategy.OBSERVER_GUIDE
    assert request.user_intent_hint == "explain policy change"
    assert request.allow_mixed_lenses is False
    assert request.strict_user_mode is True
    assert request.force_v44_planning is True
    assert request.to_dict() == {
        "article_understanding_mode": "auto",
        "visual_planning_mode": "auto",
        "visual_role_strategy": "observer_guide",
        "user_intent_hint": "explain policy change",
        "allow_mixed_lenses": False,
        "strict_user_mode": True,
        "force_v44_planning": True,
    }


def test_preflight_serializes_trimmed_explicit_fields_and_legacy_flag():
    request = ArticleVisualPlanningRequest.from_mapping(
        {
            "article_understanding_mode": "causal_mechanism",
            "strict_user_mode": True,
        }
    )

    preflight = ArticleVisualPlanningPreflight.from_request(
        request,
        explicit_fields=[" visual_planning_mode ", "", "strict_user_mode"],
        legacy_fallback_candidate=True,
        validation_warnings=[" low context ", ""],
    )

    payload = preflight.to_dict()

    assert preflight.preflight_id.startswith("preflight_")
    assert preflight.explicit_fields == ("visual_planning_mode", "strict_user_mode")
    assert payload["legacy_fallback_candidate"] is True
    assert payload["validation_warnings"] == ["low context"]
    assert payload["normalized_article_mode"] == "causal_mechanism"
    json.dumps(payload, allow_nan=False)


def test_route_decision_serializes_normalized_values():
    decision = VisualPlanningRouteDecision(
        route_decision_id="route_frame_1",
        frame_id="frame_1",
        preflight_id="preflight_v44_001",
        requested_article_understanding_mode="process_method",
        requested_visual_planning_mode="process_walkthrough",
        requested_visual_role_strategy="host_explainer",
        resolved_primary_lens="process_method",
        resolved_secondary_lenses=[ArticleUnderstandingLens.CAUSAL_MECHANISM],
        resolved_visual_planning_mode=VisualPlanningMode.PROCESS_WALKTHROUGH,
        resolved_visual_role_strategy=VisualRoleStrategy.HOST_EXPLAINER,
        primary_visual_task="process_walkthrough",
        secondary_visual_tasks=[PrimaryVisualTask.STRUCTURE_EXPLANATION],
        confidence=0.82,
        decision_reason="planner matched process lens",
        resolution_status="resolved",
        fallback_eligible=False,
        fallback_used=False,
        fallback_target=None,
        fallback_reason=None,
        mismatch_warnings=["  none  "],
    )

    payload = decision.to_dict()

    assert payload["route_decision_id"] == "route_frame_1"
    assert payload["resolution_status"] == "resolved"
    assert payload["fallback_target"] is None
    assert payload["requested_article_understanding_mode"] == "process_method"
    assert payload["requested_visual_planning_mode"] == "process_walkthrough"
    assert payload["requested_visual_role_strategy"] == "host_explainer"
    assert payload["resolved_primary_lens"] == "process_method"
    assert payload["resolved_secondary_lenses"] == ["causal_mechanism"]
    assert payload["resolved_visual_planning_mode"] == "process_walkthrough"
    assert payload["resolved_visual_role_strategy"] == "host_explainer"
    assert payload["primary_visual_task"] == "process_walkthrough"
    assert payload["secondary_visual_tasks"] == ["structure_explanation"]
    assert payload["mismatch_warnings"] == ["none"]
    json.dumps(payload, allow_nan=False)


def test_fallback_helper_allows_low_confidence_planner_failed_decisions():
    request = ArticleVisualPlanningRequest.from_mapping({})
    preflight = ArticleVisualPlanningPreflight.from_request(
        request,
        explicit_fields=(),
        legacy_fallback_candidate=True,
    )
    decision = VisualPlanningRouteDecision(
        route_decision_id="route_frame_1",
        frame_id="frame_1",
        preflight_id=preflight.preflight_id,
        requested_article_understanding_mode=ArticleUnderstandingMode.AUTO,
        requested_visual_planning_mode=VisualPlanningMode.AUTO,
        requested_visual_role_strategy=VisualRoleStrategy.AUTO,
        resolved_primary_lens="thesis_argument",
        resolved_secondary_lenses=(),
        resolved_visual_planning_mode=VisualPlanningMode.AUTO,
        resolved_visual_role_strategy=VisualRoleStrategy.AUTO,
        primary_visual_task="cognitive_explanation",
        secondary_visual_tasks=(),
        confidence=0.2,
        decision_reason="planner confidence below threshold",
        resolution_status="planner_failed",
        fallback_eligible=True,
        fallback_used=False,
        fallback_target="v4.2_visual_role_path",
        fallback_reason="insufficient context",
    )

    assert should_use_v42_compatibility_path(
        preflight,
        [decision],
        article_context_insufficient=True,
        legacy_visual_role_request_present=True,
    )


def test_fallback_helper_false_for_force_v44_or_explicit_non_auto_request():
    forced_request = ArticleVisualPlanningRequest.from_mapping({"force_v44_planning": True})
    forced_preflight = ArticleVisualPlanningPreflight.from_request(
        forced_request,
        explicit_fields=(),
        legacy_fallback_candidate=True,
    )
    explicit_request = ArticleVisualPlanningRequest.from_mapping(
        {"visual_role_strategy": "signature_presence"}
    )
    explicit_preflight = ArticleVisualPlanningPreflight.from_request(
        explicit_request,
        explicit_fields=("visual_role_strategy",),
        legacy_fallback_candidate=True,
    )

    assert not should_use_v42_compatibility_path(
        forced_preflight,
        [],
        article_context_insufficient=True,
        legacy_visual_role_request_present=True,
    )
    assert not should_use_v42_compatibility_path(
        explicit_preflight,
        [],
        article_context_insufficient=True,
        legacy_visual_role_request_present=True,
    )


@pytest.mark.parametrize(
    "confidence",
    [True, -0.1, 1.1, float("nan"), float("inf"), float("-inf")],
)
def test_route_decision_rejects_invalid_confidence(confidence):
    with pytest.raises((TypeError, ValueError), match="confidence"):
        VisualPlanningRouteDecision(
            route_decision_id="route_frame_1",
            frame_id="frame_1",
            preflight_id="preflight_v44_001",
            requested_article_understanding_mode="auto",
            requested_visual_planning_mode="auto",
            requested_visual_role_strategy="auto",
            resolved_primary_lens="thesis_argument",
            resolved_secondary_lenses=(),
            resolved_visual_planning_mode="auto",
            resolved_visual_role_strategy="auto",
            primary_visual_task="cognitive_explanation",
            secondary_visual_tasks=(),
            confidence=confidence,
            decision_reason="planner failed",
            resolution_status="planner_failed",
            fallback_eligible=True,
            fallback_used=False,
            fallback_target="v4.2_visual_role_path",
            fallback_reason="insufficient context",
        )


def test_mode_resolution_exports_public_contracts():
    assert set(mode_resolution.__all__) == {
        "ArticleVisualPlanningPreflight",
        "ArticleVisualPlanningRequest",
        "VisualPlanningRouteDecision",
        "should_use_v42_compatibility_path",
    }
