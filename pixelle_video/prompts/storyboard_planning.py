"""Structured prompt helpers for storyboard planning."""

from __future__ import annotations

import json
from typing import Any, Mapping

from pydantic import ValidationError

from pixelle_video.models.prompt_context import PromptContextInput, prompt_context_payload
from pixelle_video.models.storyboard_planning import FramePlan, StoryboardPlanningResponse
from pixelle_video.prompt_language import (
    CHINESE_PROMPT_LANGUAGE,
    DEFAULT_PROMPT_LANGUAGE,
    PromptLanguage,
    normalize_prompt_language,
)
from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template
from pixelle_video.utils.json_parsing import parse_llm_json_response


def _extract_json_payload(raw_response: str) -> Any:
    text = raw_response.strip()
    if not text:
        raise ValueError("storyboard planning response does not contain JSON")

    try:
        return parse_llm_json_response(text, allow_code_fence=True, allow_embedded_json=False)
    except json.JSONDecodeError as exc:
        raise ValueError("storyboard planning response must contain only a JSON payload") from exc


def render_storyboard_planning_prompt(
    *,
    narrations: list[str],
    prompt_contexts: PromptContextInput | None = None,
    generation_world_profile: Mapping[str, Any] | None = None,
    world_preset: Mapping[str, Any],
    shot_preset: Mapping[str, Any],
    resolved_mode: str,
    consistency_strength: str,
    role_strategy: str = "auto",
    role_locking_strength: str = "standard",
    shot_strategy: str = "adaptive",
    scene_id_start: int = 1,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
) -> RenderedPrompt:
    """Build the structured planning prompt sent to the LLM."""

    required_frame_fields = list(FramePlan.required_prompt_fields())
    frame_source_items = [
        {"scene_id": str(scene_id_start + index), "text": frame_source_text}
        for index, frame_source_text in enumerate(narrations)
    ]
    context_payload = prompt_context_payload(
        prompt_contexts,
        len(narrations),
        error_prefix="storyboard prompt_contexts",
    )
    uses_frame_context = context_payload is not None
    resolved_prompt_language = normalize_prompt_language(prompt_language)
    has_generation_world_profile = generation_world_profile is not None
    prompt_context_entries = ""
    if context_payload is not None:
        prompt_context_entries = "".join(
            f',\n  "{key}": {json.dumps(value, ensure_ascii=False, indent=2)}'
            for key, value in context_payload.items()
        )
    return render_prompt_template(
        "storyboard_planning",
        {
            "resolved_mode_json": json.dumps(resolved_mode, ensure_ascii=False),
            "prompt_language_json": json.dumps(resolved_prompt_language, ensure_ascii=False),
            "consistency_strength_json": json.dumps(consistency_strength, ensure_ascii=False),
            "role_strategy_json": json.dumps(role_strategy, ensure_ascii=False),
            "role_locking_strength_json": json.dumps(role_locking_strength, ensure_ascii=False),
            "shot_strategy_json": json.dumps(shot_strategy, ensure_ascii=False),
            "world_preset_json": json.dumps(dict(world_preset), ensure_ascii=False, indent=2),
            "shot_preset_json": json.dumps(dict(shot_preset), ensure_ascii=False, indent=2),
            "required_frame_fields_json": json.dumps(
                required_frame_fields,
                ensure_ascii=False,
                indent=2,
            ),
            "required_output_json": json.dumps(
                StoryboardPlanningResponse.model_json_schema(),
                ensure_ascii=False,
                indent=2,
            ),
            "has_generation_world_profile": has_generation_world_profile,
            "generation_world_profile_json": json.dumps(
                dict(generation_world_profile or {}),
                ensure_ascii=False,
                indent=2,
            ),
            "uses_frame_context": uses_frame_context,
            "uses_legacy_narrations": not uses_frame_context,
            "frame_source_texts_json": json.dumps(narrations, ensure_ascii=False, indent=2),
            "frame_source_items_json": json.dumps(
                frame_source_items,
                ensure_ascii=False,
                indent=2,
            ),
            "narrations_json": json.dumps(narrations, ensure_ascii=False, indent=2),
            "prompt_context_entries": prompt_context_entries,
            "write_chinese_fields": resolved_prompt_language == CHINESE_PROMPT_LANGUAGE,
        },
    )


def parse_storyboard_frames(raw_response: str) -> list[FramePlan]:
    """Parse storyboard frame plans from an LLM response."""

    payload = _extract_json_payload(raw_response)
    if not isinstance(payload, dict):
        raise ValueError("storyboard planning response must be a JSON object")

    try:
        response = StoryboardPlanningResponse.model_validate(payload)
    except ValidationError as exc:
        errors = exc.errors()
        if any(error["type"] == "missing" and error["loc"] == ("frames",) for error in errors):
            raise ValueError("storyboard planning response must include a frames array") from exc
        if any(error["loc"] == ("frames",) and error["type"] == "list_type" for error in errors):
            raise ValueError("storyboard planning response frames must be a list") from exc
        if any("scene_id" in ".".join(str(part) for part in error["loc"]) for error in errors):
            raise ValueError("storyboard frame field scene_id must be a string or integer-like number") from exc

        first_error = errors[0] if errors else None
        if first_error and first_error["type"] == "missing":
            missing_field = first_error["loc"][-1] if first_error["loc"] else "unknown"
            raise ValueError(f"missing required storyboard frame field: {missing_field}") from exc
        if first_error:
            field_name = next(
                (
                    str(part)
                    for part in reversed(first_error["loc"])
                    if isinstance(part, str) and part != "frames"
                ),
                "unknown",
            )
            raise ValueError(f"storyboard frame field {field_name} {first_error['msg']}") from exc
        raise ValueError("storyboard planning response validation failed") from exc

    return response.to_frame_plans()


__all__ = [
    "build_storyboard_planning_prompt",
    "parse_storyboard_frames",
]


def build_storyboard_planning_prompt(
    *,
    narrations: list[str],
    prompt_contexts: PromptContextInput | None = None,
    generation_world_profile: Mapping[str, Any] | None = None,
    world_preset: Mapping[str, Any],
    shot_preset: Mapping[str, Any],
    resolved_mode: str,
    consistency_strength: str,
    role_strategy: str = "auto",
    role_locking_strength: str = "standard",
    shot_strategy: str = "adaptive",
    scene_id_start: int = 1,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
) -> str:
    return render_storyboard_planning_prompt(
        narrations=narrations,
        prompt_contexts=prompt_contexts,
        generation_world_profile=generation_world_profile,
        world_preset=world_preset,
        shot_preset=shot_preset,
        resolved_mode=resolved_mode,
        consistency_strength=consistency_strength,
        role_strategy=role_strategy,
        role_locking_strength=role_locking_strength,
        shot_strategy=shot_strategy,
        scene_id_start=scene_id_start,
        prompt_language=prompt_language,
    ).text
