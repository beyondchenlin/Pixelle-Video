import json

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
    SourceEvidenceSpan,
    SubjectAnchor,
)
from pixelle_video.models.visual_planning_mode import (
    PrimaryVisualTask,
    VisibleTextPolicy,
)
from pixelle_video.services.article_concretization_planner import (
    ArticleConcretizationPlanner,
)


def _evidence(evidence_id: str, quote: str, *, role: str = "core_claim") -> SourceEvidenceSpan:
    return SourceEvidenceSpan(
        evidence_id=evidence_id,
        source_id="article-1",
        quote=quote,
        evidence_role=role,
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
    core_claim: str = "Policy feedback loops compound over time.",
    main_entities: tuple[str, ...] = ("Policy", "Market signal"),
    required_subjects: tuple[SubjectAnchor, ...] | None = None,
    source_evidence: tuple[SourceEvidenceSpan, ...] | None = None,
) -> ArticleUnderstandingPlan:
    evidence = source_evidence or (
        _evidence("article-evidence-1", "Policy feedback loops compound over time."),
    )
    subjects = required_subjects
    if subjects is None:
        subjects = (
            _subject("article-subject-1", "Policy", evidence[0].evidence_id),
            _subject("article-subject-2", "Market signal", evidence[0].evidence_id),
        )
    return ArticleUnderstandingPlan(
        article_id="article-1",
        primary_lens=ArticleUnderstandingLens.CAUSAL_MECHANISM,
        core_claim=core_claim,
        main_entities=main_entities,
        required_subjects=subjects,
        source_evidence=evidence,
    )


def _frame_plan(
    *,
    frame_claim: str = "Policy changes market incentives.",
    frame_question: str = "How does policy change incentives?",
    required_subjects: tuple[SubjectAnchor, ...] | None = None,
    source_evidence: tuple[SourceEvidenceSpan, ...] | None = None,
) -> FrameUnderstandingPlan:
    evidence = source_evidence or (
        _evidence("frame-evidence-1", "Policy changes market incentives."),
        _evidence("frame-evidence-2", "Market incentives reshape behavior."),
    )
    subjects = required_subjects
    if subjects is None:
        subjects = (
            _subject("frame-subject-1", "Policy", evidence[0].evidence_id),
            _subject("frame-subject-2", "Market incentives", evidence[1].evidence_id),
        )
    return FrameUnderstandingPlan(
        frame_id="frame-1",
        source_text="Policy changes market incentives and reshapes behavior.",
        frame_claim=frame_claim,
        frame_question=frame_question,
        primary_lens=ArticleUnderstandingLens.CAUSAL_MECHANISM,
        required_subjects=subjects,
        source_evidence=evidence,
        visible_text_policy=VisibleTextPolicy.SOURCE_TEXT_ONLY,
    )


def _layout(
    *,
    canvas_aspect_ratio: DiagramAspectRatio = DiagramAspectRatio.VERTICAL_9_16,
    diagram_panel_aspect_ratio: DiagramAspectRatio = DiagramAspectRatio.LANDSCAPE_16_9,
    panel_inside_canvas: bool = True,
    layout_intent: str = "panel_inside_canvas",
) -> DiagramLayoutResolution:
    return DiagramLayoutResolution(
        canvas_aspect_ratio=canvas_aspect_ratio,
        diagram_panel_aspect_ratio=diagram_panel_aspect_ratio,
        panel_inside_canvas=panel_inside_canvas,
        layout_intent=layout_intent,
    )


def _visible_text(
    *,
    effective_policy: VisibleTextPolicy = VisibleTextPolicy.NO_VISIBLE_TEXT,
    allowed_visible_text: tuple[str, ...] = (),
    text_origin: str = "none",
) -> VisibleTextResolution:
    return VisibleTextResolution(
        effective_policy=effective_policy,
        allowed_visible_text=allowed_visible_text,
        text_origin=text_origin,
    )


def _request(**overrides) -> ArticleConcretizationRequest:
    payload = {
        "enabled": True,
        "cognitive_anchor_kind": "causal_mechanism",
        "explanation_diagram_grammar": "process_flow",
        "series_visual_signature_role": "none",
        "diagram_render_style": "editorial_diagram",
        "diagram_aspect_ratio": "landscape_16_9",
        "diagram_visible_text_policy": "no_visible_text",
    }
    payload.update(overrides)
    return ArticleConcretizationRequest.from_mapping(payload)


