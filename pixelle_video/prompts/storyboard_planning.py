"""Structured prompt helpers for storyboard planning."""

from __future__ import annotations

import json
from typing import Any, Mapping

from pixelle_video.models.storyboard_planning import FramePlan
from pixelle_video.utils.json_parsing import parse_llm_json_response

_ALLOWED_FRAME_SOURCES = {"planner_generated", "user_edited", "repair_adjusted", "fallback_regenerated"}
_ALLOWED_OVERRIDE_SOURCES = {"user_preview"}
_ALLOWED_REPLAN_SCOPES = {"local", "adjacent", "global"}


def _to_tuple(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _require_string_field(frame: Mapping[str, Any], field_name: str) -> str:
    value = frame[field_name]
    if not isinstance(value, str):
        raise ValueError(f"storyboard frame field {field_name} must be a string")
    return value


def _require_scene_id_field(frame: Mapping[str, Any]) -> str:
    value = frame["scene_id"]

    if isinstance(value, bool):
        raise ValueError("storyboard frame field scene_id must be a string or integer-like number")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        raise ValueError("storyboard frame field scene_id must be a string or integer-like number")
    if not isinstance(value, str):
        raise ValueError("storyboard frame field scene_id must be a string or integer-like number")

    normalized = value.strip()
    if not normalized:
        raise ValueError("storyboard frame field scene_id must be a non-empty string")
    return normalized


def _require_string_sequence_field(frame: Mapping[str, Any], field_name: str) -> tuple[str, ...]:
    value = frame[field_name]
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"storyboard frame field {field_name} must be a list or tuple of strings")

    values: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"storyboard frame field {field_name} must contain strings")
        values.append(item)
    return tuple(values)


def _require_override_source_field(frame: Mapping[str, Any]) -> str | None:
    value = frame["override_source"]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("storyboard frame field override_source must be a string or null")
    if value not in _ALLOWED_OVERRIDE_SOURCES:
        raise ValueError("storyboard frame field override_source has an unsupported value")
    return value


def _require_enum_field(frame: Mapping[str, Any], field_name: str, allowed_values: set[str]) -> str:
    value = _require_string_field(frame, field_name)
    if value not in allowed_values:
        raise ValueError(f"storyboard frame field {field_name} has an unsupported value")
    return value


def _extract_json_payload(raw_response: str) -> Any:
    text = raw_response.strip()
    if not text:
        raise ValueError("storyboard planning response does not contain JSON")

    try:
        return parse_llm_json_response(text, allow_code_fence=True, allow_embedded_json=False)
    except json.JSONDecodeError as exc:
        raise ValueError("storyboard planning response must be raw JSON only") from exc


def _build_frame_properties_schema() -> dict[str, Any]:
    return {
        "scene_id": {
            "type": "string",
            "description": 'Quoted string scene identifier matching narration order, for example "1", "2", "3". Never return it as a number.',
        },
        "narration_fragment": {"type": "string"},
        "knowledge_goal": {"type": "string"},
        "shot_type": {"type": "string"},
        "shot_purpose": {"type": "string"},
        "primary_subject": {"type": "string"},
        "secondary_subjects": {"type": "array", "items": {"type": "string"}},
        "world_elements": {"type": "array", "items": {"type": "string"}},
        "continuity_anchors": {"type": "array", "items": {"type": "string"}},
        "focus_detail": {"type": "string"},
        "prompt_intent": {"type": "string"},
        "locked_fields": {"type": "array", "items": {"type": "string"}},
        "override_source": {"type": ["string", "null"], "enum": [None, *sorted(_ALLOWED_OVERRIDE_SOURCES)]},
        "frame_source": {"type": "string", "enum": sorted(_ALLOWED_FRAME_SOURCES)},
        "replan_scope": {"type": "string", "enum": sorted(_ALLOWED_REPLAN_SCOPES)},
        "planner_version": {"type": "string"},
    }


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
    frame_properties = _build_frame_properties_schema()
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
        "required_output": {
            "type": "object",
            "properties": {
                "frames": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": required_frame_fields,
                        "properties": frame_properties,
                    },
                }
            },
        },
        "instructions": [
            "Return JSON only.",
            "Produce exactly one frame plan per narration.",
            "Keep the same order as the input narrations.",
            'Return every "scene_id" as a quoted string matching narration order, never a number.',
            "Make every array field contain strings only.",
            "Validate the final payload against required_output before returning it.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_storyboard_frames(raw_response: str) -> list[FramePlan]:
    """Parse storyboard frame plans from an LLM response."""

    payload = _extract_json_payload(raw_response)
    required_fields = FramePlan.required_prompt_fields()
    if not isinstance(payload, dict):
        raise ValueError("storyboard planning response must be a JSON object")
    if "frames" not in payload:
        raise ValueError("storyboard planning response must include a frames array")

    frames_data = payload["frames"]
    if not isinstance(frames_data, list):
        raise ValueError("storyboard planning response frames must be a list")

    plans: list[FramePlan] = []
    for frame in frames_data:
        if not isinstance(frame, Mapping):
            raise ValueError("storyboard planning response frames must contain objects")

        for field_name in required_fields:
            if field_name not in frame:
                raise ValueError(f"missing required storyboard frame field: {field_name}")
            if field_name != "override_source" and frame[field_name] is None:
                raise ValueError(f"missing required storyboard frame field: {field_name}")

        plans.append(
            FramePlan(
                scene_id=_require_scene_id_field(frame),
                narration_fragment=_require_string_field(frame, "narration_fragment"),
                knowledge_goal=_require_string_field(frame, "knowledge_goal"),
                shot_type=_require_string_field(frame, "shot_type"),
                shot_purpose=_require_string_field(frame, "shot_purpose"),
                primary_subject=_require_string_field(frame, "primary_subject"),
                secondary_subjects=_require_string_sequence_field(frame, "secondary_subjects"),
                world_elements=_require_string_sequence_field(frame, "world_elements"),
                continuity_anchors=_require_string_sequence_field(frame, "continuity_anchors"),
                focus_detail=_require_string_field(frame, "focus_detail"),
                prompt_intent=_require_string_field(frame, "prompt_intent"),
                locked_fields=_require_string_sequence_field(frame, "locked_fields"),
                override_source=_require_override_source_field(frame),
                frame_source=_require_enum_field(frame, "frame_source", _ALLOWED_FRAME_SOURCES),
                replan_scope=_require_enum_field(frame, "replan_scope", _ALLOWED_REPLAN_SCOPES),
                planner_version=_require_string_field(frame, "planner_version"),
            )
        )

    return plans


__all__ = [
    "build_storyboard_planning_prompt",
    "parse_storyboard_frames",
]
