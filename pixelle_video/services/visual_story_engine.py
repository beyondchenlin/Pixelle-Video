from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

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
    render_frame_ip_fusion_prompt,
    render_ip_route_compatibility_prompt,
    render_style_harmonization_prompt,
)
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.services.visual_story_quality_gate import VisualStoryQualityGate


@dataclass(frozen=True)
class VisualStoryEngineService:
    """Article-first visual route engine.

    The engine intentionally owns the decision chain instead of treating IP insertion as
    a last-mile prompt suffix:

    1. analyze article content;
    2. generate multiple visual route candidates;
    3. score route/IP compatibility;
    4. choose a default route with conservative fallback;
    5. build frame-level visual plans;
    6. build frame-level IP fusion plans;
    7. run deterministic quality gates.
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
        normalized_source = str(source_text or "").strip()
        if not normalized_source:
            raise ValueError("source_text is required for visual story engine")
        ip_profile_payload = _ip_profile_payload(ip_profile)
        analysis, candidates, recommended_route_id = await self._analyze_routes(
            llm_service=llm_service,
            source_text=normalized_source,
            title=title,
            ip_profile=ip_profile_payload,
            channel_strategy=channel_strategy,
            user_intent_hint=user_intent_hint,
            candidate_count=candidate_count,
            target_language=target_language,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )
        compatibility_reports = await self._compatibility_reports(
            llm_service=llm_service,
            article=analysis,
            candidates=candidates,
            ip_profile=ip_profile_payload,
            channel_strategy=channel_strategy,
            target_language=target_language,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )
        scored_candidates = _apply_compatibility_scores(candidates, compatibility_reports)
        selection = self._select_route(
            candidates=scored_candidates,
            model_recommended_route_id=recommended_route_id,
            user_selected_route_id=user_selected_route_id,
            auto_select_after_seconds=auto_select_after_seconds,
        )
        selected_route = _route_by_id(scored_candidates, selection.selected_route_id)
        selected_compatibility = _compat_by_route(compatibility_reports, selected_route.route_id)
        style_plan = await self._style_harmonization(
            llm_service=llm_service,
            selected_route=selected_route,
            compatibility_report=selected_compatibility,
            ip_profile=ip_profile_payload,
            image_config=image_config,
            target_language=target_language,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )
        if enable_frame_planning:
            frame_visual_plans = self._frame_visual_plans(
                storyboard_plan=storyboard_plan,
                selected_route=selected_route,
                article=analysis,
            )
            frame_ip_fusion_plans = await self._frame_ip_fusion(
                llm_service=llm_service,
                selected_route=selected_route,
                style_plan=style_plan,
                frame_visual_plans=frame_visual_plans,
                ip_profile=ip_profile_payload,
                compatibility_report=selected_compatibility,
                target_language=target_language,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
        else:
            # Frame-level plans are owned by VisualStoryBatchOrchestrator. The route
            # engine stops at article route selection + style harmonization to avoid
            # duplicate frame planning LLM calls and duplicated prompt context.
            frame_visual_plans = ()
            frame_ip_fusion_plans = ()
        plan = VisualStoryEnginePlan(
            plan_id="visual-story-engine-v2",
            article=analysis,
            candidate_routes=scored_candidates,
            compatibility_reports=compatibility_reports,
            selection=selection,
            style_harmonization=style_plan,
            frame_visual_plans=frame_visual_plans,
            frame_ip_fusion_plans=frame_ip_fusion_plans,
            channel_memory_intent=(
                "Keep a stable channel visual signature across frames while varying role, scale, "
                "visibility, and physical integration so the IP becomes memorable without replacing article meaning."
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
        ip_profile: Mapping[str, Any] | None,
        channel_strategy: Mapping[str, Any] | None,
        user_intent_hint: str | None,
        candidate_count: int,
        target_language: str,
        trace_context: Any,
        trace_recorder: LLMInteractionRecorder | None,
    ) -> tuple[ArticleVisualUnderstanding, tuple[VisualRouteCandidate, ...], str]:
        rendered_prompt = render_article_visual_route_analysis_prompt(
            source_text=source_text,
            title=title,
            ip_profile=ip_profile,
            channel_strategy=channel_strategy,
            user_intent_hint=user_intent_hint,
            candidate_count=candidate_count,
            target_language=target_language,
        )
        try:
            response = await llm_service(
                prompt=rendered_prompt.text,
                response_type=dict,
                temperature=0.25,
                max_tokens=5000,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
            payload = _coerce_mapping_response(response)
            article = ArticleVisualUnderstanding.from_mapping(payload.get("article_understanding") or payload.get("article") or {})
            candidates = tuple(
                VisualRouteCandidate.from_mapping(item)
                for item in payload.get("candidate_routes") or payload.get("routes") or ()
                if isinstance(item, Mapping)
            )
            if len(candidates) < 1:
                raise ValueError("route analysis returned no route candidates")
            recommended_route_id = str(payload.get("recommended_route_id") or candidates[0].route_id)
            return article, candidates, recommended_route_id
        except Exception as exc:
            logger.warning("Visual route analysis failed; using deterministic fallback: {}", exc)
            return _fallback_article_and_routes(source_text, title, candidate_count)

    async def _compatibility_reports(
        self,
        *,
        llm_service: Any,
        article: ArticleVisualUnderstanding,
        candidates: Sequence[VisualRouteCandidate],
        ip_profile: Mapping[str, Any] | None,
        channel_strategy: Mapping[str, Any] | None,
        target_language: str,
        trace_context: Any,
        trace_recorder: LLMInteractionRecorder | None,
    ) -> tuple[IPRouteCompatibilityReport, ...]:
        if not ip_profile:
            return tuple(_neutral_compatibility(candidate) for candidate in candidates)
        rendered_prompt = render_ip_route_compatibility_prompt(
            article_understanding=article.to_dict(),
            candidate_routes=[candidate.to_dict() for candidate in candidates],
            ip_profile=ip_profile,
            channel_strategy=channel_strategy,
            target_language=target_language,
        )
        try:
            response = await llm_service(
                prompt=rendered_prompt.text,
                response_type=dict,
                temperature=0.2,
                max_tokens=3000,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
            compatibility_payload = _coerce_mapping_response(response)
            reports = tuple(
                IPRouteCompatibilityReport.from_mapping(item)
                for item in compatibility_payload.get("compatibility_reports") or ()
                if isinstance(item, Mapping)
            )
            if len(reports) != len(candidates):
                raise ValueError("compatibility report count mismatch")
            return reports
        except Exception as exc:
            logger.warning("IP route compatibility failed; using deterministic fallback: {}", exc)
            return tuple(_deterministic_compatibility(candidate, ip_profile=ip_profile) for candidate in candidates)

    def _select_route(
        self,
        *,
        candidates: Sequence[VisualRouteCandidate],
        model_recommended_route_id: str,
        user_selected_route_id: str | None,
        auto_select_after_seconds: int,
    ) -> RouteSelectionDecision:
        by_id = {candidate.route_id: candidate for candidate in candidates}
        ranked = sorted(candidates, key=lambda candidate: candidate.final_score, reverse=True)
        best = ranked[0]
        second = ranked[1] if len(ranked) > 1 else None
        low_confidence = best.final_score < DEFAULT_CONFIDENT_SCORE or (
            second is not None and best.final_score - second.final_score < DEFAULT_CONFIDENT_MARGIN
        )
        if user_selected_route_id and user_selected_route_id in by_id:
            return RouteSelectionDecision(
                recommended_route_id=best.route_id,
                selected_route_id=user_selected_route_id,
                selection_source=RouteSelectionSource.USER_SELECTED,
                reason="User selected visual route; overrides model/system default.",
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
                reason="Recommendation confidence was low; using conservative route that is reliable for article/IP fusion.",
                auto_select_after_seconds=auto_select_after_seconds,
                low_confidence=True,
                fallback_used=fallback.route_id != best.route_id,
                fallback_reason="low_confidence_or_small_margin",
            )
        selected = by_id.get(model_recommended_route_id, best)
        if selected.final_score + DEFAULT_CONFIDENT_MARGIN < best.final_score:
            selected = best
        return RouteSelectionDecision(
            recommended_route_id=best.route_id,
            selected_route_id=selected.route_id,
            selection_source=RouteSelectionSource.API_AUTO,
            reason="Default route selected by combined article fit, IP compatibility, channel consistency, production reliability, and risk score.",
            auto_select_after_seconds=auto_select_after_seconds,
            low_confidence=False,
        )

    async def _style_harmonization(
        self,
        *,
        llm_service: Any,
        selected_route: VisualRouteCandidate,
        compatibility_report: IPRouteCompatibilityReport,
        ip_profile: Mapping[str, Any] | None,
        image_config: Mapping[str, Any] | None,
        target_language: str,
        trace_context: Any,
        trace_recorder: LLMInteractionRecorder | None,
    ) -> StyleHarmonizationPlan:
        if not ip_profile:
            return _deterministic_style_plan(selected_route, compatibility_report, no_ip=True)
        rendered_prompt = render_style_harmonization_prompt(
            selected_route=selected_route.to_dict(),
            compatibility_report=compatibility_report.to_dict(),
            ip_profile=ip_profile,
            image_config=image_config,
            target_language=target_language,
        )
        try:
            response = await llm_service(
                prompt=rendered_prompt.text,
                response_type=dict,
                temperature=0.2,
                max_tokens=1400,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
            return StyleHarmonizationPlan.from_mapping(_coerce_mapping_response(response))
        except Exception as exc:
            logger.warning("Style harmonization failed; using deterministic fallback: {}", exc)
            return _deterministic_style_plan(selected_route, compatibility_report, no_ip=False)

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
            frame_id = str(getattr(frame, "frame_id", "") or f"frame_{index + 1:04d}")
            source_text = str(getattr(frame, "source_text", "") or "")
            visual_goal = str(getattr(frame, "visual_goal", "") or "")
            prompt_intent = str(getattr(frame, "prompt_intent", "") or "")
            primary_subject = str(getattr(frame, "primary_subject", "") or "")
            subjects = [primary_subject, *list(getattr(frame, "secondary_subjects", ()) or ()), *list(getattr(frame, "continuity_anchors", ()) or ())]
            visual_task = _visual_task_for_route(selected_route, visual_goal, prompt_intent)
            visual_logic = (
                f"Follow selected route '{selected_route.route_name}': {selected_route.visual_premise}. "
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
                    required_subjects=tuple(item for item in subjects if str(item or "").strip()) or article.key_subjects,
                    forbidden_losses=("do not replace article subjects", "do not switch visual route mid-video"),
                    evidence_refs=(frame_id,),
                    visible_text_policy="no_visible_text",
                )
            )
        return tuple(plans)

    async def _frame_ip_fusion(
        self,
        *,
        llm_service: Any,
        selected_route: VisualRouteCandidate,
        style_plan: StyleHarmonizationPlan,
        frame_visual_plans: Sequence[FrameVisualPlan],
        ip_profile: Mapping[str, Any] | None,
        compatibility_report: IPRouteCompatibilityReport,
        target_language: str,
        trace_context: Any,
        trace_recorder: LLMInteractionRecorder | None,
    ) -> tuple[FrameIPFusionPlan, ...]:
        if not frame_visual_plans:
            return ()
        if not ip_profile:
            return tuple(_no_ip_fusion(frame) for frame in frame_visual_plans)
        rendered_prompt = render_frame_ip_fusion_prompt(
            selected_route=selected_route.to_dict(),
            style_harmonization=style_plan.to_dict(),
            frame_visual_plans=[plan.to_dict() for plan in frame_visual_plans],
            ip_profile=ip_profile,
            compatibility_report=compatibility_report.to_dict(),
            target_language=target_language,
        )
        try:
            response = await llm_service(
                prompt=rendered_prompt.text,
                response_type=dict,
                temperature=0.25,
                max_tokens=5000,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
            plans = tuple(
                FrameIPFusionPlan.from_mapping(item)
                for item in _coerce_mapping_response(response).get("frame_ip_fusion_plans") or ()
                if isinstance(item, Mapping)
            )
            if len(plans) != len(frame_visual_plans):
                raise ValueError("frame IP fusion count mismatch")
            return plans
        except Exception as exc:
            logger.warning("Frame IP fusion failed; using deterministic fallback: {}", exc)
            return tuple(_deterministic_fusion(frame, selected_route, compatibility_report, style_plan) for frame in frame_visual_plans)



def _coerce_mapping_response(response: Any) -> dict[str, Any]:
    if isinstance(response, Mapping):
        return dict(response)
    if isinstance(response, str):
        import json
        text = response.strip()
        if not text:
            return {}
        # Some providers wrap JSON in fenced markdown.
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            parsed = json.loads(text)
        except Exception:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}

def _fallback_article_and_routes(source_text: str, title: str | None, candidate_count: int) -> tuple[ArticleVisualUnderstanding, tuple[VisualRouteCandidate, ...], str]:
    excerpt = source_text.strip()[:220] or title or "article"
    article = ArticleVisualUnderstanding(
        input_kind=ArticleInputKind.FULL_ARTICLE if len(source_text) > 200 else ArticleInputKind.SHORT_COPY,
        summary=excerpt,
        core_claim=excerpt,
        central_problem="What visual logic best explains this article?",
        key_subjects=(title or "article_claim",),
        cognitive_opportunities=("claim", "structure", "metaphor"),
        evidence_spans=({"evidence_id": "source-1", "quote": excerpt, "role": "fallback"},),
    )
    routes = (
        VisualRouteCandidate(
            route_id="stable_editorial_explainer",
            route_name="稳健编辑图解",
            route_type=VisualRouteType.EDITORIAL_DIAGRAM,
            visual_premise="用清晰结构和克制隐喻解释文章核心观点",
            why_it_fits_article="这是低风险、可稳定生成、适合多数文章的默认路线。",
            frame_storytelling_logic="每帧解释一个局部观点，整体保持同一频道视觉签名。",
            style_family="editorial_diagram",
            recommended_ip_role="guide",
            scores=VisualRouteScores(0.76, 0.66, 0.74, 0.72, 0.88, 0.12),
        ),
        VisualRouteCandidate(
            route_id="philosophical_metaphor",
            route_name="哲学隐喻",
            route_type=VisualRouteType.PHILOSOPHICAL_METAPHOR,
            visual_premise="把文章抽象观点转成可记住的空间或物理隐喻",
            why_it_fits_article="适合表达情绪、命运、状态、困境和思想冲突。",
            frame_storytelling_logic="每帧延展同一个隐喻世界，避免重复但保持统一。",
            style_family="handdrawn_explainer",
            recommended_ip_role="silent_witness",
            scores=VisualRouteScores(0.72, 0.82, 0.70, 0.70, 0.72, 0.2),
        ),
        VisualRouteCandidate(
            route_id="absurd_comic",
            route_name="诙谐荒诞漫画",
            route_type=VisualRouteType.ABSURD_COMIC,
            visual_premise="用荒诞角色行动把文章矛盾变成轻松可记的场景",
            why_it_fits_article="适合轻松观点、吐槽、生活观察，不适合严肃题材。",
            frame_storytelling_logic="每帧一个小包袱，但统一角色和世界规则。",
            style_family="cartoon_comic",
            recommended_ip_role="core_actor",
            scores=VisualRouteScores(0.62, 0.84, 0.82, 0.62, 0.68, 0.32),
        ),
    )[: max(1, min(candidate_count, 3))]
    return article, routes, routes[0].route_id


def _neutral_compatibility(candidate: VisualRouteCandidate) -> IPRouteCompatibilityReport:
    return IPRouteCompatibilityReport(
        route_id=candidate.route_id,
        compatible=True,
        recommended_role=VisualSignatureRole.BACKGROUND_MARK,
        recommended_visibility=IPVisibilityLevel.BACKGROUND_MARK,
        compatibility_score=0.55,
        reason="No IP profile provided; use route without mandatory character insertion.",
        mitigation_rules=("visual signature optional",),
    )


def _deterministic_compatibility(candidate: VisualRouteCandidate, *, ip_profile: Mapping[str, Any] | None) -> IPRouteCompatibilityReport:
    serious = any("严肃" in note or "sensitive" in note.lower() for note in candidate.risk_notes)
    role = VisualSignatureRole.SILENT_WITNESS if serious else candidate.recommended_ip_role
    visibility = IPVisibilityLevel.LOW if serious else _visibility_for_role(role)
    score = max(0.35, min(0.92, candidate.scores.ip_compatibility or 0.72))
    return IPRouteCompatibilityReport(
        route_id=candidate.route_id,
        compatible=score >= 0.45,
        recommended_role=role,
        recommended_visibility=visibility,
        compatibility_score=score,
        reason="Deterministic compatibility based on route role, risk, and IP presence.",
        mitigation_rules=("do not replace article subjects", "vary visibility across frames"),
        safety_warnings=("use low intrusion for sensitive content",) if serious else (),
    )


def _apply_compatibility_scores(candidates: Sequence[VisualRouteCandidate], reports: Sequence[IPRouteCompatibilityReport]) -> tuple[VisualRouteCandidate, ...]:
    by_id = {report.route_id: report for report in reports}
    resolved: list[VisualRouteCandidate] = []
    for candidate in candidates:
        report = by_id.get(candidate.route_id)
        ip_score = report.compatibility_score if report else candidate.scores.ip_compatibility
        risk_penalty = 0.08 if report and report.safety_warnings else 0.0
        scores = VisualRouteScores(
            content_fit=candidate.scores.content_fit,
            memorability=candidate.scores.memorability,
            ip_compatibility=ip_score,
            channel_consistency=candidate.scores.channel_consistency,
            production_reliability=candidate.scores.production_reliability,
            risk=min(1.0, candidate.scores.risk + risk_penalty),
        )
        resolved.append(candidate.with_scores(scores))
    return tuple(resolved)


def _route_by_id(candidates: Sequence[VisualRouteCandidate], route_id: str) -> VisualRouteCandidate:
    for candidate in candidates:
        if candidate.route_id == route_id:
            return candidate
    return max(candidates, key=lambda candidate: candidate.final_score)


def _compat_by_route(reports: Sequence[IPRouteCompatibilityReport], route_id: str) -> IPRouteCompatibilityReport:
    for report in reports:
        if report.route_id == route_id:
            return report
    return IPRouteCompatibilityReport(
        route_id=route_id,
        compatible=True,
        recommended_role=VisualSignatureRole.SILENT_WITNESS,
        recommended_visibility=IPVisibilityLevel.LOW,
        compatibility_score=0.6,
        reason="fallback compatibility",
    )


def _conservative_route(candidates: Sequence[VisualRouteCandidate]) -> VisualRouteCandidate | None:
    conservative_types = {VisualRouteType.EDITORIAL_DIAGRAM, VisualRouteType.COGNITIVE_EXPLAINER, VisualRouteType.STRUCTURE_MAP}
    options = [candidate for candidate in candidates if candidate.route_type in conservative_types]
    if not options:
        return None
    return max(options, key=lambda candidate: candidate.final_score)


def _deterministic_style_plan(selected_route: VisualRouteCandidate, report: IPRouteCompatibilityReport, *, no_ip: bool) -> StyleHarmonizationPlan:
    if no_ip or report.recommended_visibility in {IPVisibilityLevel.NONE, IPVisibilityLevel.BACKGROUND_MARK, IPVisibilityLevel.SYMBOLIC}:
        mode = StyleHarmonizationMode.SYMBOLIC_PROJECTION
    elif selected_route.style_family.value in {"cartoon_comic", "handdrawn_explainer", "editorial_diagram"}:
        mode = StyleHarmonizationMode.MATCH_ROUTE_STYLE
    else:
        mode = StyleHarmonizationMode.HYBRID_LAYERED
    return StyleHarmonizationPlan(
        route_id=selected_route.route_id,
        mode=mode,
        ip_style_policy="IP follows the selected route enough to feel native while preserving identity locks.",
        scene_style_policy=f"Scene follows {selected_route.style_family.value} and route premise.",
        boundary_rule="IP must never overwrite required article subjects or evidence meaning.",
        positive_rules=("stable IP identity", "article subjects remain primary", "scene-bound integration"),
        negative_rules=("no pasted sticker", "no subject replacement", "no mid-video route switch"),
    )


def _visual_task_for_route(route: VisualRouteCandidate, visual_goal: str, prompt_intent: str) -> str:
    if route.route_type in {VisualRouteType.PROCESS_MAP, VisualRouteType.SCIENTIFIC_ANALOGY, VisualRouteType.MATHEMATICAL_MODEL}:
        return "explain a mechanism, process, or model"
    if route.route_type in {VisualRouteType.ABSURD_COMIC, VisualRouteType.CARTOON_STORY}:
        return "turn the local claim into a readable comic beat"
    if route.route_type in {VisualRouteType.PHILOSOPHICAL_METAPHOR, VisualRouteType.EMOTIONAL_THEATER}:
        return "turn the local claim into a memorable metaphorical moment"
    return prompt_intent or visual_goal or "visualize this article frame"


def _no_ip_fusion(frame: FrameVisualPlan) -> FrameIPFusionPlan:
    return FrameIPFusionPlan(
        frame_id=frame.frame_id,
        ip_role=VisualSignatureRole.NONE,
        ip_visibility=IPVisibilityLevel.NONE,
        placement_logic="No IP profile is active for this frame.",
        action_or_function="None.",
        relation_to_article_subject="No IP subject participates.",
        style_harmonization=StyleHarmonizationMode.MATCH_ROUTE_STYLE,
        positive_prompt_clause="",
    )


def _deterministic_fusion(
    frame: FrameVisualPlan,
    route: VisualRouteCandidate,
    report: IPRouteCompatibilityReport,
    style_plan: StyleHarmonizationPlan,
) -> FrameIPFusionPlan:
    role = report.recommended_role
    visibility = _visibility_for_role(role)
    clause = _clause_for_role(role, visibility, route)
    return FrameIPFusionPlan(
        frame_id=frame.frame_id,
        ip_role=role,
        ip_visibility=visibility,
        placement_logic="Integrate the IP as a scene-bound visual signature that supports the selected route.",
        action_or_function=f"Serve the route logic: {route.visual_premise}",
        relation_to_article_subject="IP supports comprehension and does not replace required article subjects.",
        style_harmonization=style_plan.mode,
        positive_prompt_clause=clause,
        negative_constraints=("do not replace article subjects", "do not appear as a pasted sticker"),
    )


def _visibility_for_role(role: VisualSignatureRole) -> IPVisibilityLevel:
    if role in {VisualSignatureRole.CORE_ACTOR, VisualSignatureRole.CONTAINER, VisualSignatureRole.OBSTACLE}:
        return IPVisibilityLevel.MEDIUM
    if role in {VisualSignatureRole.OPERATOR, VisualSignatureRole.GUIDE, VisualSignatureRole.NARRATOR}:
        return IPVisibilityLevel.MEDIUM
    if role in {VisualSignatureRole.BACKGROUND_MARK, VisualSignatureRole.SYMBOL}:
        return IPVisibilityLevel.BACKGROUND_MARK
    if role is VisualSignatureRole.NONE:
        return IPVisibilityLevel.NONE
    return IPVisibilityLevel.LOW


def _clause_for_role(role: VisualSignatureRole, visibility: IPVisibilityLevel, route: VisualRouteCandidate) -> str:
    if role is VisualSignatureRole.NONE or visibility is IPVisibilityLevel.NONE:
        return ""
    if role is VisualSignatureRole.OPERATOR:
        return "The channel IP appears as a small operator manipulating the diagram or model without replacing article subjects."
    if role is VisualSignatureRole.GUIDE:
        return "The channel IP appears as a subtle guide pointing through the visual logic."
    if role is VisualSignatureRole.SILENT_WITNESS:
        return "The channel IP appears as a quiet witness at the edge of the scene, visible but subordinate."
    if role is VisualSignatureRole.BACKGROUND_MARK:
        return "The channel visual signature appears as a small scene-bound mark or prop detail."
    return f"The channel IP participates as {role.value}, integrated into the selected {route.route_type.value} route."


def _ip_profile_payload(ip_profile: Any) -> dict[str, Any]:
    if ip_profile is None:
        return {}
    if isinstance(ip_profile, Mapping):
        return dict(ip_profile)
    if hasattr(ip_profile, "to_dict"):
        try:
            result = ip_profile.to_dict()
            if isinstance(result, Mapping):
                return dict(result)
        except Exception:
            pass
    fields = {}
    for key in (
        "name",
        "series_visual_signature_profile_id",
        "visual_summary",
        "identity_lock",
        "minimal_traits",
        "identity_anchors",
        "style_hint",
        "world_hint",
        "negative_constraints",
        "role_presets",
        "presence_spectrum",
    ):
        value = getattr(ip_profile, key, None)
        if value not in (None, "", (), []):
            fields[key] = list(value) if isinstance(value, tuple) else value
    return fields


__all__ = ["VisualStoryEngineService"]
