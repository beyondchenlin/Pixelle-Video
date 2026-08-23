import asyncio

import pytest

from pixelle_video.models.llm_interaction_trace import LLMTraceRecordingError
from pixelle_video.models.llm_response import LLMResponseContractError
from pixelle_video.prompts.image_generation import build_image_prompt_prompt
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
async def test_generate_title_auto_respects_custom_limit_and_dynamic_budget():
    calls = []

    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            calls.append(kwargs)
            return "Short"

    title = await content_generators.generate_title(
        FakeLLM(),
        "abcdefghij",
        strategy="auto",
        max_length=5,
    )

    assert title == "Short"
    assert calls[0]["max_tokens"] == 64
    assert calls[0]["temperature"] == 0.4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "max_length", "expected"),
    [
        ("👩‍💻学习日记", 1, "👩‍💻"),
        ("🇨🇳🇺🇸新闻", 2, "🇨🇳🇺🇸"),
        ("Cafe\u0301 journal", 4, "Café"),
        ("क्षज्ञान", 1, "क्ष"),
    ],
)
async def test_generate_title_direct_truncates_user_perceived_characters(
    content,
    max_length,
    expected,
):
    title = await content_generators.generate_title(
        object(),
        content,
        strategy="direct",
        max_length=max_length,
    )

    assert title == expected


@pytest.mark.asyncio
async def test_generate_title_normalizes_provider_wrappers_and_unicode_punctuation():
    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            return "```text\n视频标题：《高效学习！》\n额外解释\n```"

    title = await content_generators.generate_title(
        FakeLLM(),
        "一篇关于高效学习方法的长文章",
        strategy="llm",
        max_length=15,
    )

    assert title == "高效学习"


@pytest.mark.asyncio
async def test_generate_title_accepts_label_on_line_before_title():
    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            return "Title:\nA Maintained Provider Boundary"

    title = await content_generators.generate_title(
        FakeLLM(),
        "Long source content that requires a generated title",
        strategy="llm",
        max_length=40,
    )

    assert title == "A Maintained Provider Boundary"


@pytest.mark.asyncio
async def test_generate_title_uses_observable_fallback_for_invalid_provider_response():
    observed = []

    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            raise LLMResponseContractError(
                "provider returned no choices",
                reason="choices_empty",
            )

    title = await content_generators.generate_title(
        FakeLLM(),
        "Deterministic source title with details",
        strategy="llm",
        max_length=13,
        stage_callback=observed.append,
    )

    assert title == "Deterministic"
    assert observed[-1]["event"] == "end"
    assert observed[-1]["strategy"] == "llm_fallback"
    assert observed[-1]["fallback_reason"] == "LLMResponseContractError"


@pytest.mark.asyncio
async def test_generate_title_never_falls_back_when_mandatory_trace_fails():
    observed = []

    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            raise LLMTraceRecordingError("trace unavailable")

    with pytest.raises(LLMTraceRecordingError):
        await content_generators.generate_title(
            FakeLLM(),
            "A long source title requiring generation",
            strategy="llm",
            stage_callback=observed.append,
        )

    assert observed[-1]["event"] == "fail"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"content": ""},
        {"content": "topic", "strategy": "unknown"},
        {"content": "topic", "max_length": 0},
        {"content": "topic", "max_length": True},
    ],
)
async def test_generate_title_rejects_invalid_contract(kwargs):
    with pytest.raises(ValueError):
        await content_generators.generate_title(object(), **kwargs)


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
async def test_visual_anchor_preparation_uses_one_prompt_call_and_no_planning_calls(
    monkeypatch,
):
    calls = []

    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            calls.append(prompt)
            return content_generators.ImagePromptBatchResponse(
                image_prompts=["prompt one", "prompt two"]
            )

    async def forbidden_planning_call(*_args, **_kwargs):
        raise AssertionError("single-pass visual anchor must not call a planner model")

    monkeypatch.setattr(
        content_generators.ContentWorldPlanner,
        "plan",
        forbidden_planning_call,
    )
    monkeypatch.setattr(
        content_generators,
        "plan_storyboard_batch",
        forbidden_planning_call,
    )
    monkeypatch.setattr(
        content_generators,
        "estimate_input_tokens",
        lambda _prompt: 100_000,
    )

    result = await content_generators.generate_styled_image_prompt_batch(
        FakeLLM(),
        narrations=["scene one", "scene two"],
        image_config={},
        batch_size=2,
        max_concurrency=1,
        max_retries=1,
        generation_world_hint="restrained historical explainer",
        shot_preset_id="documentary",
        visual_anchor_preparation_enabled=True,
        literal_style_resolution=True,
    )

    assert result.prompts[0].startswith("prompt one")
    assert result.prompts[1].startswith("prompt two")
    assert len(calls) == 1
    assert "restrained historical explainer" in calls[0]