def _resolution(
    *,
    request: ArticleConcretizationRequest | None = None,
    enabled: bool = True,
    effective_anchor_kind: CognitiveAnchorKind = CognitiveAnchorKind.CAUSAL_MECHANISM,
    effective_diagram_grammar: ExplanationDiagramGrammar = ExplanationDiagramGrammar.PROCESS_FLOW,
    effective_signature_role: SeriesVisualSignatureRole = SeriesVisualSignatureRole.NONE,
    effective_render_style: DiagramRenderStyle = DiagramRenderStyle.EDITORIAL_DIAGRAM,
    layout: DiagramLayoutResolution | None = None,
    visible_text: VisibleTextResolution | None = None,
) -> ArticleConcretizationResolution:
    return ArticleConcretizationResolution(
        request=request or _request(),
        enabled=enabled,
        effective_anchor_kind=effective_anchor_kind,
        effective_diagram_grammar=effective_diagram_grammar,
        effective_signature_role=effective_signature_role,
        effective_render_style=effective_render_style,
        layout=layout or _layout(),
        visible_text=visible_text or _visible_text(),
        approved_labels=(),
        warnings=(),
        errors=(),
        fallback_used=False,
    )


def test_planner_consumes_resolution_not_raw_request():
    raw_request = _request(
        cognitive_anchor_kind="contrast",
        explanation_diagram_grammar="contrast_board",
        series_visual_signature_role="none",
        diagram_render_style="brand_kv",
        diagram_aspect_ratio="square_1_1",
        diagram_visible_text_policy="free_text_allowed",
    )
    resolution = _resolution(
        request=raw_request,
        effective_anchor_kind=CognitiveAnchorKind.CAUSAL_MECHANISM,
        effective_diagram_grammar=ExplanationDiagramGrammar.PROCESS_FLOW,
        effective_signature_role=SeriesVisualSignatureRole.GUIDE,
        effective_render_style=DiagramRenderStyle.CLEAN_VECTOR,
        layout=_layout(
            canvas_aspect_ratio=DiagramAspectRatio.VERTICAL_9_16,
            diagram_panel_aspect_ratio=DiagramAspectRatio.LANDSCAPE_16_9,
            panel_inside_canvas=True,
        ),
        visible_text=_visible_text(
            effective_policy=VisibleTextPolicy.NO_VISIBLE_TEXT,
            allowed_visible_text=(),
            text_origin="none",
        ),
    )

    plan = ArticleConcretizationPlanner().plan(
        resolution=resolution,
        article_plan=_article_plan(),
        frame_plan=_frame_plan(),
        source_text="Source text fallback should not alter resolved fields.",
    )

    assert plan is not None
    assert plan.anchor.anchor_kind is CognitiveAnchorKind.CAUSAL_MECHANISM
    assert plan.diagram.grammar is ExplanationDiagramGrammar.PROCESS_FLOW
    assert plan.diagram.visible_text.effective_policy is VisibleTextPolicy.NO_VISIBLE_TEXT
    assert plan.series_signature.role is SeriesVisualSignatureRole.GUIDE
    assert plan.render.render_style is DiagramRenderStyle.CLEAN_VECTOR
    assert plan.render.canvas_aspect_ratio is DiagramAspectRatio.VERTICAL_9_16
    assert plan.render.diagram_panel_aspect_ratio is DiagramAspectRatio.LANDSCAPE_16_9
    json.dumps(plan.to_dict(), allow_nan=False)


def test_planner_maps_causal_mechanism_to_mechanism_diagram():
    plan = ArticleConcretizationPlanner().plan(
        resolution=_resolution(
            effective_anchor_kind=CognitiveAnchorKind.CAUSAL_MECHANISM,
            effective_diagram_grammar=ExplanationDiagramGrammar.PROCESS_FLOW,
        ),
        article_plan=_article_plan(core_claim="Policy incentives create market feedback."),
        frame_plan=_frame_plan(
            frame_claim="Policy incentives create market feedback.",
            frame_question="How do incentives create feedback?",
        ),
        source_text="Policy incentives create market feedback.",
    )

    assert plan is not None
    assert plan.anchor.anchor_kind is CognitiveAnchorKind.CAUSAL_MECHANISM
    assert plan.anchor.anchor_claim == "Policy incentives create market feedback."
    assert plan.anchor.anchor_question == "How do incentives create feedback?"
    assert plan.diagram.grammar is ExplanationDiagramGrammar.PROCESS_FLOW
    assert plan.diagram.primary_visual_task is PrimaryVisualTask.PROCESS_WALKTHROUGH
    assert "mechanism" in plan.diagram.diagram_title.casefold()
    assert "cause" in plan.diagram.visual_metaphor.casefold()


