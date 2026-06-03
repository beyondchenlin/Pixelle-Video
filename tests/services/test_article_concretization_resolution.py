import json

import pytest

from pixelle_video.models.article_concretization import (
    ArticleConcretizationRequest,
    CognitiveAnchorKind,
    DiagramAspectRatio,
    DiagramRenderStyle,
    ExplanationDiagramGrammar,
    SeriesVisualSignatureRole,
)
from pixelle_video.models.article_understanding import (
    ArticleUnderstandingLens,
    ArticleUnderstandingPlan,
    FrameUnderstandingPlan,
    SourceEvidenceSpan,
    SubjectAnchor,
)
from pixelle_video.models.visual_planning_mode import VisibleTextPolicy
from pixelle_video.services.article_concretization_resolution import (
    ArticleConcretizationResolutionConflict,
    resolve_article_concretization,
)


def _evidence(evidence_id: str, quote: str) -> SourceEvidenceSpan:
    return SourceEvidenceSpan(
        evidence_id=evidence_id,
        source_id="article-1",
        quote=quote,
        evidence_role="core_claim",
    )


def _subject(subject_id: str, label: str, evidence_id: str) -> SubjectAnchor:
    return SubjectAnchor(
        subject_id=subject_id,
        label=label,
        source_phrase=label,
        evidence_span_ids=(evidence_id,),
        importance="primary",
        visual_presence="required",
        loss_policy="forbidden",
    )


def _article_plan(
    *,
    primary_lens: ArticleUnderstandingLens | str = ArticleUnderstandingLens.THESIS_ARGUMENT,
    main_entities: tuple[str, ...] = ("Cause", "Effect"),
    quote: str = "Cause leads to Effect over time.",
) -> ArticleUnderstandingPlan:
    evidence = _evidence("article-evidence-1", quote)
    return ArticleUnderstandingPlan(
        article_id="article-1",
        primary_lens=primary_lens,
        main_entities=main_entities,
        required_subjects=(
            _subject("article-subject-1", "Cause", "article-evidence-1"),
            _subject("article-subject-2", "Effect", "article-evidence-1"),
        ),
        source_evidence=(evidence,),
    )


def _frame_plan(
    *,
    primary_lens: ArticleUnderstandingLens | str = ArticleUnderstandingLens.THESIS_ARGUMENT,
    visible_text_policy: VisibleTextPolicy | str = VisibleTextPolicy.NO_VISIBLE_TEXT,
    source_text: str = "Cause rises while Effect is delayed.",
    quote: str = "Cause produces Effect.",
) -> FrameUnderstandingPlan:
    evidence = _evidence("frame-evidence-1", quote)
    return FrameUnderstandingPlan(
        frame_id="frame-1",
        source_text=source_text,
        frame_claim="Cause changes Effect.",
        frame_question="How does the cause change the effect?",
        primary_lens=primary_lens,
        required_subjects=(
            _subject("frame-subject-1", "Cause", "frame-evidence-1"),
            _subject("frame-subject-2", "Effect", "frame-evidence-1"),
        ),
        source_evidence=(evidence,),
        visible_text_policy=visible_text_policy,
    )


def _resolve(
    request: ArticleConcretizationRequest,
    *,
    article_plan: ArticleUnderstandingPlan | None = None,
    frame_plan: FrameUnderstandingPlan | None = None,
    series_visual_signature_profile_id: str | None = "ip-1",
    template_aspect_ratio: DiagramAspectRatio = DiagramAspectRatio.VERTICAL_9_16,
    strict_user_mode: bool = True,
    series_visual_signature_strategy=None,
):
    return resolve_article_concretization(
        request=request,
        article_plan=article_plan or _article_plan(),
        frame_plan=frame_plan or _frame_plan(),
        series_visual_signature_profile_id=series_visual_signature_profile_id,
        template_aspect_ratio=template_aspect_ratio,
        strict_user_mode=strict_user_mode,
        series_visual_signature_strategy=series_visual_signature_strategy,
    )


