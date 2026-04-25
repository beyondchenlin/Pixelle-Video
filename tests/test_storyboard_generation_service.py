import pytest

from pixelle_video.services.storyboard_generation import StoryboardGenerationService


class SmartFakeLLM:
    def __init__(self, frames=None):
        self.calls = []
        self.frames = frames or [
            {
                "source_text": "开头完整表达。",
                "narration_text": "开头完整表达。",
                "visual_goal": "Introduce the main idea.",
                "prompt_intent": "A calm opening visual.",
                "source_start": 0,
                "source_end": 7,
            },
            {
                "source_text": "结尾完整表达。",
                "narration_text": "结尾完整表达。",
                "visual_goal": "Close the idea.",
                "prompt_intent": "A coherent closing visual.",
                "source_start": 7,
                "source_end": 14,
            },
        ]

    async def __call__(self, *, prompt, response_type, temperature, max_tokens):
        self.calls.append(
            {
                "prompt": prompt,
                "response_type": response_type,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return response_type(frames=self.frames)


class SequencedSmartFakeLLM:
    def __init__(self, frame_batches):
        self.calls = []
        self.frame_batches = list(frame_batches)

    async def __call__(self, *, prompt, response_type, temperature, max_tokens):
        self.calls.append(
            {
                "prompt": prompt,
                "response_type": response_type,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        frames = self.frame_batches.pop(0)
        return response_type(frames=frames)


class FailingThenSmartFakeLLM:
    def __init__(self):
        self.calls = []

    async def __call__(self, *, prompt, response_type, temperature, max_tokens):
        self.calls.append(
            {
                "prompt": prompt,
                "response_type": response_type,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if len(self.calls) == 1:
            raise ValueError("invalid structured output")
        return response_type(frames=SmartFakeLLM().frames)


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


@pytest.mark.asyncio
async def test_smart_auto_uses_llm_to_create_plan_from_whole_source_text():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})
    llm = SmartFakeLLM()

    plan = await service.generate(
        llm_service=llm,
        source_text="开头完整表达。结尾完整表达。",
        storyboard_mode="smart",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert plan.mode.value == "smart"
    assert plan.count_mode.value == "auto"
    assert plan.resolved_scene_count == 2
    assert plan.frames[0].visual_goal == "Introduce the main idea."
    assert plan.frames[1].prompt_intent == "A coherent closing visual."
    assert llm.calls[0]["response_type"].__name__ == "SmartStoryboardPlanResponse"
    assert "开头完整表达。结尾完整表达。" in llm.calls[0]["prompt"]
    assert plan.diagnostics["strategy"] == "smart"


@pytest.mark.asyncio
async def test_smart_backfills_source_ranges_from_exact_source_text_matches():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})
    llm = SmartFakeLLM(
        frames=[
            {
                "source_text": "开头完整表达。",
                "narration_text": "开头完整表达。",
                "visual_goal": "Introduce the main idea.",
                "prompt_intent": "A calm opening visual.",
            },
            {
                "source_text": "结尾完整表达。",
                "narration_text": "结尾完整表达。",
                "visual_goal": "Close the idea.",
                "prompt_intent": "A coherent closing visual.",
            },
        ]
    )

    plan = await service.generate(
        llm_service=llm,
        source_text="开头完整表达。结尾完整表达。",
        storyboard_mode="smart",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert [(frame.source_start, frame.source_end) for frame in plan.frames] == [(0, 7), (7, 14)]
    assert [
        plan.source_text[frame.source_start : frame.source_end]
        for frame in plan.frames
    ] == [frame.source_text for frame in plan.frames]


@pytest.mark.asyncio
async def test_smart_repairs_unlocatable_source_text_once():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})
    llm = SequencedSmartFakeLLM(
        [
            [
                {
                    "source_text": "不存在的片段。",
                    "narration_text": "不存在的片段。",
                    "visual_goal": "Bad segment.",
                    "prompt_intent": "Bad segment.",
                }
            ],
            SmartFakeLLM().frames,
        ]
    )

    plan = await service.generate(
        llm_service=llm,
        source_text="开头完整表达。结尾完整表达。",
        storyboard_mode="smart",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert len(llm.calls) == 2
    assert "Repair the previous storyboard response" in llm.calls[1]["prompt"]
    assert plan.resolved_scene_count == 2


@pytest.mark.asyncio
async def test_smart_repairs_backwards_source_ranges_once():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})
    backwards_frames = [
        {
            "source_text": "结尾完整表达。",
            "narration_text": "结尾完整表达。",
            "visual_goal": "Close the idea.",
            "prompt_intent": "A coherent closing visual.",
        },
        {
            "source_text": "开头完整表达。",
            "narration_text": "开头完整表达。",
            "visual_goal": "Introduce the main idea.",
            "prompt_intent": "A calm opening visual.",
        },
    ]
    llm = SequencedSmartFakeLLM([backwards_frames, SmartFakeLLM().frames])

    plan = await service.generate(
        llm_service=llm,
        source_text="开头完整表达。结尾完整表达。",
        storyboard_mode="smart",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert len(llm.calls) == 2
    assert plan.narration_texts() == ["开头完整表达。", "结尾完整表达。"]


@pytest.mark.asyncio
async def test_smart_rejects_backwards_source_ranges_after_repair():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})
    backwards_frames = [
        {
            "source_text": "结尾完整表达。",
            "narration_text": "结尾完整表达。",
            "visual_goal": "Close the idea.",
            "prompt_intent": "A coherent closing visual.",
        },
        {
            "source_text": "开头完整表达。",
            "narration_text": "开头完整表达。",
            "visual_goal": "Introduce the main idea.",
            "prompt_intent": "A calm opening visual.",
        },
    ]
    llm = SequencedSmartFakeLLM([backwards_frames, backwards_frames])

    with pytest.raises(ValueError, match="smart storyboard frame source ranges must be ordered"):
        await service.generate(
            llm_service=llm,
            source_text="开头完整表达。结尾完整表达。",
            storyboard_mode="smart",
            storyboard_count_mode="auto",
            storyboard_scene_count=None,
        )

    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_smart_repairs_invalid_structured_output_once():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})
    llm = FailingThenSmartFakeLLM()

    plan = await service.generate(
        llm_service=llm,
        source_text="开头完整表达。结尾完整表达。",
        storyboard_mode="smart",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert len(llm.calls) == 2
    assert "Repair the previous storyboard response" in llm.calls[1]["prompt"]
    assert plan.resolved_scene_count == 2


@pytest.mark.asyncio
async def test_smart_repairs_manual_count_mismatch_once():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})
    llm = SequencedSmartFakeLLM(
        [
            [
                {
                    "source_text": "开头完整表达。",
                    "narration_text": "开头完整表达。",
                    "visual_goal": "Introduce the main idea.",
                    "prompt_intent": "A calm opening visual.",
                }
            ],
            SmartFakeLLM().frames,
        ]
    )

    plan = await service.generate(
        llm_service=llm,
        source_text="开头完整表达。结尾完整表达。",
        storyboard_mode="smart",
        storyboard_count_mode="manual",
        storyboard_scene_count=2,
    )

    assert len(llm.calls) == 2
    assert plan.resolved_scene_count == 2


