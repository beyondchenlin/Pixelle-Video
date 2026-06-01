import pytest

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


def test_subject_anchor_requires_evidence_span_ids_and_serializes_them_as_list():
    with pytest.raises(ValueError, match="evidence_span_ids"):
        SubjectAnchor(
            subject_id="subject-1",
            label="Market",
            source_phrase="the market",
            evidence_span_ids=(),
            importance=0.8,
            visual_presence="required",
            loss_policy="forbidden",
        )

    anchor = SubjectAnchor(
        subject_id="subject-1",
        label="Market",
        source_phrase="the market",
        evidence_span_ids=["evidence-1", " evidence-2 "],
        importance=0.8,
        visual_presence="required",
        loss_policy="forbidden",
    )

    assert anchor.evidence_span_ids == ("evidence-1", "evidence-2")
    assert anchor.to_dict()["evidence_span_ids"] == ["evidence-1", "evidence-2"]


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
        importance=1,
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
