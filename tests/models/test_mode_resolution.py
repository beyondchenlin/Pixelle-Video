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


@pytest.mark.parametrize("field_name", ["strict_user_mode", "force_v44_planning"])
def test_request_rejects_unknown_boolean_strings(field_name):
    with pytest.raises(ValueError, match=field_name):
        ArticleVisualPlanningRequest.from_mapping({field_name: "maybe"})


@pytest.mark.parametrize("field_name", ["strict_user_mode", "force_v44_planning"])
def test_preflight_rejects_unknown_boolean_strings(field_name):
    kwargs = {
        "preflight_id": "preflight_v44_001",
        "requested": ArticleVisualPlanningRequest.from_mapping({}),
        "normalized_article_mode": "auto",
        "normalized_visual_mode": "auto",
        "normalized_visual_role_strategy": "auto",
        "strict_user_mode": False,
        "force_v44_planning": False,
        "explicit_fields": (),
        "legacy_fallback_candidate": True,
    }
    kwargs[field_name] = "maybe"

    with pytest.raises(ValueError, match=field_name):
        ArticleVisualPlanningPreflight(**kwargs)


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
        requested_article_mode="process_method",
        requested_visual_mode="process_walkthrough",
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
    assert payload["requested_article_mode"] == "process_method"
    assert payload["requested_visual_mode"] == "process_walkthrough"
    assert payload["requested_visual_role_strategy"] == "host_explainer"
    assert "requested_article_understanding_mode" not in payload
    assert "requested_visual_planning_mode" not in payload
    assert decision.requested_article_understanding_mode is ArticleUnderstandingMode.PROCESS_METHOD
    assert decision.requested_visual_planning_mode is VisualPlanningMode.PROCESS_WALKTHROUGH
    assert payload["resolved_primary_lens"] == "process_method"
    assert payload["resolved_secondary_lenses"] == ["causal_mechanism"]
    assert payload["resolved_visual_planning_mode"] == "process_walkthrough"
    assert payload["resolved_visual_role_strategy"] == "host_explainer"
    assert payload["primary_visual_task"] == "process_walkthrough"
    assert payload["secondary_visual_tasks"] == ["structure_explanation"]
    assert payload["mismatch_warnings"] == ["none"]
    json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize(
    "resolution_status",
    ["resolved", "low_confidence", "planner_failed", "fallback_used"],
)
def test_route_decision_accepts_stable_resolution_statuses(resolution_status):
    decision = VisualPlanningRouteDecision(
        route_decision_id=f"route_{resolution_status}",
        frame_id="frame_1",
        preflight_id="preflight_v44_001",
        requested_article_mode="auto",
        requested_visual_mode="auto",
        requested_visual_role_strategy="auto",
        resolved_primary_lens="thesis_argument",
        resolved_secondary_lenses=(),
        resolved_visual_planning_mode="auto",
        resolved_visual_role_strategy="auto",
        primary_visual_task="cognitive_explanation",
        secondary_visual_tasks=(),
        confidence=0.7,
        decision_reason="status contract check",
        resolution_status=resolution_status,
        fallback_eligible=False,
        fallback_used=resolution_status == "fallback_used",
        fallback_target=None,
        fallback_reason=None,
    )

    assert decision.resolution_status == resolution_status
    assert decision.to_dict()["resolution_status"] == resolution_status


@pytest.mark.parametrize("resolution_status", ["not_a_valid_status", "", "   ", None])
def test_route_decision_rejects_invalid_resolution_statuses(resolution_status):
    with pytest.raises((TypeError, ValueError), match="resolution_status"):
        VisualPlanningRouteDecision(
            route_decision_id="route_invalid_status",
            frame_id="frame_1",
            preflight_id="preflight_v44_001",
            requested_article_mode="auto",
            requested_visual_mode="auto",
            requested_visual_role_strategy="auto",
            resolved_primary_lens="thesis_argument",
            resolved_secondary_lenses=(),
            resolved_visual_planning_mode="auto",
            resolved_visual_role_strategy="auto",
            primary_visual_task="cognitive_explanation",
            secondary_visual_tasks=(),
            confidence=0.7,
            decision_reason="status contract check",
            resolution_status=resolution_status,
            fallback_eligible=False,
            fallback_used=False,
            fallback_target=None,
            fallback_reason=None,
        )


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
        requested_article_mode=ArticleUnderstandingMode.AUTO,
        requested_visual_mode=VisualPlanningMode.AUTO,
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


def test_fallback_helper_false_when_legacy_fallback_not_candidate():
    request = ArticleVisualPlanningRequest.from_mapping({})
    preflight = ArticleVisualPlanningPreflight.from_request(
        request,
        explicit_fields=(),
        legacy_fallback_candidate=False,
    )

    assert not should_use_v42_compatibility_path(
        preflight,
        [],
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
            requested_article_mode="auto",
            requested_visual_mode="auto",
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


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("requested_article_mode", "not_a_mode"),
        ("requested_visual_mode", "not_a_mode"),
        ("requested_visual_role_strategy", "not_a_strategy"),
    ],
)
def test_route_decision_rejects_invalid_requested_modes_and_strategy(
    field_name,
    value,
):
    kwargs = _route_decision_kwargs()
    kwargs[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        VisualPlanningRouteDecision(**kwargs)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("resolved_primary_lens", "not_a_lens"),
        ("resolved_secondary_lenses", ["not_a_lens"]),
        ("resolved_visual_planning_mode", "not_a_mode"),
        ("resolved_visual_role_strategy", "not_a_strategy"),
        ("primary_visual_task", "not_a_task"),
        ("secondary_visual_tasks", ["not_a_task"]),
    ],
)
def test_route_decision_rejects_invalid_resolved_modes_lenses_and_tasks(
    field_name,
    value,
):
    kwargs = _route_decision_kwargs()
    kwargs[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        VisualPlanningRouteDecision(**kwargs)


def test_mode_resolution_exports_public_contracts():
    assert set(mode_resolution.__all__) == {
        "ArticleVisualPlanningPreflight",
        "ArticleVisualPlanningRequest",
        "VisualPlanningRouteDecision",
        "should_use_v42_compatibility_path",
    }


def _route_decision_kwargs():
    return {
        "route_decision_id": "route_frame_1",
        "frame_id": "frame_1",
        "preflight_id": "preflight_v44_001",
        "requested_article_mode": "auto",
        "requested_visual_mode": "auto",
        "requested_visual_role_strategy": "auto",
        "resolved_primary_lens": "thesis_argument",
        "resolved_secondary_lenses": (),
        "resolved_visual_planning_mode": "auto",
        "resolved_visual_role_strategy": "auto",
        "primary_visual_task": "cognitive_explanation",
        "secondary_visual_tasks": (),
        "confidence": 0.7,
        "decision_reason": "planner check",
        "resolution_status": "resolved",
        "fallback_eligible": False,
        "fallback_used": False,
        "fallback_target": None,
        "fallback_reason": None,
    }
