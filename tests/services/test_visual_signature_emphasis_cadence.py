from __future__ import annotations

import pytest

from pixelle_video.models.visual_signature_emphasis import VisualSignatureEmphasis
from pixelle_video.services.visual_signature_emphasis_cadence import (
    VisualSignatureEmphasisCadencePlanner,
)


def _plan(frame_count: int, *, storyboard_plan_id: str = "plan-series-a"):
    frame_ids = tuple(f"frame-{index}" for index in range(1, frame_count + 1))
    decisions = VisualSignatureEmphasisCadencePlanner().plan(
        frame_ids=frame_ids,
        storyboard_plan_id=storyboard_plan_id,
    )
    return frame_ids, decisions


@pytest.mark.parametrize(
    ("frame_count", "expected_enhanced_count"),
    (
        (1, 1),
        (9, 1),
        (10, 1),
        (11, 2),
        (20, 2),
        (21, 3),
        (100, 10),
        (101, 11),
    ),
)
def test_cadence_rounds_one_tenth_up_with_one_frame_minimum(
    frame_count: int,
    expected_enhanced_count: int,
):
    frame_ids, decisions = _plan(frame_count)

    enhanced = [
        decision
        for decision in decisions
        if decision.emphasis is VisualSignatureEmphasis.ENHANCED
    ]

    assert len(decisions) == len(frame_ids)
    assert len(enhanced) == expected_enhanced_count


def test_cadence_spreads_enhanced_frames_across_balanced_windows():
    frame_ids, decisions = _plan(21)
    enhanced_indexes = {
        frame_ids.index(decision.frame_id)
        for decision in decisions
        if decision.emphasis is VisualSignatureEmphasis.ENHANCED
    }

    assert len(enhanced_indexes & set(range(0, 7))) == 1
    assert len(enhanced_indexes & set(range(7, 14))) == 1
    assert len(enhanced_indexes & set(range(14, 21))) == 1


@pytest.mark.parametrize("frame_count", (11, 20, 21, 50, 101))
def test_cadence_never_places_enhanced_frames_next_to_each_other(frame_count):
    frame_ids, decisions = _plan(frame_count)
    enhanced_indexes = sorted(
        frame_ids.index(decision.frame_id)
        for decision in decisions
        if decision.emphasis is VisualSignatureEmphasis.ENHANCED
    )

    assert all(
        current_index - previous_index >= 3
        for previous_index, current_index in zip(
            enhanced_indexes,
            enhanced_indexes[1:],
        )
    )


def test_cadence_is_reproducible_from_stable_storyboard_plan_id():
    frame_ids, first = _plan(25, storyboard_plan_id="plan-stable")

    second = VisualSignatureEmphasisCadencePlanner().plan(
        frame_ids=frame_ids,
        storyboard_plan_id="plan-stable",
    )

    assert first == second


def test_cadence_accepts_empty_batch_with_a_stable_storyboard_plan_id():
    planner = VisualSignatureEmphasisCadencePlanner()

    assert planner.plan(frame_ids=(), storyboard_plan_id="plan-empty") == ()


@pytest.mark.parametrize(
    "frame_ids",
    (("",), ("frame-a", "frame-a")),
)
def test_cadence_rejects_invalid_frame_ids(frame_ids):
    with pytest.raises(ValueError, match="frame_ids"):
        VisualSignatureEmphasisCadencePlanner().plan(
            frame_ids=frame_ids,
            storyboard_plan_id="plan-invalid-frames",
        )


def test_cadence_rejects_bare_string_as_frame_sequence():
    with pytest.raises(TypeError, match="sequence"):
        VisualSignatureEmphasisCadencePlanner().plan(
            frame_ids="frame-a",
            storyboard_plan_id="plan-invalid-sequence",
        )


@pytest.mark.parametrize(
    ("invalid_plan_id", "expected_error"),
    (
        (None, TypeError),
        (1, TypeError),
        ("", ValueError),
        ("   ", ValueError),
    ),
)
def test_cadence_rejects_invalid_storyboard_plan_id(
    invalid_plan_id,
    expected_error,
):
    with pytest.raises(expected_error, match="storyboard_plan_id"):
        VisualSignatureEmphasisCadencePlanner().plan(
            frame_ids=("frame-a",),
            storyboard_plan_id=invalid_plan_id,
        )


def test_cadence_scales_linearly_for_long_series():
    frame_ids, decisions = _plan(10_001)

    assert len(decisions) == len(frame_ids)
    assert sum(
        decision.emphasis is VisualSignatureEmphasis.ENHANCED
        for decision in decisions
    ) == 1_001
