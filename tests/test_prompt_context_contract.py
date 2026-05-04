from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.prompts.image_generation import build_image_prompt_prompt
from pixelle_video.prompts.video_generation import build_video_prompt_prompt


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


def test_image_prompt_template_can_request_chinese_output():
    prompt = build_image_prompt_prompt(
        narrations=["Small habits compound."],
        min_words=30,
        max_words=60,
        prompt_language="zh_CN",
    )

    assert "必须使用中文" in prompt
    assert "Image prompts must use English" not in prompt


def test_prompt_context_payload_can_carry_ip_adaptation_package():
    envelope = PromptContextEnvelope(
        plan_context={"plan_source_text": "从长乐门出发。"},
        frame_contexts=[
            {
                "frame_source_text": "从长乐门出发。",
                "ip_adaptation": {
                    "ip_presence_type": "scene_integrated",
                    "presence_mode": "support",
                },
                "ip_presence_options": ["scene_integrated", "low_intrusion", "absent"],
                "style_context": {"style_kind": "visual_only"},
            }
        ],
    )

    payload = envelope.to_prompt_payload()

    assert payload["prompt_contexts"][0]["ip_adaptation"]["ip_presence_type"] == "scene_integrated"
    assert "low_intrusion" in payload["prompt_contexts"][0]["ip_presence_options"]
    assert payload["prompt_contexts"][0]["style_context"]["style_kind"] == "visual_only"


def test_image_prompt_template_explains_ip_adaptation_text_plan_contract():
    prompt = build_image_prompt_prompt(
        narrations=["Start from Changle Gate."],
        min_words=30,
        max_words=60,
        prompt_contexts=PromptContextEnvelope(
            plan_context={"plan_source_text": "Start from Changle Gate."},
            frame_contexts=[
                {
                    "frame_source_text": "Start from Changle Gate.",
                    "ip_adaptation": {
                        "ip_presence_type": "scene_integrated",
                        "image_text_plan": {
                            "summary_text": "Start from Changle Gate",
                            "scene_text": ["Changle Gate"],
                            "visible_text_whitelist": [
                                "Start from Changle Gate",
                                "Changle Gate",
                            ],
                        },
                    },
                }
            ],
        ),
    )

    assert "ip_adaptation" in prompt
    assert "summary_text" in prompt
    assert "scene_text" in prompt
    assert "visible_text_whitelist" in prompt
    assert "do not output field names" in prompt.lower()
