from pixelle_video.utils.text_splitting import format_caption_text


def test_strip_terminal_preserves_closing_quotes_after_terminal_punctuation():
    assert format_caption_text('"Hello."', punctuation_mode="strip_terminal") == '"Hello"'
    assert (
        format_caption_text(
            "\u201c\u4f60\u597d\u3002\u201d",
            punctuation_mode="strip_terminal",
        )
        == "\u201c\u4f60\u597d\u201d"
    )
    assert (
        format_caption_text(
            "\u4ed6\u8bf4\uff1a\u201c\u597d\u3002\u201d",
            punctuation_mode="strip_terminal",
        )
        == "\u4ed6\u8bf4\uff1a\u201c\u597d\u201d"
    )


def test_strip_terminal_keeps_closing_quotes_without_terminal_punctuation():
    assert (
        format_caption_text(
            "\u201c\u4f60\u597d\u201d",
            punctuation_mode="strip_terminal",
        )
        == "\u201c\u4f60\u597d\u201d"
    )
