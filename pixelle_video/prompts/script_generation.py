from __future__ import annotations

import json


def build_script_generation_prompt(
    *,
    topic: str,
    length_instruction: str,
) -> str:
    payload = {
        "task": "generate_complete_video_script_source_text",
        "topic": topic,
        "length_instruction": length_instruction,
        "requirements": [
            "Generate one complete source_text for the whole video script.",
            "The source_text must be coherent as a complete script before storyboard splitting.",
            "Do not split the script into storyboard frames.",
            "Do not generate image prompts.",
            "Return JSON only.",
        ],
        "output_schema": {
            "source_text": "The complete source_text script for the video.",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = ["build_script_generation_prompt"]
