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
from pixelle_video.models.visual_planning_mode import VisibleTextPolicy


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