def test_image_prompt_template_preserves_json_contract_and_explains_ip_scene_description():
    prompt = build_image_prompt_prompt(
        narrations=["Start from Changle Gate."],
        min_words=30,
        max_words=60,
        prompt_contexts=[
            {
                "frame_source_text": "Start from Changle Gate.",
                "ip_scene_description": "white rabbit standing by the gate",
            }
        ],
    )

    assert '"image_prompts"' in prompt
    assert "Only output JSON" in prompt
    assert "ip_scene_description" in prompt
    assert "list[str]" not in prompt
    assert "weave it into the scene" in prompt
    assert "Do not invent or insert a recurring identity" in prompt


def test_image_prompt_template_carries_ip_scene_description_and_style_context():
    prompt = build_image_prompt_prompt(
        narrations=["从长乐门出发。"],
        min_words=30,
        max_words=60,
        prompt_contexts=[
            {
                "frame_source_text": "从长乐门出发。",
                "ip_scene_description": "白色卡通兔子站在古城门前",
                "style_context": {"style_kind": "visual_only"},
            }
        ],
        prompt_language="zh_CN",
    )

    assert "ip_scene_description" in prompt
    assert "style_context" in prompt
    assert "weave it into the scene" in prompt
    assert "overlay" in prompt.lower()


@pytest.mark.asyncio
async def test_generate_image_prompts_can_request_chinese_output():
    captured_prompt: list[str] = []

    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            captured_prompt.append(prompt)
            return content_generators.ImagePromptBatchResponse(image_prompts=["中文提示词"])

    prompts = await content_generators.generate_image_prompts(
        FakeLLM(),
        narrations=["small habits compound"],
        batch_size=10,
        prompt_language="zh_CN",
    )

    assert "必须使用中文" in captured_prompt[0]
    assert prompts == ["中文提示词"]


@pytest.mark.asyncio
async def test_generate_image_prompts_runs_batches_concurrently_and_preserves_order():
    class FakeLLM:
        def __init__(self):
            self._lock = asyncio.Lock()
            self._next_call = 0
            self._active_calls = 0
            self.max_active_calls = 0
            self.outputs = [
                ["prompt 1", "prompt 2"],
                ["prompt 3", "prompt 4"],
                ["prompt 5"],
            ]
            self.delays = [0.04, 0.01, 0.0]

        async def __call__(self, prompt, **kwargs):
            async with self._lock:
                call_index = self._next_call
                self._next_call += 1
                self._active_calls += 1
                self.max_active_calls = max(self.max_active_calls, self._active_calls)

            try:
                await asyncio.sleep(self.delays[call_index])
                return content_generators.ImagePromptBatchResponse(
                    image_prompts=self.outputs[call_index]
                )
            finally:
                async with self._lock:
                    self._active_calls -= 1

    llm = FakeLLM()

    prompts = await content_generators.generate_image_prompts(
        llm,
        narrations=["scene 1", "scene 2", "scene 3", "scene 4", "scene 5"],
        batch_size=2,
        max_concurrency=2,
    )

    assert prompts == ["prompt 1", "prompt 2", "prompt 3", "prompt 4", "prompt 5"]
    assert llm.max_active_calls == 2


@pytest.mark.asyncio
async def test_generate_image_prompts_failure_event_reports_retry_count_from_failed_batch():
    observed = []

    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            if "scene 1" in prompt:
                return content_generators.ImagePromptBatchResponse(
                    image_prompts=["wrong prompt count"]
                )
            return content_generators.ImagePromptBatchResponse(
                image_prompts=["prompt"] * prompt.count("scene ")
            )

    with pytest.raises(ValueError, match="prompt count mismatch"):
        await content_generators.generate_image_prompts(
            FakeLLM(),
            narrations=["scene 1", "scene 2", "scene 3", "scene 4", "scene 5"],
            batch_size=2,
            max_concurrency=1,
            max_retries=3,
            stage_callback=observed.append,
        )

    fail_event = next(
        item
        for item in observed
        if item["stage"] == "image_prompt_batch" and item["event"] == "fail"
    )
    assert fail_event["retry_count"] == 2
    assert fail_event["batch_total"] == 3


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


@pytest.mark.asyncio
async def test_generate_video_prompts_runs_batches_concurrently_and_preserves_order():
    class FakeLLM:
        def __init__(self):
            self._lock = asyncio.Lock()
            self._next_call = 0
            self._active_calls = 0
            self.max_active_calls = 0
            self.outputs = [
                ["video prompt 1", "video prompt 2"],
                ["video prompt 3", "video prompt 4"],
            ]
            self.delays = [0.04, 0.01]

        async def __call__(self, prompt, **kwargs):
            async with self._lock:
                call_index = self._next_call
                self._next_call += 1
                self._active_calls += 1
                self.max_active_calls = max(self.max_active_calls, self._active_calls)

            try:
                await asyncio.sleep(self.delays[call_index])
                return content_generators.VideoPromptBatchResponse(
                    video_prompts=self.outputs[call_index]
                )
            finally:
                async with self._lock:
                    self._active_calls -= 1

    llm = FakeLLM()

    prompts = await content_generators.generate_video_prompts(
        llm,
        narrations=["scene 1", "scene 2", "scene 3", "scene 4"],
        batch_size=2,
        max_concurrency=2,
    )

    assert prompts == ["video prompt 1", "video prompt 2", "video prompt 3", "video prompt 4"]
    assert llm.max_active_calls == 2
