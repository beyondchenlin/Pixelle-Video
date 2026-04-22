import pytest

from pixelle_video.utils.content_generators import split_narration_script
from pixelle_video.utils.text_splitting import (
    split_text_into_sentences,
    split_text_into_subtitle_phrases,
    split_text_into_tts_phrases,
)


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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("No.2 item", ["No.2 item"]),
        ("U.S.A.Test", ["U.S.A.Test"]),
    ],
)
def test_split_text_into_sentences_keeps_common_abbreviation_patterns_together(text, expected):
    assert split_text_into_sentences(text) == expected


def test_split_text_into_sentences_keeps_ellipsis_inside_the_same_sentence():
    text = "Wait... really."

    assert split_text_into_sentences(text) == ["Wait... really."]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Wait... really?", ["Wait...", "really?"]),
        ("\u7b49\u4e00\u7b49\u2026\u2026\u518d\u51b3\u5b9a\u3002", ["\u7b49\u4e00\u7b49\u2026\u2026", "\u518d\u51b3\u5b9a\u3002"]),
        ("Pause\u2014then act.", ["Pause\u2014", "then act."]),
    ],
)
def test_split_text_into_subtitle_phrases_splits_on_expression_pauses(text, expected):
    assert split_text_into_subtitle_phrases(text) == expected


def test_split_text_into_tts_phrases_splits_mixed_script_clause_pauses():
    text = "先学会呼吸控制, then float in water, 保持身体平直, keep your kick relaxed, 最后再稳定划水"

    assert split_text_into_tts_phrases(text) == [
        "先学会呼吸控制,",
        "then float in water,",
        "保持身体平直,",
        "keep your kick relaxed,",
        "最后再稳定划水",
    ]
