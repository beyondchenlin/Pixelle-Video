import json

import pytest

import pixelle_video.models.article_concretization as ac
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
from pixelle_video.models.visual_planning_mode import PrimaryVisualTask, VisibleTextPolicy


def _request() -> ArticleConcretizationRequest:
    return ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "cognitive_anchor_kind": "causal_mechanism",
            "explanation_diagram_grammar": "process_flow",
            "series_visual_signature_role": "guide",
            "diagram_render_style": "editorial_diagram",
            "diagram_aspect_ratio": "landscape_16_9",
            "diagram_visible_text_policy": "approved_labels_only",
            "diagram_approved_labels": ["Cause", "Effect"],
        }
    )


def _visible_text() -> VisibleTextResolution:
    return VisibleTextResolution(
        effective_policy=VisibleTextPolicy.APPROVED_LABELS_ONLY,
        allowed_visible_text=["Cause", "Effect"],
        text_origin="approved",
        warnings=["trimmed to approved labels"],
    )


def _layout() -> DiagramLayoutResolution:
    return DiagramLayoutResolution(
        canvas_aspect_ratio=DiagramAspectRatio.LANDSCAPE_16_9,
        diagram_panel_aspect_ratio=DiagramAspectRatio.SQUARE_1_1,
        panel_inside_canvas=True,
        layout_intent="panel_inside_canvas",
        warnings=["panel inset for title safe area"],
    )


def _resolution(
    request: ArticleConcretizationRequest | None = None,
) -> ArticleConcretizationResolution:
    request = request or _request()
    return ArticleConcretizationResolution(
        request=request,
        enabled=True,
        effective_anchor_kind=CognitiveAnchorKind.CAUSAL_MECHANISM,
        effective_diagram_grammar=ExplanationDiagramGrammar.PROCESS_FLOW,
        effective_signature_role=SeriesVisualSignatureRole.GUIDE,
        effective_render_style=DiagramRenderStyle.EDITORIAL_DIAGRAM,
        layout=_layout(),
        visible_text=_visible_text(),
        approved_labels=["Cause", "Effect"],
        warnings=["resolved from explicit request"],
        errors=[],
        fallback_used=False,
    )


def _anchor() -> "ac.CognitiveAnchorPlan":
    return ac.CognitiveAnchorPlan(
        anchor_id=" anchor-1 ",
        anchor_kind=CognitiveAnchorKind.CAUSAL_MECHANISM,
        anchor_claim=" Policy feedback loops compound over time. ",
        anchor_question=" Why does the feedback loop accelerate? ",
        source_evidence_ids=["ev-1", "ev-2"],
        main_entities=["Policy", "Market", "Policy"],
        required_subjects=["regulator", "market signal"],
        source_text_excerpt=" The policy change triggered a market feedback loop. ",
        confidence=0.82,
    )


def _diagram() -> "ac.ExplanationDiagramBrief":
    return ac.ExplanationDiagramBrief(
        brief_id=" diagram-1 ",
        grammar=ExplanationDiagramGrammar.PROCESS_FLOW,
        primary_visual_task=PrimaryVisualTask.COGNITIVE_EXPLANATION,
        diagram_title=" Feedback Loop ",
        visual_metaphor="A regulator dial changes a market pressure gauge.",
        composition_rules=["left-to-right cause chain", "show feedback arrow"],
        panel_plan=["Panel 1: policy dial", "Panel 2: market pressure"],
        forbidden_losses=["do not omit the regulator", "do not flatten causality"],
        visible_text=_visible_text(),
    )


def _signature(
    *,
    enabled: bool = True,
    role: SeriesVisualSignatureRole = SeriesVisualSignatureRole.GUIDE,
    visual_weight: float = 0.35,
) -> "ac.SeriesVisualSignatureContract":
    return ac.SeriesVisualSignatureContract(
        enabled=enabled,
        role=role,
        identity_profile_id=" signature-profile-7 ",
        participation_rule="Guide appears only as an explanatory marker.",
        replacement_policy="no_subject_replacement",
        visual_weight=visual_weight,
        forbidden_behaviors=["replace article subjects", "dominate the panel"],
    )


def _render() -> "ac.DiagramRenderContract":
    return ac.DiagramRenderContract(
        render_style=DiagramRenderStyle.EDITORIAL_DIAGRAM,
        canvas_aspect_ratio=DiagramAspectRatio.LANDSCAPE_16_9,
        diagram_panel_aspect_ratio=DiagramAspectRatio.SQUARE_1_1,
        panel_inside_canvas=True,
        style_rules=["clean editorial linework", "muted accent color for arrows"],
        negative_style_rules=["no photorealistic background", "no decorative text"],
    )


