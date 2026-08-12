import pytest
from pydantic import ValidationError

from pixelle_video.models.llm_interaction_trace import LLMTraceContext
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
from pixelle_video.services.frame_batch_contract import extract_frame_batch_records
from pixelle_video.services.visual_route_analysis_contract import VisualRouteScoreResponse
from pixelle_video.services.visual_story_engine import VisualStoryEngineService


def _valid_route_analysis_response() -> dict:
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
                    "channel_consistency": 0.75,
                    "production_reliability": 0.8,
                    "risk": 0.1,
                },
            }
        ],
        "recommended_route_id": "route-a",
    }


class _RouteAnalysisLLM:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        return _valid_route_analysis_response()


class _RouteAnalysisScoreRepairLLM:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        if len(self.calls) > 1:
            return {
                "score_repairs": [
                    {
                        "candidate_index": 0,
                        "scores": {
                            "content_fit": 0.9,
                            "memorability": 0.8,
                            "channel_consistency": 0.75,
                            "production_reliability": 0.8,
                            "risk": 0.1,
                        },
                    }
                ]
            }
        return {
            "article_understanding": {
                "summary": "summary",
                "core_claim": "claim",
                "central_problem": "problem",
            },
            "candidates": [
                {
                    "route_id": 1,
                    "route_name": "Malformed Scores Route",
                    "route_type": "editorial_diagram",
                    "visual_premise": "premise",
                    "why_it_fits_article": "because",
                    "scores": "content_fit",
                    "memorability": "channel_consistency",
                    "production_reliability": "risk",
                }
            ],
        }


def test_evidence_span_accepts_string_source():
    span = EvidenceSpan.from_mapping("quoted source")

    assert span.evidence_id == "evidence-1"
    assert span.quote == "quoted source"
    assert span.role == "support"


def test_visual_story_frame_response_contract_accepts_wrapped_data_items():
    assert extract_frame_batch_records(
        {"data": [{"frame_id": "f1"}]},
        primary_key="frame_visual_plans",
        stage="test",
    ) == ({"frame_id": "f1"},)
    assert extract_frame_batch_records(
        {"items": [{"frame_id": "f2"}]},
        primary_key="frame_visual_plans",
        stage="test",
    ) == ({"frame_id": "f2"},)


