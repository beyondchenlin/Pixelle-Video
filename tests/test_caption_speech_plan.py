from pixelle_video.models.caption_speech_plan import build_caption_speech_plan
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame


def test_caption_speech_plan_splits_on_punctuation_and_strips_display_text():
    plan = build_caption_speech_plan("First, budget matters. Then pick a date!")

    assert [unit.speech_text for unit in plan.units] == [
        "First,",
        "budget matters.",
        "Then pick a date!",
    ]
    assert [unit.display_text for unit in plan.units] == [
        "First",
        "budget matters",
        "Then pick a date",
    ]
    assert [plan.source_text[unit.source_start : unit.source_end] for unit in plan.units] == [
        unit.speech_text for unit in plan.units
    ]


def test_caption_speech_plan_maps_units_to_overlapping_storyboard_frames():
    storyboard_plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="Budget matters.",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="Budget",
                visual_goal="Show the budget.",
                prompt_intent="Budget visual.",
                source_start=0,
                source_end=6,
            ),
            StoryboardPlanFrame(
                index=2,
                source_text=" matters.",
                visual_goal="Show the impact.",
                prompt_intent="Impact visual.",
                source_start=6,
                source_end=15,
            ),
        ],
    )

    plan = build_caption_speech_plan(
        storyboard_plan.source_text,
        storyboard_plan=storyboard_plan,
    )

    assert len(plan.units) == 1
    assert plan.units[0].speech_text == "Budget matters."
    assert plan.units[0].frame_indices == (0, 1)


def test_caption_speech_plan_maps_units_when_storyboard_frames_do_not_have_ranges():
    storyboard_plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="Budget matters. Timeline matters.",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="Budget matters.",
                visual_goal="Show the budget.",
                prompt_intent="Budget visual.",
            ),
            StoryboardPlanFrame(
                index=2,
                source_text="Timeline matters.",
                visual_goal="Show the timeline.",
                prompt_intent="Timeline visual.",
            ),
        ],
    )

    plan = build_caption_speech_plan(
        storyboard_plan.source_text,
        storyboard_plan=storyboard_plan,
    )

    assert [unit.speech_text for unit in plan.units] == [
        "Budget matters.",
        "Timeline matters.",
    ]
    assert [unit.frame_indices for unit in plan.units] == [(0,), (1,)]


def test_caption_speech_plan_keeps_partial_explicit_frame_ranges():
    storyboard_plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="Budget matters. Timeline matters.",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="Budget matters.",
                visual_goal="Show the budget.",
                prompt_intent="Budget visual.",
                source_start=0,
                source_end=15,
            ),
            StoryboardPlanFrame(
                index=2,
                source_text="Timeline matters.",
                visual_goal="Show the timeline.",
                prompt_intent="Timeline visual.",
            ),
        ],
    )

    plan = build_caption_speech_plan(
        storyboard_plan.source_text,
        storyboard_plan=storyboard_plan,
    )

    assert [unit.frame_indices for unit in plan.units] == [(0,), (1,)]


def test_caption_speech_plan_preserves_source_text_coordinates():
    source_text = "Budget matters.\nTimeline matters."
    plan = build_caption_speech_plan(source_text)

    assert plan.source_text == source_text
    assert [plan.source_text[unit.source_start : unit.source_end] for unit in plan.units] == [
        "Budget matters.",
        "Timeline matters.",
    ]
