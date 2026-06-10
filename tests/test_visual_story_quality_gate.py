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
from pixelle_video.services.visual_story_quality_gate import VisualStoryQualityGate


def _plan_with_fusion(text):
    article = ArticleVisualUnderstanding("full_article", "summary", "claim", "problem")
    route = VisualRouteCandidate("r", "R", "editorial_diagram", "premise", "fits")
    return VisualStoryEnginePlan(
        plan_id="p",
        article=article,
        candidate_routes=(route,),
        compatibility_reports=(IPRouteCompatibilityReport("r", True, "guide", "low", 0.7, "ok"),),
        selection=RouteSelectionDecision("r", "r", "api_auto", "best"),
        style_harmonization=StyleHarmonizationPlan("r", "hybrid_layered", "ip", "scene", "boundary"),
        frame_visual_plans=(FrameVisualPlan("f", 0, "source", "claim", "task", "logic", required_subjects=("subject",)),),
        frame_ip_fusion_plans=(FrameIPFusionPlan("f", "guide", "low", text, "support", "not replacing", "hybrid_layered"),),
    )


def test_quality_gate_rejects_replacement_language():
    with pytest.raises(ValueError):
        VisualStoryQualityGate().assert_valid(_plan_with_fusion("replace the article subject"))


def test_quality_gate_accepts_support_language():
    VisualStoryQualityGate().assert_valid(_plan_with_fusion("stand beside the article subject"))
