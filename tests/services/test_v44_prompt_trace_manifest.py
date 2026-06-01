import json

import pytest

from pixelle_video.models.article_understanding import ArticleUnderstandingLens
from pixelle_video.models.mode_resolution import VisualPlanningRouteDecision
from pixelle_video.models.visual_planning_mode import PrimaryVisualTask, VisualPlanningMode
from pixelle_video.models.visual_role_strategy import VisualRoleStrategy
from pixelle_video.services.v44_prompt_trace_manifest import (
    build_v44_prompt_trace_manifest,
    write_v44_prompt_trace_manifest,
)


def test_manifest_collects_route_ids_resolved_modes_fallbacks_and_payloads():
    first = _route_decision(
        route_decision_id="route-frame-1",
        frame_id="frame-1",
        resolved_primary_lens=ArticleUnderstandingLens.PROCESS_METHOD,
        resolved_visual_planning_mode=VisualPlanningMode.PROCESS_WALKTHROUGH,
        resolved_visual_role_strategy=VisualRoleStrategy.HOST_EXPLAINER,
    )
    second = _route_decision(
        route_decision_id="route-frame-2",
        frame_id="frame-2",
        resolution_status="planner_failed",
        fallback_used=False,
        fallback_target="v4.2_visual_role_path",
        fallback_reason="article context insufficient",
    )

    manifest = build_v44_prompt_trace_manifest(
        article_id="article-1",
        frame_ids=["frame-1", "frame-2"],
        requested_modes={
            "article_understanding_mode": "process_method",
            "visual_planning_mode": "process_walkthrough",
            "visual_role_strategy": "host_explainer",
        },
        route_decisions=[first, second],
        critic_status="passed",
        repair_rounds=1,
    )

    assert manifest["schema_version"] == "v4.4"
    assert manifest["article_id"] == "article-1"
    assert manifest["frames"] == ["frame-1", "frame-2"]
    assert manifest["resolved_modes"] == {
        "primary_lens": "process_method",
        "visual_planning_mode": "process_walkthrough",
        "visual_role_strategy": "host_explainer",
    }
    assert manifest["route_decision_ids"] == {
        "frame-1": "route-frame-1",
        "frame-2": "route-frame-2",
    }
    assert manifest["fallbacks"] == [
        {
            "frame_id": "frame-2",
            "route_decision_id": "route-frame-2",
            "fallback_target": "v4.2_visual_role_path",
            "fallback_reason": "article context insufficient",
            "resolution_status": "planner_failed",
        }
    ]
    assert manifest["route_decisions"] == [first.to_dict(), second.to_dict()]
    json.dumps(manifest, allow_nan=False)


def test_manifest_uses_none_resolved_modes_without_route_decisions():
    manifest = build_v44_prompt_trace_manifest(
        article_id="article-1",
        frame_ids=["frame-1"],
        requested_modes={
            "article_understanding_mode": "auto",
            "visual_planning_mode": "auto",
            "visual_role_strategy": "auto",
        },
        route_decisions=[],
        critic_status="skipped",
        repair_rounds=0,
    )

    assert manifest["resolved_modes"] == {
        "primary_lens": None,
        "visual_planning_mode": None,
        "visual_role_strategy": None,
    }
    assert manifest["route_decision_ids"] == {}
    assert manifest["fallbacks"] == []
    assert manifest["route_decisions"] == []


def test_manifest_detaches_requested_modes_from_input_mutation():
    requested_modes = {
        "article_understanding_mode": "auto",
        "visual_planning_mode": "auto",
        "visual_role_strategy": "auto",
        "nested": {"value": ["original"]},
    }

    manifest = build_v44_prompt_trace_manifest(
        article_id="article-1",
        frame_ids=["frame-1"],
        requested_modes=requested_modes,
        route_decisions=[],
        critic_status="passed",
        repair_rounds=0,
    )
    requested_modes["nested"]["value"].append("mutated")

    assert manifest["requested_modes"]["nested"]["value"] == ["original"]


@pytest.mark.parametrize("requested_modes", [[], "auto"])
def test_manifest_rejects_non_mapping_requested_modes(requested_modes):
    with pytest.raises((TypeError, ValueError), match="requested_modes"):
        build_v44_prompt_trace_manifest(
            article_id="article-1",
            frame_ids=["frame-1"],
            requested_modes=requested_modes,
            route_decisions=[],
            critic_status="passed",
            repair_rounds=0,
        )


