import pytest

from pixelle_video.utils.content_generators import split_narration_script


@pytest.mark.asyncio
async def test_split_narration_script_sentence_mode_only_uses_sentence_end_punctuation():
    script = "第一句，第二句；第三句：继续。第四句？"

    narrations = await split_narration_script(script, split_mode="sentence")

    assert narrations == ["第一句，第二句；第三句：继续。", "第四句？"]


@pytest.mark.asyncio
async def test_split_narration_script_punctuation_mode_splits_on_common_punctuation():
    script = "第一句，第二句；第三句：继续。第四句？"

    narrations = await split_narration_script(script, split_mode="punctuation")

    assert narrations == ["第一句，", "第二句；", "第三句：", "继续。", "第四句？"]