def test_disabled_request_returns_noop_resolution():
    request = ArticleConcretizationRequest.from_mapping({})

    resolution = _resolve(
        request,
        series_visual_signature_profile_id=None,
        series_visual_signature_strategy="signature_presence",
    )

    assert resolution.enabled is False
    assert resolution.effective_anchor_kind is CognitiveAnchorKind.AUTO
    assert resolution.effective_diagram_grammar is ExplanationDiagramGrammar.AUTO
    assert resolution.effective_signature_role is SeriesVisualSignatureRole.NONE
    assert resolution.effective_render_style is DiagramRenderStyle.AUTO
    assert resolution.layout.to_dict() == {
        "canvas_aspect_ratio": "vertical_9_16",
        "diagram_panel_aspect_ratio": "vertical_9_16",
        "panel_inside_canvas": False,
        "layout_intent": "template_default",
        "warnings": [],
    }
    assert resolution.visible_text.to_dict() == {
        "effective_policy": "no_visible_text",
        "allowed_visible_text": [],
        "text_origin": "none",
        "warnings": [],
    }
    assert resolution.approved_labels == ()
    assert resolution.warnings == ()
    assert resolution.errors == ()
    assert resolution.fallback_used is False
    assert resolution.fallback_reason is None
    json.dumps(resolution.to_dict(), allow_nan=False)


def test_explicit_anchor_with_auto_grammar_uses_anchor_default():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "cognitive_anchor_kind": "structure",
            "explanation_diagram_grammar": "auto",
        }
    )

    resolution = _resolve(request)

    assert resolution.effective_anchor_kind is CognitiveAnchorKind.STRUCTURE
    assert resolution.effective_diagram_grammar is ExplanationDiagramGrammar.STRUCTURE_MAP
    assert resolution.warnings == ()


def test_compatible_anchor_grammar_matrix_allows_structure_relationship_map_in_strict_mode():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "cognitive_anchor_kind": "structure",
            "explanation_diagram_grammar": "relationship_map",
        }
    )

    resolution = _resolve(request, strict_user_mode=True)

    assert resolution.effective_anchor_kind is CognitiveAnchorKind.STRUCTURE
    assert resolution.effective_diagram_grammar is ExplanationDiagramGrammar.RELATIONSHIP_MAP
    assert resolution.fallback_used is False
    assert resolution.fallback_reason is None
    assert resolution.warnings == ()


def test_non_strict_incompatible_anchor_grammar_warns_and_repairs():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "cognitive_anchor_kind": "structure",
            "explanation_diagram_grammar": "process_flow",
        }
    )

    resolution = _resolve(request, strict_user_mode=False)

    assert resolution.effective_diagram_grammar is ExplanationDiagramGrammar.STRUCTURE_MAP
    assert resolution.fallback_used is True
    assert resolution.fallback_reason == "incompatible_anchor_grammar"
    assert any("process_flow" in warning for warning in resolution.warnings)


def test_strict_incompatible_anchor_grammar_raises():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "cognitive_anchor_kind": "structure",
            "explanation_diagram_grammar": "process_flow",
        }
    )

    with pytest.raises(ArticleConcretizationResolutionConflict, match="process_flow"):
        _resolve(request, strict_user_mode=True)


def test_incompatible_anchor_grammar_still_raises_and_repairs_after_matrix_expansion():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "cognitive_anchor_kind": "relationship",
            "explanation_diagram_grammar": "contrast_board",
        }
    )

    with pytest.raises(ArticleConcretizationResolutionConflict, match="contrast_board"):
        _resolve(request, strict_user_mode=True)

    resolution = _resolve(request, strict_user_mode=False)

    assert resolution.effective_anchor_kind is CognitiveAnchorKind.RELATIONSHIP
    assert resolution.effective_diagram_grammar is ExplanationDiagramGrammar.RELATIONSHIP_MAP
    assert resolution.fallback_used is True
    assert resolution.fallback_reason == "incompatible_anchor_grammar"


def test_causal_mechanism_anchor_defaults_to_process_flow():
    request = ArticleConcretizationRequest.from_mapping({"enabled": True})

    resolution = _resolve(
        request,
        frame_plan=_frame_plan(primary_lens=ArticleUnderstandingLens.CAUSAL_MECHANISM),
    )

    assert resolution.effective_anchor_kind is CognitiveAnchorKind.CAUSAL_MECHANISM
    assert resolution.effective_diagram_grammar is ExplanationDiagramGrammar.PROCESS_FLOW


def test_state_anchor_defaults_to_metaphor_scene():
    request = ArticleConcretizationRequest.from_mapping({"enabled": True})

    resolution = _resolve(
        request,
        frame_plan=_frame_plan(primary_lens=ArticleUnderstandingLens.COGNITIVE_STATE),
    )

    assert resolution.effective_anchor_kind is CognitiveAnchorKind.STATE
    assert resolution.effective_diagram_grammar is ExplanationDiagramGrammar.METAPHOR_SCENE