def test_request_accepts_flat_payload():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "article_concretization_enabled": True,
            "cognitive_anchor_kind": "causal_mechanism",
            "explanation_diagram_grammar": "process_flow",
            "series_visual_signature_role": "guide",
            "diagram_render_style": "editorial_diagram",
            "diagram_aspect_ratio": "landscape_16_9",
            "diagram_visible_text_policy": "approved_labels_only",
            "diagram_approved_labels": [" Cause ", "Effect", "Cause", ""],
            "diagram_user_intent_hint": "  explain the policy feedback loop  ",
        }
    )

    assert request.enabled is True
    assert request.cognitive_anchor_kind is CognitiveAnchorKind.CAUSAL_MECHANISM
    assert request.explanation_diagram_grammar is ExplanationDiagramGrammar.PROCESS_FLOW
    assert request.series_visual_signature_role is SeriesVisualSignatureRole.GUIDE
    assert request.diagram_render_style is DiagramRenderStyle.EDITORIAL_DIAGRAM
    assert request.diagram_aspect_ratio is DiagramAspectRatio.LANDSCAPE_16_9
    assert request.diagram_visible_text_policy is VisibleTextPolicy.APPROVED_LABELS_ONLY
    assert request.diagram_approved_labels == ("Cause", "Effect")
    assert request.diagram_user_intent_hint == "explain the policy feedback loop"
    assert request.to_dict() == {
        "enabled": True,
        "cognitive_anchor_kind": "causal_mechanism",
        "explanation_diagram_grammar": "process_flow",
        "series_visual_signature_role": "guide",
        "diagram_render_style": "editorial_diagram",
        "diagram_aspect_ratio": "landscape_16_9",
        "diagram_visible_text_policy": "approved_labels_only",
        "diagram_approved_labels": ["Cause", "Effect"],
        "diagram_user_intent_hint": "explain the policy feedback loop",
    }
    json.dumps(request.to_dict(), allow_nan=False)


def test_request_accepts_nested_payload():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "article_concretization": {
                "enabled": True,
                "cognitive_anchor_kind": "structure",
                "explanation_diagram_grammar": "structure_map",
                "series_visual_signature_role": "container",
                "diagram_render_style": "clean_vector",
                "diagram_aspect_ratio": "square_1_1",
                "diagram_visible_text_policy": "symbolic_labels_only",
                "diagram_approved_labels": ("Node", "Edge"),
                "diagram_user_intent_hint": "show system parts",
            }
        }
    )

    assert request.enabled is True
    assert request.cognitive_anchor_kind is CognitiveAnchorKind.STRUCTURE
    assert request.explanation_diagram_grammar is ExplanationDiagramGrammar.STRUCTURE_MAP
    assert request.series_visual_signature_role is SeriesVisualSignatureRole.CONTAINER
    assert request.diagram_render_style is DiagramRenderStyle.CLEAN_VECTOR
    assert request.diagram_aspect_ratio is DiagramAspectRatio.SQUARE_1_1
    assert request.diagram_visible_text_policy is VisibleTextPolicy.SYMBOLIC_LABELS_ONLY
    assert request.diagram_approved_labels == ("Node", "Edge")
    assert request.diagram_user_intent_hint == "show system parts"


def test_nested_payload_overrides_flat_payload():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "article_concretization_enabled": False,
            "cognitive_anchor_kind": "process",
            "explanation_diagram_grammar": "process_flow",
            "series_visual_signature_role": "operator",
            "diagram_render_style": "brand_kv",
            "diagram_aspect_ratio": "vertical_9_16",
            "diagram_visible_text_policy": "no_visible_text",
            "diagram_approved_labels": "flat",
            "diagram_user_intent_hint": "flat hint",
            "article_concretization": {
                "enabled": True,
                "cognitive_anchor_kind": "relationship",
                "explanation_diagram_grammar": "relationship_map",
                "series_visual_signature_role": "silent_witness",
                "diagram_render_style": "ink_collage",
                "diagram_aspect_ratio": "portrait_4_5",
                "diagram_visible_text_policy": "source_text_only",
                "diagram_approved_labels": "nested, flat, nested",
                "diagram_user_intent_hint": "nested hint",
            },
        }
    )

    assert request.enabled is True
    assert request.cognitive_anchor_kind is CognitiveAnchorKind.RELATIONSHIP
    assert request.explanation_diagram_grammar is ExplanationDiagramGrammar.RELATIONSHIP_MAP
    assert request.series_visual_signature_role is SeriesVisualSignatureRole.SILENT_WITNESS
    assert request.diagram_render_style is DiagramRenderStyle.INK_COLLAGE
    assert request.diagram_aspect_ratio is DiagramAspectRatio.PORTRAIT_4_5
    assert request.diagram_visible_text_policy is VisibleTextPolicy.SOURCE_TEXT_ONLY
    assert request.diagram_approved_labels == ("nested", "flat")
    assert request.diagram_user_intent_hint == "nested hint"


