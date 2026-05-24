"""Service for deriving the current-generation content world profile."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from loguru import logger

from pixelle_video.models.content_world import (
    ContentWorldHintSource,
    ContentWorldProfile,
)
from pixelle_video.models.llm_interaction_trace import (
    LLMTraceContext,
    LLMTraceError,
    trace_context_with_prompt_template,
)
from pixelle_video.prompts.content_world import (
    parse_content_world_profile,
    render_content_world_prompt,
)
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder


class ContentWorldPlanner:
    async def plan(
        self,
        *,
        llm_service,
        source_text: str,
        generation_world_hint: str | None = None,
        ip_world_hint: str | None = None,
        world_preset: Mapping[str, Any] | None = None,
        trace_context: LLMTraceContext | None = None,
        trace_recorder: LLMInteractionRecorder | None = None,
    ) -> ContentWorldProfile:
        hint_source = _resolve_hint_source(generation_world_hint, ip_world_hint)
        rendered_prompt = render_content_world_prompt(
            source_text=source_text,
            generation_world_hint=_optional_text(generation_world_hint),
            ip_world_hint=_optional_text(ip_world_hint),
            world_preset=world_preset,
        )
        try:
            response = await llm_service(
                prompt=rendered_prompt.text,
                response_type=dict,
                temperature=0.2,
                max_tokens=900,
                trace_context=(
                    trace_context_with_prompt_template(
                        trace_context,
                        rendered_prompt=rendered_prompt,
                        attempt=1,
                        stage="content_world_planning",
                    )
                    if trace_context is not None
                    else None
                ),
                trace_recorder=trace_recorder,
            )
            profile = parse_content_world_profile(response, hint_source=hint_source)
            return profile if profile.has_content() else _fallback_profile(source_text)
        except LLMTraceError:
            raise
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
