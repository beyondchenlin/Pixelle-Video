from __future__ import annotations

import json
from typing import Any

from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template

DEFAULT_SCRIPT_TEMPLATE_ID = "default"


def render_script_generation_prompt(
    *,
    topic: str,
    length_mode: str,
    target_words: int | None,
    template_id: str = DEFAULT_SCRIPT_TEMPLATE_ID,
    user_intent_hint: str | None = None,
) -> RenderedPrompt:
    if template_id != DEFAULT_SCRIPT_TEMPLATE_ID:
        raise ValueError("only the registered default script generation template is available")
    normalized_length_mode = str(length_mode or "auto")
    variables: dict[str, Any] = {
        "topic_json": json.dumps(topic, ensure_ascii=False),
        "user_intent_json": json.dumps(user_intent_hint or "", ensure_ascii=False),
        "length_auto": normalized_length_mode == "auto",
        "length_targeted": normalized_length_mode != "auto",
        "target_words": target_words or "",
    }
    return render_prompt_template(
        "script_generation",
        variables,
    )


def build_script_generation_prompt(
    *,
    topic: str,
    length_mode: str = "auto",
    target_words: int | None = None,
    template_id: str = DEFAULT_SCRIPT_TEMPLATE_ID,
    user_intent_hint: str | None = None,
) -> str:
    return render_script_generation_prompt(
        topic=topic,
        length_mode=length_mode,
        target_words=target_words,
        template_id=template_id,
        user_intent_hint=user_intent_hint,
    ).text


__all__ = [
    "DEFAULT_SCRIPT_TEMPLATE_ID",
    "build_script_generation_prompt",
    "render_script_generation_prompt",
]
