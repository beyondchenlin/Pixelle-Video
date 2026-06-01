import json

import pytest

from pixelle_video.models import article_understanding
from pixelle_video.models.article_understanding import (
    ArticleUnderstandingLens,
    ArticleUnderstandingMode,
    ArticleUnderstandingPlan,
    FrameUnderstandingPlan,
    SourceEvidenceSpan,
    SubjectAnchor,
)
from pixelle_video.models.visual_planning_mode import VisibleTextPolicy, VisualPlanningMode


def test_article_understanding_mode_defaults_and_known_values():
    assert (
        ArticleUnderstandingMode.from_value("cognitive_state")
        is ArticleUnderstandingMode.COGNITIVE_STATE
    )
    assert ArticleUnderstandingMode.from_value("not_a_mode") is ArticleUnderstandingMode.AUTO
    assert ArticleUnderstandingMode.from_value(None) is ArticleUnderstandingMode.AUTO


def test_article_understanding_lens_defaults_and_known_values():
    assert (
        ArticleUnderstandingLens.from_value("contrast_conflict")
        is ArticleUnderstandingLens.CONTRAST_CONFLICT
    )
    assert (
        ArticleUnderstandingLens.from_value("not_a_lens")
        is ArticleUnderstandingLens.THESIS_ARGUMENT
    )
    assert ArticleUnderstandingLens.from_value(None) is ArticleUnderstandingLens.THESIS_ARGUMENT
    assert (
        ArticleUnderstandingLens.from_value(
            "not_a_lens",
            default=ArticleUnderstandingLens.COGNITIVE_STATE,
        )
        is ArticleUnderstandingLens.COGNITIVE_STATE
    )


def test_subject_anchor_requires_evidence_span_ids_and_serializes_them_as_list():
    with pytest.raises(ValueError, match="evidence_span_ids"):
        SubjectAnchor(
            subject_id="subject-1",
            label="Market",
            source_phrase="the market",
            evidence_span_ids=(),
            importance="primary",
            visual_presence="required",
            loss_policy="forbidden",
        )

    anchor = SubjectAnchor(
        subject_id="subject-1",
        label="Market",
        source_phrase="the market",
        evidence_span_ids=["evidence-1", " evidence-2 "],
        importance="primary",
        visual_presence="required",
        loss_policy="forbidden",
    )

    assert anchor.evidence_span_ids == ("evidence-1", "evidence-2")
    assert anchor.to_dict()["evidence_span_ids"] == ["evidence-1", "evidence-2"]
    assert anchor.to_dict()["importance"] == "primary"


@pytest.mark.parametrize("value", [{"score": 0.9}, 1])
def test_subject_anchor_rejects_non_string_importance(value):
    with pytest.raises((TypeError, ValueError), match="importance"):
        SubjectAnchor(
            subject_id="subject-1",
            label="Market",
            source_phrase="the market",
            evidence_span_ids=("evidence-1",),
            importance=value,
            visual_presence="required",
            loss_policy="forbidden",
        )


@pytest.mark.parametrize("value", ["", "   ", None])
def test_subject_anchor_requires_non_blank_importance(value):
    with pytest.raises((TypeError, ValueError), match="importance"):
        SubjectAnchor(
            subject_id="subject-1",
            label="Market",
            source_phrase="the market",
            evidence_span_ids=("evidence-1",),
            importance=value,
            visual_presence="required",
            loss_policy="forbidden",
        )


def test_source_evidence_span_allows_omitting_optional_location_fields():
    evidence = SourceEvidenceSpan(
        evidence_id="evidence-1",
        source_id="article-1",
        quote="markets reprice risk",
        evidence_role="core_claim",
    )

    assert evidence.frame_id is None
    assert evidence.start_char is None
    assert evidence.end_char is None
    assert evidence.to_dict() == {
        "evidence_id": "evidence-1",
        "source_id": "article-1",
        "frame_id": None,
        "start_char": None,
        "end_char": None,
        "quote": "markets reprice risk",
        "evidence_role": "core_claim",
    }


