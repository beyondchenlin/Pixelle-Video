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
Helpers for turning raw style prefixes into runtime structured style specs.
"""

import hashlib
import json
import re
from typing import Any, Optional

from loguru import logger

from pixelle_video.config.prompt_prefix_library import get_active_image_prompt_prefix_item
from pixelle_video.models.style_resolution import ResolvedStyleSpec, StyleSourceSpec
from pixelle_video.prompts import build_style_resolution_prompt


RESOLVER_VERSION = "2026-04-21-v1"
VALID_STYLE_KINDS = {"visual_only", "ip_world", "hybrid"}
REQUIRED_STYLE_PROFILE_KEYS = (
    "style_kind",
    "subject_policy",
    "shape_language",
    "material",
    "palette",
    "lighting",
    "world_elements",
    "consistency_anchor",
    "negative_rules",
)

_STYLE_RESOLUTION_CACHE: dict[str, ResolvedStyleSpec] = {}


def reset_style_resolution_cache() -> None:
    _STYLE_RESOLUTION_CACHE.clear()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def resolve_style_source(
    image_config,
    prompt_prefix_override: Optional[str] = None,
) -> Optional[StyleSourceSpec]:
    override = (prompt_prefix_override or "").strip()
    if override:
        content_hash = _hash_text(override)
        return StyleSourceSpec(
            origin="request",
            raw_content=override,
            content_hash=content_hash,
            source_identity=f"request:{content_hash}",
            item_id=None,
        )

    active_item = get_active_image_prompt_prefix_item(image_config)
    if active_item:
        raw_content = (active_item.get("content") or "").strip()
        if raw_content:
            content_hash = _hash_text(raw_content)
            return StyleSourceSpec(
                origin="library",
                raw_content=raw_content,
                content_hash=content_hash,
                source_identity=f"library:{active_item['id']}",
                item_id=active_item["id"],
            )

    legacy_prefix = ""
    if isinstance(image_config, dict):
        legacy_prefix = (image_config.get("prompt_prefix") or "").strip()
    else:
        legacy_prefix = (getattr(image_config, "prompt_prefix", "") or "").strip()

    if legacy_prefix:
        content_hash = _hash_text(legacy_prefix)
        return StyleSourceSpec(
            origin="legacy",
            raw_content=legacy_prefix,
            content_hash=content_hash,
            source_identity=f"legacy:{content_hash}",
            item_id=None,
        )

    return None


def build_style_resolution_cache_key(source: StyleSourceSpec) -> str:
    if source.origin == "library" and source.item_id:
        return f"library:{source.item_id}:{source.content_hash}:{RESOLVER_VERSION}"
    return f"{source.origin}:{source.content_hash}:{RESOLVER_VERSION}"


def _read_value(container: Any, key: str, default: Any = None) -> Any:
    if isinstance(container, dict):
        return container.get(key, default)
    return getattr(container, key, default)


def _unique_non_empty(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = (value or "").strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(cleaned)
    return deduped


def _world_identity_tokens(world_preset: Any) -> set[str]:
    raw_values = [
        str(_read_value(world_preset, "preset_id", "") or ""),
        str(_read_value(world_preset, "display_name", "") or ""),
        str(_read_value(world_preset, "style_core", "") or ""),
    ]
    tokens: set[str] = set()
    for value in raw_values:
        for token in re.findall(r"[a-z0-9]+", value.lower()):
            if len(token) >= 4:
                tokens.add(token)
    return tokens


def _style_mentions_world_identity(resolved_style: ResolvedStyleSpec, world_preset: Any) -> bool:
    world_tokens = _world_identity_tokens(world_preset)
    if not world_tokens:
        return False

    style_text = " ".join(
        [
            resolved_style.raw_content,
            str(resolved_style.style_profile.get("consistency_anchor", "") or ""),
            str(resolved_style.style_profile.get("world_elements", "") or ""),
            resolved_style.prompt_template,
        ]
    ).lower()
    return any(token in style_text for token in world_tokens)


def normalize_storyboard_style(
    *,
    resolved_style: Optional[ResolvedStyleSpec],
    world_preset: Any,
) -> Optional[dict[str, Any]]:
    if resolved_style is None:
        return None

    style_profile = resolved_style.style_profile or {}
    visual_fields = {
        "shape_language": (style_profile.get("shape_language") or "").strip(),
        "material": (style_profile.get("material") or "").strip(),
        "palette": (style_profile.get("palette") or "").strip(),
        "lighting": (style_profile.get("lighting") or "").strip(),
    }
    classification = "compatible_refinement"
    keep_consistency_anchor = True

    if resolved_style.style_kind in {"ip_world", "hybrid"} and not _style_mentions_world_identity(
        resolved_style,
        world_preset,
    ):
        classification = "conflicting_world_override"
        keep_consistency_anchor = False

    suffix_parts = list(visual_fields.values())
    if keep_consistency_anchor:
        suffix_parts.append((style_profile.get("consistency_anchor") or "").strip())
    visual_suffix = ", ".join(_unique_non_empty(suffix_parts))

    normalized_profile = {
        "style_kind": "visual_only",
        "subject_policy": "preserve_subject_semantics",
        "shape_language": visual_fields["shape_language"],
        "material": visual_fields["material"],
        "palette": visual_fields["palette"],
        "lighting": visual_fields["lighting"],
        "world_elements": "",
        "consistency_anchor": (style_profile.get("consistency_anchor") or "").strip() if keep_consistency_anchor else "",
        "negative_rules": (style_profile.get("negative_rules") or "").strip(),
    }
    return {
        "classification": classification,
        "visual_suffix": visual_suffix,
        "style_profile": normalized_profile,
    }


def _validate_style_kind(value: str) -> str:
    style_kind = (value or "").strip()
    if style_kind not in VALID_STYLE_KINDS:
        raise ValueError(f"Invalid style_kind: {style_kind}")
    return style_kind


def _validate_prompt_template(value: str) -> str:
    prompt_template = (value or "").strip()
    if prompt_template and prompt_template.count("{prompt}") != 1:
        raise ValueError("prompt_template must contain {prompt} exactly once")
    return prompt_template


def _validate_style_profile(data: dict) -> dict:
    missing = [key for key in REQUIRED_STYLE_PROFILE_KEYS if key not in data]
    if missing:
        raise ValueError(f"style_profile missing keys: {', '.join(missing)}")

    style_profile = {key: (data.get(key) or "").strip() for key in REQUIRED_STYLE_PROFILE_KEYS}
    style_profile["style_kind"] = _validate_style_kind(style_profile["style_kind"])
    return style_profile


def _parse_resolved_style_spec(response: str, source: StyleSourceSpec) -> ResolvedStyleSpec:
    data = json.loads(response)
    style_kind = _validate_style_kind(data["style_kind"])
    prompt_template = _validate_prompt_template(data.get("prompt_template") or "")
    style_profile = _validate_style_profile(data["style_profile"])

    return ResolvedStyleSpec(
        style_kind=style_kind,
        prompt_template=prompt_template,
        negative_prompt=(data.get("negative_prompt") or "").strip(),
        style_profile=style_profile,
        content_hash=source.content_hash,
        resolver_version=RESOLVER_VERSION,
        source_identity=source.source_identity,
        raw_content=source.raw_content,
    )


async def resolve_style_spec(llm_service, source: StyleSourceSpec) -> ResolvedStyleSpec:
    cache_key = build_style_resolution_cache_key(source)
    cached = _STYLE_RESOLUTION_CACHE.get(cache_key)
    if cached is not None:
        return cached

    prompt = build_style_resolution_prompt(source.raw_content)
    response = await llm_service(prompt=prompt, temperature=0.2, max_tokens=1200)
    resolved = _parse_resolved_style_spec(response, source)
    _STYLE_RESOLUTION_CACHE[cache_key] = resolved
    logger.debug("Resolved style {} via runtime cache key {}", source.source_identity, cache_key)
    return resolved
