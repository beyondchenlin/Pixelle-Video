"""Structured prompt helpers for storyboard planning."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from pixelle_video.models.storyboard_planning import FramePlan


def _to_tuple(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _extract_json_payload(raw_response: str) -> Any:
    text = raw_response.strip()

    fenced_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text, re.IGNORECASE)
    if fenced_match:
        text = fenced_match.group(1).strip()

    if text.startswith("{") or text.startswith("["):
        return json.loads(text)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("storyboard planning response does not contain JSON")


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
        "required_output": {
            "type": "object",
            "properties": {
                "frames": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": required_frame_fields,
                    },
                }
            },
        },
        "instructions": [
            "Return JSON only.",
            "Produce exactly one frame plan per narration.",
            "Keep the same order as the input narrations.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_storyboard_frames(raw_response: str) -> list[FramePlan]:
    """Parse storyboard frame plans from an LLM response."""

    payload = _extract_json_payload(raw_response)
    required_fields = FramePlan.required_prompt_fields()
    frames_data: Any

    if isinstance(payload, list):
        frames_data = payload
    elif isinstance(payload, dict):
        frames_data = payload.get("frames", [])
    else:
        raise ValueError("storyboard planning response must be a JSON object or array")

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
                scene_id=str(frame["scene_id"]),
                narration_fragment=str(frame["narration_fragment"]),
                knowledge_goal=str(frame["knowledge_goal"]),
                shot_type=str(frame["shot_type"]),
                shot_purpose=str(frame["shot_purpose"]),
                primary_subject=str(frame["primary_subject"]),
                secondary_subjects=_to_tuple(frame["secondary_subjects"]),
                world_elements=_to_tuple(frame["world_elements"]),
                continuity_anchors=_to_tuple(frame["continuity_anchors"]),
                focus_detail=str(frame["focus_detail"]),
                prompt_intent=str(frame["prompt_intent"]),
                locked_fields=tuple(str(value) for value in _to_tuple(frame["locked_fields"])),
                override_source=frame["override_source"],
                frame_source=str(frame["frame_source"]),
                replan_scope=str(frame["replan_scope"]),
                planner_version=str(frame["planner_version"]),
            )
        )

    return plans


__all__ = [
    "build_storyboard_planning_prompt",
    "parse_storyboard_frames",
]
