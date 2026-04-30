import pytest

from pixelle_video.models.storyboard_plan import ScriptLengthMode
from pixelle_video.services.script_generation import ScriptGenerationService


class ScriptFakeLLM:
    def __init__(self, source_text="完整文案第一句。完整文案第二句。"):
        self.calls = []
        self.source_text = source_text

    async def __call__(self, *, prompt, response_type, temperature, max_tokens):
        self.calls.append(
            {
                "prompt": prompt,
                "response_type": response_type,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return response_type(source_text=self.source_text)


@pytest.mark.asyncio
async def test_script_generation_returns_complete_source_text_from_topic():
    llm = ScriptFakeLLM("  完整文案第一句。完整文案第二句。 ")

    source_text = await ScriptGenerationService().generate(
        llm_service=llm,
        topic="讲一个关于自律的短视频",
        script_length_mode=ScriptLengthMode.AUTO,
        script_target_words=None,
    )

    assert source_text == "完整文案第一句。完整文案第二句。"
    assert len(llm.calls) == 1
    assert "讲一个关于自律的短视频" in llm.calls[0]["prompt"]
    assert "complete source_text" in llm.calls[0]["prompt"]


def test_script_generation_prompt_loads_plain_narration_strategy():
    import json

    from pixelle_video.prompts.script_generation import build_script_generation_prompt

    prompt = build_script_generation_prompt(
        topic="强者思维",
        length_instruction="Write about 200 words.",
    )
    payload = json.loads(prompt)

    assert payload["task"] == "generate_complete_video_script_source_text"
    assert "短视频编导" in payload["script_generation_strategy"]
    assert "第一句话要有冲击力" in payload["script_generation_strategy"]
    assert "然后只输出一段最终可直接用于短视频口播和分镜的完整文案。" in payload["script_generation_strategy"]
    assert "id: default" not in payload["script_generation_strategy"]
    assert "【目标用户】" not in payload["script_generation_strategy"]
    assert "【推荐标题】" not in payload["script_generation_strategy"]
    assert "【完整口播文案】" not in payload["script_generation_strategy"]
    assert "Return JSON only." in payload["requirements"]
    assert payload["output_contract"]["type"] == "json_object"
    assert payload["output_contract"]["must_return_json_only"] is True
    assert payload["output_contract"]["allowed_top_level_keys"] == ["source_text"]
    assert "section headings" in " ".join(payload["output_contract"]["forbidden_output"])
    assert payload["output_schema"] == {
        "source_text": "The complete source_text script for the video.",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_fragment"),
    [
        (ScriptLengthMode.AUTO, "natural length"),
        (ScriptLengthMode.SHORT, "about 120 words"),
        (ScriptLengthMode.MEDIUM, "about 240 words"),
        (ScriptLengthMode.LONG, "about 420 words"),
    ],
)
async def test_script_generation_length_modes_shape_prompt(mode, expected_fragment):
    llm = ScriptFakeLLM()

    await ScriptGenerationService().generate(
        llm_service=llm,
        topic="AI 教育短视频",
        script_length_mode=mode,
        script_target_words=None,
    )

    assert expected_fragment in llm.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_script_generation_custom_word_count_shapes_prompt():
    llm = ScriptFakeLLM()

    await ScriptGenerationService().generate(
        llm_service=llm,
        topic="AI 教育短视频",
        script_length_mode="custom",
        script_target_words=180,
    )

    assert "about 180 words" in llm.calls[0]["prompt"]
    assert llm.calls[0]["max_tokens"] == 1200


@pytest.mark.asyncio
async def test_script_generation_caps_custom_word_count_tokens_to_structured_output_budget():
    llm = ScriptFakeLLM()

    await ScriptGenerationService().generate(
        llm_service=llm,
        topic="Long-form documentary script",
        script_length_mode="custom",
        script_target_words=10000,
    )

    assert llm.calls[0]["max_tokens"] == 32000


@pytest.mark.asyncio
async def test_script_generation_custom_word_count_must_be_positive():
    with pytest.raises(ValueError, match="script_target_words must be a positive integer"):
        await ScriptGenerationService().generate(
            llm_service=ScriptFakeLLM(),
            topic="AI 教育短视频",
            script_length_mode="custom",
            script_target_words=0,
        )


@pytest.mark.asyncio
async def test_script_generation_rejects_empty_structured_output():
    with pytest.raises(ValueError, match="source_text must not be empty"):
        await ScriptGenerationService().generate(
            llm_service=ScriptFakeLLM("   "),
            topic="AI 教育短视频",
            script_length_mode="auto",
            script_target_words=None,
        )


@pytest.mark.asyncio
async def test_script_generation_preserves_plain_text_without_semantic_section_filtering():
    llm = ScriptFakeLLM("【完整口播文案】这个短语本身就在被讨论。")

    source_text = await ScriptGenerationService().generate(
        llm_service=llm,
        topic="讨论文案标签本身",
        script_length_mode="auto",
        script_target_words=None,
    )

    assert source_text == "【完整口播文案】这个短语本身就在被讨论。"
