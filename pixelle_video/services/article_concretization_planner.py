from __future__ import annotations

from collections.abc import Iterable, Sequence
from enum import Enum
from typing import Any

from pixelle_video.models.article_concretization import (
    ArticleConcretizationPlan,
    ArticleConcretizationResolution,
    CognitiveAnchorKind,
    CognitiveAnchorPlan,
    DiagramRenderContract,
    DiagramRenderStyle,
    ExplanationDiagramBrief,
    ExplanationDiagramGrammar,
    SeriesVisualSignatureContract,
    SeriesVisualSignatureRole,
)
from pixelle_video.models.article_understanding import (
    ArticleUnderstandingPlan,
    FrameUnderstandingPlan,
    SubjectAnchor,
)
from pixelle_video.models.visual_planning_mode import PrimaryVisualTask

_DEFAULT_ENTITY = "article_claim"


class ArticleConcretizationPlanner:
    def plan(
        self,
        *,
        resolution: ArticleConcretizationResolution,
        article_plan: ArticleUnderstandingPlan,
        frame_plan: FrameUnderstandingPlan,
        source_text: str,
        identity_profile_id: str | None = None,
    ) -> ArticleConcretizationPlan | None:
        if not resolution.enabled:
            return None

        anchor_claim = _first_text(
            frame_plan.frame_claim,
            article_plan.core_claim,
            _excerpt(source_text),
        )
        anchor_question = _first_text(
            frame_plan.frame_question,
            _question_for_claim(anchor_claim),
        )
        source_evidence_ids = _source_evidence_ids(article_plan, frame_plan)
        source_excerpt = _source_text_excerpt(article_plan, frame_plan, source_text)
        selected_subjects = _preferred_subject_labels(article_plan, frame_plan)

        anchor = CognitiveAnchorPlan(
            anchor_id=f"{frame_plan.frame_id}-cognitive-anchor",
            anchor_kind=resolution.effective_anchor_kind,
            anchor_claim=anchor_claim,
            anchor_question=anchor_question,
            source_evidence_ids=source_evidence_ids,
            main_entities=selected_subjects,
            required_subjects=selected_subjects,
            source_text_excerpt=source_excerpt,
            confidence=_anchor_confidence(source_evidence_ids),
        )
        diagram = _build_diagram_brief(
            resolution=resolution,
            frame_plan=frame_plan,
            anchor_claim=anchor_claim,
            selected_subjects=selected_subjects,
            source_evidence_ids=source_evidence_ids,
        )
        signature = _build_signature_contract(
            resolution.effective_signature_role,
            identity_profile_id=identity_profile_id,
        )
        render = _build_render_contract(resolution)

        return ArticleConcretizationPlan(
            plan_id=f"{frame_plan.frame_id}-article-concretization-plan",
            frame_id=frame_plan.frame_id,
            request=resolution.request,
            resolution=resolution,
            anchor=anchor,
            diagram=diagram,
            series_signature=signature,
            render=render,
        )


def _build_diagram_brief(
    *,
    resolution: ArticleConcretizationResolution,
    frame_plan: FrameUnderstandingPlan,
    anchor_claim: str,
    selected_subjects: tuple[str, ...],
    source_evidence_ids: tuple[str, ...],
) -> ExplanationDiagramBrief:
    grammar = resolution.effective_diagram_grammar
    anchor_kind = resolution.effective_anchor_kind
    return ExplanationDiagramBrief(
        brief_id=f"{frame_plan.frame_id}-explanation-diagram",
        grammar=grammar,
        primary_visual_task=_primary_visual_task(anchor_kind),
        diagram_title=_diagram_title(anchor_kind, anchor_claim),
        visual_metaphor=_visual_metaphor(anchor_kind, grammar),
        composition_rules=_composition_rules(
            grammar=grammar,
            subjects=selected_subjects,
            evidence_ids=source_evidence_ids,
            panel_inside_canvas=resolution.layout.panel_inside_canvas,
            user_intent_hint=resolution.request.diagram_user_intent_hint,
        ),
        panel_plan=_panel_plan(grammar, selected_subjects),
        forbidden_losses=_forbidden_losses(
            anchor_kind=anchor_kind,
            subjects=selected_subjects,
            evidence_ids=source_evidence_ids,
        ),
        visible_text=resolution.visible_text,
    )


