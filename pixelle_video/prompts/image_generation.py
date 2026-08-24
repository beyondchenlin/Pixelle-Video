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
from collections.abc import Mapping, Sequence
from typing import Any, List, Literal, Optional

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
ImagePromptScope = Literal["full_context", "ordinary_content_only"]



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
    prompt_scope: ImagePromptScope = "full_context",
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
    if prompt_scope not in {"full_context", "ordinary_content_only"}:
        raise ValueError("unsupported image prompt scope")
    if visual_anchor_preparation_enabled and prompt_scope != "full_context":
        raise ValueError(
            "visual-anchor preparation requires the full image prompt context"
        )

    if prompt_scope == "full_context":
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
        (style_profile or None) if prompt_scope == "full_context" else None,
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
    plan_context = envelope.plan_context if envelope is not None else {}
    generation_world = _mapping_value(plan_context.get("generation_world_profile"))
    plan_route = _mapping_value(plan_context.get("selected_visual_route"))
    plan_reference = _mapping_value(plan_context.get("reference_image"))
    frames: list[dict[str, Any]] = []
    for index, narration in enumerate(narrations):
        context = contexts[index]
        visual_plan = _mapping_value(context.get("visual_story_frame_plan"))
        article_plan = _mapping_value(context.get("article_concretization_plan"))
        article_anchor = _mapping_value(article_plan.get("anchor"))
        article_diagram = _mapping_value(article_plan.get("diagram"))
        article_visible_text = _mapping_value(article_diagram.get("visible_text"))
        selected_route = _mapping_value(context.get("selected_visual_route")) or plan_route
        reference_image = _mapping_value(context.get("reference_image")) or plan_reference
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
                    article_anchor.get("main_entities"),
                    article_anchor.get("required_subjects"),
                    reference_image.get("subject_summary"),
                    reference_image.get("identity_anchors"),
                    generation_world.get("ip_integration_guidance"),
                ),
                "action": _unique_prompt_values(
                    context.get("visual_goal"),
                    context.get("prompt_intent"),
                    context.get("focus_detail"),
                    visual_plan.get("local_claim"),
                    visual_plan.get("visual_task"),
                    visual_plan.get("visual_logic"),
                    article_anchor.get("anchor_claim"),
                    article_anchor.get("anchor_question"),
                    article_diagram.get("primary_visual_task"),
                    selected_route.get("visual_premise"),
                    selected_route.get("frame_storytelling_logic"),
                    selected_route.get("route_specific_rules"),
                    selected_route.get("sample_frame_premise"),
                    reference_image.get("prompt_fallback_hint"),
                ),
                "composition": _unique_prompt_values(
                    context.get("shot_type"),
                    context.get("shot_purpose"),
                    context.get("world_elements"),
                    visual_plan.get("scene_arena"),
                    visual_plan.get("physical_metaphor"),
                    visual_plan.get("frame_storytelling_logic"),
                    visual_plan.get("visible_text_policy"),
                    visual_plan.get("forbidden_losses"),
                    generation_world.get("summary"),
                    generation_world.get("time_space"),
                    generation_world.get("visual_environment"),
                    generation_world.get("atmosphere"),
                    generation_world.get("cultural_context"),
                    generation_world.get("story_constraints"),
                    article_diagram.get("grammar"),
                    article_diagram.get("visual_metaphor"),
                    article_diagram.get("composition_rules"),
                    article_diagram.get("panel_plan"),
                    article_visible_text.get("effective_policy"),
                    article_visible_text.get("allowed_visible_text"),
                    reference_image.get("composition_summary"),
                    reference_image.get("negative_constraints"),
                ),
            }
        )
    return {"frames": frames}


def _mapping_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


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
        if isinstance(value, Mapping):
            append(value.get("label") or value.get("name"))
            return
        if isinstance(value, (set, frozenset)):
            for item in sorted(value, key=lambda item: str(item)):
                append(item)
            return
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                append(item)
            return

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
    prompt_scope: ImagePromptScope = "full_context",
) -> str:
    return render_image_prompt_prompt(
        narrations,
        min_words,
        max_words,
        style_profile=style_profile,
        prompt_contexts=prompt_contexts,
        prompt_language=prompt_language,
        visual_anchor_preparation_enabled=visual_anchor_preparation_enabled,
        prompt_scope=prompt_scope,
    ).text
