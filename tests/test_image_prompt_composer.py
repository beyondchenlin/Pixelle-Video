import pytest

from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.services.image_prompt_composer import ImagePromptComposer


def _plan():
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text="第一句。第二句。",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="第一句。",
                narration_text="第一句。",
                visual_goal="Show idea one.",
                prompt_intent="Visual metaphor one.",
                source_start=0,
                source_end=4,
            ),
            StoryboardPlanFrame(
                index=2,
                source_text="第二句。",
                narration_text="第二句。",
                visual_goal="Show idea two.",
                prompt_intent="Visual metaphor two.",
                source_start=4,
                source_end=8,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_composer_generates_one_prompt_per_plan_frame(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured.update(kwargs)
        return type(
            "Batch",
            (),
            {
                "prompts": ["prompt one", "prompt two"],
                "resolved_style": None,
                "negative_prompt": None,
                "planning_snapshot": {"frames": [{"scene_id": "1"}, {"scene_id": "2"}]},
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    result = await ImagePromptComposer().compose(
        llm_service=object(),
        storyboard_plan=_plan(),
        image_config={},
        prompt_prefix="clean style",
    )

    assert captured["narrations"] == ["第一句。", "第二句。"]
    assert captured["prompt_contexts"][0]["visual_goal"] == "Show idea one."
    assert captured["prompt_contexts"][1]["prompt_intent"] == "Visual metaphor two."
    assert result.prompts == ["prompt one", "prompt two"]
    assert result.planning_snapshot["frames"] == [{"scene_id": "1"}, {"scene_id": "2"}]
    assert result.planning_snapshot["storyboard_generation"]["resolved_scene_count"] == 2


@pytest.mark.asyncio
async def test_composer_rejects_prompt_count_mismatch(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        return type(
            "Batch",
            (),
            {
                "prompts": ["prompt one"],
                "resolved_style": None,
                "negative_prompt": None,
                "planning_snapshot": None,
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    with pytest.raises(ValueError, match="image prompt count must match storyboard frame count"):
        await ImagePromptComposer().compose(
            llm_service=object(),
            storyboard_plan=_plan(),
            image_config={},
        )