def _build_signature_contract(
    role: SeriesVisualSignatureRole,
    *,
    identity_profile_id: str | None,
) -> SeriesVisualSignatureContract:
    if role in {SeriesVisualSignatureRole.NONE, SeriesVisualSignatureRole.AUTO}:
        return SeriesVisualSignatureContract(
            enabled=False,
            role=SeriesVisualSignatureRole.NONE,
            identity_profile_id=None,
            participation_rule="No recurring series signature participates.",
            replacement_policy="no_subject_replacement",
            visual_weight=0.0,
            forbidden_behaviors=(
                "do not replace article subjects",
                "do not add a recurring signature subject",
            ),
        )
    if not identity_profile_id:
        raise ValueError("identity_profile_id is required for enabled series signature")

    return SeriesVisualSignatureContract(
        enabled=True,
        role=role,
        identity_profile_id=identity_profile_id,
        participation_rule=(
            f"Series signature identity {identity_profile_id} participates as "
            f"{role.value} role only; it must not replace article subjects."
        ),
        replacement_policy="no_subject_replacement",
        visual_weight=_signature_visual_weight(role),
        forbidden_behaviors=(
            "do not replace article subjects",
            "do not override required subjects",
            "do not become the evidence source",
        ),
    )


def _build_render_contract(
    resolution: ArticleConcretizationResolution,
) -> DiagramRenderContract:
    render_style = resolution.effective_render_style
    return DiagramRenderContract(
        render_style=render_style,
        canvas_aspect_ratio=resolution.layout.canvas_aspect_ratio,
        diagram_panel_aspect_ratio=resolution.layout.diagram_panel_aspect_ratio,
        panel_inside_canvas=resolution.layout.panel_inside_canvas,
        style_rules=_style_rules(render_style),
        negative_style_rules=_negative_style_rules(render_style),
    )


def _primary_visual_task(anchor_kind: CognitiveAnchorKind) -> PrimaryVisualTask:
    if anchor_kind in {CognitiveAnchorKind.CAUSAL_MECHANISM, CognitiveAnchorKind.PROCESS}:
        return PrimaryVisualTask.PROCESS_WALKTHROUGH
    if anchor_kind in {CognitiveAnchorKind.STRUCTURE, CognitiveAnchorKind.EVIDENCE}:
        return PrimaryVisualTask.STRUCTURE_EXPLANATION
    if anchor_kind is CognitiveAnchorKind.CONTRAST:
        return PrimaryVisualTask.CONTRAST_ARGUMENT
    if anchor_kind is CognitiveAnchorKind.RELATIONSHIP:
        return PrimaryVisualTask.RELATIONSHIP_MAPPING
    return PrimaryVisualTask.COGNITIVE_EXPLANATION


def _diagram_title(anchor_kind: CognitiveAnchorKind, claim: str) -> str:
    prefix_by_kind = {
        CognitiveAnchorKind.CAUSAL_MECHANISM: "Mechanism",
        CognitiveAnchorKind.PROCESS: "Process",
        CognitiveAnchorKind.STRUCTURE: "Structure",
        CognitiveAnchorKind.EVIDENCE: "Evidence",
        CognitiveAnchorKind.CONTRAST: "Contrast",
        CognitiveAnchorKind.RELATIONSHIP: "Relationship",
        CognitiveAnchorKind.DECISION_PATH: "Decision Path",
        CognitiveAnchorKind.STATE_MACHINE: "State Machine",
        CognitiveAnchorKind.STATE: "State",
        CognitiveAnchorKind.METAPHOR: "Metaphor",
        CognitiveAnchorKind.JUDGMENT: "Claim",
        CognitiveAnchorKind.AUTO: "Article Claim",
    }
    title_claim = _title_text(claim)
    return f"{prefix_by_kind.get(anchor_kind, 'Article Claim')}: {title_claim}"


def _visual_metaphor(
    anchor_kind: CognitiveAnchorKind,
    grammar: ExplanationDiagramGrammar,
) -> str:
    if anchor_kind is CognitiveAnchorKind.CAUSAL_MECHANISM:
        return "cause and effect chain with feedback arrows"
    if anchor_kind is CognitiveAnchorKind.PROCESS:
        return "ordered steps moving through a clear pathway"
    if anchor_kind is CognitiveAnchorKind.STRUCTURE:
        return "labeled parts arranged around a central system"
    if anchor_kind is CognitiveAnchorKind.EVIDENCE:
        return "evidence cards connected to the central claim"
    if anchor_kind is CognitiveAnchorKind.CONTRAST:
        return "two opposing columns with a decisive comparison line"
    if anchor_kind is CognitiveAnchorKind.RELATIONSHIP:
        return "nodes and links showing how subjects influence each other"
    if grammar is ExplanationDiagramGrammar.METAPHOR_SCENE:
        return "abstract pressure field around the article claim"
    return "plain explanatory diagram centered on the article claim"


