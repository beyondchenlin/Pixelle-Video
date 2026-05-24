"""Prompt helpers for current-generation content world profiling."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pixelle_video.models.content_world import ContentWorldProfile
from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template
from pixelle_video.utils.json_parsing import parse_llm_json_response


def render_content_world_prompt(
    *,
    source_text: str,
    generation_world_hint: str | None = None,
    ip_world_hint: str | None = None,
    world_preset: Mapping[str, Any] | None = None,
) -> RenderedPrompt:
    return render_prompt_template(
        "content_world",
        {
            "source_text_json": json.dumps(source_text, ensure_ascii=False),
            "generation_world_hint_json": json.dumps(generation_world_hint, ensure_ascii=False),
            "ip_world_hint_json": json.dumps(ip_world_hint, ensure_ascii=False),
            "world_preset_json": json.dumps(dict(world_preset or {}), ensure_ascii=False, indent=2),
        },
    )


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


def build_content_world_prompt(
    *,
    source_text: str,
    generation_world_hint: str | None = None,
    ip_world_hint: str | None = None,
    world_preset: Mapping[str, Any] | None = None,
) -> str:
    return render_content_world_prompt(
        source_text=source_text,
        generation_world_hint=generation_world_hint,
        ip_world_hint=ip_world_hint,
        world_preset=world_preset,
    ).text
