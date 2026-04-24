from pixelle_video.utils.text_splitting import join_tts_sentence_units


def test_direct_joiner_removes_space_after_closing_quote():
    joined = join_tts_sentence_units(
        [
            "\u4ed6\u8bf4\uff1a\u201c\u597d\u3002\u201d",
            "\u7136\u540e\u8d70\u4e86",
        ],
        joiner_mode="direct",
    )

    assert joined == "\u4ed6\u8bf4\uff1a\u201c\u597d\u3002\u201d\u7136\u540e\u8d70\u4e86\u3002"
