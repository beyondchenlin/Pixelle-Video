from pixelle_video.prompts.image_generation import build_image_prompt_prompt
from pixelle_video.prompts.video_generation import build_video_prompt_prompt


def _prompt_contexts():
    return [
        {
            "plan_source_text": "Full script. It has two connected ideas.",
            "frame_source_text": "Full script.",
            "narration_text": "Full script.",
            "visual_goal": "Show the connected idea.",
            "prompt_intent": "Keep continuity with the full script.",
        }
    ]


def test_image_prompt_template_requires_frame_aware_context():
    prompt = build_image_prompt_prompt(
        narrations=["Full script."],
        min_words=30,
        max_words=60,
        prompt_contexts=_prompt_contexts(),
    )

    assert "plan_source_text" in prompt
    assert "frame_source_text" in prompt
    assert "visual_goal" in prompt
    assert "prompt_intent" in prompt
    assert "Use prompt_contexts as the primary source" in prompt


def test_video_prompt_template_requires_frame_aware_context():
    prompt = build_video_prompt_prompt(
        narrations=["Full script."],
        min_words=30,
        max_words=60,
        prompt_contexts=_prompt_contexts(),
    )

    assert "plan_source_text" in prompt
    assert "frame_source_text" in prompt
    assert "visual_goal" in prompt
    assert "prompt_intent" in prompt
    assert "Use prompt_contexts as the primary source" in prompt
