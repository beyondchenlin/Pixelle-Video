# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Video prompt generation template

For generating video prompts from storyboard frame context.
"""

import json
from typing import Any, List, Optional

from pixelle_video.models.prompt_context import PromptContextInput, prompt_context_payload
from pixelle_video.prompt_language import (
    CHINESE_PROMPT_LANGUAGE,
    DEFAULT_PROMPT_LANGUAGE,
    PromptLanguage,
    normalize_prompt_language,
)
from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template


def render_video_prompt_prompt(
    narrations: List[str],
    min_words: int,
    max_words: int,
    style_profile: Optional[dict[str, Any]] = None,
    prompt_contexts: Optional[PromptContextInput] = None,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
) -> RenderedPrompt:
    """
    Build video prompt generation prompt
    
    Args:
        narrations: List of narrations
        min_words: Minimum word count
        max_words: Maximum word count
    
    Returns:
        Formatted prompt for LLM
    
    Example:
        >>> build_video_prompt_prompt(narrations, 50, 100)
    """
    context_payload = prompt_context_payload(prompt_contexts, len(narrations))
    payload: dict[str, Any] = (
        {"frame_source_texts": narrations}
        if context_payload is not None
        else {"narrations": narrations}
    )
    if context_payload is not None:
        payload.update(context_payload)
    narrations_json = json.dumps(payload, ensure_ascii=False, indent=2)
    style_profile_json = json.dumps(style_profile or None, ensure_ascii=False, indent=2)
    resolved_prompt_language = normalize_prompt_language(prompt_language)
    if resolved_prompt_language == CHINESE_PROMPT_LANGUAGE:
        output_language_label = "Chinese"
        language_requirement = "Video prompts must use Chinese"
        description_length_guidance = (
            "Ensure clear, complete, and creative descriptions "
            f"(roughly equivalent in detail density to {min_words}-{max_words} English words)"
        )
        example_prompt = "[detailed Chinese video prompt with dynamic elements and camera movements]"
    else:
        output_language_label = "English"
        language_requirement = "Video prompts must use English"
        description_length_guidance = (
            f"Ensure clear, complete, and creative descriptions (recommended {min_words}-{max_words} English words)"
        )
        example_prompt = "[detailed English video prompt with dynamic elements and camera movements]"
    
    return render_prompt_template(
        "video_generation",
        {
            "input_payload": payload,
            "style_profile_json": style_profile_json,
            "narrations_json": narrations_json,
            "narrations_count": len(narrations),
            "min_words": min_words,
            "max_words": max_words,
            "output_language_label": output_language_label,
            "language_requirement": language_requirement,
            "description_length_guidance": description_length_guidance,
            "example_prompt": example_prompt,
        },
    )



def build_video_prompt_prompt(
    narrations: List[str],
    min_words: int,
    max_words: int,
    style_profile: Optional[dict[str, Any]] = None,
    prompt_contexts: Optional[PromptContextInput] = None,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
) -> str:
    return render_video_prompt_prompt(
        narrations,
        min_words,
        max_words,
        style_profile=style_profile,
        prompt_contexts=prompt_contexts,
        prompt_language=prompt_language,
    ).text
