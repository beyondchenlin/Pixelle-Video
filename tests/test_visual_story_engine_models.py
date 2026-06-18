import pytest

from pixelle_video.models.visual_story_engine import (
    ArticleVisualUnderstanding,
    EvidenceSpan,
    FrameIPFusionPlan,
    FrameVisualPlan,
    IPRouteCompatibilityReport,
    RouteSelectionDecision,
    StyleHarmonizationPlan,
    VisualRouteCandidate,
    VisualRouteScores,
    VisualStoryEnginePlan,
)
from pixelle_video.services.visual_story_frame_services import _list_payload
from pixelle_video.services.visual_story_engine import VisualStoryEngineService


class _RouteAnalysisLLM:
    async def __call__(self, **kwargs):
        return {
            "article_understanding": {
                "summary": "summary",
                "core_claim": "claim",
                "central_problem": "problem",
                "evidence_spans": ["quoted source"],
            },
            "candidates": [
                {
                    "route_id": "route-a",
                    "route_name": "Route A",
                    "route_type": "editorial_diagram",
                    "visual_premise": "premise",
                    "why_it_fits_article": "because",
                    "scores": {
                        "content_fit": 0.9,
                        "memorability": 0.8,
                        "ip_compatibility": 0.7,
                        "production_reliability": 0.8,
                        "risk": 0.1,
                    },
                }
            ],
            "recommended_route_id": "route-a",
        }


def test_evidence_span_accepts_string_source():
    span = EvidenceSpan.from_mapping("quoted source")

    assert span.evidence_id == "evidence-1"
    assert span.quote == "quoted source"
    assert span.role == "support"


def test_visual_story_frame_list_payload_accepts_wrapped_data_items():
    assert _list_payload({"data": [{"frame_id": "f1"}]}, "frame_visual_plans") == [
        {"frame_id": "f1"}
    ]
    assert _list_payload({"items": [{"frame_id": "f2"}]}, "frame_visual_plans") == [
        {"frame_id": "f2"}
    ]


@pytest.mark.asyncio
async def test_visual_route_analysis_accepts_template_candidates_key():
    article, routes, recommended_route_id = await VisualStoryEngineService()._analyze_routes(
        llm_service=_RouteAnalysisLLM(),
        source_text="source article",
        title="title",
        ip_profile=None,
        channel_strategy=None,
        user_intent_hint=None,
        candidate_count=1,
        target_language="en",
        trace_context=None,
        trace_recorder=None,
    )

    assert article.core_claim == "claim"
    assert article.evidence_spans[0].quote == "quoted source"
    assert [route.route_id for route in routes] == ["route-a"]
    assert recommended_route_id == "route-a"


def test_visual_story_engine_plan_roundtrip():
    article = ArticleVisualUnderstanding(
        input_kind="full_article",
        summary="summary",
        core_claim="claim",
        central_problem="problem",
    )
    route = VisualRouteCandidate(
        route_id="route-a",
        route_name="Route A",
        route_type="philosophical_metaphor",
        visual_premise="premise",
        why_it_fits_article="because",
        scores=VisualRouteScores(content_fit=0.9, memorability=0.8, ip_compatibility=0.7, production_reliability=0.8, risk=0.1),
    )
    compat = IPRouteCompatibilityReport(
        route_id="route-a",
        compatible=True,
        recommended_role="silent_witness",
        recommended_visibility="low",
        compatibility_score=0.8,
        reason="fits",
    )
    selection = RouteSelectionDecision(
        recommended_route_id="route-a",
        selected_route_id="route-a",
        selection_source="api_auto",
        reason="best",
    )
    style = StyleHarmonizationPlan(
        route_id="route-a",
        mode="hybrid_layered",
        ip_style_policy="ip",
        scene_style_policy="scene",
        boundary_rule="boundary",
    )
    frame = FrameVisualPlan(
        frame_id="f1",
        frame_index=0,
        source_text="source",
        local_claim="claim",
        visual_task="task",
        visual_logic="logic",
    )
    fusion = FrameIPFusionPlan(
        frame_id="f1",
        ip_role="silent_witness",
        ip_visibility="low",
        placement_logic="edge",
        action_or_function="witness",
        relation_to_article_subject="not replacing",
        style_harmonization="hybrid_layered",
    )
    plan = VisualStoryEnginePlan(
        plan_id="p1",
        article=article,
        candidate_routes=(route,),
        compatibility_reports=(compat,),
        selection=selection,
        style_harmonization=style,
        frame_visual_plans=(frame,),
        frame_ip_fusion_plans=(fusion,),
    )
    payload = plan.to_dict()
    assert payload["selected_visual_route"]["route_id"] == "route-a"
    assert payload["frame_ip_fusion_plans"][0]["ip_role"] == "silent_witness"