def test_nested_enabled_alias_overrides_flat_enabled_alias():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "article_concretization": {
                "article_concretization_enabled": False,
            },
        }
    )

    assert request.enabled is False
    assert request.to_dict()["enabled"] is False


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("cognitive_anchor_kind", "not_an_anchor"),
        ("explanation_diagram_grammar", "not_a_grammar"),
        ("series_visual_signature_role", "not_a_role"),
        ("diagram_render_style", "not_a_style"),
        ("diagram_aspect_ratio", "not_a_ratio"),
        ("diagram_visible_text_policy", "not_a_policy"),
    ],
)
def test_request_rejects_unknown_enum_values(field_name, bad_value):
    with pytest.raises(ValueError, match=field_name):
        ArticleConcretizationRequest.from_mapping({field_name: bad_value})


def test_request_rejects_too_long_user_intent_hint():
    with pytest.raises(ValueError, match="diagram_user_intent_hint"):
        ArticleConcretizationRequest.from_mapping(
            {"diagram_user_intent_hint": "x" * 501}
        )


def test_request_parses_approved_labels_from_list_and_csv():
    from_list = ArticleConcretizationRequest.from_mapping(
        {"diagram_approved_labels": ["Alpha", " Beta ", "", "Alpha", None, 7]}
    )
    from_csv = ArticleConcretizationRequest.from_mapping(
        {"diagram_approved_labels": "Alpha, Beta,, Alpha ,7"}
    )

    assert from_list.diagram_approved_labels == ("Alpha", "Beta", "7")
    assert from_csv.diagram_approved_labels == ("Alpha", "Beta", "7")


def test_disabled_request_serializes_noop_defaults():
    request = ArticleConcretizationRequest.from_mapping({})

    assert request.enabled is False
    assert request.to_dict() == {
        "enabled": False,
        "cognitive_anchor_kind": "auto",
        "explanation_diagram_grammar": "auto",
        "series_visual_signature_role": "none",
        "diagram_render_style": "auto",
        "diagram_aspect_ratio": "auto",
        "diagram_visible_text_policy": "no_visible_text",
        "diagram_approved_labels": [],
        "diagram_user_intent_hint": None,
    }


def test_request_accepts_free_text_allowed_policy():
    request = ArticleConcretizationRequest.from_mapping(
        {
            "enabled": True,
            "diagram_visible_text_policy": "free_text_allowed",
        }
    )

    assert request.diagram_visible_text_policy is VisibleTextPolicy.FREE_TEXT_ALLOWED
    assert request.to_dict()["diagram_visible_text_policy"] == "free_text_allowed"


def test_full_plan_serializes_request_resolution_anchor_diagram_signature_render():
    request = _request()
    plan = ac.ArticleConcretizationPlan(
        plan_id=" plan-1 ",
        request=request,
        resolution=_resolution(request),
        anchor=_anchor(),
        diagram=_diagram(),
        series_signature=_signature(),
        render=_render(),
    )

    assert plan.plan_id == "plan-1"
    assert plan.anchor.anchor_id == "anchor-1"
    assert plan.anchor.source_evidence_ids == ("ev-1", "ev-2")
    assert plan.anchor.main_entities == ("Policy", "Market")
    assert plan.diagram.composition_rules == (
        "left-to-right cause chain",
        "show feedback arrow",
    )
    assert plan.diagram.panel_plan == (
        "Panel 1: policy dial",
        "Panel 2: market pressure",
    )
    assert plan.series_signature.identity_profile_id == "signature-profile-7"
    assert plan.series_signature.forbidden_behaviors == (
        "replace article subjects",
        "dominate the panel",
    )
    assert plan.render.style_rules == (
        "clean editorial linework",
        "muted accent color for arrows",
    )

    payload = plan.to_dict()

    assert payload["plan_id"] == "plan-1"
    assert payload["request"] == request.to_dict()
    assert payload["resolution"] == plan.resolution.to_dict()
    assert payload["anchor"] == {
        "anchor_id": "anchor-1",
        "anchor_kind": "causal_mechanism",
        "anchor_claim": "Policy feedback loops compound over time.",
        "anchor_question": "Why does the feedback loop accelerate?",
        "source_evidence_ids": ["ev-1", "ev-2"],
        "main_entities": ["Policy", "Market"],
        "required_subjects": ["regulator", "market signal"],
        "source_text_excerpt": "The policy change triggered a market feedback loop.",
        "confidence": 0.82,
    }
    assert payload["diagram"]["primary_visual_task"] == "cognitive_explanation"
    assert payload["diagram"]["visible_text"] == _visible_text().to_dict()
    assert payload["series_signature"]["role"] == "guide"
    assert payload["render"]["diagram_panel_aspect_ratio"] == "square_1_1"
    json.dumps(payload, allow_nan=False)


