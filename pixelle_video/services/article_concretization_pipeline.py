from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.models.article_concretization import (
    ArticleConcretizationPlan,
    DiagramAspectRatio,
)
from pixelle_video.models.article_understanding import (
    ArticleUnderstandingLens,
    ArticleUnderstandingMode,
    ArticleUnderstandingPlan,
    FrameUnderstandingPlan,
    SourceEvidenceSpan,
    SubjectAnchor,
)
from pixelle_video.models.mode_resolution import ArticleVisualPlanningRequest
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.visual_planning_mode import VisibleTextPolicy
from pixelle_video.services.article_concretization_planner import (
    ArticleConcretizationPlanner,
)
from pixelle_video.services.article_concretization_resolution import (
    resolve_article_concretization,
)

MODE_TO_LENS: Mapping[ArticleUnderstandingMode, ArticleUnderstandingLens] = {
    ArticleUnderstandingMode.THESIS_ARGUMENT: ArticleUnderstandingLens.THESIS_ARGUMENT,
    ArticleUnderstandingMode.CAUSAL_MECHANISM: ArticleUnderstandingLens.CAUSAL_MECHANISM,
    ArticleUnderstandingMode.COGNITIVE_STATE: ArticleUnderstandingLens.COGNITIVE_STATE,
    ArticleUnderstandingMode.PROCESS_METHOD: ArticleUnderstandingLens.PROCESS_METHOD,
    ArticleUnderstandingMode.RELATIONSHIP_STRUCTURE: ArticleUnderstandingLens.RELATIONSHIP_STRUCTURE,
    ArticleUnderstandingMode.CONTRAST_CONFLICT: ArticleUnderstandingLens.CONTRAST_CONFLICT,
    ArticleUnderstandingMode.NARRATIVE_EVENT: ArticleUnderstandingLens.NARRATIVE_EVENT,
    ArticleUnderstandingMode.METAPHOR_SYMBOLIC: ArticleUnderstandingLens.METAPHOR_SYMBOLIC,
}


def build_article_concretization_plans(
    *,
    storyboard_plan: StoryboardPlan,
    params: Mapping[str, Any],
    series_visual_signature_profile_id: str | None,
    template_aspect_ratio: DiagramAspectRatio,
) -> tuple[ArticleConcretizationPlan, ...]:
    request = ArticleVisualPlanningRequest.from_mapping(params)
    concretization_request = request.article_concretization
    if not concretization_request.enabled:
        return ()

    article_plan = _article_understanding_plan(
        storyboard_plan=storyboard_plan,
        primary_lens=_primary_lens(request.article_understanding_mode),
    )
    plans: list[ArticleConcretizationPlan] = []
    planner = ArticleConcretizationPlanner()
    for frame in storyboard_plan.frames:
        frame_plan = _frame_understanding_plan(
            frame=frame,
            article_plan=article_plan,
        )
        resolution = resolve_article_concretization(
            request=concretization_request,
            article_plan=article_plan,
            frame_plan=frame_plan,
            series_visual_signature_profile_id=series_visual_signature_profile_id,
            template_aspect_ratio=template_aspect_ratio,
            strict_user_mode=request.strict_user_mode,
            series_visual_signature_strategy=request.series_visual_signature_strategy,
        )
        plan = planner.plan(
            resolution=resolution,
            article_plan=article_plan,
            frame_plan=frame_plan,
            source_text=storyboard_plan.source_text,
            identity_profile_id=series_visual_signature_profile_id,
        )
        if plan is None:
            raise ValueError("enabled article concretization produced no plan")
        plans.append(plan)
    article_concretization_plans_by_frame(
        storyboard_plan=storyboard_plan,
        plans=plans,
    )
    return tuple(plans)


def diagram_aspect_ratio_from_canvas(width: int, height: int) -> DiagramAspectRatio:
    if width <= 0 or height <= 0:
        return DiagramAspectRatio.AUTO
    if width == height:
        return DiagramAspectRatio.SQUARE_1_1
    if width > height:
        return DiagramAspectRatio.LANDSCAPE_16_9
    return (
        DiagramAspectRatio.VERTICAL_9_16
        if height / width >= 1.6
        else DiagramAspectRatio.PORTRAIT_4_5
    )


def article_concretization_snapshot(
    *,
    storyboard_plan: StoryboardPlan,
    plans: Sequence[ArticleConcretizationPlan],
) -> dict[str, Any]:
    plans_by_frame = article_concretization_plans_by_frame(
        storyboard_plan=storyboard_plan,
        plans=plans,
    )
    return {frame_id: plan.to_dict() for frame_id, plan in plans_by_frame.items()}