def test_approved_labels_only_requires_labels():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "diagram_visible_text_policy": "approved_labels_only",
        }
    )

    with pytest.raises(ArticleConcretizationResolutionConflict, match="approved labels"):
        _resolve(request, frame_plan=_frame_plan(visible_text_policy=VisibleTextPolicy.FREE_TEXT_ALLOWED))


def test_visible_text_intersection_source_and_approved():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "diagram_visible_text_policy": "approved_labels_only",
            "diagram_approved_labels": ["Cause", "Outside", "Effect"],
        }
    )

    resolution = _resolve(
        request,
        frame_plan=_frame_plan(visible_text_policy=VisibleTextPolicy.SOURCE_TEXT_ONLY),
    )

    assert resolution.visible_text.effective_policy is VisibleTextPolicy.APPROVED_LABELS_ONLY
    assert resolution.visible_text.allowed_visible_text == ("Cause", "Effect")
    assert resolution.visible_text.text_origin == "intersection"
    assert resolution.approved_labels == ("Cause", "Outside", "Effect")


def test_visible_text_intersection_uses_token_boundary_for_ascii_labels():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "diagram_visible_text_policy": "approved_labels_only",
            "diagram_approved_labels": ["AI"],
        }
    )

    resolution = _resolve(
        request,
        frame_plan=_frame_plan(
            visible_text_policy=VisibleTextPolicy.SOURCE_TEXT_ONLY,
            quote="A chair remains beside the table.",
        ),
        strict_user_mode=False,
    )

    assert resolution.visible_text.effective_policy is VisibleTextPolicy.NO_VISIBLE_TEXT
    assert resolution.visible_text.allowed_visible_text == ()
    assert resolution.fallback_used is True
    assert resolution.fallback_reason == "visible_text_intersection_empty"
    assert any("visible text" in warning for warning in resolution.warnings)


def test_empty_visible_text_intersection_non_strict_downgrades_to_no_visible_text():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "diagram_visible_text_policy": "approved_labels_only",
            "diagram_approved_labels": ["Outside"],
        }
    )

    resolution = _resolve(
        request,
        frame_plan=_frame_plan(
            visible_text_policy=VisibleTextPolicy.SOURCE_TEXT_ONLY,
            source_text="Only internal source terms.",
            quote="Internal terms only.",
        ),
        strict_user_mode=False,
    )

    assert resolution.visible_text.effective_policy is VisibleTextPolicy.NO_VISIBLE_TEXT
    assert resolution.visible_text.allowed_visible_text == ()
    assert resolution.visible_text.text_origin == "none"
    assert resolution.fallback_used is True
    assert resolution.fallback_reason == "visible_text_intersection_empty"
    assert any("visible text" in warning for warning in resolution.warnings)


def test_empty_visible_text_intersection_strict_raises():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "diagram_visible_text_policy": "approved_labels_only",
            "diagram_approved_labels": ["Outside"],
        }
    )

    with pytest.raises(ArticleConcretizationResolutionConflict, match="visible text"):
        _resolve(
            request,
            frame_plan=_frame_plan(
                visible_text_policy=VisibleTextPolicy.SOURCE_TEXT_ONLY,
                source_text="Only internal source terms.",
                quote="Internal terms only.",
            ),
            strict_user_mode=True,
        )


def test_visible_text_intersection_does_not_allow_article_only_source_terms():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "diagram_visible_text_policy": "approved_labels_only",
            "diagram_approved_labels": ["Cause", "ArticleOnly"],
        }
    )

    resolution = _resolve(
        request,
        article_plan=_article_plan(
            main_entities=("Cause", "ArticleOnly"),
            quote="ArticleOnly appears only in article evidence.",
        ),
        frame_plan=_frame_plan(
            visible_text_policy=VisibleTextPolicy.SOURCE_TEXT_ONLY,
            quote="Cause appears in frame evidence.",
        ),
        strict_user_mode=True,
    )

    assert resolution.visible_text.allowed_visible_text == ("Cause",)


def test_article_only_visible_text_intersection_non_strict_downgrades_to_no_visible_text():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "diagram_visible_text_policy": "approved_labels_only",
            "diagram_approved_labels": ["ArticleOnly"],
        }
    )

    resolution = _resolve(
        request,
        article_plan=_article_plan(
            main_entities=("ArticleOnly",),
            quote="ArticleOnly appears only in article evidence.",
        ),
        frame_plan=_frame_plan(
            visible_text_policy=VisibleTextPolicy.SOURCE_TEXT_ONLY,
            source_text="Source text mentions ArticleOnly but frame evidence does not.",
            quote="Frame evidence names supported terms only.",
        ),
        strict_user_mode=False,
    )

    assert resolution.visible_text.effective_policy is VisibleTextPolicy.NO_VISIBLE_TEXT
    assert resolution.visible_text.allowed_visible_text == ()
    assert resolution.fallback_used is True
    assert resolution.fallback_reason == "visible_text_intersection_empty"
    assert any("visible text" in warning for warning in resolution.warnings)