def test_xiaohei_render_style_does_not_insert_signature_when_role_none():
    signature = ac.SeriesVisualSignatureContract(
        enabled=False,
        role=SeriesVisualSignatureRole.NONE,
        identity_profile_id=None,
        participation_rule="No recurring signature participates.",
        replacement_policy="no_subject_replacement",
        visual_weight=0.0,
        forbidden_behaviors=["do not replace article subjects"],
    )
    render = ac.DiagramRenderContract(
        render_style=DiagramRenderStyle.XIAOHEI_HANDDRAWN,
        canvas_aspect_ratio=DiagramAspectRatio.LANDSCAPE_16_9,
        diagram_panel_aspect_ratio=DiagramAspectRatio.LANDSCAPE_16_9,
        panel_inside_canvas=False,
        style_rules=[
            "loose black marker linework",
            "plain paper texture",
        ],
        negative_style_rules=["no photorealistic shading"],
    )

    assert signature.to_dict()["role"] == "none"
    assert render.style_rules == (
        "loose black marker linework",
        "plain paper texture",
    )
    render_payload = render.to_dict()
    assert render_payload["style_rules"] == [
        "loose black marker linework",
        "plain paper texture",
    ]
    assert "signature" not in " ".join(render_payload["style_rules"]).lower()
    assert "character" not in " ".join(render_payload["style_rules"]).lower()


@pytest.mark.parametrize(
    ("field_name", "rules"),
    [
        ("style_rules", ["include fixed mascot character signature"]),
        ("style_rules", ["use a recurring figure in each panel"]),
        ("style_rules", ["black solid figure appears in every frame"]),
        ("style_rules", ["recurring-figure marker in every panel"]),
        ("style_rules", ["same black solid figure appears in all panels"]),
        ("style_rules", ["black solid silhouette appears in every frame"]),
        ("style_rules", ["same Xiaohei silhouette appears in every panel"]),
        ("negative_style_rules", ["do not include Xiaohei character as recurring figure"]),
        ("negative_style_rules", ["do not add recurring figure"]),
        ("negative_style_rules", ["do not use black solid figure in every frame"]),
        ("negative_style_rules", ["no recurring-figure marker"]),
        ("negative_style_rules", ["do not add same Xiaohei silhouette in all panels"]),
    ],
)
def test_xiaohei_render_style_rejects_fixed_signature_semantics(
    field_name,
    rules,
):
    kwargs = {
        "render_style": DiagramRenderStyle.XIAOHEI_HANDDRAWN,
        "canvas_aspect_ratio": DiagramAspectRatio.LANDSCAPE_16_9,
        "diagram_panel_aspect_ratio": DiagramAspectRatio.LANDSCAPE_16_9,
        "panel_inside_canvas": False,
        "style_rules": [
            "hand-drawn explanatory panel style",
            "simple black linework",
            "limited red orange blue annotation marks",
            "plain paper texture",
            "white background",
            "clean contours",
        ],
        "negative_style_rules": ["no photorealistic shading"],
    }
    kwargs[field_name] = rules

    with pytest.raises(ValueError, match=field_name):
        ac.DiagramRenderContract(**kwargs)


def test_xiaohei_render_style_allows_surface_style_rules():
    render = ac.DiagramRenderContract(
        render_style=DiagramRenderStyle.XIAOHEI_HANDDRAWN,
        canvas_aspect_ratio=DiagramAspectRatio.LANDSCAPE_16_9,
        diagram_panel_aspect_ratio=DiagramAspectRatio.LANDSCAPE_16_9,
        panel_inside_canvas=False,
        style_rules=[
            "hand-drawn explanatory panel style",
            "simple black linework",
            "limited red orange blue annotation marks",
            "plain paper texture",
            "white background",
            "clean contours",
        ],
        negative_style_rules=["no photorealistic shading"],
    )

    assert render.style_rules == (
        "hand-drawn explanatory panel style",
        "simple black linework",
        "limited red orange blue annotation marks",
        "plain paper texture",
        "white background",
        "clean contours",
    )