def article_concretization_plans_by_frame(
    *,
    storyboard_plan: StoryboardPlan,
    plans: Sequence[ArticleConcretizationPlan],
) -> dict[str, ArticleConcretizationPlan]:
    if not plans:
        return {}
    frame_ids = [frame.frame_id for frame in storyboard_plan.frames]
    plan_frame_ids = [plan.frame_id for plan in plans]
    if plan_frame_ids != frame_ids:
        raise ValueError("article_concretization_plans must match storyboard frame ids")
    return dict(zip(frame_ids, plans, strict=True))


def _primary_lens(mode: ArticleUnderstandingMode) -> ArticleUnderstandingLens:
    return MODE_TO_LENS.get(mode, ArticleUnderstandingLens.THESIS_ARGUMENT)


def _article_understanding_plan(
    *,
    storyboard_plan: StoryboardPlan,
    primary_lens: ArticleUnderstandingLens,
) -> ArticleUnderstandingPlan:
    evidence = tuple(
        _evidence_for_frame(storyboard_plan=storyboard_plan, frame=frame)
        for frame in storyboard_plan.frames
    )
    subject_labels = _dedupe(
        label
        for frame in storyboard_plan.frames
        for label in _subject_labels_for_frame(frame)
    )
    if not subject_labels:
        subject_labels = ("Article claim",)
    evidence_id = evidence[0].evidence_id
    return ArticleUnderstandingPlan(
        article_id=storyboard_plan.plan_id,
        primary_lens=primary_lens,
        core_claim=_first_text(
            *(frame.visual_goal for frame in storyboard_plan.frames),
            storyboard_plan.source_text,
        ),
        central_problem=_first_text(
            *(frame.prompt_intent for frame in storyboard_plan.frames),
            storyboard_plan.source_text,
        ),
        main_entities=subject_labels,
        required_subjects=tuple(
            _subject_anchor(
                subject_id=f"{storyboard_plan.plan_id}-subject-{index + 1}",
                label=label,
                evidence_id=evidence_id,
            )
            for index, label in enumerate(subject_labels)
        ),
        source_evidence=evidence,
    )


def _frame_understanding_plan(
    *,
    frame: StoryboardPlanFrame,
    article_plan: ArticleUnderstandingPlan,
) -> FrameUnderstandingPlan:
    evidence = SourceEvidenceSpan(
        evidence_id=f"{frame.frame_id}-article-concretization-evidence",
        source_id=article_plan.article_id,
        frame_id=frame.frame_id,
        quote=frame.source_text,
        evidence_role="frame_claim",
        start_char=frame.source_start,
        end_char=frame.source_end,
    )
    labels = _subject_labels_for_frame(frame) or tuple(article_plan.main_entities)
    if not labels:
        labels = ("Article claim",)
    return FrameUnderstandingPlan(
        frame_id=frame.frame_id,
        source_text=frame.source_text,
        frame_claim=_first_text(frame.visual_goal, frame.source_text),
        frame_question=_first_text(frame.prompt_intent, frame.visual_goal, frame.source_text),
        primary_lens=article_plan.primary_lens,
        required_subjects=tuple(
            _subject_anchor(
                subject_id=f"{frame.frame_id}-subject-{index + 1}",
                label=label,
                evidence_id=evidence.evidence_id,
            )
            for index, label in enumerate(labels)
        ),
        source_evidence=(evidence,),
        visible_text_policy=VisibleTextPolicy.FREE_TEXT_ALLOWED,
    )


def _evidence_for_frame(
    *,
    storyboard_plan: StoryboardPlan,
    frame: StoryboardPlanFrame,
) -> SourceEvidenceSpan:
    return SourceEvidenceSpan(
        evidence_id=f"{frame.frame_id}-article-concretization-evidence",
        source_id=storyboard_plan.plan_id,
        frame_id=frame.frame_id,
        quote=frame.source_text,
        evidence_role="frame_source",
        start_char=frame.source_start,
        end_char=frame.source_end,
    )


def _subject_anchor(*, subject_id: str, label: str, evidence_id: str) -> SubjectAnchor:
    return SubjectAnchor(
        subject_id=subject_id,
        label=label,
        source_phrase=label,
        evidence_span_ids=(evidence_id,),
        importance="primary",
        visual_presence="required",
        loss_policy="forbidden",
    )


def _subject_labels_for_frame(frame: StoryboardPlanFrame) -> tuple[str, ...]:
    return _dedupe(
        (
            frame.primary_subject,
            *frame.secondary_subjects,
            *frame.continuity_anchors,
        )
    )


def _dedupe(values: Sequence[Any]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return tuple(normalized)


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return "Article claim"


__all__ = [
    "article_concretization_plans_by_frame",
    "article_concretization_snapshot",
    "build_article_concretization_plans",
    "diagram_aspect_ratio_from_canvas",
]
