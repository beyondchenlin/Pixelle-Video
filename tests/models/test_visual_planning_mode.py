import pytest

from pixelle_video.models.visual_planning_mode import (
    PrimaryVisualTask,
    VisibleTextPolicy,
    VisualPlanningMode,
)


def test_visual_planning_mode_accepts_known_value():
    assert (
        VisualPlanningMode.from_value("cognitive_illustration")
        is VisualPlanningMode.COGNITIVE_ILLUSTRATION
    )


def test_visual_planning_mode_rejects_signature_strategy_terms():
    assert VisualPlanningMode.from_value("host_explainer") is VisualPlanningMode.AUTO
    assert VisualPlanningMode.from_value("signature_presence") is VisualPlanningMode.AUTO


def test_visible_text_policy_defaults_and_known_values():
    assert VisibleTextPolicy.from_value(None) is VisibleTextPolicy.NO_VISIBLE_TEXT
    assert VisibleTextPolicy.from_value("source_text_only") is VisibleTextPolicy.SOURCE_TEXT_ONLY


def test_visible_text_policy_accepts_free_text_allowed():
    assert (
        VisibleTextPolicy.from_value("free_text_allowed")
        is VisibleTextPolicy.FREE_TEXT_ALLOWED
    )


def test_visible_text_policy_rejects_unknown_values():
    with pytest.raises(ValueError, match="visible_text_policy"):
        VisibleTextPolicy.from_value("free_text")


@pytest.mark.parametrize("value", [False, 0, [], object()])
def test_visible_text_policy_rejects_non_string_default_like_values(value):
    with pytest.raises(ValueError, match="visible_text_policy"):
        VisibleTextPolicy.from_value(value)


def test_primary_visual_task_defaults_and_known_values():
    assert (
        PrimaryVisualTask.from_value("cognitive_explanation")
        is PrimaryVisualTask.COGNITIVE_EXPLANATION
    )
    assert PrimaryVisualTask.from_value("not_a_task") is PrimaryVisualTask.SCENE_RECONSTRUCTION