def test_signature_enabled_requires_non_none_role():
    for role in (SeriesVisualSignatureRole.NONE, SeriesVisualSignatureRole.AUTO):
        with pytest.raises(ValueError, match="role"):
            _signature(enabled=True, role=role)

    disabled = ac.SeriesVisualSignatureContract(
        enabled=False,
        role=SeriesVisualSignatureRole.NONE,
        identity_profile_id=" ",
        participation_rule="Disabled signature stays out of the frame.",
        replacement_policy="no_subject_replacement",
        visual_weight=0.0,
        forbidden_behaviors=[],
    )

    assert disabled.role is SeriesVisualSignatureRole.NONE
    assert disabled.identity_profile_id is None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"role": SeriesVisualSignatureRole.GUIDE}, "role"),
        ({"identity_profile_id": "ip-1"}, "identity_profile_id"),
        ({"visual_weight": 0.1}, "visual_weight"),
    ],
)
def test_signature_disabled_rejects_contradictory_presence_fields(
    overrides,
    message,
):
    kwargs = {
        "enabled": False,
        "role": SeriesVisualSignatureRole.NONE,
        "identity_profile_id": None,
        "participation_rule": "Disabled signature stays out of the frame.",
        "replacement_policy": "no_subject_replacement",
        "visual_weight": 0.0,
        "forbidden_behaviors": [],
    }
    kwargs.update(overrides)

    with pytest.raises(ValueError, match=message):
        ac.SeriesVisualSignatureContract(**kwargs)


def test_signature_visual_weight_range_validation():
    for bad_weight in (-0.01, 1.01):
        with pytest.raises(ValueError, match="visual_weight"):
            _signature(visual_weight=bad_weight)

    assert _signature(visual_weight=0.0).visual_weight == 0.0
    assert _signature(visual_weight=1.0).visual_weight == 1.0


def test_diagram_render_contract_serializes_canvas_and_panel_ratio():
    render = ac.DiagramRenderContract(
        render_style="clean_vector",
        canvas_aspect_ratio="landscape_16_9",
        diagram_panel_aspect_ratio="portrait_4_5",
        panel_inside_canvas="true",
        style_rules=["thin vector strokes"],
        negative_style_rules=["no texture"],
    )

    assert render.style_rules == ("thin vector strokes",)
    assert render.negative_style_rules == ("no texture",)
    assert render.to_dict() == {
        "render_style": "clean_vector",
        "canvas_aspect_ratio": "landscape_16_9",
        "diagram_panel_aspect_ratio": "portrait_4_5",
        "panel_inside_canvas": True,
        "style_rules": ["thin vector strokes"],
        "negative_style_rules": ["no texture"],
    }


def test_cognitive_anchor_plan_requires_source_evidence_or_source_text_fallback():
    with pytest.raises(ValueError, match="source_text_excerpt"):
        ac.CognitiveAnchorPlan(
            anchor_id="anchor-blank",
            anchor_kind="judgment",
            anchor_claim="A concrete claim is present.",
            anchor_question="What question does the claim answer?",
            source_evidence_ids=[],
            main_entities=[],
            required_subjects=[],
            source_text_excerpt=" ",
            confidence=0.5,
        )

    fallback_anchor = ac.CognitiveAnchorPlan(
        anchor_id="anchor-fallback",
        anchor_kind="judgment",
        anchor_claim="A concrete claim is present.",
        anchor_question="What question does the claim answer?",
        source_evidence_ids=[],
        main_entities=["claimant"],
        required_subjects=["claimant"],
        source_text_excerpt="Fallback source sentence.",
        confidence=1.0,
    )

    assert fallback_anchor.source_evidence_ids == ()
    assert fallback_anchor.source_text_excerpt == "Fallback source sentence."


def test_cognitive_anchor_plan_rejects_blank_source_text_excerpt_even_with_evidence():
    with pytest.raises(ValueError, match="source_text_excerpt"):
        ac.CognitiveAnchorPlan(
            anchor_id="anchor-evidence",
            anchor_kind="judgment",
            anchor_claim="A concrete claim is present.",
            anchor_question="What question does the claim answer?",
            source_evidence_ids=["ev-1"],
            main_entities=["claimant"],
            required_subjects=["claimant"],
            source_text_excerpt=" ",
            confidence=0.5,
        )
