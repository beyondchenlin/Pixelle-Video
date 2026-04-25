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