def test_planner_uses_required_subjects_before_claim_split():
    frame_evidence = (_evidence("frame-evidence-claim", "Named actors are abstract."),)
    frame_subjects = (
        _subject("frame-subject-1", "Observed driver", "frame-evidence-claim"),
        _subject("frame-subject-2", "Measured outcome", "frame-evidence-claim"),
    )

    plan = ArticleConcretizationPlanner().plan(
        resolution=_resolution(),
        article_plan=_article_plan(main_entities=("Article fallback",)),
        frame_plan=_frame_plan(
            frame_claim="Alpha, Beta and Gamma drive Delta in the system.",
            required_subjects=frame_subjects,
            source_evidence=frame_evidence,
        ),
        source_text="Alpha, Beta and Gamma drive Delta in the system.",
    )

    assert plan is not None
    assert plan.anchor.required_subjects == ("Observed driver", "Measured outcome")
    assert plan.anchor.main_entities == ("Observed driver", "Measured outcome")
    assert "Alpha" not in plan.anchor.main_entities
    assert "Delta" not in plan.anchor.required_subjects


def test_planner_keeps_source_evidence_ids():
    frame_evidence = (
        _evidence("frame-evidence-a", "Policy changes market incentives."),
        _evidence("frame-evidence-b", "Market incentives reshape behavior."),
    )

    plan = ArticleConcretizationPlanner().plan(
        resolution=_resolution(),
        article_plan=_article_plan(
            source_evidence=(
                _evidence("article-evidence-a", "The article-level evidence is lower priority."),
            )
        ),
        frame_plan=_frame_plan(source_evidence=frame_evidence),
        source_text="Policy changes market incentives and reshapes behavior.",
    )

    assert plan is not None
    assert plan.anchor.source_evidence_ids == ("frame-evidence-a", "frame-evidence-b")
    assert plan.anchor.source_text_excerpt == "Policy changes market incentives."


def test_planner_builds_signature_contract_from_resolved_role():
    plan = ArticleConcretizationPlanner().plan(
        resolution=_resolution(effective_signature_role=SeriesVisualSignatureRole.GUIDE),
        article_plan=_article_plan(),
        frame_plan=_frame_plan(),
        source_text="Policy changes market incentives.",
    )

    assert plan is not None
    assert plan.series_signature.enabled is True
    assert plan.series_signature.role is SeriesVisualSignatureRole.GUIDE
    assert plan.series_signature.identity_profile_id is None
    assert plan.series_signature.replacement_policy == "no_subject_replacement"
    assert plan.series_signature.visual_weight == 0.35
    assert "role only" in plan.series_signature.participation_rule.casefold()
    assert any(
        "replace article subjects" in behavior
        for behavior in plan.series_signature.forbidden_behaviors
    )


def test_planner_builds_render_contract_from_layout_resolution():
    plan = ArticleConcretizationPlanner().plan(
        resolution=_resolution(
            effective_render_style=DiagramRenderStyle.XIAOHEI_HANDDRAWN,
            layout=_layout(
                canvas_aspect_ratio=DiagramAspectRatio.VERTICAL_9_16,
                diagram_panel_aspect_ratio=DiagramAspectRatio.LANDSCAPE_16_9,
                panel_inside_canvas=True,
            ),
        ),
        article_plan=_article_plan(),
        frame_plan=_frame_plan(),
        source_text="Policy changes market incentives.",
    )

    assert plan is not None
    assert plan.render.render_style is DiagramRenderStyle.XIAOHEI_HANDDRAWN
    assert plan.render.canvas_aspect_ratio is DiagramAspectRatio.VERTICAL_9_16
    assert plan.render.diagram_panel_aspect_ratio is DiagramAspectRatio.LANDSCAPE_16_9
    assert plan.render.panel_inside_canvas is True
    render_rules = " ".join(plan.render.style_rules).casefold()
    assert "signature" not in render_rules
    assert "character" not in render_rules
    assert "mascot" not in render_rules
    assert "recurring" not in render_rules
    assert any("surface style only" in rule.casefold() for rule in plan.render.negative_style_rules)


def test_planner_disabled_resolution_returns_none_or_noop_without_prompt_parts():
    plan = ArticleConcretizationPlanner().plan(
        resolution=_resolution(
            request=_request(enabled=False),
            enabled=False,
            effective_anchor_kind=CognitiveAnchorKind.AUTO,
            effective_diagram_grammar=ExplanationDiagramGrammar.AUTO,
            effective_signature_role=SeriesVisualSignatureRole.NONE,
            effective_render_style=DiagramRenderStyle.AUTO,
            layout=_layout(
                canvas_aspect_ratio=DiagramAspectRatio.VERTICAL_9_16,
                diagram_panel_aspect_ratio=DiagramAspectRatio.VERTICAL_9_16,
                panel_inside_canvas=False,
                layout_intent="template_default",
            ),
            visible_text=_visible_text(),
        ),
        article_plan=_article_plan(),
        frame_plan=_frame_plan(),
        source_text="Disabled article concretization should not build prompt parts.",
    )

    assert plan is None
