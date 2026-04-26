from pixelle_video.prompts.image_generation import build_image_prompt_prompt
from pixelle_video.prompts.video_generation import build_video_prompt_prompt
from pixelle_video.models.prompt_context import PromptContextEnvelope


def _prompt_contexts():
    return PromptContextEnvelope(
        plan_context={
            "plan_source_text": "Full script. It has two connected ideas.",
        },
        frame_contexts=[
            {
                "frame_source_text": "Full script.",
                "visual_goal": "Show the connected idea.",
                "prompt_intent": "Keep continuity with the full script.",
            }
        ],
    )


def _legacy_prompt_contexts():
    return [
        {
            "plan_source_text": "Full script. It has two connected ideas.",
            "frame_source_text": "Full script.",
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
    assert prompt.count("Full script. It has two connected ideas.") == 1
    assert '"frame_source_texts"' in prompt
    assert '"narrations"' not in prompt
    assert "narration" not in prompt.lower()


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
    assert prompt.count("Full script. It has two connected ideas.") == 1
    assert '"frame_source_texts"' in prompt
    assert '"narrations"' not in prompt
    assert "narration" not in prompt.lower()


def test_legacy_prompt_contexts_are_compacted_into_plan_context():
    prompt = build_image_prompt_prompt(
        narrations=["Full script."],
        min_words=30,
        max_words=60,
        prompt_contexts=_legacy_prompt_contexts(),
    )

    assert "plan_context" in prompt
    assert prompt.count("Full script. It has two connected ideas.") == 1
