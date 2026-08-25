from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.visual_signature_emphasis import (
    VISUAL_SIGNATURE_EMPHASIS_CADENCE_VERSION,
    VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL,
    VisualSignatureEmphasis,
    VisualSignatureEmphasisCadencePlan,
)
from pixelle_video.services.visual_signature_emphasis_cadence import (
    VisualSignatureEmphasisCadencePlanner,
)


def _storyboard_plan(
    frame_count: int,
    *,
    plan_id: str = "plan-series-a",
    frame_id_prefix: str = "frame",
    changed_source_by_index: dict[int, str] | None = None,
    metadata_tag: str = "original",
) -> StoryboardPlan:
    changed_sources = changed_source_by_index or {}
    frames = [
        StoryboardPlanFrame(
            index=index,
            frame_id=f"{frame_id_prefix}-{index}",
            source_text=changed_sources.get(index, f"第{index}个画面的原文。"),
            visual_goal=f"表现第{index}个事件",
            prompt_intent=f"生成第{index}个画面",
            metadata={"audit_tag": metadata_tag},
        )
        for index in range(1, frame_count + 1)
    ]
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=" ".join(frame.source_text for frame in frames),
        frames=frames,
        plan_id=plan_id,
    )


def _plan(frame_count: int, **kwargs) -> VisualSignatureEmphasisCadencePlan:
    return VisualSignatureEmphasisCadencePlanner().plan(
        storyboard_plan=_storyboard_plan(frame_count, **kwargs)
    )


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
    cadence = _plan(frame_count)

    enhanced = [
        decision
        for decision in cadence.decisions
        if decision.emphasis is VisualSignatureEmphasis.ENHANCED
    ]

    assert len(cadence.decisions) == frame_count
    assert cadence.enhanced_frame_count == expected_enhanced_count
    assert len(enhanced) == expected_enhanced_count


def test_cadence_invariants_hold_across_all_supported_threshold_shapes():
    for frame_count in range(1, 501):
        cadence = _plan(frame_count)
        enhanced = [
            decision
            for decision in cadence.decisions
            if decision.emphasis is VisualSignatureEmphasis.ENHANCED
        ]
        expected_count = (
            frame_count + VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL - 1
        ) // VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL

        assert len(enhanced) == expected_count
        assert [decision.selection_window_index for decision in enhanced] == list(
            range(expected_count)
        )
        assert all(
            current.frame_index - previous.frame_index >= 3
            for previous, current in zip(enhanced, enhanced[1:])
        )
        for window_index, decision in enumerate(enhanced):
            window_start = window_index * frame_count // expected_count
            window_end = (window_index + 1) * frame_count // expected_count
            assert window_start <= decision.frame_index - 1 < window_end


def test_cadence_is_reproducible_from_storyboard_semantics():
    storyboard_plan = _storyboard_plan(25)
    planner = VisualSignatureEmphasisCadencePlanner()

    first = planner.plan(storyboard_plan=storyboard_plan)
    second = planner.plan(storyboard_plan=storyboard_plan)

    assert first == second


def test_cadence_selection_is_independent_from_mutable_plan_and_frame_ids():
    first = _plan(
        25,
        plan_id=" plan-a ",
        frame_id_prefix="first",
        metadata_tag="first-run",
    )
    second = _plan(
        25,
        plan_id="plan-b",
        frame_id_prefix="second",
        metadata_tag="second-run",
    )

    assert first.storyboard_plan_id == " plan-a "
    assert first.selection_input_sha256 == second.selection_input_sha256
    assert [
        (decision.emphasis, decision.selection_window_index) for decision in first.decisions
    ] == [(decision.emphasis, decision.selection_window_index) for decision in second.decisions]


def test_semantic_change_is_contained_to_its_selection_window():
    first = _plan(25)
    second = _plan(
        25,
        changed_source_by_index={1: "第一个画面的原文已发生语义变化。"},
    )

    assert first.selection_input_sha256 != second.selection_input_sha256
    first_later_windows = [
        decision.frame_index
        for decision in first.decisions
        if decision.selection_window_index in {1, 2}
    ]
    second_later_windows = [
        decision.frame_index
        for decision in second.decisions
        if decision.selection_window_index in {1, 2}
    ]
    assert first_later_windows == second_later_windows


def test_cadence_serializes_a_versioned_replay_contract():
    cadence = _plan(11)

    payload = cadence.model_dump(mode="json")

    assert payload["cadence_version"] == VISUAL_SIGNATURE_EMPHASIS_CADENCE_VERSION
    assert payload["frame_interval"] == VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL
    assert payload["enhanced_frame_count"] == 2
    assert re.fullmatch(r"[0-9a-f]{64}", payload["selection_input_sha256"])
    assert [decision["frame_index"] for decision in payload["decisions"]] == list(range(1, 12))


def test_cadence_contract_rejects_adjacent_enhanced_decisions():
    payload = _plan(21).model_dump(mode="json")
    for decision in payload["decisions"]:
        decision["emphasis"] = "standard"
        decision["selection_window_index"] = None
    for window_index, frame_index in enumerate((7, 8, 15)):
        payload["decisions"][frame_index - 1]["emphasis"] = "enhanced"
        payload["decisions"][frame_index - 1]["selection_window_index"] = window_index

    with pytest.raises(ValidationError, match="at least three frames apart"):
        VisualSignatureEmphasisCadencePlan.model_validate(payload)


def test_cadence_contract_rejects_decisions_outside_balanced_windows():
    payload = _plan(21).model_dump(mode="json")
    for decision in payload["decisions"]:
        decision["emphasis"] = "standard"
        decision["selection_window_index"] = None
    for window_index, frame_index in enumerate((1, 15, 21)):
        payload["decisions"][frame_index - 1]["emphasis"] = "enhanced"
        payload["decisions"][frame_index - 1]["selection_window_index"] = window_index

    with pytest.raises(ValidationError, match="inside their balanced windows"):
        VisualSignatureEmphasisCadencePlan.model_validate(payload)


def test_cadence_rejects_non_storyboard_input():
    with pytest.raises(TypeError, match="StoryboardPlan"):
        VisualSignatureEmphasisCadencePlanner().plan(storyboard_plan=object())


def test_cadence_handles_long_series_without_quadratic_work():
    cadence = _plan(10_001)

    assert len(cadence.decisions) == 10_001
    assert cadence.enhanced_frame_count == 1_001
