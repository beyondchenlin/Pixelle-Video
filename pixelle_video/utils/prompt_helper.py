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
Prompt helper utilities

Simple utilities for building prompts with optional prefixes.
"""

from typing import Any, Optional

from pixelle_video.models.style_resolution import ResolvedStyleSpec


def _read_value(container: Any, key: str, default: Any = None) -> Any:
    if isinstance(container, dict):
        return container.get(key, default)
    return getattr(container, key, default)


def _normalize_prompt_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (list, tuple)):
        raw_values = values
    else:
        raw_values = [values]

    normalized: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        cleaned = str(value or "").strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(cleaned)
    return normalized


def _apply_prompt_template(prompt: str, prompt_template: str = "") -> str:
    template = (prompt_template or "").strip()
    if template and "{prompt}" in template:
        return template.replace("{prompt}", prompt)
    return prompt


def build_image_prompt(prompt: str, prefix: str = "") -> str:
    """
    Build final image prompt with optional prefix
    
    Args:
        prompt: User's raw prompt
        prefix: Optional prefix to add before the prompt
    
    Returns:
        Final prompt with prefix applied (if provided)
    
    Examples:
        >>> build_image_prompt("a cat", "")
        'a cat'
        
        >>> build_image_prompt("a cat", "anime style")
        'anime style, a cat'
        
        >>> build_image_prompt("a cat", "  anime style  ")
        'anime style, a cat'
    """
    prefix = prefix.strip() if prefix else ""
    prompt = prompt.strip() if prompt else ""
    
    if prefix and prompt:
        return f"{prefix}, {prompt}"
    elif prefix:
        return prefix
    else:
        return prompt


def assemble_image_prompt(
    base_prompt: str,
    raw_prefix: str = "",
    resolved_style: Optional[ResolvedStyleSpec] = None,
) -> str:
    if resolved_style is None:
        return build_image_prompt(base_prompt, raw_prefix)

    base_prompt = base_prompt.strip()
    template = (resolved_style.prompt_template or "").strip()
    templated = _apply_prompt_template(base_prompt, template)

    if resolved_style.style_kind == "ip_world":
        if template:
            return templated

        world_prefix = raw_prefix.strip() or (resolved_style.raw_content or "").strip()
        if world_prefix and world_prefix.lower() not in base_prompt.lower():
            return build_image_prompt(base_prompt, world_prefix)
        return base_prompt

    if resolved_style.style_kind == "hybrid":
        raw_prefix = raw_prefix.strip()
        if raw_prefix and raw_prefix.lower() not in templated.lower():
            return f"{templated}, {raw_prefix}"
        return templated

    if template:
        return templated
    return build_image_prompt(base_prompt, raw_prefix)


def assemble_storyboard_prompt(
    *,
    base_prompt: str,
    frame_plan: Any,
    world_preset: Any,
    normalized_style: Optional[dict[str, Any]] = None,
) -> str:
    prompt = ", ".join(
        _normalize_prompt_list(
            [
                _read_value(world_preset, "display_name", ""),
                _read_value(world_preset, "style_core", ""),
                _read_value(frame_plan, "shot_type", ""),
                _read_value(frame_plan, "shot_purpose", ""),
                *_normalize_prompt_list(_read_value(frame_plan, "world_elements", ())),
                base_prompt,
            ]
        )
    )

    if normalized_style is not None:
        prompt = _apply_prompt_template(prompt, normalized_style.get("prompt_template", ""))

    if normalized_style is not None:
        visual_suffix = normalized_style.get("visual_suffix", "")
        if visual_suffix and visual_suffix.lower() not in prompt.lower():
            prompt = ", ".join(_normalize_prompt_list([prompt, visual_suffix]))
    return prompt


def assemble_negative_prompt(
    resolved_style: Optional[ResolvedStyleSpec],
    supports_negative_prompt: bool,
) -> Optional[str]:
    if not resolved_style or not supports_negative_prompt:
        return None

    negative_prompt = (resolved_style.negative_prompt or "").strip()
    return negative_prompt or None
