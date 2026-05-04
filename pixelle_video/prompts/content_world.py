"""Prompt helpers for current-generation content world profiling."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pixelle_video.models.content_world import ContentWorldProfile
from pixelle_video.utils.json_parsing import parse_llm_json_response


def build_content_world_prompt(
    *,
    source_text: str,
    generation_world_hint: str | None = None,
    ip_world_hint: str | None = None,
    world_preset: Mapping[str, Any] | None = None,
) -> str:
    payload = {
        "task": "extract_current_generation_world_profile",
        "source_text": source_text,
        "generation_world_hint": generation_world_hint,
        "ip_default_world_hint": ip_world_hint,
        "world_preset": dict(world_preset or {}),
        "required_output": {
            "summary": "string",
            "time_space": "string",
            "visual_environment": "string",
            "atmosphere": "string",
            "cultural_context": "string",
            "story_constraints": "string",
            "ip_integration_guidance": "string",
        },
        "instructions": [
            "Return JSON only.",
            "Treat generation_world_hint as the highest priority when present.",
            "Use ip_default_world_hint only as compatibility guidance, not as the current story world.",
            "Do not output markdown fences.",
            "Do not output hex color codes.",
            "Do not copy field names into natural language values.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_content_world_profile(
    raw_response: Any,
    *,
    hint_source,
) -> ContentWorldProfile:
    if isinstance(raw_response, ContentWorldProfile):
        return raw_response
    if isinstance(raw_response, Mapping):
        payload = dict(raw_response)
    else:
        payload = parse_llm_json_response(
            str(raw_response).strip(),
            allow_code_fence=True,
            allow_embedded_json=False,
        )
    if not isinstance(payload, Mapping):
        raise ValueError("content world response must be a JSON object")
    payload = dict(payload)
    payload["hint_source"] = hint_source
    return ContentWorldProfile.from_dict(payload)


__all__ = ["build_content_world_prompt", "parse_content_world_profile"]