@pytest.mark.parametrize("value", ["", "   ", None])
@pytest.mark.parametrize(
    "field_name",
    ["evidence_id", "source_id", "quote", "evidence_role"],
)
def test_source_evidence_span_requires_required_text_fields(field_name, value):
    kwargs = {
        "evidence_id": "evidence-1",
        "source_id": "article-1",
        "quote": "markets reprice risk",
        "evidence_role": "core_claim",
    }
    kwargs[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        SourceEvidenceSpan(**kwargs)


def test_article_understanding_plan_serializes_json_safe_values():
    evidence = SourceEvidenceSpan(
        evidence_id="evidence-1",
        source_id="article-1",
        frame_id="frame-1",
        start_char=3,
        end_char=17,
        quote="markets reprice risk",
        evidence_role="core_claim",
    )
    subject = SubjectAnchor(
        subject_id="subject-1",
        label="Markets",
        source_phrase="markets",
        evidence_span_ids=("evidence-1",),
        importance="primary",
        visual_presence="required",
        loss_policy="forbidden",
    )
    plan = ArticleUnderstandingPlan(
        article_id="article-1",
        primary_lens="cognitive_state",
        secondary_lenses=[ArticleUnderstandingLens.CAUSAL_MECHANISM],
        lens_confidence={
            ArticleUnderstandingLens.COGNITIVE_STATE: 0.91,
            "causal_mechanism": 0.74,
        },
        lens_payloads={
            ArticleUnderstandingLens.COGNITIVE_STATE: {
                "mode": ArticleUnderstandingMode.COGNITIVE_STATE,
                "scores": (0.7, 0.2),
            }
        },
        required_subjects=[subject],
        unsuitable_visual_modes=[VisualPlanningMode.PROCESS_WALKTHROUGH, "relationship_map"],
        source_evidence=[evidence],
    )

    payload = plan.to_dict()

    assert payload["primary_lens"] == "cognitive_state"
    assert payload["secondary_lenses"] == ["causal_mechanism"]
    assert payload["lens_confidence"] == {
        "cognitive_state": 0.91,
        "causal_mechanism": 0.74,
    }
    assert payload["lens_payloads"] == {
        "cognitive_state": {
            "mode": "cognitive_state",
            "scores": [0.7, 0.2],
        }
    }
    assert payload["required_subjects"] == [subject.to_dict()]
    assert payload["unsuitable_visual_modes"] == ["process_walkthrough", "relationship_map"]
    assert payload["source_evidence"] == [evidence.to_dict()]
    json.dumps(payload, allow_nan=False)


def test_article_understanding_plan_rejects_non_finite_lens_confidence():
    with pytest.raises(ValueError, match="lens_confidence|finite number"):
        ArticleUnderstandingPlan(
            article_id="article-1",
            primary_lens="cognitive_state",
            lens_confidence={"x": float("nan")},
        )


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("primary_lens", {"primary_lens": "not_a_lens"}),
        (
            "secondary_lenses",
            {"primary_lens": "cognitive_state", "secondary_lenses": ["not_a_lens"]},
        ),
    ],
)
def test_article_understanding_plan_rejects_invalid_lens_facts(field_name, kwargs):
    with pytest.raises(ValueError, match=field_name):
        ArticleUnderstandingPlan(article_id="article-1", **kwargs)


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("primary_lens", {"primary_lens": "not_a_lens"}),
        (
            "secondary_lenses",
            {"primary_lens": "cognitive_state", "secondary_lenses": ["not_a_lens"]},
        ),
    ],
)
def test_frame_understanding_plan_rejects_invalid_lens_facts(field_name, kwargs):
    with pytest.raises(ValueError, match=field_name):
        FrameUnderstandingPlan(
            frame_id="frame-1",
            source_text="Original article text",
            frame_claim="A claim",
            frame_question="A question?",
            **kwargs,
        )


def test_article_understanding_plan_rejects_dangling_subject_evidence_refs():
    with pytest.raises(ValueError, match="missing-evidence"):
        ArticleUnderstandingPlan(
            article_id="article-1",
            primary_lens="cognitive_state",
            required_subjects=[
                SubjectAnchor(
                    subject_id="subject-1",
                    label="Markets",
                    source_phrase="markets",
                    evidence_span_ids=("missing-evidence",),
                    importance="primary",
                    visual_presence="required",
                    loss_policy="forbidden",
                )
            ],
            source_evidence=[
                SourceEvidenceSpan(
                    evidence_id="evidence-1",
                    source_id="article-1",
                    quote="markets reprice risk",
                    evidence_role="core_claim",
                )
            ],
        )


