from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

from pixelle_video.models.llm_interaction_trace import trace_context_with_prompt_template
from pixelle_video.models.visual_story_engine import (
    DEFAULT_CONFIDENT_MARGIN,
    DEFAULT_CONFIDENT_SCORE,
    DEFAULT_ROUTE_CANDIDATE_COUNT,
    DEFAULT_WEB_AUTO_SELECT_SECONDS,
    ArticleInputKind,
    ArticleVisualUnderstanding,
    FrameIPFusionPlan,
    FrameVisualPlan,
    IPRouteCompatibilityReport,
    IPVisibilityLevel,
    RouteSelectionDecision,
    RouteSelectionSource,
    StyleHarmonizationMode,
    StyleHarmonizationPlan,
    VisualRouteCandidate,
    VisualRouteScores,
    VisualRouteType,
    VisualSignatureRole,
    VisualStoryEnginePlan,
)
from pixelle_video.prompts.visual_story_engine import (
    render_article_visual_route_analysis_prompt,
    render_article_visual_route_score_repair_prompt,
)
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.services.visual_route_analysis_contract import (
    VisualRouteAnalysisContractError,
    coerce_route_analysis_response,
    ensure_unique_route_ids,
    extract_article_payload,
    extract_route_candidates,
    normalize_candidate_count,
    parse_route_candidates,
    recognized_payload_keys,
    score_repair_article_context,
    score_repair_candidate_context,
    validate_score_repairs,
)
from pixelle_video.services.visual_story_quality_gate import VisualStoryQualityGate


class _VisualRouteScoreRepairRequestError(RuntimeError):
    """The bounded score-repair model request failed."""


