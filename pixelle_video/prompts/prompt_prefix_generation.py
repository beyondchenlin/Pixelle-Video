# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");

"""Prompt builder for prompt prefix generation via LLM."""

from pixelle_video.config.prompt_prefix_library import get_prompt_prefix_category_options
from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template


def render_prompt_prefix_generation_prompt(user_idea: str, language: str = "en_US") -> RenderedPrompt:
    """Render the LLM prompt for prompt prefix candidate generation."""
    style_ids, scene_ids = get_prompt_prefix_category_options()
    language_hint = "Chinese" if language == "zh_CN" else "English"

    return render_prompt_template(
        "prompt_prefix_generation",
        {
            "user_idea": user_idea,
            "language_hint": language_hint,
            "style_ids_csv": ", ".join(style_ids),
            "scene_ids_csv": ", ".join(scene_ids),
        },
    )


def build_prompt_prefix_generation_prompt(user_idea: str, language: str = "en_US") -> str:
    """Build the LLM prompt for prompt prefix candidate generation."""
    return render_prompt_prefix_generation_prompt(user_idea, language=language).text
