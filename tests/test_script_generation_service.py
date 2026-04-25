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
    llm = ScriptFakeLLM("  完整文案第一句。完整文案第二句。  ")

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
