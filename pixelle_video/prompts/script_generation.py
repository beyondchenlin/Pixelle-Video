from __future__ import annotations

import json

from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template

DEFAULT_SCRIPT_TEMPLATE_ID = "default"


def render_script_generation_prompt(
    *,
    topic: str,
    length_instruction: str,
    template_id: str = DEFAULT_SCRIPT_TEMPLATE_ID,
) -> RenderedPrompt:
    if template_id != DEFAULT_SCRIPT_TEMPLATE_ID:
        raise ValueError("only the registered default script generation template is available")
    return render_prompt_template(
        "script_generation",
        {
            "topic_json": json.dumps(topic, ensure_ascii=False),
            "length_instruction_json": json.dumps(length_instruction, ensure_ascii=False),
        },
    )


def build_script_generation_prompt(
    *,
    topic: str,
    length_instruction: str,
    template_id: str = DEFAULT_SCRIPT_TEMPLATE_ID,
) -> str:
    return render_script_generation_prompt(
        topic=topic,
        length_instruction=length_instruction,
        template_id=template_id,
    ).text


__all__ = [
    "DEFAULT_SCRIPT_TEMPLATE_ID",
    "build_script_generation_prompt",
    "render_script_generation_prompt",
]