@pytest.mark.parametrize("requested_modes", [{1: "auto"}, {"": "auto"}, {"   ": "auto"}])
def test_manifest_rejects_invalid_requested_mode_keys(requested_modes):
    with pytest.raises((TypeError, ValueError), match="requested_modes"):
        build_v44_prompt_trace_manifest(
            article_id="article-1",
            frame_ids=["frame-1"],
            requested_modes=requested_modes,
            route_decisions=[],
            critic_status="passed",
            repair_rounds=0,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_manifest_rejects_non_finite_requested_mode_values(value):
    with pytest.raises((TypeError, ValueError), match="requested_modes|JSON|finite"):
        build_v44_prompt_trace_manifest(
            article_id="article-1",
            frame_ids=["frame-1"],
            requested_modes={"article_understanding_mode": value},
            route_decisions=[],
            critic_status="passed",
            repair_rounds=0,
        )


def test_writer_creates_prompt_trace_manifest_with_strict_json(tmp_path):
    output_path = write_v44_prompt_trace_manifest(
        tmp_path,
        article_id="article-1",
        frame_ids=["frame-1"],
        requested_modes={
            "article_understanding_mode": "auto",
            "visual_planning_mode": "auto",
            "visual_role_strategy": "auto",
        },
        route_decisions=[_route_decision()],
        critic_status="passed",
        repair_rounds=0,
    )

    assert output_path == tmp_path / "prompt_traces" / "manifest.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    json.dumps(payload, allow_nan=False)
    assert payload["schema_version"] == "v4.4"
    assert payload["route_decision_ids"] == {"frame-1": "route-frame-1"}


@pytest.mark.parametrize("article_id", ["", "   ", None, 123])
def test_manifest_rejects_invalid_article_id(article_id):
    with pytest.raises((TypeError, ValueError), match="article_id"):
        build_v44_prompt_trace_manifest(
            article_id=article_id,
            frame_ids=["frame-1"],
            requested_modes={},
            route_decisions=[],
            critic_status="passed",
            repair_rounds=0,
        )


@pytest.mark.parametrize("frame_ids", [None, "frame-1", [], ["   "], ["frame-1", 2]])
def test_manifest_rejects_invalid_frame_ids(frame_ids):
    with pytest.raises((TypeError, ValueError), match="frame_ids"):
        build_v44_prompt_trace_manifest(
            article_id="article-1",
            frame_ids=frame_ids,
            requested_modes={},
            route_decisions=[],
            critic_status="passed",
            repair_rounds=0,
        )


@pytest.mark.parametrize("critic_status", ["", "   ", None, False])
def test_manifest_rejects_invalid_critic_status(critic_status):
    with pytest.raises((TypeError, ValueError), match="critic_status"):
        build_v44_prompt_trace_manifest(
            article_id="article-1",
            frame_ids=["frame-1"],
            requested_modes={},
            route_decisions=[],
            critic_status=critic_status,
            repair_rounds=0,
        )


@pytest.mark.parametrize("repair_rounds", [-1, True, 1.5, "1"])
def test_manifest_rejects_invalid_repair_rounds(repair_rounds):
    with pytest.raises((TypeError, ValueError), match="repair_rounds"):
        build_v44_prompt_trace_manifest(
            article_id="article-1",
            frame_ids=["frame-1"],
            requested_modes={},
            route_decisions=[],
            critic_status="passed",
            repair_rounds=repair_rounds,
        )


def test_manifest_rejects_non_route_decisions():
    with pytest.raises(TypeError, match="route_decisions"):
        build_v44_prompt_trace_manifest(
            article_id="article-1",
            frame_ids=["frame-1"],
            requested_modes={},
            route_decisions=[{"frame_id": "frame-1"}],
            critic_status="passed",
            repair_rounds=0,
        )


def _route_decision(**overrides):
    kwargs = {
        "route_decision_id": "route-frame-1",
        "frame_id": "frame-1",
        "preflight_id": "preflight-v44-1",
        "requested_article_mode": "auto",
        "requested_visual_mode": "auto",
        "requested_visual_role_strategy": "auto",
        "resolved_primary_lens": "thesis_argument",
        "resolved_secondary_lenses": (),
        "resolved_visual_planning_mode": "auto",
        "resolved_visual_role_strategy": "auto",
        "primary_visual_task": "cognitive_explanation",
        "secondary_visual_tasks": (PrimaryVisualTask.STRUCTURE_EXPLANATION,),
        "confidence": 0.8,
        "decision_reason": "planner matched frame",
        "resolution_status": "resolved",
        "fallback_eligible": False,
        "fallback_used": False,
        "fallback_target": None,
        "fallback_reason": None,
    }
    kwargs.update(overrides)
    return VisualPlanningRouteDecision(**kwargs)
