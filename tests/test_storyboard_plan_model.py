import hashlib
import json
from dataclasses import FrozenInstanceError

import pytest

from pixelle_video.models.storyboard_plan import (
    SourceSpan,
    StoryboardCountMode,
    StoryboardGenerationMode,
    StoryboardPlan,
    StoryboardPlanFrame,
)


def test_storyboard_plan_assigns_digest_and_serializes_frames():
    plan = StoryboardPlan.build(
        mode=StoryboardGenerationMode.PUNCTUATION,
        count_mode=StoryboardCountMode.AUTO,
        requested_scene_count=None,
        source_text="第一句。第二句。",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="第一句。",
                narration_text="第一句。",
                visual_goal="Show the first idea.",
                prompt_intent="A clear visual metaphor for the first idea.",
                source_start=0,
                source_end=4,
            ),
            StoryboardPlanFrame(
                index=2,
                source_text="第二句。",
                narration_text="第二句。",
                visual_goal="Show the second idea.",
                prompt_intent="A clear visual metaphor for the second idea.",
                source_start=4,
                source_end=8,
            ),
        ],
    )

    payload = plan.to_dict()

    assert plan.resolved_scene_count == 2
    assert plan.source_digest
    assert payload["frames"][0]["frame_id"].startswith("frame_")
    assert payload["frames"][1]["index"] == 2


def test_source_spans_index_plan_source_text():
    span = SourceSpan(start=0, end=3, text="abc", reason="primary")
    frame = StoryboardPlanFrame(
        index=1,
        source_text="abc",
        narration_text="abc",
        visual_goal="show abc",
        prompt_intent="show abc",
        source_start=None,
        source_end=None,
        metadata={"source_spans": [span.to_dict()]},
    )

    plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="abcdef",
        frames=[frame],
    )

    assert plan.frames[0].metadata["source_spans"][0]["text"] == "abc"


def test_storyboard_plan_digest_uses_normalized_source_text():
    plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="  abc  ",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="abc",
                narration_text="abc",
                visual_goal="show abc",
                prompt_intent="show abc",
            )
        ],
    )

    assert plan.source_text == "abc"
    assert plan.source_digest == hashlib.sha256("abc".encode("utf-8")).hexdigest()


def test_storyboard_plan_owns_frames_after_build():
    original_frame = StoryboardPlanFrame(
        index=1,
        source_text="abc",
        narration_text="abc",
        visual_goal="show abc",
        prompt_intent="show abc",
        metadata={"tags": ["original"]},
    )
    frames = [original_frame]

    plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="abc",
        frames=frames,
    )

    frames.append(
        StoryboardPlanFrame(
            index=2,
            source_text="def",
            narration_text="def",
            visual_goal="show def",
            prompt_intent="show def",
        )
    )
    with pytest.raises(FrozenInstanceError):
        original_frame.narration_text = "changed"
    with pytest.raises(TypeError):
        original_frame.metadata["tags"] += ("mutated",)

    assert plan.resolved_scene_count == 1
    assert len(plan.frames) == 1
    assert plan.frames[0] is not original_frame
    assert plan.frames[0].narration_text == "abc"
    assert plan.frames[0].metadata["tags"] == ("original",)


def test_storyboard_plan_to_dict_deep_copies_nested_payloads():
    plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="abc",
        diagnostics={"warnings": [{"code": "demo"}]},
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="abc",
                narration_text="abc",
                visual_goal="show abc",
                prompt_intent="show abc",
                metadata={"source_spans": [{"start": 0, "end": 3, "text": "abc"}]},
            )
        ],
    )

    payload = plan.to_dict()
    payload["diagnostics"]["warnings"][0]["code"] = "changed"
    payload["frames"][0]["metadata"]["source_spans"][0]["text"] = "changed"

    assert plan.diagnostics["warnings"][0]["code"] == "demo"
    assert plan.frames[0].metadata["source_spans"][0]["text"] == "abc"


def test_storyboard_plan_rejects_non_contiguous_indices():
    with pytest.raises(ValueError, match="frame indexes must start at 1 and be contiguous"):
        StoryboardPlan.build(
            mode="sentence",
            count_mode="auto",
            requested_scene_count=None,
            source_text="one two",
            frames=[
                StoryboardPlanFrame(
                    index=2,
                    source_text="one two",
                    narration_text="one two",
                    visual_goal="show text",
                    prompt_intent="show text",
                )
            ],
        )


def test_storyboard_plan_rejects_invalid_source_span_text():
    with pytest.raises(ValueError, match="source_spans text must match source_text slice"):
        StoryboardPlan.build(
            mode="smart",
            count_mode="auto",
            requested_scene_count=None,
            source_text="abcdef",
            frames=[
                StoryboardPlanFrame(
                    index=1,
                    source_text="abc",
                    narration_text="abc",
                    visual_goal="show abc",
                    prompt_intent="show abc",
                    metadata={"source_spans": [SourceSpan(start=0, end=3, text="wrong").to_dict()]},
                )
            ],
        )


