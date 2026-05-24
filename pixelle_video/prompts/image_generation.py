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
Image prompt generation template

For generating image prompts from storyboard frame context.
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

# ==================== PRESET IMAGE STYLES ====================
# Predefined visual styles for different use cases

IMAGE_STYLE_PRESETS = {
    "stick_figure": {
        "name": "Stick Figure Sketch",
        "description": "stick figure style sketch, black and white lines, pure white background, minimalist hand-drawn feel",
        "use_case": "General scenes, simple and intuitive"
    },
    
    "minimal": {
        "name": "Minimalist Abstract",
        "description": "minimalist abstract art, geometric shapes, clean composition, modern design, soft pastel colors",
        "use_case": "Modern, artistic feel"
    },
    
    "concept": {
        "name": "Conceptual Visual",
        "description": "conceptual visual metaphors, symbolic elements, thought-provoking imagery, artistic interpretation",
        "use_case": "Deep content, philosophical thinking"
    },
}

# Default preset
DEFAULT_IMAGE_STYLE = "stick_figure"



def render_image_prompt_prompt(
    narrations: List[str],
    min_words: int,
    max_words: int,
    style_profile: Optional[dict[str, Any]] = None,
    prompt_contexts: Optional[PromptContextInput] = None,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
) -> RenderedPrompt:
    """
    Build image prompt generation prompt
    
    Note: Style/prefix will be applied later via prompt_prefix in config.
    
    Args:
        narrations: List of narrations
        min_words: Minimum word count
        max_words: Maximum word count
    
    Returns:
        Formatted prompt for LLM
    
    Example:
        >>> build_image_prompt_prompt(narrations, 50, 100)
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
    
    return render_prompt_template(
        "image_generation",
        {
            "input_payload": payload,
            "style_profile_json": style_profile_json,
            "narrations_json": narrations_json,
            "narrations_count": len(narrations),
            "min_words": min_words,
            "max_words": max_words,
            "output_language_chinese": resolved_prompt_language == CHINESE_PROMPT_LANGUAGE,
            "output_language_english": resolved_prompt_language != CHINESE_PROMPT_LANGUAGE,
        },
    )



def build_image_prompt_prompt(
    narrations: List[str],
    min_words: int,
    max_words: int,
    style_profile: Optional[dict[str, Any]] = None,
    prompt_contexts: Optional[PromptContextInput] = None,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
) -> str:
    return render_image_prompt_prompt(
        narrations,
        min_words,
        max_words,
        style_profile=style_profile,
        prompt_contexts=prompt_contexts,
        prompt_language=prompt_language,
    ).text
