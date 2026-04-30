from pixelle_video.prompts.video_generation import build_video_prompt_prompt


def test_build_video_prompt_prompt_uses_requested_word_range():
    prompt = build_video_prompt_prompt(
        narrations=["a dog runs through a cartoon park"],
        min_words=12,
        max_words=34,
        style_profile=None,
        prompt_language="en_US",
    )

    assert "recommended 12-34 English words" in prompt
    assert "recommended 50-100 English words" not in prompt


def test_build_video_prompt_prompt_can_request_chinese_output():
    prompt = build_video_prompt_prompt(
        narrations=["Small habits compound."],
        min_words=30,
        max_words=60,
        prompt_language="zh_CN",
    )

    assert "Video prompts must use Chinese" in prompt
    assert "Video prompts must use English" not in prompt
