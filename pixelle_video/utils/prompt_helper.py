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

import re
from collections.abc import Mapping, Sequence
from typing import Any, Optional

from pixelle_video.models.style_resolution import ResolvedStyleSpec
from pixelle_video.models.text_overlay import DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT

NO_TEXT_POSITIVE_RULE = DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT
NO_TEXT_NEGATIVE_RULES: tuple[str, ...] = (
    "text",
    "letters",
    "words",
    "typography",
    "subtitles",
    "captions",
    "watermark",
    "logo",
    "Chinese characters",
    "English letters",
    "handwriting",
    "calligraphy",
    "printed text",
)
PLANNED_TEXT_POSITIVE_GUARD = (
    "only render the explicitly requested planned text, no extra captions, "
    "no extra subtitles, no watermark, no logo text, no random letters"
)
PLANNED_TEXT_NEGATIVE_RULES: tuple[str, ...] = (
    "unplanned text",
    "random letters",
    "watermark",
    "logo text",
    "extra captions",
    "extra subtitles",
)
_HEX_COLOR_RE = re.compile(
    r"(?<![0-9a-fA-F])#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-fA-F])"
)
_FIELD_LABEL_RE = re.compile(
    r"['\"]?\b(?:summary_text|scene_text|title_hex|ip_presence_type|presence_mode|"
    r"visible_text_whitelist|negative_constraints|identity_color_terms|"
    r"generation_world_profile|story_constraints|ip_integration_guidance|ip_adaptation"
    r")\b['\"]?\s*[:：?]\s*",
    re.IGNORECASE,
)


def _read_value(container: Any, key: str, default: Any = None) -> Any:
    if isinstance(container, Mapping):
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


def _humanize_prompt_token(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"[_-]+", " ", text).strip()


def _sentence_clause(*values: Any) -> str:
    return ", ".join(
        _normalize_prompt_list([_humanize_prompt_token(value) for value in values])
    )


_NEUTRAL_WORLD_PRESET_IDS = frozenset(
    {
        "neutral",
        "neutral_knowledge_storyboard",
        "knowledge_storyboard",
        "clean_classroom",
        "default_storyboard",
        "generic_storyboard",
    }
)


def _semantic_world_identity(world_preset: Any) -> str:
    preset_id = str(
        _read_value(world_preset, "preset_id", "")
        or _read_value(world_preset, "id", "")
        or _read_value(world_preset, "world_preset_id", "")
    ).strip()
    if preset_id.lower() in _NEUTRAL_WORLD_PRESET_IDS:
        return ""

    display_name = _read_value(world_preset, "display_name", "")
    identity = str(display_name or "").strip()
    if not identity:
        return ""

    lowered = identity.lower()
    if "neutral" in lowered:
        return ""
    if lowered in {"default", "generic", "storyboard", "knowledge storyboard"}:
        return ""
    return identity


def _normalize_negative_rule_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (list, tuple)):
        raw_values = values
    else:
        raw_values = [values]

    normalized: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        if value is None:
            continue
        segments = str(value).split(",") if isinstance(value, str) else [str(value)]
        for segment in segments:
            cleaned = str(segment or "").strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(cleaned)
    return normalized


def _read_nested_value(container: Any, path: Sequence[str]) -> Any:
    current = container
    for key in path:
        if current is None:
            return None
        current = _read_value(current, key, None)
    return current


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


def apply_no_text_policy(prompt: str, enabled: bool = True) -> str:
    cleaned_prompt = (prompt or "").strip()
    if not enabled or not cleaned_prompt:
        return cleaned_prompt

    if NO_TEXT_POSITIVE_RULE.lower() in cleaned_prompt.lower():
        return cleaned_prompt

    return ", ".join(_normalize_prompt_list([cleaned_prompt, NO_TEXT_POSITIVE_RULE]))


def apply_image_text_policy(prompt: str, image_text_policy: Any) -> str:
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_prompt:
        return cleaned_prompt
    if not _read_value(image_text_policy, "suppress_embedded_text", False):
        return cleaned_prompt
    positive_prompt = str(
        _read_value(image_text_policy, "positive_prompt", "") or ""
    ).strip()
    if not positive_prompt:
        return cleaned_prompt
    return ", ".join(_normalize_prompt_list([cleaned_prompt, positive_prompt]))


def apply_text_rendering_policy(
    prompt: str,
    *,
    policy: Any,
    has_native_hints: bool,
) -> str:
    if has_native_hints and _read_value(policy, "allow_native_text_in_image", False):
        return ", ".join(_normalize_prompt_list([prompt, PLANNED_TEXT_POSITIVE_GUARD]))

    return apply_no_text_policy(
        prompt,
        enabled=_read_value(policy, "suppress_unplanned_embedded_text", True),
    )


def sanitize_visual_prompt_text(prompt: str) -> str:
    cleaned = _HEX_COLOR_RE.sub("", str(prompt or ""))
    cleaned = _FIELD_LABEL_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,，。；;])", r"\1", cleaned)
    cleaned = re.sub(r"([,，；;])\s*([,，；;])+", r"\1", cleaned)
    return cleaned.strip(" ,，;；")


