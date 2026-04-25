from __future__ import annotations

import json


def build_smart_storyboard_prompt(
    *,
    source_text: str,
    count_mode: str,
    requested_scene_count: int | None,
    min_scene_count: int,
    max_scene_count: int,
) -> str:
    count_instruction = (
        f"Create exactly {requested_scene_count} storyboard frames."
        if count_mode == "manual"
        else f"Choose the best storyboard frame count between {min_scene_count} and {max_scene_count}."
    )
    payload = {
        "task": "create_storyboard_plan_from_complete_source_text",
        "source_text": source_text,
        "count_instruction": count_instruction,
        "requirements": [
            "Understand the complete source_text before creating frames.",
            "The returned frames must cover the entire source_text in source order.",
            "Do not omit meaningful source_text; only whitespace-only gaps between frames are allowed.",
            "Frames may merge adjacent ideas when one sentence is too small for a visual scene.",
            "Frames may split a long sentence when it naturally contains multiple visual beats.",
            "Maintain continuity of style, subjects, and visual logic across all frames.",
            "Do not generate final image prompts.",
            "Return JSON only.",
        ],
        "frame_schema": {
            "source_text": "Text covered by this frame.",
            "narration_text": "Voiceover text for this frame.",
            "visual_goal": "What this frame should communicate visually.",
            "prompt_intent": "Guidance for later image prompt composition.",
            "source_start": "Optional Python string start index into source_text.",
            "source_end": "Optional Python string end index into source_text.",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