@dataclass(frozen=True)
class VisualStoryEngineService:
    """Article-first, content-only visual route engine.

    Recurring visual identity is intentionally outside this engine. This stage
    owns article understanding, content route selection, and content frame plans.
    The canonical V4.5 visual-signature projector is the only identity owner.

    Historical ``ip_profile`` and ``image_config`` parameters remain accepted so
    existing callers do not break, but they cannot influence route analysis,
    route ranking, style planning, frame planning, or model-call count.
    """

    async def prepare(
        self,
        *,
        llm_service: Any,
        source_text: str,
        storyboard_plan: Any,
        title: str | None = None,
        ip_profile: Any = None,
        image_config: Mapping[str, Any] | None = None,
        channel_strategy: Mapping[str, Any] | None = None,
        user_selected_route_id: str | None = None,
        user_intent_hint: str | None = None,
        candidate_count: int = DEFAULT_ROUTE_CANDIDATE_COUNT,
        target_language: str = "zh",
        auto_select_after_seconds: int = DEFAULT_WEB_AUTO_SELECT_SECONDS,
        trace_context: Any = None,
        trace_recorder: LLMInteractionRecorder | None = None,
        enable_frame_planning: bool = True,
    ) -> VisualStoryEnginePlan:
        del ip_profile, image_config
        normalized_source = str(source_text or "").strip()
        if not normalized_source:
            raise ValueError("source_text is required for visual story engine")

        analysis, raw_candidates = await self._analyze_routes(
            llm_service=llm_service,
            source_text=normalized_source,
            title=title,
            channel_strategy=_content_channel_strategy(channel_strategy),
            user_intent_hint=user_intent_hint,
            candidate_count=candidate_count,
            target_language=target_language,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )
        candidates = tuple(_content_only_candidate(item) for item in raw_candidates)
        compatibility_reports = tuple(
            _neutral_compatibility(candidate) for candidate in candidates
        )
        selection = self._select_route(
            candidates=candidates,
            user_selected_route_id=user_selected_route_id,
            auto_select_after_seconds=auto_select_after_seconds,
        )
        selected_route = _route_by_id(candidates, selection.selected_route_id)
        style_plan = _content_style_plan(selected_route)

        if enable_frame_planning:
            frame_visual_plans = self._frame_visual_plans(
                storyboard_plan=storyboard_plan,
                selected_route=selected_route,
                article=analysis,
            )
            frame_ip_fusion_plans = tuple(
                _no_ip_fusion(frame) for frame in frame_visual_plans
            )
        else:
            frame_visual_plans = ()
            frame_ip_fusion_plans = ()

        plan = VisualStoryEnginePlan(
            plan_id="visual-story-engine-v3-content-only",
            article=analysis,
            candidate_routes=candidates,
            compatibility_reports=compatibility_reports,
            selection=selection,
            style_harmonization=style_plan,
            frame_visual_plans=frame_visual_plans,
            frame_ip_fusion_plans=frame_ip_fusion_plans,
            channel_memory_intent=(
                "Keep article route, composition logic, and scene style stable across frames. "
                "Recurring visual identity is owned only by canonical V4.5 final projection."
            ),
        )
        VisualStoryQualityGate().assert_valid(plan)
        return plan

    async def _analyze_routes(
        self,
        *,
        llm_service: Any,
        source_text: str,
        title: str | None,
        channel_strategy: Mapping[str, Any] | None,
        user_intent_hint: str | None,
        candidate_count: int,
        target_language: str,
        trace_context: Any,
        trace_recorder: LLMInteractionRecorder | None,
    ) -> tuple[ArticleVisualUnderstanding, tuple[VisualRouteCandidate, ...]]:
        candidate_count = normalize_candidate_count(candidate_count)
        rendered_prompt = render_article_visual_route_analysis_prompt(
            source_text=source_text,
            title=title,
            channel_strategy=channel_strategy,
            user_intent_hint=user_intent_hint,
            candidate_count=candidate_count,
            target_language=target_language,
        )
        prompt_trace_context = (
            trace_context_with_prompt_template(
                trace_context,
                rendered_prompt=rendered_prompt,
                attempt=1,
                stage="article_visual_route_analysis",
            )
            if trace_context is not None
            else None
        )
        try:
            response = await llm_service(
                prompt=rendered_prompt.text,
                response_type=dict,
                temperature=0.25,
                max_tokens=5000,
                trace_context=prompt_trace_context,
                trace_recorder=trace_recorder,
            )
        except Exception as exc:
            logger.warning(
                "Visual route analysis request failed; using deterministic fallback: {}",
                type(exc).__name__,
            )
            return _fallback_article_and_routes(source_text, title, candidate_count)

        payload = coerce_route_analysis_response(response)
        article_raw = extract_article_payload(payload)
        if not article_raw:
            logger.warning(
                "Visual route analysis omitted article understanding; preserving route "
                "candidates with deterministic article context"
            )
            article, _ = _fallback_article_and_routes(
                source_text,
                title,
                candidate_count,
            )
        else:
            try:
                article = ArticleVisualUnderstanding.from_mapping(article_raw)
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "Visual route article understanding was invalid; preserving route "
                    "candidates with deterministic article context: {}",
                    type(exc).__name__,
                )
                article, _ = _fallback_article_and_routes(
                    source_text,
                    title,
                    candidate_count,
                )
        raw_candidates = extract_route_candidates(payload)
        parsed = parse_route_candidates(raw_candidates)

        candidates_by_index = dict(parsed.accepted)
        if parsed.repairable:
            logger.info(
                "Visual route analysis contained {} candidate(s) with invalid scores; "
                "requesting bounded score-only repair",
                len(parsed.repairable),
            )
            try:
                repaired_scores = await self._repair_route_scores(
                    llm_service=llm_service,
                    article=article,
                    candidates=parsed.repairable,
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                )
            except (
                VisualRouteAnalysisContractError,
                _VisualRouteScoreRepairRequestError,
            ) as exc:
                logger.warning(
                    "Visual route score repair failed; discarding only unrepaired "
                    "candidates: {}",
                    _route_contract_error_summary(exc),
                )
                repaired_scores = {}
            for candidate_index, candidate in parsed.repairable:
                scores = repaired_scores.get(candidate_index)
                if scores is not None:
                    candidates_by_index[candidate_index] = candidate.with_scores(scores)

        candidates = ensure_unique_route_ids(
            tuple(
                candidate
                for _, candidate in sorted(candidates_by_index.items())
            )
        )
        if candidates:
            omitted_count = len(raw_candidates) - len(candidates)
            if omitted_count:
                logger.warning(
                    "Visual route analysis omitted {} unusable candidate(s) after isolated "
                    "validation; continuing with {} valid candidate(s)",
                    omitted_count,
                    len(candidates),
                )
            return article, candidates

        logger.warning(
            "Visual route analysis returned no usable candidates; using deterministic "
            "fallback | payload_keys={} candidate_count={} rejected_count={}",
            recognized_payload_keys(payload),
            len(raw_candidates),
            parsed.rejected_count + len(parsed.repairable),
        )
        return _fallback_article_and_routes(source_text, title, candidate_count)

    async def _repair_route_scores(
        self,
        *,
        llm_service: Any,
        article: ArticleVisualUnderstanding,
        candidates: Sequence[tuple[int, VisualRouteCandidate]],
        trace_context: Any,
        trace_recorder: LLMInteractionRecorder | None,
    ) -> dict[int, VisualRouteScores]:
        rendered_prompt = render_article_visual_route_score_repair_prompt(
            article_understanding=score_repair_article_context(article),
            candidates=[
                score_repair_candidate_context(candidate_index, candidate)
                for candidate_index, candidate in candidates
            ],
        )
        prompt_trace_context = (
            trace_context_with_prompt_template(
                trace_context,
                rendered_prompt=rendered_prompt,
                attempt=1,
                stage="article_visual_route_score_repair",
                metadata={"candidate_count": len(candidates)},
            )
            if trace_context is not None
            else None
        )
        try:
            response = await llm_service(
                prompt=rendered_prompt.text,
                response_type=dict,
                temperature=0.0,
                max_tokens=max(800, min(2500, len(candidates) * 300)),
                trace_context=prompt_trace_context,
                trace_recorder=trace_recorder,
            )
        except Exception as exc:
            raise _VisualRouteScoreRepairRequestError(
                type(exc).__name__
            ) from exc
        payload = coerce_route_analysis_response(response)
        expected_indices = {candidate_index for candidate_index, _ in candidates}
        return validate_score_repairs(payload, expected_indices)

    def _select_route(
        self,
        *,
        candidates: Sequence[VisualRouteCandidate],
        user_selected_route_id: str | None,
        auto_select_after_seconds: int,
    ) -> RouteSelectionDecision:
        by_id = {candidate.route_id: candidate for candidate in candidates}
        ranked = sorted(
            candidates,
            key=lambda candidate: candidate.final_score,
            reverse=True,
        )
        best = ranked[0]
        second = ranked[1] if len(ranked) > 1 else None
        low_confidence = best.final_score < DEFAULT_CONFIDENT_SCORE or (
            second is not None
            and best.final_score - second.final_score < DEFAULT_CONFIDENT_MARGIN
        )
        if user_selected_route_id and user_selected_route_id in by_id:
            return RouteSelectionDecision(
                recommended_route_id=best.route_id,
                selected_route_id=user_selected_route_id,
                selection_source=RouteSelectionSource.USER_SELECTED,
                reason="User selected visual route; overrides the deterministic content ranking.",
                auto_select_after_seconds=auto_select_after_seconds,
                user_overrode=user_selected_route_id != best.route_id,
                low_confidence=low_confidence,
            )
        if low_confidence:
            fallback = _conservative_route(candidates) or best
            return RouteSelectionDecision(
                recommended_route_id=best.route_id,
                selected_route_id=fallback.route_id,
                selection_source=RouteSelectionSource.FALLBACK_CONSERVATIVE,
                reason=(
                    "Content-route confidence was low; using a conservative route "
                    "with reliable visual explainability."
                ),
                auto_select_after_seconds=auto_select_after_seconds,
                low_confidence=True,
                fallback_used=fallback.route_id != best.route_id,
                fallback_reason="low_confidence_or_small_margin",
            )
        return RouteSelectionDecision(
            recommended_route_id=best.route_id,
            selected_route_id=best.route_id,
            selection_source=RouteSelectionSource.API_AUTO,
            reason=(
                "Default route selected by deterministic article fit, memorability, "
                "channel consistency, production reliability, and risk. Model-provided "
                "final scores and recurring identity compatibility are ignored."
            ),
            auto_select_after_seconds=auto_select_after_seconds,
            low_confidence=False,
        )

    def _frame_visual_plans(
        self,
        *,
        storyboard_plan: Any,
        selected_route: VisualRouteCandidate,
        article: ArticleVisualUnderstanding,
    ) -> tuple[FrameVisualPlan, ...]:
        frames = tuple(getattr(storyboard_plan, "frames", ()) or ())
        if not frames:
            return ()
        plans: list[FrameVisualPlan] = []
        for index, frame in enumerate(frames):
            frame_id = str(
                getattr(frame, "frame_id", "") or f"frame_{index + 1:04d}"
            )
            source_text = str(getattr(frame, "source_text", "") or "")
            visual_goal = str(getattr(frame, "visual_goal", "") or "")
            prompt_intent = str(getattr(frame, "prompt_intent", "") or "")
            primary_subject = str(getattr(frame, "primary_subject", "") or "")
            subjects = [
                primary_subject,
                *list(getattr(frame, "secondary_subjects", ()) or ()),
                *list(getattr(frame, "continuity_anchors", ()) or ()),
            ]
            visual_task = _visual_task_for_route(
                selected_route,
                visual_goal,
                prompt_intent,
            )
            visual_logic = (
                f"Follow selected route '{selected_route.route_name}': "
                f"{selected_route.visual_premise}. "
                f"This frame should express: {visual_goal or source_text}."
            )
            plans.append(
                FrameVisualPlan(
                    frame_id=frame_id,
                    frame_index=index,
                    source_text=source_text or article.core_claim,
                    local_claim=visual_goal or source_text or article.core_claim,
                    visual_task=visual_task,
                    visual_logic=visual_logic,
                    required_subjects=(
                        tuple(item for item in subjects if str(item or "").strip())
                        or article.key_subjects
                    ),
                    forbidden_losses=(
                        "do not replace article subjects",
                        "do not switch visual route mid-video",
                    ),
                    evidence_refs=(frame_id,),
                    visible_text_policy="no_visible_text",
                )
            )
        return tuple(plans)