def build_visible_text_whitelist_clause(whitelist: Any) -> str:
    allowed_text = _normalize_prompt_list(whitelist)
    if not allowed_text:
        return ""
    quoted = "、".join(f"“{item}”" for item in allowed_text)
    return f"画面文字只允许白名单内容：{quoted}；only whitelisted text may appear, no extra words."


def merge_z_image_constraints_into_prompt(
    prompt: str,
    *,
    extra_constraints: Any = None,
    visible_text_whitelist: Any = None,
) -> str:
    clauses = [sanitize_visual_prompt_text(prompt)]
    whitelist_clause = build_visible_text_whitelist_clause(visible_text_whitelist)
    if whitelist_clause:
        clauses.append(whitelist_clause)
    clauses.extend(_normalize_negative_rule_list(extra_constraints))
    return sanitize_visual_prompt_text(", ".join(_normalize_prompt_list(clauses)))


def ip_negative_constraints_from_context(frame_context: Any) -> tuple[str, ...]:
    constraints = frame_context.get("ip_negative_constraints", ())
    if isinstance(constraints, (list, tuple)):
        return tuple(_normalize_negative_rule_list(constraints))
    return ()


def ip_visible_text_whitelist_from_context(frame_context: Any) -> tuple[str, ...]:
    image_text_plan = frame_context.get("ip_image_text_plan", {})
    if not isinstance(image_text_plan, Mapping):
        return ()
    whitelist = image_text_plan.get("visible_text_whitelist", ())
    return tuple(_normalize_prompt_list(whitelist))


def select_image_text_negative_prompt(image_text_policy: Any) -> tuple[str, ...] | None:
    if not _read_value(image_text_policy, "suppress_embedded_text", False):
        return None
    negative_prompt = str(
        _read_value(image_text_policy, "negative_prompt", "") or ""
    ).strip()
    if not negative_prompt:
        return None
    return tuple(_normalize_negative_rule_list([negative_prompt]))


def select_negative_text_rules(
    *,
    policy: Any,
    has_native_hints: bool,
) -> tuple[str, ...] | None:
    if has_native_hints and _read_value(policy, "allow_native_text_in_image", False):
        return PLANNED_TEXT_NEGATIVE_RULES
    if _read_value(policy, "suppress_unplanned_embedded_text", True):
        return NO_TEXT_NEGATIVE_RULES
    return None


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
        if template and template != "{prompt}":
            return templated

        world_prefix = raw_prefix.strip() or (resolved_style.raw_content or "").strip()
        if world_prefix and world_prefix.lower() not in base_prompt.lower():
            return build_image_prompt(base_prompt, world_prefix)
        return base_prompt

    if resolved_style.style_kind == "hybrid":
        if template and template != "{prompt}":
            return templated

        raw_prefix = raw_prefix.strip()
        if raw_prefix and raw_prefix.lower() not in templated.lower():
            return f"{templated}, {raw_prefix}"
        return templated

    if template and template != "{prompt}":
        return templated
    return build_image_prompt(base_prompt, raw_prefix)


def assemble_storyboard_prompt(
    *,
    base_prompt: str,
    frame_plan: Any,
    world_preset: Any,
    normalized_style: Optional[dict[str, Any]] = None,
) -> str:
    base = sanitize_visual_prompt_text(base_prompt)
    world_identity = _semantic_world_identity(world_preset)
    style_core = _humanize_prompt_token(_read_value(world_preset, "style_core", ""))
    shot_type = _humanize_prompt_token(_read_value(frame_plan, "shot_type", ""))
    shot_purpose = _humanize_prompt_token(_read_value(frame_plan, "shot_purpose", ""))
    world_elements = _sentence_clause(
        *_normalize_prompt_list(_read_value(frame_plan, "world_elements", ()))
    )

    clauses = [base]
    if world_identity:
        clauses.append(f"set in the {world_identity} world")
    if style_core:
        clauses.append(f"rendered as {style_core}")
    if shot_type or shot_purpose:
        camera_parts = _sentence_clause(shot_type, shot_purpose)
        if camera_parts:
            clauses.append(f"framed as {camera_parts}")
    if world_elements:
        clauses.append(f"with {world_elements} integrated into the environment")

    prompt = "; ".join(_normalize_prompt_list(clauses))

    if normalized_style is not None:
        prompt = _apply_prompt_template(prompt, normalized_style.get("prompt_template", ""))
        visual_suffix = _humanize_prompt_token(normalized_style.get("visual_suffix", ""))
        if visual_suffix and visual_suffix.lower() not in prompt.lower():
            prompt = "; ".join(_normalize_prompt_list([prompt, visual_suffix]))
    return sanitize_visual_prompt_text(prompt)


def assemble_negative_prompt(
    resolved_style: Optional[ResolvedStyleSpec],
    supports_negative_prompt: bool,
    extra_negative_rules: Any = None,
) -> Optional[str]:
    if not supports_negative_prompt:
        return None

    negative_prompt_parts: list[str] = []
    if resolved_style is not None:
        negative_prompt_parts.append(resolved_style.negative_prompt or "")
    if extra_negative_rules is not None:
        negative_prompt_parts.extend(_normalize_negative_rule_list(extra_negative_rules))

    normalized = _normalize_negative_rule_list(negative_prompt_parts)
    if not normalized:
        return None
    return ", ".join(normalized)
