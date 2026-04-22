"""Structured prompt helpers for storyboard planning."""

from __future__ import annotations

import json
from typing import Any, Mapping

from pydantic import ValidationError

from pixelle_video.models.storyboard_planning import FramePlan, StoryboardPlanningResponse
from pixelle_video.utils.json_parsing import parse_llm_json_response


def _extract_json_payload(raw_response: str) -> Any:
    text = raw_response.strip()
    if not text:
        raise ValueError("storyboard planning response does not contain JSON")

    try:
        return parse_llm_json_response(text, allow_code_fence=True, allow_embedded_json=False)
    except json.JSONDecodeError as exc:
        raise ValueError("storyboard planning response must contain only a JSON payload") from exc


def build_storyboard_planning_prompt(
    *,
    narrations: list[str],
    world_preset: Mapping[str, Any],
    shot_preset: Mapping[str, Any],
    resolved_mode: str,
    consistency_strength: str,
    role_strategy: str = "auto",
    role_locking_strength: str = "standard",
    shot_strategy: str = "adaptive",
) -> str:
    """Build the structured planning prompt sent to the LLM."""

    required_frame_fields = list(FramePlan.required_prompt_fields())
    payload = {
        "task": "plan_storyboard_frames",
        "resolved_mode": resolved_mode,
        "consistency_strength": consistency_strength,
        "role_strategy": role_strategy,
        "role_locking_strength": role_locking_strength,
        "shot_strategy": shot_strategy,
        "narrations": narrations,
        "world_preset": dict(world_preset),
        "shot_preset": dict(shot_preset),
        "required_frame_fields": required_frame_fields,
        "required_output": StoryboardPlanningResponse.model_json_schema(),
        "instructions": [
            "Return JSON only.",
            "Produce exactly one frame plan per narration.",
            "Keep the same order as the input narrations.",
            'Return every "scene_id" as a quoted string matching narration order, never a number.',
            "Make every array field contain strings only.",
            "Validate the final payload against required_output before returning it.",
            "Do not wrap the JSON in markdown fences.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


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
