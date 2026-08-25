from __future__ import annotations

import pytest

from pixelle_video.models.visual_signature_emphasis import VisualSignatureEmphasis
from pixelle_video.services.visual_signature_emphasis_cadence import (
    VisualSignatureEmphasisCadencePlanner,
)


def _plan(frame_count: int, *, seed_offset: int = 0):
    frame_ids = tuple(f"frame-{index}" for index in range(1, frame_count + 1))
    seeds = {
        frame_id: seed_offset + index
        for index, frame_id in enumerate(frame_ids, start=1)
    }
    decisions = VisualSignatureEmphasisCadencePlanner().plan(
        frame_ids=frame_ids,
        random_seeds_by_frame=seeds,
    )
    return frame_ids, seeds, decisions


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
    frame_ids, _, decisions = _plan(frame_count)

    enhanced = [
        decision
        for decision in decisions
        if decision.emphasis is VisualSignatureEmphasis.ENHANCED
    ]

    assert len(decisions) == len(frame_ids)
    assert len(enhanced) == expected_enhanced_count


def test_cadence_spreads_enhanced_frames_across_balanced_windows():
    frame_ids, _, decisions = _plan(21)
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
    frame_ids, _, decisions = _plan(frame_count)
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


def test_cadence_is_reproducible_from_registered_frame_seeds():
    frame_ids, seeds, first = _plan(25, seed_offset=100)

    second = VisualSignatureEmphasisCadencePlanner().plan(
        frame_ids=frame_ids,
        random_seeds_by_frame=seeds,
    )

    assert first == second


def test_cadence_accepts_empty_batch_only_with_empty_seed_mapping():
    planner = VisualSignatureEmphasisCadencePlanner()

    assert planner.plan(frame_ids=(), random_seeds_by_frame={}) == ()
    with pytest.raises(ValueError, match="every frame id"):
        planner.plan(frame_ids=(), random_seeds_by_frame={"unknown": 1})


@pytest.mark.parametrize(
    "frame_ids",
    (("",), ("frame-a", "frame-a")),
)
def test_cadence_rejects_invalid_frame_ids(frame_ids):
    with pytest.raises(ValueError, match="frame_ids"):
        VisualSignatureEmphasisCadencePlanner().plan(
            frame_ids=frame_ids,
            random_seeds_by_frame={frame_id: 1 for frame_id in frame_ids},
        )


def test_cadence_rejects_bare_string_as_frame_sequence():
    with pytest.raises(TypeError, match="sequence"):
        VisualSignatureEmphasisCadencePlanner().plan(
            frame_ids="frame-a",
            random_seeds_by_frame={"frame-a": 1},
        )


@pytest.mark.parametrize("invalid_seed", (0, -1, 2**64, True, "1"))
def test_cadence_rejects_invalid_registered_seed(invalid_seed):
    with pytest.raises(ValueError, match="random seed"):
        VisualSignatureEmphasisCadencePlanner().plan(
            frame_ids=("frame-a",),
            random_seeds_by_frame={"frame-a": invalid_seed},
        )


def test_cadence_rejects_missing_or_unknown_seed_keys():
    planner = VisualSignatureEmphasisCadencePlanner()

    with pytest.raises(ValueError, match="every frame id"):
        planner.plan(
            frame_ids=("frame-a", "frame-b"),
            random_seeds_by_frame={"frame-a": 1},
        )
    with pytest.raises(ValueError, match="every frame id"):
        planner.plan(
            frame_ids=("frame-a",),
            random_seeds_by_frame={"frame-a": 1, "frame-b": 2},
        )


def test_cadence_scales_linearly_for_long_series():
    frame_ids, _, decisions = _plan(10_001)

    assert len(decisions) == len(frame_ids)
    assert sum(
        decision.emphasis is VisualSignatureEmphasis.ENHANCED
        for decision in decisions
    ) == 1_001