@pytest.mark.asyncio
async def test_smart_rejects_unlocatable_source_text_after_repair():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})
    bad_frame = [
        {
            "source_text": "不存在的片段。",
            "narration_text": "不存在的片段。",
            "visual_goal": "Bad segment.",
            "prompt_intent": "Bad segment.",
        }
    ]
    llm = SequencedSmartFakeLLM([bad_frame, bad_frame])

    with pytest.raises(ValueError, match="smart storyboard frame source_text must be traceable"):
        await service.generate(
            llm_service=llm,
            source_text="开头完整表达。结尾完整表达。",
            storyboard_mode="smart",
            storyboard_count_mode="auto",
            storyboard_scene_count=None,
        )

    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_smart_manual_requires_exact_scene_count():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})

    with pytest.raises(ValueError, match="expected 3 smart storyboard frames"):
        await service.generate(
            llm_service=SmartFakeLLM(),
            source_text="开头完整表达。结尾完整表达。",
            storyboard_mode="smart",
            storyboard_count_mode="manual",
            storyboard_scene_count=3,
        )


@pytest.mark.asyncio
async def test_smart_manual_accepts_exact_scene_count():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})

    plan = await service.generate(
        llm_service=SmartFakeLLM(),
        source_text="开头完整表达。结尾完整表达。",
        storyboard_mode="smart",
        storyboard_count_mode="manual",
        storyboard_scene_count=2,
    )

    assert plan.count_mode.value == "manual"
    assert plan.requested_scene_count == 2
    assert plan.resolved_scene_count == 2


@pytest.mark.asyncio
async def test_smart_requires_llm_service():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})

    with pytest.raises(ValueError, match="smart storyboard mode requires llm_service"):
        await service.generate(
            llm_service=None,
            source_text="开头完整表达。",
            storyboard_mode="smart",
            storyboard_count_mode="auto",
            storyboard_scene_count=None,
        )


@pytest.mark.asyncio
async def test_smart_rejects_unknown_count_mode_before_calling_llm():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})
    llm = SmartFakeLLM()

    with pytest.raises(ValueError, match="unsupported storyboard count mode"):
        await service.generate(
            llm_service=llm,
            source_text="开头完整表达。",
            storyboard_mode="smart",
            storyboard_count_mode="unknown",
            storyboard_scene_count=None,
        )

    assert llm.calls == []


@pytest.mark.asyncio
async def test_smart_manual_scene_count_must_be_within_configured_bounds():
    service = StoryboardGenerationService(config={"min_scene_count": 2, "max_scene_count": 4})

    with pytest.raises(ValueError, match="storyboard_scene_count must be within configured bounds"):
        await service.generate(
            llm_service=SmartFakeLLM(),
            source_text="开头完整表达。结尾完整表达。",
            storyboard_mode="smart",
            storyboard_count_mode="manual",
            storyboard_scene_count=5,
        )


@pytest.mark.asyncio
async def test_smart_auto_rejects_too_few_frames():
    service = StoryboardGenerationService(config={"min_scene_count": 2, "max_scene_count": 10})
    llm = SmartFakeLLM(
        frames=[
            {
                "source_text": "开头完整表达。",
                "narration_text": "开头完整表达。",
                "visual_goal": "Introduce the main idea.",
                "prompt_intent": "A calm opening visual.",
                "source_start": 0,
                "source_end": 7,
            }
        ]
    )

    with pytest.raises(ValueError, match="too few storyboard frames"):
        await service.generate(
            llm_service=llm,
            source_text="开头完整表达。结尾完整表达。",
            storyboard_mode="smart",
            storyboard_count_mode="auto",
            storyboard_scene_count=None,
        )


@pytest.mark.asyncio
async def test_smart_auto_rejects_too_many_frames():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 1})

    with pytest.raises(ValueError, match="too many storyboard frames"):
        await service.generate(
            llm_service=SmartFakeLLM(),
            source_text="开头完整表达。结尾完整表达。",
            storyboard_mode="smart",
            storyboard_count_mode="auto",
            storyboard_scene_count=None,
        )
