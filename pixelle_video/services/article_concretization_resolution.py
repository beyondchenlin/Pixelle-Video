from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from enum import Enum
from types import MappingProxyType
from typing import Any

from pixelle_video.models.article_concretization import (
    ArticleConcretizationRequest,
    ArticleConcretizationResolution,
    CognitiveAnchorKind,
    DiagramAspectRatio,
    DiagramLayoutResolution,
    DiagramRenderStyle,
    ExplanationDiagramGrammar,
    SeriesVisualSignatureRole,
    VisibleTextResolution,
)
from pixelle_video.models.article_understanding import (
    ArticleUnderstandingLens,
    ArticleUnderstandingPlan,
    FrameUnderstandingPlan,
)
from pixelle_video.models.visual_planning_mode import VisibleTextPolicy


class ArticleConcretizationResolutionConflict(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


DEFAULT_ANCHOR_BY_LENS: Mapping[ArticleUnderstandingLens, CognitiveAnchorKind] = MappingProxyType(
    {
        ArticleUnderstandingLens.THESIS_ARGUMENT: CognitiveAnchorKind.JUDGMENT,
        ArticleUnderstandingLens.CAUSAL_MECHANISM: CognitiveAnchorKind.CAUSAL_MECHANISM,
        ArticleUnderstandingLens.COGNITIVE_STATE: CognitiveAnchorKind.STATE,
        ArticleUnderstandingLens.PROCESS_METHOD: CognitiveAnchorKind.PROCESS,
        ArticleUnderstandingLens.RELATIONSHIP_STRUCTURE: CognitiveAnchorKind.RELATIONSHIP,
        ArticleUnderstandingLens.CONTRAST_CONFLICT: CognitiveAnchorKind.CONTRAST,
        ArticleUnderstandingLens.NARRATIVE_EVENT: CognitiveAnchorKind.PROCESS,
        ArticleUnderstandingLens.METAPHOR_SYMBOLIC: CognitiveAnchorKind.METAPHOR,
    }
)

DEFAULT_GRAMMAR_BY_ANCHOR: Mapping[CognitiveAnchorKind, ExplanationDiagramGrammar] = MappingProxyType(
    {
        CognitiveAnchorKind.AUTO: ExplanationDiagramGrammar.AUTO,
        CognitiveAnchorKind.JUDGMENT: ExplanationDiagramGrammar.SINGLE_EXPLANATION_IMAGE,
        CognitiveAnchorKind.CAUSAL_MECHANISM: ExplanationDiagramGrammar.PROCESS_FLOW,
        CognitiveAnchorKind.PROCESS: ExplanationDiagramGrammar.PROCESS_FLOW,
        CognitiveAnchorKind.STRUCTURE: ExplanationDiagramGrammar.STRUCTURE_MAP,
        CognitiveAnchorKind.STATE: ExplanationDiagramGrammar.METAPHOR_SCENE,
        CognitiveAnchorKind.METAPHOR: ExplanationDiagramGrammar.METAPHOR_SCENE,
        CognitiveAnchorKind.CONTRAST: ExplanationDiagramGrammar.CONTRAST_BOARD,
        CognitiveAnchorKind.RELATIONSHIP: ExplanationDiagramGrammar.RELATIONSHIP_MAP,
        CognitiveAnchorKind.EVIDENCE: ExplanationDiagramGrammar.EVIDENCE_MAP,
        CognitiveAnchorKind.DECISION_PATH: ExplanationDiagramGrammar.DECISION_TREE,
        CognitiveAnchorKind.STATE_MACHINE: ExplanationDiagramGrammar.STATE_MACHINE,
    }
)

COMPATIBLE_GRAMMARS_BY_ANCHOR: Mapping[
    CognitiveAnchorKind, tuple[ExplanationDiagramGrammar, ...]
] = MappingProxyType(
    {
        CognitiveAnchorKind.JUDGMENT: (
            ExplanationDiagramGrammar.SINGLE_EXPLANATION_IMAGE,
            ExplanationDiagramGrammar.CONTRAST_BOARD,
            ExplanationDiagramGrammar.METAPHOR_SCENE,
        ),
        CognitiveAnchorKind.CAUSAL_MECHANISM: (
            ExplanationDiagramGrammar.PROCESS_FLOW,
            ExplanationDiagramGrammar.STRUCTURE_MAP,
            ExplanationDiagramGrammar.METAPHOR_SCENE,
        ),
        CognitiveAnchorKind.PROCESS: (
            ExplanationDiagramGrammar.PROCESS_FLOW,
            ExplanationDiagramGrammar.MULTI_PANEL_COMIC,
            ExplanationDiagramGrammar.STATE_MACHINE,
        ),
        CognitiveAnchorKind.STRUCTURE: (
            ExplanationDiagramGrammar.STRUCTURE_MAP,
            ExplanationDiagramGrammar.RELATIONSHIP_MAP,
        ),
        CognitiveAnchorKind.STATE: (
            ExplanationDiagramGrammar.METAPHOR_SCENE,
            ExplanationDiagramGrammar.STATE_MACHINE,
            ExplanationDiagramGrammar.SINGLE_EXPLANATION_IMAGE,
        ),
        CognitiveAnchorKind.METAPHOR: (
            ExplanationDiagramGrammar.METAPHOR_SCENE,
            ExplanationDiagramGrammar.SINGLE_EXPLANATION_IMAGE,
        ),
        CognitiveAnchorKind.CONTRAST: (
            ExplanationDiagramGrammar.CONTRAST_BOARD,
            ExplanationDiagramGrammar.SINGLE_EXPLANATION_IMAGE,
        ),
        CognitiveAnchorKind.RELATIONSHIP: (
            ExplanationDiagramGrammar.RELATIONSHIP_MAP,
            ExplanationDiagramGrammar.STRUCTURE_MAP,
        ),
        CognitiveAnchorKind.EVIDENCE: (
            ExplanationDiagramGrammar.EVIDENCE_MAP,
            ExplanationDiagramGrammar.STRUCTURE_MAP,
        ),
        CognitiveAnchorKind.DECISION_PATH: (
            ExplanationDiagramGrammar.DECISION_TREE,
            ExplanationDiagramGrammar.PROCESS_FLOW,
        ),
        CognitiveAnchorKind.STATE_MACHINE: (
            ExplanationDiagramGrammar.STATE_MACHINE,
            ExplanationDiagramGrammar.PROCESS_FLOW,
        ),
    }
)

AUTO_SIGNATURE_ROLE_BY_ANCHOR: Mapping[CognitiveAnchorKind, SeriesVisualSignatureRole] = MappingProxyType(
    {
        CognitiveAnchorKind.CAUSAL_MECHANISM: SeriesVisualSignatureRole.OPERATOR,
        CognitiveAnchorKind.PROCESS: SeriesVisualSignatureRole.OPERATOR,
        CognitiveAnchorKind.DECISION_PATH: SeriesVisualSignatureRole.OPERATOR,
        CognitiveAnchorKind.STATE_MACHINE: SeriesVisualSignatureRole.OPERATOR,
        CognitiveAnchorKind.STRUCTURE: SeriesVisualSignatureRole.GUIDE,
        CognitiveAnchorKind.RELATIONSHIP: SeriesVisualSignatureRole.GUIDE,
        CognitiveAnchorKind.EVIDENCE: SeriesVisualSignatureRole.GUIDE,
        CognitiveAnchorKind.JUDGMENT: SeriesVisualSignatureRole.SILENT_WITNESS,
        CognitiveAnchorKind.STATE: SeriesVisualSignatureRole.SILENT_WITNESS,
        CognitiveAnchorKind.METAPHOR: SeriesVisualSignatureRole.SILENT_WITNESS,
        CognitiveAnchorKind.CONTRAST: SeriesVisualSignatureRole.SILENT_WITNESS,
    }
)


def resolve_article_concretization(
    *,
    request: ArticleConcretizationRequest,
    article_plan: ArticleUnderstandingPlan,
    frame_plan: FrameUnderstandingPlan,
    series_visual_signature_profile_id: str | None,
    template_aspect_ratio: DiagramAspectRatio,
    strict_user_mode: bool,
    series_visual_signature_strategy: Any = None,
) -> ArticleConcretizationResolution:
    template_ratio = _diagram_aspect_ratio(template_aspect_ratio, "template_aspect_ratio")
    if not request.enabled:
        return _disabled_resolution(request=request, template_aspect_ratio=template_ratio)

    warnings: list[str] = []
    fallback_reason: str | None = None

    def mark_fallback(reason: str | None) -> None:
        nonlocal fallback_reason
        if reason is not None and fallback_reason is None:
            fallback_reason = reason

    anchor = _resolve_anchor(request=request, article_plan=article_plan, frame_plan=frame_plan)
    grammar, grammar_warnings, grammar_fallback = _resolve_grammar(
        request=request,
        anchor=anchor,
        strict_user_mode=strict_user_mode,
    )
    warnings.extend(grammar_warnings)
    mark_fallback(grammar_fallback)

    layout = _resolve_layout(request=request, template_aspect_ratio=template_ratio)
    warnings.extend(layout.warnings)

    visible_text, visible_text_fallback = _resolve_visible_text(
        request=request,
        frame_plan=frame_plan,
        strict_user_mode=strict_user_mode,
    )
    warnings.extend(visible_text.warnings)
    mark_fallback(visible_text_fallback)

    signature_role, signature_warnings, signature_fallback = _resolve_signature_role(
        request=request,
        anchor=anchor,
        grammar=grammar,
        series_visual_signature_profile_id=series_visual_signature_profile_id,
        strict_user_mode=strict_user_mode,
    )
    warnings.extend(signature_warnings)
    mark_fallback(signature_fallback)

    warnings.extend(
        _legacy_series_visual_signature_strategy_warnings(
            request=request,
            series_visual_signature_strategy=series_visual_signature_strategy,
        )
    )

    return ArticleConcretizationResolution(
        request=request,
        enabled=True,
        effective_anchor_kind=anchor,
        effective_diagram_grammar=grammar,
        effective_signature_role=signature_role,
        effective_render_style=request.diagram_render_style,
        layout=layout,
        visible_text=visible_text,
        approved_labels=request.diagram_approved_labels,
        warnings=warnings,
        errors=(),
        fallback_used=fallback_reason is not None,
        fallback_reason=fallback_reason,
    )


def _disabled_resolution(
    *,
    request: ArticleConcretizationRequest,
    template_aspect_ratio: DiagramAspectRatio,
) -> ArticleConcretizationResolution:
    return ArticleConcretizationResolution(
        request=request,
        enabled=False,
        effective_anchor_kind=CognitiveAnchorKind.AUTO,
        effective_diagram_grammar=ExplanationDiagramGrammar.AUTO,
        effective_signature_role=SeriesVisualSignatureRole.NONE,
        effective_render_style=DiagramRenderStyle.AUTO,
        layout=DiagramLayoutResolution(
            canvas_aspect_ratio=template_aspect_ratio,
            diagram_panel_aspect_ratio=template_aspect_ratio,
            panel_inside_canvas=False,
            layout_intent="template_default",
        ),
        visible_text=VisibleTextResolution(
            effective_policy=VisibleTextPolicy.NO_VISIBLE_TEXT,
            allowed_visible_text=(),
            text_origin="none",
        ),
        approved_labels=(),
        warnings=(),
        errors=(),
        fallback_used=False,
        fallback_reason=None,
    )


def _resolve_anchor(
    *,
    request: ArticleConcretizationRequest,
    article_plan: ArticleUnderstandingPlan,
    frame_plan: FrameUnderstandingPlan,
) -> CognitiveAnchorKind:
    if request.cognitive_anchor_kind is not CognitiveAnchorKind.AUTO:
        return request.cognitive_anchor_kind
    lens = getattr(frame_plan, "primary_lens", None) or article_plan.primary_lens
    return DEFAULT_ANCHOR_BY_LENS.get(lens, CognitiveAnchorKind.JUDGMENT)


def _resolve_grammar(
    *,
    request: ArticleConcretizationRequest,
    anchor: CognitiveAnchorKind,
    strict_user_mode: bool,
) -> tuple[ExplanationDiagramGrammar, tuple[str, ...], str | None]:
    default_grammar = DEFAULT_GRAMMAR_BY_ANCHOR.get(anchor, ExplanationDiagramGrammar.SINGLE_EXPLANATION_IMAGE)
    requested_grammar = request.explanation_diagram_grammar
    if requested_grammar is ExplanationDiagramGrammar.AUTO:
        return default_grammar, (), None

    compatible_grammars = COMPATIBLE_GRAMMARS_BY_ANCHOR.get(anchor, (default_grammar,))
    if requested_grammar in compatible_grammars:
        return requested_grammar, (), None

    warning = (
        f"Diagram grammar {requested_grammar.value} is incompatible with "
        f"anchor {anchor.value}; repaired to {default_grammar.value}."
    )
    if strict_user_mode:
        raise ArticleConcretizationResolutionConflict("incompatible_anchor_grammar", warning)
    return default_grammar, (warning,), "incompatible_anchor_grammar"


def _resolve_layout(
    *,
    request: ArticleConcretizationRequest,
    template_aspect_ratio: DiagramAspectRatio,
) -> DiagramLayoutResolution:
    requested_ratio = request.diagram_aspect_ratio
    if requested_ratio in {DiagramAspectRatio.AUTO, DiagramAspectRatio.TEMPLATE}:
        return DiagramLayoutResolution(
            canvas_aspect_ratio=template_aspect_ratio,
            diagram_panel_aspect_ratio=template_aspect_ratio,
            panel_inside_canvas=False,
            layout_intent="match_canvas",
        )
    if requested_ratio is template_aspect_ratio:
        return DiagramLayoutResolution(
            canvas_aspect_ratio=template_aspect_ratio,
            diagram_panel_aspect_ratio=requested_ratio,
            panel_inside_canvas=False,
            layout_intent="match_canvas",
        )

    warning = (
        f"Diagram panel aspect ratio {requested_ratio.value} is placed inside "
        f"template canvas {template_aspect_ratio.value}."
    )
    return DiagramLayoutResolution(
        canvas_aspect_ratio=template_aspect_ratio,
        diagram_panel_aspect_ratio=requested_ratio,
        panel_inside_canvas=True,
        layout_intent="panel_inside_canvas",
        warnings=(warning,),
    )


def _resolve_visible_text(
    *,
    request: ArticleConcretizationRequest,
    frame_plan: FrameUnderstandingPlan,
    strict_user_mode: bool,
) -> tuple[VisibleTextResolution, str | None]:
    policies = (
        VisibleTextPolicy.FREE_TEXT_ALLOWED,
        frame_plan.visible_text_policy,
        request.diagram_visible_text_policy,
    )
    if VisibleTextPolicy.NO_VISIBLE_TEXT in policies:
        return _no_visible_text_resolution(), None

    constraints = tuple(policy for policy in policies if policy is not VisibleTextPolicy.FREE_TEXT_ALLOWED)
    if not constraints:
        return (
            VisibleTextResolution(
                effective_policy=VisibleTextPolicy.FREE_TEXT_ALLOWED,
                allowed_visible_text=(),
                text_origin="free",
            ),
            None,
        )

    approved_labels = request.diagram_approved_labels
    needs_approved_labels = VisibleTextPolicy.APPROVED_LABELS_ONLY in constraints
    if needs_approved_labels and not approved_labels:
        return _visible_text_conflict_or_downgrade(
            reason="approved_labels_required",
            message="approved labels are required for approved_labels_only visible text",
            strict_user_mode=strict_user_mode,
        )

    needs_source_text = VisibleTextPolicy.SOURCE_TEXT_ONLY in constraints
    if needs_source_text and needs_approved_labels:
        allowed = tuple(
            label
            for label in approved_labels
            if _source_allows_label(label, frame_plan=frame_plan)
        )
        if not allowed:
            return _visible_text_conflict_or_downgrade(
                reason="visible_text_intersection_empty",
                message="visible text intersection is empty for source_text_only and approved_labels_only",
                strict_user_mode=strict_user_mode,
            )
        return (
            VisibleTextResolution(
                effective_policy=VisibleTextPolicy.APPROVED_LABELS_ONLY,
                allowed_visible_text=allowed,
                text_origin="intersection",
            ),
            None,
        )

    if needs_approved_labels:
        return (
            VisibleTextResolution(
                effective_policy=VisibleTextPolicy.APPROVED_LABELS_ONLY,
                allowed_visible_text=approved_labels,
                text_origin="approved",
            ),
            None,
        )

    if needs_source_text:
        return (
            VisibleTextResolution(
                effective_policy=VisibleTextPolicy.SOURCE_TEXT_ONLY,
                allowed_visible_text=_source_terms(frame_plan=frame_plan),
                text_origin="source",
            ),
            None,
        )

    if VisibleTextPolicy.SYMBOLIC_LABELS_ONLY in constraints:
        return (
            VisibleTextResolution(
                effective_policy=VisibleTextPolicy.SYMBOLIC_LABELS_ONLY,
                allowed_visible_text=(),
                text_origin="symbolic_controlled",
            ),
            None,
        )

    return _no_visible_text_resolution(), None


def _visible_text_conflict_or_downgrade(
    *,
    reason: str,
    message: str,
    strict_user_mode: bool,
) -> tuple[VisibleTextResolution, str | None]:
    if strict_user_mode:
        raise ArticleConcretizationResolutionConflict(reason, message)
    warning = f"{message}; downgraded visible text to no_visible_text."
    return (
        VisibleTextResolution(
            effective_policy=VisibleTextPolicy.NO_VISIBLE_TEXT,
            allowed_visible_text=(),
            text_origin="none",
            warnings=(warning,),
        ),
        reason,
    )


def _no_visible_text_resolution() -> VisibleTextResolution:
    return VisibleTextResolution(
        effective_policy=VisibleTextPolicy.NO_VISIBLE_TEXT,
        allowed_visible_text=(),
        text_origin="none",
    )


def _resolve_signature_role(
    *,
    request: ArticleConcretizationRequest,
    anchor: CognitiveAnchorKind,
    grammar: ExplanationDiagramGrammar,
    series_visual_signature_profile_id: str | None,
    strict_user_mode: bool,
) -> tuple[SeriesVisualSignatureRole, tuple[str, ...], str | None]:
    requested_role = request.series_visual_signature_role
    if requested_role is SeriesVisualSignatureRole.NONE:
        return SeriesVisualSignatureRole.NONE, (), None
    if requested_role is SeriesVisualSignatureRole.AUTO:
        if not _has_series_visual_signature_profile_id(series_visual_signature_profile_id):
            return _signature_role_requires_ip_profile_resolution(
                requested_role=requested_role,
                strict_user_mode=strict_user_mode,
            )
        return _auto_signature_role(anchor=anchor, grammar=grammar), (), None
    if _has_series_visual_signature_profile_id(series_visual_signature_profile_id):
        return requested_role, (), None

    return _signature_role_requires_ip_profile_resolution(
        requested_role=requested_role,
        strict_user_mode=strict_user_mode,
    )


def _signature_role_requires_ip_profile_resolution(
    *,
    requested_role: SeriesVisualSignatureRole,
    strict_user_mode: bool,
) -> tuple[SeriesVisualSignatureRole, tuple[str, ...], str | None]:
    warning = (
        f"Series visual signature role {requested_role.value} requires series_visual_signature_profile_id; "
        "repaired to none."
    )
    if strict_user_mode:
        raise ArticleConcretizationResolutionConflict("signature_role_requires_ip_profile", warning)
    return SeriesVisualSignatureRole.NONE, (warning,), "signature_role_requires_ip_profile"


def _auto_signature_role(
    *,
    anchor: CognitiveAnchorKind,
    grammar: ExplanationDiagramGrammar,
) -> SeriesVisualSignatureRole:
    if grammar in {
        ExplanationDiagramGrammar.PROCESS_FLOW,
        ExplanationDiagramGrammar.DECISION_TREE,
        ExplanationDiagramGrammar.STATE_MACHINE,
    }:
        return SeriesVisualSignatureRole.OPERATOR
    return AUTO_SIGNATURE_ROLE_BY_ANCHOR.get(anchor, SeriesVisualSignatureRole.SILENT_WITNESS)


def _legacy_series_visual_signature_strategy_warnings(
    *,
    request: ArticleConcretizationRequest,
    series_visual_signature_strategy: Any,
) -> tuple[str, ...]:
    if request.series_visual_signature_role is not SeriesVisualSignatureRole.NONE:
        return ()
    strategy = _series_visual_signature_strategy_text(series_visual_signature_strategy)
    if not strategy or strategy in {"auto", "none"}:
        return ()
    return (
        "series_visual_signature_strategy is legacy when article_concretization is enabled "
        f"and series_visual_signature_role is none: {strategy}.",
    )


def _series_visual_signature_strategy_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        value = value.get("series_visual_signature_strategy") or value.get("strategy")
    if isinstance(value, Enum):
        value = value.value
    text = str(value or "").strip().lower()
    return text or None


def _source_allows_label(
    label: str,
    *,
    frame_plan: FrameUnderstandingPlan,
) -> bool:
    needle = label.casefold()
    if not needle:
        return False
    source_terms = {term.casefold() for term in _source_terms(frame_plan=frame_plan)}
    if needle in source_terms:
        return True
    return any(_quote_contains_label(text, label) for text in _source_texts(frame_plan=frame_plan))


def _source_terms(
    *,
    frame_plan: FrameUnderstandingPlan,
) -> tuple[str, ...]:
    terms: list[str] = []
    _extend_unique(terms, (subject.label for subject in frame_plan.required_subjects))
    return tuple(terms)


def _source_texts(
    *,
    frame_plan: FrameUnderstandingPlan,
) -> tuple[str, ...]:
    texts: list[str] = []
    _extend_unique(texts, (evidence.quote for evidence in frame_plan.source_evidence))
    return tuple(texts)


def _quote_contains_label(quote: str, label: str) -> bool:
    if _requires_token_boundary(label):
        return _contains_ascii_token_sequence(quote, label)
    return label.casefold() in quote.casefold()


def _requires_token_boundary(label: str) -> bool:
    return label.isascii() and bool(re.search(r"[A-Za-z0-9]", label))


def _contains_ascii_token_sequence(quote: str, label: str) -> bool:
    label_tokens = _ascii_tokens(label)
    if not label_tokens:
        return False
    quote_tokens = _ascii_tokens(quote)
    if len(label_tokens) > len(quote_tokens):
        return False
    window_size = len(label_tokens)
    return any(
        tuple(quote_tokens[index : index + window_size]) == tuple(label_tokens)
        for index in range(len(quote_tokens) - window_size + 1)
    )


def _ascii_tokens(text: str) -> list[str]:
    return [match.group(0).casefold() for match in re.finditer(r"[A-Za-z0-9]+", text)]


def _extend_unique(target: list[str], values: Sequence[Any]) -> None:
    seen = {value.casefold() for value in target}
    for value in values:
        text = str(value.value if isinstance(value, Enum) else value or "").strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        target.append(text)
        seen.add(key)


def _diagram_aspect_ratio(value: Any, field_name: str) -> DiagramAspectRatio:
    if isinstance(value, DiagramAspectRatio):
        return value
    text = str(value.value if isinstance(value, Enum) else value or "").strip()
    if not text:
        return DiagramAspectRatio.AUTO
    for ratio in DiagramAspectRatio:
        if text.lower() == ratio.value.lower() or text.lower() == ratio.name.lower():
            return ratio
    raise ValueError(f"{field_name} must be a valid DiagramAspectRatio")


def _has_series_visual_signature_profile_id(value: str | None) -> bool:
    return bool(str(value or "").strip())


__all__ = [
    "AUTO_SIGNATURE_ROLE_BY_ANCHOR",
    "COMPATIBLE_GRAMMARS_BY_ANCHOR",
    "DEFAULT_ANCHOR_BY_LENS",
    "DEFAULT_GRAMMAR_BY_ANCHOR",
    "ArticleConcretizationResolutionConflict",
    "resolve_article_concretization",
]
