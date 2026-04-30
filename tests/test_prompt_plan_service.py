import pytest

from pixelle_video.models.storyboard_plan import (
    StoryboardCountMode,
    StoryboardGenerationMode,
    StoryboardPlan,
    StoryboardPlanFrame,
)
from pixelle_video.services.prompt_plan_service import build_prompt_plan_bundle


def _storyboard_plan() -> StoryboardPlan:
    return StoryboardPlan.build(
        mode=StoryboardGenerationMode.SENTENCE,
        count_mode=StoryboardCountMode.AUTO,
        requested_scene_count=None,
        source_text="The fox finds a lantern. The village glows.",
        plan_id="storyboard_plan_001",
        frames=[
            StoryboardPlanFrame(
                frame_id="frame_0001",
                index=1,
                source_text="The fox finds a lantern.",
                visual_goal="fox discovers a lantern",
                prompt_intent="show curiosity and warm light",
            ),
            StoryboardPlanFrame(
                frame_id="frame_0002",
                index=2,
                source_text="The village glows.",
                visual_goal="village lights turn on",
                prompt_intent="show a cozy night village",
            ),
        ],
    )


def test_build_prompt_plan_bundle_preserves_frame_ids_and_links_drafts():
    bundle = build_prompt_plan_bundle(
        storyboard_plan=_storyboard_plan(),
        image_prompts=[
            "fox cub holding a lantern, warm storybook light",
            "cozy village glowing at night, soft painted texture",
        ],
        source_trace_id="trace_image_prompt_batch",
    )

    assert bundle.storyboard_plan_id == "storyboard_plan_001"
    assert [draft.frame_id for draft in bundle.image_prompt_drafts] == [
        "frame_0001",
        "frame_0002",
    ]
    assert [plan.frame_id for plan in bundle.prompt_plans] == [
        "frame_0001",
        "frame_0002",
    ]
    assert bundle.prompt_plans[0].image_prompt_draft_id == (
        bundle.image_prompt_drafts[0].image_prompt_draft_id
    )
    assert bundle.prompt_plans[0].final_prompt == (
        "fox cub holding a lantern, warm storybook light"
    )
    assert bundle.prompt_plans[0].prompt_sections == {
        "source_text": "The fox finds a lantern.",
        "visual_goal": "fox discovers a lantern",
        "prompt_intent": "show curiosity and warm light",
        "generated_prompt": "fox cub holding a lantern, warm storybook light",
    }
    assert bundle.prompt_plans[0].source_trace_id == "trace_image_prompt_batch"


def test_prompt_plan_bundle_serializes_for_repository_contract():
    bundle = build_prompt_plan_bundle(
        storyboard_plan=_storyboard_plan(),
        image_prompts=[
            "fox cub holding a lantern, warm storybook light",
            "cozy village glowing at night, soft painted texture",
        ],
    )

    payload = bundle.to_dict()

    assert payload["storyboard_plan_id"] == "storyboard_plan_001"
    assert len(payload["image_prompt_drafts"]) == 2
    assert len(payload["prompt_plans"]) == 2
    assert payload["prompt_plans"][0]["frame_id"] == "frame_0001"
    assert payload["prompt_plans"][0]["image_prompt_draft_id"] == (
        payload["image_prompt_drafts"][0]["image_prompt_draft_id"]
    )


def test_build_prompt_plan_bundle_rejects_prompt_frame_count_mismatch():
    with pytest.raises(ValueError, match="image prompt count must match storyboard frame count"):
        build_prompt_plan_bundle(
            storyboard_plan=_storyboard_plan(),
            image_prompts=["only one prompt"],
        )