def test_storyboard_plan_rejects_unsorted_source_spans():
    with pytest.raises(ValueError, match="source_spans must be sorted by start"):
        StoryboardPlan.build(
            mode="smart",
            count_mode="auto",
            requested_scene_count=None,
            source_text="abcdef",
            frames=[
                StoryboardPlanFrame(
                    index=1,
                    source_text="abcdef",
                    narration_text="abcdef",
                    visual_goal="show abcdef",
                    prompt_intent="show abcdef",
                    metadata={
                        "source_spans": [
                            SourceSpan(start=3, end=6, text="def").to_dict(),
                            SourceSpan(start=0, end=3, text="abc").to_dict(),
                        ]
                    },
                )
            ],
        )


def test_storyboard_plan_rejects_manual_count_mismatch():
    with pytest.raises(ValueError, match="requested_scene_count must match frame count"):
        StoryboardPlan.build(
            mode="smart",
            count_mode="manual",
            requested_scene_count=2,
            source_text="abc",
            frames=[
                StoryboardPlanFrame(
                    index=1,
                    source_text="abc",
                    narration_text="abc",
                    visual_goal="show abc",
                    prompt_intent="show abc",
                )
            ],
        )


def test_storyboard_plan_rejects_requested_count_outside_smart_manual():
    with pytest.raises(ValueError, match="requested_scene_count is only valid for smart manual mode"):
        StoryboardPlan.build(
            mode="sentence",
            count_mode="auto",
            requested_scene_count=1,
            source_text="abc",
            frames=[
                StoryboardPlanFrame(
                    index=1,
                    source_text="abc",
                    narration_text="abc",
                    visual_goal="show abc",
                    prompt_intent="show abc",
                )
            ],
        )


def test_storyboard_plan_rejects_manual_count_mode_outside_smart():
    with pytest.raises(ValueError, match="manual count mode is only valid for smart mode"):
        StoryboardPlan.build(
            mode="sentence",
            count_mode="manual",
            requested_scene_count=None,
            source_text="abc",
            frames=[
                StoryboardPlanFrame(
                    index=1,
                    source_text="abc",
                    narration_text="abc",
                    visual_goal="show abc",
                    prompt_intent="show abc",
                )
            ],
        )


def test_storyboard_plan_rejects_duplicate_frame_ids():
    with pytest.raises(ValueError, match="frame_id must be unique"):
        StoryboardPlan.build(
            mode="smart",
            count_mode="auto",
            requested_scene_count=None,
            source_text="abcdef",
            frames=[
                StoryboardPlanFrame(
                    frame_id="frame_duplicate",
                    index=1,
                    source_text="abc",
                    narration_text="abc",
                    visual_goal="show abc",
                    prompt_intent="show abc",
                ),
                StoryboardPlanFrame(
                    frame_id="frame_duplicate",
                    index=2,
                    source_text="def",
                    narration_text="def",
                    visual_goal="show def",
                    prompt_intent="show def",
                ),
            ],
        )


def test_storyboard_plan_rejects_invalid_revision():
    with pytest.raises(ValueError, match="revision must be a positive integer"):
        StoryboardPlan.build(
            mode="smart",
            count_mode="auto",
            requested_scene_count=None,
            revision=0,
            source_text="abc",
            frames=[
                StoryboardPlanFrame(
                    index=1,
                    source_text="abc",
                    narration_text="abc",
                    visual_goal="show abc",
                    prompt_intent="show abc",
                )
            ],
        )


def test_storyboard_plan_serializes_sourcespan_objects_as_json_safe_dicts():
    plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="abcdef",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="abc",
                narration_text="abc",
                visual_goal="show abc",
                prompt_intent="show abc",
                metadata={"source_spans": [SourceSpan(start=0, end=3, text="abc")]},
            )
        ],
    )

    payload = plan.to_dict()

    assert payload["frames"][0]["metadata"]["source_spans"] == [
        {"start": 0, "end": 3, "text": "abc", "reason": ""}
    ]
    json.dumps(payload)


def test_storyboard_plan_rejects_source_text_that_conflicts_with_source_range():
    with pytest.raises(ValueError, match="frame source_text must match source range slice"):
        StoryboardPlan.build(
            mode="sentence",
            count_mode="auto",
            requested_scene_count=None,
            source_text="abcdef",
            frames=[
                StoryboardPlanFrame(
                    index=1,
                    source_text="zzz",
                    narration_text="abc",
                    visual_goal="show abc",
                    prompt_intent="show abc",
                    source_start=0,
                    source_end=3,
                )
            ],
        )