def _composition_rules(
    *,
    grammar: ExplanationDiagramGrammar,
    subjects: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    panel_inside_canvas: bool,
    user_intent_hint: str | None,
) -> tuple[str, ...]:
    subject_rule = "preserve required subjects: " + ", ".join(subjects)
    evidence_rule = (
        "ground the diagram in evidence ids: " + ", ".join(evidence_ids)
        if evidence_ids
        else "ground the diagram in the source text excerpt"
    )
    layout_rule = (
        "place the diagram panel inside the canvas"
        if panel_inside_canvas
        else "use the full canvas for the diagram"
    )
    rules = [
        f"use {grammar.value} grammar",
        subject_rule,
        evidence_rule,
        layout_rule,
    ]
    if user_intent_hint:
        rules.append(f"user intent: {user_intent_hint}")
    return tuple(rules)


def _panel_plan(
    grammar: ExplanationDiagramGrammar,
    subjects: tuple[str, ...],
) -> tuple[str, ...]:
    first_subject = subjects[0]
    last_subject = subjects[-1]
    if grammar is ExplanationDiagramGrammar.PROCESS_FLOW:
        return (
            f"Start state: {first_subject}",
            "Middle state: show the causal transition",
            f"End state: {last_subject}",
        )
    if grammar is ExplanationDiagramGrammar.CONTRAST_BOARD:
        return (
            f"Left side: {first_subject}",
            f"Right side: {last_subject}",
            "Center: explain the contrast criterion",
        )
    if grammar is ExplanationDiagramGrammar.RELATIONSHIP_MAP:
        return (
            "Center: article claim node",
            "Around it: required subject nodes",
            "Edges: label the relationships without inventing new actors",
        )
    if grammar in {
        ExplanationDiagramGrammar.STRUCTURE_MAP,
        ExplanationDiagramGrammar.EVIDENCE_MAP,
    }:
        return (
            "Top: central claim",
            "Middle: required subject structure",
            "Bottom: evidence-supported implications",
        )
    if grammar in {
        ExplanationDiagramGrammar.DECISION_TREE,
        ExplanationDiagramGrammar.STATE_MACHINE,
    }:
        return (
            f"Entry: {first_subject}",
            "Branches: article-supported transitions",
            f"Terminal state: {last_subject}",
        )
    return (
        "Primary panel: article claim",
        "Secondary area: required subjects",
        "Support area: evidence cue",
    )


def _forbidden_losses(
    *,
    anchor_kind: CognitiveAnchorKind,
    subjects: tuple[str, ...],
    evidence_ids: tuple[str, ...],
) -> tuple[str, ...]:
    losses = [
        f"do not change anchor kind {anchor_kind.value}",
        "do not omit required subjects: " + ", ".join(subjects),
    ]
    if evidence_ids:
        losses.append("do not drop evidence ids: " + ", ".join(evidence_ids))
    else:
        losses.append("do not drop the source text excerpt")
    return tuple(losses)


def _style_rules(render_style: DiagramRenderStyle) -> tuple[str, ...]:
    if render_style is DiagramRenderStyle.XIAOHEI_HANDDRAWN:
        return (
            "hand-drawn explanatory panel style",
            "simple black marker linework",
            "plain paper texture",
            "limited red orange blue annotation marks",
        )
    if render_style is DiagramRenderStyle.EDITORIAL_DIAGRAM:
        return (
            "clean editorial linework",
            "muted accent color for arrows",
            "high contrast explanatory shapes",
        )
    if render_style is DiagramRenderStyle.CLEAN_VECTOR:
        return (
            "precise vector strokes",
            "flat fills with restrained accent colors",
            "clear geometric hierarchy",
        )
    if render_style is DiagramRenderStyle.CINEMATIC_METAPHOR:
        return (
            "cinematic lighting on symbolic shapes",
            "clear foreground and background depth",
            "controlled dramatic contrast",
        )
    if render_style is DiagramRenderStyle.BRAND_KV:
        return (
            "key visual composition",
            "brand-safe color balance",
            "polished campaign layout",
        )
    if render_style is DiagramRenderStyle.THREE_D_CONCEPT:
        return (
            "simple 3d conceptual forms",
            "soft studio lighting",
            "legible spatial hierarchy",
        )
    if render_style is DiagramRenderStyle.INK_COLLAGE:
        return (
            "ink collage texture",
            "cut-paper explanatory shapes",
            "controlled high-contrast edges",
        )
    return (
        "neutral explanatory diagram style",
        "clear subject hierarchy",
        "readable shape language",
    )