@pytest.mark.asyncio
async def test_visual_route_analysis_accepts_template_candidates_key():
    llm = _RouteAnalysisLLM()

    article, routes = await VisualStoryEngineService()._analyze_routes(
        llm_service=llm,
        source_text="source article",
        title="title",
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
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_visual_route_analysis_repairs_only_malformed_scores_once():
    llm = _RouteAnalysisScoreRepairLLM()
    trace_context = LLMTraceContext(
        workspace_id="workspace",
        task_id="task",
        operation="visual_story_engine",
    )

    article, routes = await VisualStoryEngineService()._analyze_routes(
        llm_service=llm,
        source_text="source article secret marker",
        title="title",
        channel_strategy=None,
        user_intent_hint=None,
        candidate_count=1,
        target_language="en",
        trace_context=trace_context,
        trace_recorder=None,
    )

    assert article.core_claim == "claim"
    assert [route.route_id for route in routes] == ["1"]
    assert routes[0].scores.channel_consistency == 0.75
    assert len(llm.calls) == 2
    assert [call["temperature"] for call in llm.calls] == [0.25, 0.0]
    assert "score_repairs" in llm.calls[1]["prompt"]
    assert "Malformed Scores Route" in llm.calls[1]["prompt"]
    assert "source article secret marker" not in llm.calls[1]["prompt"]
    assert [
        call["trace_context"].stage
        for call in llm.calls
    ] == [
        "article_visual_route_analysis",
        "article_visual_route_score_repair",
    ]
    assert [
        call["trace_context"].metadata["prompt_template"]["prompt_id"]
        for call in llm.calls
    ] == [
        "article_visual_route_analysis",
        "article_visual_route_score_repair",
    ]


@pytest.mark.asyncio
async def test_visual_route_analysis_preserves_legacy_envelope_and_score_aliases():
    class _LegacyEnvelopeLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def __call__(self, **kwargs):
            self.calls += 1
            return {
                "data": {
                    "article": {
                        "article_summary": "legacy summary",
                        "main_claim": "legacy claim",
                    },
                    "route_candidates": [
                        {
                            "id": 7,
                            "title": "Legacy Route",
                            "type": "structure_map",
                            "premise": "legacy premise",
                            "reason": "legacy reason",
                            "content_fit_score": 0.81,
                            "visual_memorability_score": 0.72,
                            "channel_fit": 0.73,
                            "production_reliability_score": 0.84,
                            "risk_score": 0.11,
                        }
                    ],
                }
            }

    llm = _LegacyEnvelopeLLM()
    article, routes = await VisualStoryEngineService()._analyze_routes(
        llm_service=llm,
        source_text="source article",
        title="title",
        channel_strategy=None,
        user_intent_hint=None,
        candidate_count=1,
        target_language="en",
        trace_context=None,
        trace_recorder=None,
    )

    assert article.core_claim == "legacy claim"
    assert [route.route_id for route in routes] == ["7"]
    assert routes[0].scores.memorability == 0.72
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_visual_route_analysis_isolates_failed_score_repair():
    class _PartialRepairLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def __call__(self, **kwargs):
            self.calls += 1
            if self.calls > 1:
                return {"score_repairs": [{"candidate_index": 1, "scores": "risk"}]}
            response = _valid_route_analysis_response()
            response["candidates"].append(
                {
                    "route_id": "route-b",
                    "route_name": "Route B",
                    "route_type": "structure_map",
                    "visual_premise": "premise b",
                    "why_it_fits_article": "because b",
                    "scores": "content_fit",
                }
            )
            return response

    llm = _PartialRepairLLM()
    _, routes = await VisualStoryEngineService()._analyze_routes(
        llm_service=llm,
        source_text="source article",
        title="title",
        channel_strategy=None,
        user_intent_hint=None,
        candidate_count=2,
        target_language="en",
        trace_context=None,
        trace_recorder=None,
    )

    assert [route.route_id for route in routes] == ["route-a"]
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_visual_route_analysis_makes_duplicate_route_ids_unambiguous():
    class _DuplicateRouteLLM:
        async def __call__(self, **kwargs):
            response = _valid_route_analysis_response()
            first = response["candidates"][0]
            first["route_id"] = "x" * 80
            response["candidates"].append(
                {
                    **first,
                    "route_name": "Duplicate Route",
                }
            )
            return response

    _, routes = await VisualStoryEngineService()._analyze_routes(
        llm_service=_DuplicateRouteLLM(),
        source_text="source article",
        title="title",
        channel_strategy=None,
        user_intent_hint=None,
        candidate_count=2,
        target_language="en",
        trace_context=None,
        trace_recorder=None,
    )

    assert len({route.route_id for route in routes}) == 2
    assert routes[0].route_id == "x" * 80
    assert routes[1].route_id.endswith("_2")
    assert len(routes[1].route_id) == 80


@pytest.mark.asyncio
async def test_visual_route_analysis_preserves_routes_when_article_details_are_invalid():
    class _InvalidArticleLLM:
        async def __call__(self, **kwargs):
            response = _valid_route_analysis_response()
            response["article_understanding"]["evidence_spans"] = [
                {"quote": "evidence", "start_char": "invalid"}
            ]
            return response

    article, routes = await VisualStoryEngineService()._analyze_routes(
        llm_service=_InvalidArticleLLM(),
        source_text="source article used for fallback context",
        title="title",
        channel_strategy=None,
        user_intent_hint=None,
        candidate_count=1,
        target_language="en",
        trace_context=None,
        trace_recorder=None,
    )

    assert article.core_claim == "source article used for fallback context"
    assert [route.route_id for route in routes] == ["route-a"]


@pytest.mark.asyncio
async def test_visual_route_analysis_does_not_retry_structurally_invalid_routes():
    class _InvalidRouteLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def __call__(self, **kwargs):
            self.calls += 1
            return {"candidates": ["not an object"]}

    llm = _InvalidRouteLLM()
    _, routes = await VisualStoryEngineService()._analyze_routes(
        llm_service=llm,
        source_text="source article",
        title="title",
        channel_strategy=None,
        user_intent_hint=None,
        candidate_count=1,
        target_language="en",
        trace_context=None,
        trace_recorder=None,
    )

    assert routes[0].route_id == "stable_editorial_explainer"
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_visual_route_analysis_does_not_retry_provider_failures():
    class _FailedProviderLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def __call__(self, **kwargs):
            self.calls += 1
            raise TimeoutError("provider timeout with sensitive details")

    llm = _FailedProviderLLM()
    _, routes = await VisualStoryEngineService()._analyze_routes(
        llm_service=llm,
        source_text="source article",
        title="title",
        channel_strategy=None,
        user_intent_hint=None,
        candidate_count=1,
        target_language="en",
        trace_context=None,
        trace_recorder=None,
    )

    assert routes[0].route_id == "stable_editorial_explainer"
    assert llm.calls == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("content_fit", "0.8"),
        ("memorability", True),
        ("channel_consistency", float("nan")),
        ("production_reliability", float("inf")),
        ("risk", -0.1),
        ("risk", 1.1),
    ],
)
def test_visual_route_score_contract_rejects_non_json_probability(field, value):
    payload = {
        "content_fit": 0.8,
        "memorability": 0.7,
        "channel_consistency": 0.6,
        "production_reliability": 0.9,
        "risk": 0.1,
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        VisualRouteScoreResponse.model_validate(payload)


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
        scores=VisualRouteScores(
            content_fit=0.9,
            memorability=0.8,
            ip_compatibility=0.7,
            production_reliability=0.8,
            risk=0.1,
        ),
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