def test_storyboard_plan_direct_constructor_enforces_invariants():
    with pytest.raises(ValueError, match="resolved_scene_count must match frame count"):
        StoryboardPlan(
            plan_id="plan_test",
            revision=1,
            mode=StoryboardGenerationMode.SMART,
            count_mode=StoryboardCountMode.AUTO,
            requested_scene_count=None,
            resolved_scene_count=2,
            source_text="abc",
            source_digest=hashlib.sha256("abc".encode("utf-8")).hexdigest(),
            frames=(
                StoryboardPlanFrame(
                    frame_id="frame_0001",
                    index=1,
                    source_text="abc",
                    narration_text="abc",
                    visual_goal="show abc",
                    prompt_intent="show abc",
                ),
            ),
            diagnostics={},
        )


def test_storyboard_plan_is_immutable_after_construction():
    plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="abcdef",
        diagnostics={"warnings": [{"code": "demo"}]},
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="abc",
                narration_text="abc",
                visual_goal="show abc",
                prompt_intent="show abc",
                secondary_subjects=["subject"],
                metadata={"source_spans": [SourceSpan(start=0, end=3, text="abc")]},
            )
        ],
    )

    with pytest.raises(FrozenInstanceError):
        plan.resolved_scene_count = 99
    with pytest.raises(FrozenInstanceError):
        plan.frames[0].narration_text = ""
    with pytest.raises(FrozenInstanceError):
        plan.frames[0].secondary_subjects += ("mutated",)
    with pytest.raises(TypeError):
        plan.frames[0].metadata["source_spans"][0]["text"] = "bad"
    with pytest.raises(TypeError):
        plan.diagnostics["warnings"][0]["code"] = "changed"

    assert plan.resolved_scene_count == 1
    assert plan.frames[0].narration_text == "abc"
    assert plan.frames[0].metadata["source_spans"][0]["text"] == "abc"
    assert plan.diagnostics["warnings"][0]["code"] == "demo"


@pytest.mark.parametrize("requested_scene_count", [True, 1.0, "1", 0])
def test_storyboard_plan_rejects_non_strict_manual_scene_counts(requested_scene_count):
    with pytest.raises(ValueError, match="requested_scene_count must be a positive integer"):
        StoryboardPlan.build(
            mode="smart",
            count_mode="manual",
            requested_scene_count=requested_scene_count,
            source_text="abc",
            frames=[
                StoryboardPlanFrame(
                    index=1,
                    source_text="abc",
                    narration_text="abc",
                    visual_goal="show abc",
                    prompt_intent="show abc",
                )
            ],
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("revision", True, "revision must be a positive integer"),
        ("resolved_scene_count", True, "resolved_scene_count must be a positive integer"),
    ],
)
def test_storyboard_plan_rejects_bool_plan_count_fields(field, value, message):
    kwargs = {
        "plan_id": "plan_test",
        "revision": 1,
        "mode": StoryboardGenerationMode.SMART,
        "count_mode": StoryboardCountMode.AUTO,
        "requested_scene_count": None,
        "resolved_scene_count": 1,
        "source_text": "abc",
        "source_digest": hashlib.sha256("abc".encode("utf-8")).hexdigest(),
        "frames": (
            StoryboardPlanFrame(
                frame_id="frame_0001",
                index=1,
                source_text="abc",
                narration_text="abc",
                visual_goal="show abc",
                prompt_intent="show abc",
            ),
        ),
        "diagnostics": {},
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=message):
        StoryboardPlan(**kwargs)


def test_storyboard_plan_rejects_bool_frame_index():
    with pytest.raises(ValueError, match="frame index must be a positive integer"):
        StoryboardPlan.build(
            mode="smart",
            count_mode="auto",
            requested_scene_count=None,
            source_text="abc",
            frames=[
                StoryboardPlanFrame(
                    index=True,
                    source_text="abc",
                    narration_text="abc",
                    visual_goal="show abc",
                    prompt_intent="show abc",
                )
            ],
        )


def test_storyboard_plan_rejects_bool_source_range_offsets():
    with pytest.raises(ValueError, match="source_start and source_end must be integers"):
        StoryboardPlan.build(
            mode="sentence",
            count_mode="auto",
            requested_scene_count=None,
            source_text="abc",
            frames=[
                StoryboardPlanFrame(
                    index=1,
                    source_text="abc",
                    narration_text="abc",
                    visual_goal="show abc",
                    prompt_intent="show abc",
                    source_start=False,
                    source_end=3,
                )
            ],
        )


def test_storyboard_plan_rejects_bool_source_span_offsets():
    with pytest.raises(ValueError, match="source_spans start and end must be integers"):
        StoryboardPlan.build(
            mode="smart",
            count_mode="auto",
            requested_scene_count=None,
            source_text="abc",
            frames=[
                StoryboardPlanFrame(
                    index=1,
                    source_text="abc",
                    narration_text="abc",
                    visual_goal="show abc",
                    prompt_intent="show abc",
                    metadata={"source_spans": [SourceSpan(start=False, end=3, text="abc")]},
                )
            ],
        )
