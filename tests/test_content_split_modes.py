import pytest

from pixelle_video.utils.content_generators import split_narration_script
from pixelle_video.utils.text_splitting import split_text_into_sentences


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


@pytest.mark.asyncio
async def test_split_narration_script_punctuation_mode_splits_on_all_unicode_punctuation():
    script = "Alpha-Beta/Next，中文；Done。"

    narrations = await split_narration_script(script, split_mode="punctuation")

    assert narrations == ["Alpha-", "Beta/", "Next，", "中文；", "Done。"]


def test_split_text_into_sentences_handles_decimals_quotes_and_cjk():
    text = 'Version 2.1 is out. He said, "Go." Then left. 第一段。第二段！第三段？'

    assert split_text_into_sentences(text) == [
        'Version 2.1 is out.',
        'He said, "Go."',
        'Then left.',
        '第一段。',
        '第二段！',
        '第三段？',
    ]


@pytest.mark.asyncio
async def test_split_narration_script_sentence_mode_reuses_shared_sentence_splitter():
    script = 'Version 2.1 is out. He said, "Go." Then left. 第一段。第二段！第三段？'

    narrations = await split_narration_script(script, split_mode="sentence")

    assert narrations == [
        'Version 2.1 is out.',
        'He said, "Go."',
        'Then left.',
        '第一段。',
        '第二段！',
        '第三段？',
    ]


def test_split_text_into_sentences_handles_no_space_english_boundary():
    text = "Wait!Another sentence."

    assert split_text_into_sentences(text) == [
        "Wait!",
        "Another sentence.",
    ]
