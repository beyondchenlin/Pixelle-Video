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

from pixelle_video.models.prompt_context import (
    PromptContextInput,
    llm_prompt_context_payload,
    normalize_prompt_contexts,
)
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
    *,
    series_visual_signature_enabled: bool = False,
    series_visual_signature_display_name: str = "",
    series_visual_signature_identity_traits: str = "",
    series_visual_signature_role_description: str = "",
    visual_anchor_preparation_enabled: bool = False,
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
    if visual_anchor_preparation_enabled:
        context_payload = llm_prompt_context_payload(prompt_contexts, len(narrations))
        payload: dict[str, Any] = (
            {"frame_source_texts": narrations}
            if context_payload is not None
            else {"narrations": narrations}
        )
        if context_payload is not None:
            payload.update(context_payload)
        template_id = "image_generation"
    else:
        payload = _ordinary_image_prompt_payload(narrations, prompt_contexts)
        template_id = "ordinary_image_generation"
    narrations_json = json.dumps(payload, ensure_ascii=False, indent=2)
    style_profile_json = json.dumps(
        (style_profile or None) if visual_anchor_preparation_enabled else None,
        ensure_ascii=False,
        indent=2,
    )
    resolved_prompt_language = normalize_prompt_language(prompt_language)
    
    return render_prompt_template(
        template_id,
        {
            "input_payload": payload,
            "style_profile_json": style_profile_json,
            "narrations_json": narrations_json,
            "narrations_count": len(narrations),
            "min_words": min_words,
            "max_words": max_words,
            "output_language_chinese": resolved_prompt_language == CHINESE_PROMPT_LANGUAGE,
            "output_language_english": resolved_prompt_language != CHINESE_PROMPT_LANGUAGE,
            "series_visual_signature_enabled": series_visual_signature_enabled,
            "series_visual_signature_display_name": series_visual_signature_display_name,
            "series_visual_signature_identity_traits": series_visual_signature_identity_traits,
            "series_visual_signature_role_description": series_visual_signature_role_description,
            "visual_anchor_preparation_enabled": visual_anchor_preparation_enabled,
        },
    )


def _ordinary_image_prompt_payload(
    narrations: List[str],
    prompt_contexts: Optional[PromptContextInput],
) -> dict[str, Any]:
    envelope = normalize_prompt_contexts(prompt_contexts, len(narrations))
    contexts = envelope.frame_contexts if envelope is not None else tuple({} for _ in narrations)
    frames: list[dict[str, Any]] = []
    for index, narration in enumerate(narrations):
        context = contexts[index]
        visual_plan = context.get("visual_story_frame_plan")
        visual_plan = visual_plan if isinstance(visual_plan, dict) else {}
        frames.append(
            {
                "current_storyboard": str(
                    context.get("frame_source_text") or narration
                ).strip(),
                "subjects": _unique_prompt_values(
                    context.get("primary_subject"),
                    context.get("secondary_subjects"),
                    context.get("required_subjects"),
                    visual_plan.get("required_subjects"),
                ),
                "action": _unique_prompt_values(
                    context.get("visual_goal"),
                    context.get("prompt_intent"),
                    context.get("focus_detail"),
                    visual_plan.get("local_claim"),
                    visual_plan.get("visual_task"),
                    visual_plan.get("visual_logic"),
                ),
                "composition": _unique_prompt_values(
                    context.get("shot_type"),
                    context.get("shot_purpose"),
                    context.get("world_elements"),
                    visual_plan.get("scene_arena"),
                    visual_plan.get("physical_metaphor"),
                    visual_plan.get("frame_storytelling_logic"),
                ),
            }
        )
    return {"frames": frames}


def _unique_prompt_values(*values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    def append(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            text = value.strip()
            if text and text.lower() not in seen:
                seen.add(text.lower())
                result.append(text)
            return
        if isinstance(value, dict):
            append(value.get("label") or value.get("name"))
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                append(item)
            return
        append(str(value))

    for value in values:
        append(value)
    return result



def build_image_prompt_prompt(
    narrations: List[str],
    min_words: int,
    max_words: int,
    style_profile: Optional[dict[str, Any]] = None,
    prompt_contexts: Optional[PromptContextInput] = None,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
    visual_anchor_preparation_enabled: bool = False,
) -> str:
    return render_image_prompt_prompt(
        narrations,
        min_words,
        max_words,
        style_profile=style_profile,
        prompt_contexts=prompt_contexts,
        prompt_language=prompt_language,
        visual_anchor_preparation_enabled=visual_anchor_preparation_enabled,
    ).text