def test_article_only_visible_text_intersection_strict_raises():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "diagram_visible_text_policy": "approved_labels_only",
            "diagram_approved_labels": ["ArticleOnly"],
        }
    )

    with pytest.raises(ArticleConcretizationResolutionConflict, match="visible text"):
        _resolve(
            request,
            article_plan=_article_plan(
                main_entities=("ArticleOnly",),
                quote="ArticleOnly appears only in article evidence.",
            ),
            frame_plan=_frame_plan(
                visible_text_policy=VisibleTextPolicy.SOURCE_TEXT_ONLY,
                source_text="Source text mentions ArticleOnly but frame evidence does not.",
                quote="Frame evidence names supported terms only.",
            ),
            strict_user_mode=True,
        )


def test_landscape_panel_inside_vertical_canvas_is_allowed_in_strict_mode():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "diagram_aspect_ratio": "landscape_16_9",
        }
    )

    resolution = _resolve(
        request,
        template_aspect_ratio=DiagramAspectRatio.VERTICAL_9_16,
        strict_user_mode=True,
    )

    assert resolution.layout.canvas_aspect_ratio is DiagramAspectRatio.VERTICAL_9_16
    assert resolution.layout.diagram_panel_aspect_ratio is DiagramAspectRatio.LANDSCAPE_16_9
    assert resolution.layout.panel_inside_canvas is True
    assert resolution.layout.layout_intent == "panel_inside_canvas"
    assert any("panel" in warning for warning in resolution.warnings)


def test_canvas_override_conflict_raises_only_when_canvas_override_is_explicit():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "diagram_aspect_ratio": "landscape_16_9",
        }
    )

    resolution = _resolve(
        request,
        template_aspect_ratio=DiagramAspectRatio.PORTRAIT_4_5,
        strict_user_mode=True,
    )

    assert resolution.layout.canvas_aspect_ratio is DiagramAspectRatio.PORTRAIT_4_5
    assert resolution.layout.diagram_panel_aspect_ratio is DiagramAspectRatio.LANDSCAPE_16_9
    assert resolution.layout.panel_inside_canvas is True


def test_signature_role_requires_ip_profile_in_strict_mode():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "series_visual_signature_role": "operator",
        }
    )

    with pytest.raises(ArticleConcretizationResolutionConflict, match="series_visual_signature_profile_id"):
        _resolve(request, series_visual_signature_profile_id=None, strict_user_mode=True)


def test_signature_role_without_ip_non_strict_drops_to_none_with_warning():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "series_visual_signature_role": "operator",
        }
    )

    resolution = _resolve(request, series_visual_signature_profile_id=None, strict_user_mode=False)

    assert resolution.effective_signature_role is SeriesVisualSignatureRole.NONE
    assert resolution.fallback_used is True
    assert resolution.fallback_reason == "signature_role_requires_ip_profile"
    assert any("series_visual_signature_profile_id" in warning for warning in resolution.warnings)


def test_auto_signature_role_requires_ip_profile_in_strict_mode():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "series_visual_signature_role": "auto",
        }
    )

    with pytest.raises(ArticleConcretizationResolutionConflict, match="series_visual_signature_profile_id"):
        _resolve(request, series_visual_signature_profile_id=None, strict_user_mode=True)


def test_auto_signature_role_without_ip_non_strict_drops_to_none_with_warning():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "series_visual_signature_role": "auto",
        }
    )

    resolution = _resolve(request, series_visual_signature_profile_id=None, strict_user_mode=False)

    assert resolution.effective_signature_role is SeriesVisualSignatureRole.NONE
    assert resolution.fallback_used is True
    assert resolution.fallback_reason == "signature_role_requires_ip_profile"
    assert any("series_visual_signature_profile_id" in warning for warning in resolution.warnings)


def test_old_series_visual_signature_strategy_conflict_records_warning():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "series_visual_signature_role": "none",
        }
    )

    resolution = _resolve(
        request,
        series_visual_signature_profile_id=None,
        strict_user_mode=True,
        series_visual_signature_strategy="signature_presence",
    )

    assert resolution.effective_signature_role is SeriesVisualSignatureRole.NONE
    assert any("series_visual_signature_strategy" in warning for warning in resolution.warnings)
