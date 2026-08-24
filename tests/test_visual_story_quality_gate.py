import pytest

from pixelle_video.models.visual_story_engine import (
    ArticleVisualUnderstanding,
    FrameIPFusionPlan,
    FrameVisualPlan,
    IPRouteCompatibilityReport,
    RouteSelectionDecision,
    StyleHarmonizationPlan,
    VisualRouteCandidate,
    VisualStoryEnginePlan,
)
from pixelle_video.services.content_bound_ip_planner import ContentBoundIPPlanner
from pixelle_video.services.visual_story_quality_gate import VisualStoryQualityGate


def _plan_with_fusion(text: str, *, replacement: bool = False):
    article = ArticleVisualUnderstanding("full_article", "summary", "claim", "problem")
    route = VisualRouteCandidate("r", "R", "editorial_diagram", "premise", "fits")
    frame_payload = ContentBoundIPPlanner().enrich_frame_visual_plan(
        {
            "frame_id": "f",
            "frame_index": 0,
            "source_text": "source",
            "local_claim": "claim",
            "visual_task": "task",
            "visual_logic": "logic",
            "required_subjects": ("subject",),
        },
        selected_visual_route=route.to_dict(),
        article_summary=article.to_dict(),
    )
    fusion_payload = ContentBoundIPPlanner().plan_for_frame(
        frame_payload, selected_visual_route=route.to_dict()
    )
    fusion_payload["action_or_function"] = text
    if replacement:
        fusion_payload["relation_to_article_subject"] = "replace the article subject"
    return VisualStoryEnginePlan(
        plan_id="p",
        article=article,
        candidate_routes=(route,),
        compatibility_reports=(IPRouteCompatibilityReport("r", True, "guide", "low", 0.7, "ok"),),
        selection=RouteSelectionDecision("r", "r", "api_auto", "best"),
        style_harmonization=StyleHarmonizationPlan(
            "r", "hybrid_layered", "ip", "scene", "boundary"
        ),
        frame_visual_plans=(FrameVisualPlan.from_mapping(frame_payload),),
        frame_ip_fusion_plans=(FrameIPFusionPlan.from_mapping(fusion_payload),),
    )


def test_quality_gate_rejects_replacement_language():
    with pytest.raises(ValueError):
        VisualStoryQualityGate().assert_valid(
            _plan_with_fusion("content-bound action", replacement=True)
        )


def test_quality_gate_rejects_active_content_bound_action_contract():
    with pytest.raises(ValueError, match="active recurring-IP planning is forbidden"):
        VisualStoryQualityGate().assert_valid(
            _plan_with_fusion("operate the explanatory model")
        )


def test_quality_gate_rejects_missing_expected_frame_coverage():
    with pytest.raises(ValueError, match="exactly cover expected frame IDs"):
        VisualStoryQualityGate().assert_valid(
            _plan_with_fusion("operate the explanatory model"),
            expected_frame_ids=("f", "missing-frame"),
        )


def test_quality_gate_preserves_route_only_plan_compatibility_without_expected_frames():
    populated = _plan_with_fusion("operate the explanatory model")
    route_only = VisualStoryEnginePlan(
        plan_id=populated.plan_id,
        article=populated.article,
        candidate_routes=populated.candidate_routes,
        compatibility_reports=populated.compatibility_reports,
        selection=populated.selection,
        style_harmonization=populated.style_harmonization,
        frame_visual_plans=(),
        frame_ip_fusion_plans=(),
    )

    VisualStoryQualityGate().assert_valid(route_only)
    with pytest.raises(ValueError, match="exactly cover expected frame IDs"):
        VisualStoryQualityGate().assert_valid(route_only, expected_frame_ids=("f",))
