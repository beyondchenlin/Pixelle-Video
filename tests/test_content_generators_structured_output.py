import pytest

from pixelle_video.utils import content_generators


@pytest.mark.asyncio
async def test_generate_title_reports_stage_callback():
    observed = []

    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            return "Demo Title"

    title = await content_generators.generate_title(
        FakeLLM(),
        "demo topic with enough words",
        strategy="llm",
        stage_callback=observed.append,
    )

    assert title == "Demo Title"
    assert [item["event"] for item in observed] == ["start", "end"]
    assert observed[0]["stage"] == "title_generation"
    assert observed[1]["latency_ms"] >= 0
    assert observed[1]["llm_call_count"] == 1


@pytest.mark.asyncio
async def test_generate_image_prompts_stage_callback_reports_actual_llm_call_count_for_batched_stage():
    observed = []

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        async def __call__(self, prompt, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return content_generators.ImagePromptBatchResponse(image_prompts=["prompt"] * 10)
            return content_generators.ImagePromptBatchResponse(image_prompts=["prompt"])

    prompts = await content_generators.generate_image_prompts(
        FakeLLM(),
        narrations=["scene"] * 11,
        batch_size=10,
        stage_callback=observed.append,
    )

    assert len(prompts) == 11
    end_event = next(
        item
        for item in observed
        if item["stage"] == "image_prompt_batch" and item["event"] == "end"
    )
    assert end_event["llm_call_count"] == 2
    assert end_event["batch_total"] == 2
    assert end_event["retry_count"] == 0
    assert end_event["narration_count"] == 11


@pytest.mark.asyncio
async def test_generate_narrations_from_topic_uses_structured_output():
    captured_response_type: list[object] = []

    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            captured_response_type.append(kwargs.get("response_type"))
            return content_generators.NarrationBatchResponse(
                narrations=["第一段", "第二段"]
            )

    narrations = await content_generators.generate_narrations_from_topic(
        FakeLLM(),
        topic="测试主题",
        n_scenes=2,
    )

    assert captured_response_type == [content_generators.NarrationBatchResponse]
    assert narrations == ["第一段", "第二段"]


@pytest.mark.asyncio
async def test_generate_narrations_from_content_uses_structured_output():
    captured_response_type: list[object] = []

    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            captured_response_type.append(kwargs.get("response_type"))
            return content_generators.NarrationBatchResponse(
                narrations=["第一段", "第二段", "第三段"]
            )

    narrations = await content_generators.generate_narrations_from_content(
        FakeLLM(),
        content="测试内容",
        n_scenes=3,
    )

    assert captured_response_type == [content_generators.NarrationBatchResponse]
    assert narrations == ["第一段", "第二段", "第三段"]


@pytest.mark.asyncio
async def test_generate_image_prompts_uses_structured_output():
    captured_response_type: list[object] = []

    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            captured_response_type.append(kwargs.get("response_type"))
            return content_generators.ImagePromptBatchResponse(
                image_prompts=["prompt one", "prompt two"]
            )

    prompts = await content_generators.generate_image_prompts(
        FakeLLM(),
        narrations=["场景一", "场景二"],
        batch_size=10,
    )

    assert captured_response_type == [content_generators.ImagePromptBatchResponse]
    assert prompts == ["prompt one", "prompt two"]


@pytest.mark.asyncio
async def test_generate_video_prompts_uses_structured_output():
    captured_response_type: list[object] = []

    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            captured_response_type.append(kwargs.get("response_type"))
            return content_generators.VideoPromptBatchResponse(
                video_prompts=["video prompt one", "video prompt two"]
            )

    prompts = await content_generators.generate_video_prompts(
        FakeLLM(),
        narrations=["场景一", "场景二"],
        batch_size=10,
    )

    assert captured_response_type == [content_generators.VideoPromptBatchResponse]
    assert prompts == ["video prompt one", "video prompt two"]
