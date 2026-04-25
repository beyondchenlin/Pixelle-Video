import pytest

from pixelle_video.services.storyboard_generation import StoryboardGenerationService


@pytest.mark.asyncio
async def test_punctuation_mode_splits_on_all_unicode_punctuation():
    service = StoryboardGenerationService(config={"max_scene_count": 10})

    plan = await service.generate(
        llm_service=None,
        source_text="第一段，继续；结束。Next: done!",
        storyboard_mode="punctuation",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert [frame.narration_text for frame in plan.frames] == [
        "第一段，",
        "继续；",
        "结束。",
        "Next:",
        "done!",
    ]
    assert plan.mode.value == "punctuation"
    assert plan.count_mode.value == "auto"
    assert plan.diagnostics["strategy"] == "punctuation"
    assert [
        plan.source_text[frame.source_start : frame.source_end]
        for frame in plan.frames
    ] == [frame.source_text for frame in plan.frames]


@pytest.mark.asyncio
async def test_sentence_mode_splits_only_sentence_boundaries():
    service = StoryboardGenerationService(config={"max_scene_count": 10})

    plan = await service.generate(
        llm_service=None,
        source_text="第一段，继续；结束。Next: not yet? Done!",
        storyboard_mode="sentence",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert [frame.narration_text for frame in plan.frames] == [
        "第一段，继续；结束。",
        "Next: not yet?",
        "Done!",
    ]
    assert plan.mode.value == "sentence"
    assert plan.diagnostics["split_count"] == 3


@pytest.mark.asyncio
async def test_sentence_mode_keeps_closing_punctuation_with_sentence():
    service = StoryboardGenerationService(config={"max_scene_count": 10})

    plan = await service.generate(
        llm_service=None,
        source_text="他说：“好。”然后继续。Really?) Next.",
        storyboard_mode="sentence",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert [frame.narration_text for frame in plan.frames] == [
        "他说：“好。”",
        "然后继续。",
        "Really?)",
        "Next.",
    ]


@pytest.mark.asyncio
async def test_sentence_mode_keeps_continuous_terminators_together():
    service = StoryboardGenerationService(config={"max_scene_count": 10})

    plan = await service.generate(
        llm_service=None,
        source_text="真的吗？！Yes!! Next",
        storyboard_mode="sentence",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert [frame.narration_text for frame in plan.frames] == [
        "真的吗？！",
        "Yes!!",
        "Next",
    ]


@pytest.mark.asyncio
async def test_storyboard_generation_normalizes_whitespace_and_preserves_ranges():
    service = StoryboardGenerationService(config={"max_scene_count": 10})

    plan = await service.generate(
        llm_service=None,
        source_text="  第一段。\n\n第二段  继续。  ",
        storyboard_mode="sentence",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert plan.source_text == "第一段。 第二段 继续。"
    assert [frame.narration_text for frame in plan.frames] == ["第一段。", "第二段 继续。"]
    assert [
        plan.source_text[frame.source_start : frame.source_end]
        for frame in plan.frames
    ] == [frame.source_text for frame in plan.frames]


@pytest.mark.asyncio
async def test_punctuation_mode_normalizes_whitespace_and_preserves_ranges():
    service = StoryboardGenerationService(config={"max_scene_count": 10})

    plan = await service.generate(
        llm_service=None,
        source_text="  第一段，\n\n第二段:  继续！  ",
        storyboard_mode="punctuation",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert plan.source_text == "第一段， 第二段: 继续！"
    assert [frame.narration_text for frame in plan.frames] == [
        "第一段，",
        "第二段:",
        "继续！",
    ]
    assert [
        plan.source_text[frame.source_start : frame.source_end]
        for frame in plan.frames
    ] == [frame.source_text for frame in plan.frames]


@pytest.mark.asyncio
async def test_deterministic_strategy_rejects_over_max_scene_count():
    service = StoryboardGenerationService(config={"max_scene_count": 2})

    with pytest.raises(ValueError, match="too many storyboard frames"):
        await service.generate(
            llm_service=None,
            source_text="一。二。三。",
            storyboard_mode="sentence",
            storyboard_count_mode="auto",
            storyboard_scene_count=None,
        )


@pytest.mark.asyncio
async def test_deterministic_strategy_falls_back_to_one_frame_when_no_text_segments():
    service = StoryboardGenerationService(config={"max_scene_count": 10})

    plan = await service.generate(
        llm_service=None,
        source_text="！！！",
        storyboard_mode="sentence",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert [frame.narration_text for frame in plan.frames] == ["！！！"]
    assert plan.resolved_scene_count == 1


@pytest.mark.asyncio
async def test_deterministic_strategy_rejects_empty_source_text():
    service = StoryboardGenerationService(config={"max_scene_count": 10})

    with pytest.raises(ValueError, match="source_text must not be empty"):
        await service.generate(
            llm_service=None,
            source_text="   ",
            storyboard_mode="sentence",
            storyboard_count_mode="auto",
            storyboard_scene_count=None,
        )


@pytest.mark.asyncio
async def test_storyboard_generation_rejects_unknown_mode():
    service = StoryboardGenerationService(config={"max_scene_count": 10})

    with pytest.raises(ValueError, match="unsupported storyboard mode"):
        await service.generate(
            llm_service=None,
            source_text="一句。",
            storyboard_mode="unknown",
            storyboard_count_mode="auto",
            storyboard_scene_count=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("max_scene_count", [0, "30", True, None])
@pytest.mark.asyncio
async def test_storyboard_generation_rejects_invalid_max_scene_count_config(max_scene_count):
    service = StoryboardGenerationService(config={"max_scene_count": max_scene_count})

    with pytest.raises(ValueError, match="max_scene_count must be a positive integer"):
        await service.generate(
            llm_service=None,
            source_text="一句。",
            storyboard_mode="sentence",
            storyboard_count_mode="auto",
            storyboard_scene_count=None,
        )


@pytest.mark.asyncio
async def test_deterministic_strategy_rejects_manual_count_mode():
    service = StoryboardGenerationService(config={"max_scene_count": 10})

    with pytest.raises(ValueError, match="manual count mode is only valid for smart mode"):
        await service.generate(
            llm_service=None,
            source_text="一句。",
            storyboard_mode="sentence",
            storyboard_count_mode="manual",
            storyboard_scene_count=None,
        )


@pytest.mark.asyncio
async def test_deterministic_strategy_rejects_manual_scene_count():
    service = StoryboardGenerationService(config={"max_scene_count": 10})

    with pytest.raises(ValueError, match="requested_scene_count is only valid for smart manual mode"):
        await service.generate(
            llm_service=None,
            source_text="一句。",
            storyboard_mode="sentence",
            storyboard_count_mode="auto",
            storyboard_scene_count=1,
        )