def test_frame_understanding_plan_rejects_dangling_subject_evidence_refs():
    with pytest.raises(ValueError, match="missing-evidence"):
        FrameUnderstandingPlan(
            frame_id="frame-1",
            source_text="Original article text",
            frame_claim="A claim",
            frame_question="A question?",
            primary_lens="cognitive_state",
            required_subjects=[
                SubjectAnchor(
                    subject_id="subject-1",
                    label="Markets",
                    source_phrase="markets",
                    evidence_span_ids=("missing-evidence",),
                    importance="primary",
                    visual_presence="required",
                    loss_policy="forbidden",
                )
            ],
            source_evidence=[
                SourceEvidenceSpan(
                    evidence_id="evidence-1",
                    source_id="article-1",
                    quote="markets reprice risk",
                    evidence_role="core_claim",
                )
            ],
        )


def test_article_understanding_plan_rejects_duplicate_evidence_ids():
    with pytest.raises(ValueError, match="duplicate evidence_id"):
        ArticleUnderstandingPlan(
            article_id="article-1",
            primary_lens="cognitive_state",
            source_evidence=[
                SourceEvidenceSpan(
                    evidence_id="evidence-1",
                    source_id="article-1",
                    quote="first quote",
                    evidence_role="core_claim",
                ),
                SourceEvidenceSpan(
                    evidence_id="evidence-1",
                    source_id="article-1",
                    quote="second quote",
                    evidence_role="supporting_claim",
                ),
            ],
        )


def test_article_understanding_plan_rejects_nested_lens_confidence_value():
    with pytest.raises(TypeError, match="lens_confidence|finite number"):
        ArticleUnderstandingPlan(
            article_id="article-1",
            primary_lens="cognitive_state",
            lens_confidence={"cognitive_state": {"score": 0.9}},
        )


@pytest.mark.parametrize("value", ["0.9", True, float("nan"), float("inf"), float("-inf")])
def test_article_understanding_plan_rejects_invalid_lens_confidence_values(value):
    with pytest.raises((TypeError, ValueError), match="lens_confidence|finite number"):
        ArticleUnderstandingPlan(
            article_id="article-1",
            primary_lens="cognitive_state",
            lens_confidence={"cognitive_state": value},
        )


def test_article_understanding_plan_rejects_nested_non_finite_lens_payload():
    with pytest.raises(ValueError, match="JSON|finite"):
        ArticleUnderstandingPlan(
            article_id="article-1",
            primary_lens="cognitive_state",
            lens_payloads={"x": {"score": float("inf")}},
        )


def test_article_understanding_plan_freezes_lens_mappings():
    plan = ArticleUnderstandingPlan(
        article_id="article-1",
        primary_lens="cognitive_state",
        lens_confidence={"cognitive_state": 0.91},
        lens_payloads={"cognitive_state": {"score": 0.91}},
    )

    with pytest.raises(TypeError):
        plan.lens_confidence["new"] = 1.0

    with pytest.raises(TypeError):
        plan.lens_payloads["cognitive_state"]["new"] = "x"


def test_article_understanding_plan_to_dict_is_strict_json_serializable():
    plan = ArticleUnderstandingPlan(
        article_id="article-1",
        primary_lens="cognitive_state",
        lens_confidence={"cognitive_state": 0.91},
        lens_payloads={"cognitive_state": {"scores": [0.7, 0.2]}},
    )

    json.dumps(plan.to_dict(), allow_nan=False)


def test_frame_understanding_plan_defaults_visible_text_policy_and_serializes_it():
    plan = FrameUnderstandingPlan(
        frame_id="frame-1",
        source_text="Original article text",
        frame_claim="A claim",
        frame_question="A question?",
        primary_lens=ArticleUnderstandingLens.THESIS_ARGUMENT,
    )

    assert plan.visible_text_policy is VisibleTextPolicy.NO_VISIBLE_TEXT
    assert plan.to_dict()["visible_text_policy"] == "no_visible_text"


def test_article_understanding_exports_public_contract_classes():
    assert set(article_understanding.__all__) == {
        "ArticleUnderstandingLens",
        "ArticleUnderstandingMode",
        "ArticleUnderstandingPlan",
        "FrameUnderstandingPlan",
        "SourceEvidenceSpan",
        "SubjectAnchor",
    }
