from pixelle_video.prompts.content_narration import build_content_narration_prompt
from pixelle_video.prompts.topic_narration import build_topic_narration_prompt


def test_topic_narration_prompt_preserves_natural_punctuation_by_default():
    prompt = build_topic_narration_prompt(
        topic="如何学习法语",
        n_storyboard=5,
        min_words=5,
        max_words=20,
    )

    assert "生成文稿时保留自然标点。" in prompt
    assert "Do not use punctuation at the end" not in prompt
    assert "不要为了字幕展示去掉标点" not in prompt


def test_topic_narration_prompt_can_disable_punctuation_hint():
    prompt = build_topic_narration_prompt(
        topic="如何学习法语",
        n_storyboard=5,
        min_words=5,
        max_words=20,
        preserve_natural_punctuation=False,
    )

    assert "生成文稿时保留自然标点。" not in prompt
    assert "Do not use punctuation at the end" not in prompt


def test_content_narration_prompt_preserves_natural_punctuation_by_default():
    prompt = build_content_narration_prompt(
        content="一段原始内容",
        n_storyboard=5,
        min_words=5,
        max_words=20,
    )

    assert "生成文稿时保留自然标点。" in prompt
    assert "Do not use punctuation at the end" not in prompt
