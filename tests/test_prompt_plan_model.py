from dataclasses import FrozenInstanceError

import pytest

from pixelle_video.models.prompt_plan import (
    ImagePromptDraft,
    PromptPlan,
    PromptProjection,
)


def test_image_prompt_draft_round_trips_frame_prompt_and_trace_link():
    draft = ImagePromptDraft(
        image_prompt_draft_id="draft_001",
        storyboard_plan_id="storyboard_plan_001",
        frame_id="frame_0001",
        prompt_text="warm storybook village, soft light",
        source_trace_id="trace_001",
        metadata={"composer": "stage1a"},
    )

    assert ImagePromptDraft.from_dict(draft.to_dict()) == draft
    assert draft.to_dict() == {
        "image_prompt_draft_id": "draft_001",
        "storyboard_plan_id": "storyboard_plan_001",
        "frame_id": "frame_0001",
        "prompt_text": "warm storybook village, soft light",
        "source_trace_id": "trace_001",
        "metadata": {"composer": "stage1a"},
    }

    with pytest.raises(FrozenInstanceError):
        draft.frame_id = "changed"
    with pytest.raises(TypeError):
        draft.metadata["composer"] = "changed"


def test_prompt_plan_uses_canonical_stage1a_shape():
    plan = PromptPlan(
        prompt_plan_id="prompt_plan_001",
        storyboard_plan_id="storyboard_plan_001",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_001",
        prompt_sections={
            "subject": "a fox cub looking at lanterns",
            "style": "warm storybook illustration",
            "camera": "medium shot",
        },
        final_prompt="a fox cub looking at lanterns, warm storybook illustration, medium shot",
        source_trace_id="trace_001",
        character_ids=("char_fox",),
        scene_id="scene_village",
        prop_ids=("prop_lantern",),
        style_id="style_storybook",
    )

    payload = plan.to_dict()

    assert payload == {
        "prompt_plan_id": "prompt_plan_001",
        "storyboard_plan_id": "storyboard_plan_001",
        "frame_id": "frame_0001",
        "image_prompt_draft_id": "draft_001",
        "prompt_sections": {
            "subject": "a fox cub looking at lanterns",
            "style": "warm storybook illustration",
            "camera": "medium shot",
        },
        "final_prompt": "a fox cub looking at lanterns, warm storybook illustration, medium shot",
        "source_trace_id": "trace_001",
        "character_ids": ["char_fox"],
        "scene_id": "scene_village",
        "prop_ids": ["prop_lantern"],
        "style_id": "style_storybook",
        "metadata": {},
    }
    assert "panel_prompt" not in payload
    assert "base_prompt" not in payload
    assert "positive_prompt" not in payload
    assert PromptPlan.from_dict(payload) == plan


def test_prompt_projection_is_read_model_for_generation_and_stage2_refs():
    plan = PromptPlan(
        prompt_plan_id="prompt_plan_001",
        storyboard_plan_id="storyboard_plan_001",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_001",
        prompt_sections={"subject": "fox cub", "style": "storybook"},
        final_prompt="fox cub, storybook",
        character_ids=("char_fox",),
        scene_id="scene_village",
        prop_ids=("prop_lantern", "prop_book"),
        style_id="style_storybook",
    )

    projection = PromptProjection.from_prompt_plan(plan)

    assert projection.to_dict() == {
        "prompt_plan_id": "prompt_plan_001",
        "storyboard_plan_id": "storyboard_plan_001",
        "frame_id": "frame_0001",
        "final_prompt": "fox cub, storybook",
        "prompt_sections": {"subject": "fox cub", "style": "storybook"},
        "asset_refs": {
            "character_ids": ["char_fox"],
            "scene_id": "scene_village",
            "prop_ids": ["prop_lantern", "prop_book"],
            "style_id": "style_storybook",
        },
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"prompt_plan_id": "", "final_prompt": "x", "prompt_sections": {"subject": "x"}},
        {"prompt_plan_id": "plan", "final_prompt": "", "prompt_sections": {"subject": "x"}},
        {"prompt_plan_id": "plan", "final_prompt": "x", "prompt_sections": {}},
        {"prompt_plan_id": "plan", "final_prompt": "x", "prompt_sections": {"": "x"}},
        {"prompt_plan_id": "plan", "final_prompt": "x", "prompt_sections": {"subject": ""}},
    ],
)
def test_prompt_plan_rejects_missing_canonical_fields(kwargs):
    base = {
        "storyboard_plan_id": "storyboard_plan_001",
        "frame_id": "frame_0001",
        "image_prompt_draft_id": "draft_001",
    }

    with pytest.raises(ValueError):
        PromptPlan(**base, **kwargs)