def _negative_style_rules(render_style: DiagramRenderStyle) -> tuple[str, ...]:
    if render_style is DiagramRenderStyle.XIAOHEI_HANDDRAWN:
        return (
            "surface style only; no fixed identity semantics",
            "no photorealistic shading",
            "no decorative text",
        )
    return (
        "no decorative text",
        "no unsupported subject substitution",
        "no style rule that changes the article claim",
    )


def _signature_visual_weight(role: SeriesVisualSignatureRole) -> float:
    if role in {
        SeriesVisualSignatureRole.SILENT_WITNESS,
        SeriesVisualSignatureRole.BACKGROUND_MARK,
    }:
        return 0.2
    if role in {SeriesVisualSignatureRole.GUIDE, SeriesVisualSignatureRole.OPERATOR}:
        return 0.35
    if role in {
        SeriesVisualSignatureRole.CORE_ACTOR,
        SeriesVisualSignatureRole.CONTAINER,
        SeriesVisualSignatureRole.OBSTACLE,
    }:
        return 0.45
    return 0.0


def _preferred_subject_labels(
    article_plan: ArticleUnderstandingPlan,
    frame_plan: FrameUnderstandingPlan,
) -> tuple[str, ...]:
    for values in (
        _subject_labels(frame_plan.required_subjects),
        _subject_labels(article_plan.required_subjects),
        _text_tuple(article_plan.main_entities),
    ):
        if values:
            return values
    return (_DEFAULT_ENTITY,)


def _subject_labels(subjects: Sequence[SubjectAnchor]) -> tuple[str, ...]:
    return _unique_text(getattr(subject, "label", "") for subject in subjects)


def _source_evidence_ids(
    article_plan: ArticleUnderstandingPlan,
    frame_plan: FrameUnderstandingPlan,
) -> tuple[str, ...]:
    frame_ids = _evidence_ids(frame_plan.source_evidence)
    if frame_ids:
        return frame_ids
    article_ids = _evidence_ids(article_plan.source_evidence)
    if article_ids:
        return article_ids
    return _unique_text(
        evidence_id
        for subject in (*frame_plan.required_subjects, *article_plan.required_subjects)
        for evidence_id in getattr(subject, "evidence_span_ids", ())
    )


def _evidence_ids(values: Sequence[Any]) -> tuple[str, ...]:
    return _unique_text(getattr(value, "evidence_id", "") for value in values)


def _source_text_excerpt(
    article_plan: ArticleUnderstandingPlan,
    frame_plan: FrameUnderstandingPlan,
    source_text: str,
) -> str:
    return _first_text(
        _first_evidence_quote(frame_plan.source_evidence),
        _first_evidence_quote(article_plan.source_evidence),
        _excerpt(source_text),
        _excerpt(frame_plan.source_text),
        _excerpt(frame_plan.frame_claim),
        _excerpt(article_plan.core_claim),
        _DEFAULT_ENTITY,
    )


def _first_evidence_quote(values: Sequence[Any]) -> str:
    for value in values:
        quote = _text(getattr(value, "quote", ""))
        if quote:
            return _excerpt(quote)
    return ""


def _anchor_confidence(source_evidence_ids: tuple[str, ...]) -> float:
    return 0.86 if source_evidence_ids else 0.62


def _question_for_claim(claim: str) -> str:
    if not claim:
        return "What does this article claim?"
    return "What does this article claim?"


def _title_text(text: str) -> str:
    title = _excerpt(text, max_length=72).rstrip(".!?;:")
    return title or _DEFAULT_ENTITY


def _excerpt(value: Any, *, max_length: int = 220) -> str:
    text = _text(value)
    if len(text) <= max_length:
        return text
    truncated = text[: max_length - 1].rstrip()
    return f"{truncated}..."


def _text_tuple(values: Sequence[Any]) -> tuple[str, ...]:
    return _unique_text(_text(value) for value in values)


def _unique_text(values: Iterable[Any]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        key = text.casefold()
        if not text or key in seen:
            continue
        normalized.append(text)
        seen.add(key)
    return tuple(normalized)


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return _DEFAULT_ENTITY


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        value = value.value
    return str(value).strip()


__all__ = ["ArticleConcretizationPlanner"]