def _content_only_candidate(candidate: VisualRouteCandidate) -> VisualRouteCandidate:
    source_scores = candidate.scores
    content_scores = VisualRouteScores(
        content_fit=source_scores.content_fit,
        memorability=source_scores.memorability,
        ip_compatibility=0.0,
        channel_consistency=source_scores.channel_consistency,
        production_reliability=source_scores.production_reliability,
        risk=source_scores.risk,
        final=None,
    )
    return VisualRouteCandidate(
        route_id=candidate.route_id,
        route_name=candidate.route_name,
        route_type=candidate.route_type,
        visual_premise=candidate.visual_premise,
        why_it_fits_article=candidate.why_it_fits_article,
        frame_storytelling_logic=candidate.frame_storytelling_logic,
        style_family=candidate.style_family,
        recommended_ip_role=VisualSignatureRole.NONE,
        ip_fit_reason=(
            "Recurring identity is out of scope for Visual Story; canonical V4.5 final projection owns it."
        ),
        route_specific_rules=candidate.route_specific_rules,
        risk_notes=candidate.risk_notes,
        sample_frame_premise=candidate.sample_frame_premise,
        scores=content_scores,
    )


def _content_channel_strategy(
    value: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key, child in value.items():
        normalized = str(key).strip().lower().replace("-", "_")
        if (
            normalized == "ip"
            or normalized.startswith("ip_")
            or "visual_signature" in normalized
            or "recurring_ip" in normalized
            or "mascot" in normalized
        ):
            continue
        if isinstance(child, Mapping):
            result[str(key)] = _content_channel_strategy(child)
        else:
            result[str(key)] = child
    return result


def _neutral_compatibility(
    candidate: VisualRouteCandidate,
) -> IPRouteCompatibilityReport:
    return IPRouteCompatibilityReport(
        route_id=candidate.route_id,
        compatible=True,
        recommended_role=VisualSignatureRole.NONE,
        recommended_visibility=IPVisibilityLevel.NONE,
        compatibility_score=0.0,
        reason=(
            "Recurring identity compatibility is intentionally not evaluated in "
            "Visual Story; canonical V4.5 final projection owns it."
        ),
        mitigation_rules=(),
    )


def _content_style_plan(
    selected_route: VisualRouteCandidate,
) -> StyleHarmonizationPlan:
    return StyleHarmonizationPlan(
        route_id=selected_route.route_id,
        mode=StyleHarmonizationMode.MATCH_ROUTE_STYLE,
        ip_style_policy=(
            "No recurring identity styling occurs in Visual Story; canonical V4.5 projection owns identity styling."
        ),
        scene_style_policy=(
            f"Scene follows {selected_route.style_family.value} and the selected content route premise."
        ),
        boundary_rule=(
            "This stage may style article content only; recurring visual identity is out of scope."
        ),
        positive_rules=(
            "stable content route",
            "article subjects remain primary",
            "consistent scene style",
        ),
        negative_rules=(
            "no recurring identity insertion",
            "no article subject replacement",
            "no mid-video route switch",
        ),
    )


def _no_ip_fusion(frame: FrameVisualPlan) -> FrameIPFusionPlan:
    return FrameIPFusionPlan(
        frame_id=frame.frame_id,
        ip_role=VisualSignatureRole.NONE,
        ip_visibility=IPVisibilityLevel.NONE,
        placement_logic="Recurring visual identity is not planned in Visual Story.",
        action_or_function="None.",
        relation_to_article_subject="No recurring visual identity participates here.",
        style_harmonization=StyleHarmonizationMode.MATCH_ROUTE_STYLE,
        positive_prompt_clause="",
        negative_constraints=(),
        content_relation_type="disabled_in_visual_story",
    )


def _visual_task_for_route(
    route: VisualRouteCandidate,
    visual_goal: str,
    prompt_intent: str,
) -> str:
    if route.route_type in {
        VisualRouteType.PROCESS_MAP,
        VisualRouteType.SCIENTIFIC_ANALOGY,
        VisualRouteType.MATHEMATICAL_MODEL,
    }:
        return "explain a mechanism, process, or model"
    if route.route_type in {
        VisualRouteType.ABSURD_COMIC,
        VisualRouteType.CARTOON_STORY,
    }:
        return "turn the local claim into a readable comic beat"
    if route.route_type in {
        VisualRouteType.PHILOSOPHICAL_METAPHOR,
        VisualRouteType.EMOTIONAL_THEATER,
    }:
        return "turn the local claim into a memorable metaphorical moment"
    return prompt_intent or visual_goal or "visualize this article frame"


def _route_contract_error_summary(exc: Exception) -> str:
    error_code = getattr(exc, "code", None)
    if isinstance(error_code, str) and error_code:
        return f"{type(exc).__name__}:{error_code}"
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            details = errors(
                include_url=False,
                include_context=False,
                include_input=False,
            )
        except TypeError:
            details = errors()
        fields = [
            ".".join(str(part) for part in detail.get("loc", ()))
            for detail in details[:5]
        ]
        field_summary = ", ".join(field for field in fields if field)
        suffix = f": {field_summary}" if field_summary else ""
        return f"{len(details)} schema validation error(s){suffix}"
    return type(exc).__name__


def _fallback_article_and_routes(
    source_text: str,
    title: str | None,
    candidate_count: int,
) -> tuple[ArticleVisualUnderstanding, tuple[VisualRouteCandidate, ...]]:
    excerpt = source_text.strip()[:220] or title or "article"
    article = ArticleVisualUnderstanding(
        input_kind=(
            ArticleInputKind.FULL_ARTICLE
            if len(source_text) > 200
            else ArticleInputKind.SHORT_COPY
        ),
        summary=excerpt,
        core_claim=excerpt,
        central_problem="What visual logic best explains this article?",
        key_subjects=(title or "article_claim",),
        cognitive_opportunities=("claim", "structure", "metaphor"),
        evidence_spans=(
            {"evidence_id": "source-1", "quote": excerpt, "role": "fallback"},
        ),
    )
    routes = (
        VisualRouteCandidate(
            route_id="stable_editorial_explainer",
            route_name="稳健编辑图解",
            route_type=VisualRouteType.EDITORIAL_DIAGRAM,
            visual_premise="用清晰结构和克制隐喻解释文章核心观点",
            why_it_fits_article="这是低风险、可稳定生成、适合多数文章的默认路线。",
            frame_storytelling_logic="每帧解释一个局部观点，整体保持同一内容视觉路线。",
            style_family="editorial_diagram",
            recommended_ip_role="none",
            scores=VisualRouteScores(0.76, 0.66, 0.0, 0.72, 0.88, 0.12),
        ),
        VisualRouteCandidate(
            route_id="philosophical_metaphor",
            route_name="哲学隐喻",
            route_type=VisualRouteType.PHILOSOPHICAL_METAPHOR,
            visual_premise="把文章抽象观点转成可记住的空间或物理隐喻",
            why_it_fits_article="适合表达情绪、命运、状态、困境和思想冲突。",
            frame_storytelling_logic="每帧延展同一个隐喻世界，避免重复但保持统一。",
            style_family="handdrawn_explainer",
            recommended_ip_role="none",
            scores=VisualRouteScores(0.72, 0.82, 0.0, 0.70, 0.72, 0.2),
        ),
        VisualRouteCandidate(
            route_id="absurd_comic",
            route_name="诙谐荒诞漫画",
            route_type=VisualRouteType.ABSURD_COMIC,
            visual_premise="用荒诞行动把文章矛盾变成轻松可记的场景",
            why_it_fits_article="适合轻松观点、吐槽、生活观察，不适合严肃题材。",
            frame_storytelling_logic="每帧一个小包袱，但统一内容世界规则。",
            style_family="cartoon_comic",
            recommended_ip_role="none",
            scores=VisualRouteScores(0.62, 0.84, 0.0, 0.62, 0.68, 0.32),
        ),
    )[: max(1, min(candidate_count, 3))]
    return article, routes


def _route_by_id(
    candidates: Sequence[VisualRouteCandidate],
    route_id: str,
) -> VisualRouteCandidate:
    for candidate in candidates:
        if candidate.route_id == route_id:
            return candidate
    return max(candidates, key=lambda candidate: candidate.final_score)


def _conservative_route(
    candidates: Sequence[VisualRouteCandidate],
) -> VisualRouteCandidate | None:
    conservative_types = {
        VisualRouteType.EDITORIAL_DIAGRAM,
        VisualRouteType.COGNITIVE_EXPLAINER,
        VisualRouteType.STRUCTURE_MAP,
    }
    options = [
        candidate
        for candidate in candidates
        if candidate.route_type in conservative_types
    ]
    if not options:
        return None
    return max(options, key=lambda candidate: candidate.final_score)


__all__ = ["VisualStoryEngineService"]
