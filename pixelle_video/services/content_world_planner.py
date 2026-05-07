"""Service for deriving the current-generation content world profile."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from loguru import logger

from pixelle_video.models.content_world import (
    ContentWorldHintSource,
    ContentWorldProfile,
)
from pixelle_video.prompts.content_world import (
    build_content_world_prompt,
    parse_content_world_profile,
)


class ContentWorldPlanner:
    async def plan(
        self,
        *,
        llm_service,
        source_text: str,
        generation_world_hint: str | None = None,
        ip_world_hint: str | None = None,
        world_preset: Mapping[str, Any] | None = None,
    ) -> ContentWorldProfile:
        hint_source = _resolve_hint_source(generation_world_hint, ip_world_hint)
        prompt = build_content_world_prompt(
            source_text=source_text,
            generation_world_hint=_optional_text(generation_world_hint),
            ip_world_hint=_optional_text(ip_world_hint),
            world_preset=world_preset,
        )
        try:
            response = await llm_service(
                prompt=prompt,
                response_type=dict,
                temperature=0.2,
                max_tokens=900,
            )
            profile = parse_content_world_profile(response, hint_source=hint_source)
            return profile if profile.has_content() else _fallback_profile(source_text)
        except Exception as exc:
            logger.warning("Content world planning failed; using fallback profile: {}", exc)
            return _fallback_profile(source_text)


def _resolve_hint_source(
    generation_world_hint: str | None,
    ip_world_hint: str | None,
) -> ContentWorldHintSource:
    if _optional_text(generation_world_hint):
        return ContentWorldHintSource.MANUAL
    if _optional_text(ip_world_hint):
        return ContentWorldHintSource.IP_DEFAULT
    return ContentWorldHintSource.GENERATED_FROM_SCRIPT


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _fallback_profile(source_text: str) -> ContentWorldProfile:
    source_excerpt = _optional_text(source_text) or ""
    return ContentWorldProfile(
        summary=source_excerpt[:80],
        story_constraints="",
        ip_integration_guidance="",
        hint_source=ContentWorldHintSource.FALLBACK,
        generation_failed=True,
    )


__all__ = ["ContentWorldPlanner"]
