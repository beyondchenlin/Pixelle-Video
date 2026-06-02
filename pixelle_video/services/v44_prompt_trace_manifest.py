from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from pixelle_video.models.mode_resolution import JSONValue, VisualPlanningRouteDecision

_RESOLVED_MODE_KEYS = (
    "primary_lens",
    "visual_planning_mode",
    "visual_role_strategy",
)


def build_v44_prompt_trace_manifest(
    article_id: Any,
    frame_ids: Any,
    requested_modes: Mapping[str, Any],
    route_decisions: Sequence[VisualPlanningRouteDecision],
    critic_status: Any,
    repair_rounds: Any,
) -> dict[str, JSONValue]:
    article_id_value = _require_text("article_id", article_id)
    frames = _normalize_frame_ids(frame_ids)
    requested_modes_payload = _normalize_requested_modes(requested_modes)
    decisions = _normalize_route_decisions(route_decisions)
    decisions_by_frame = _route_decisions_by_frame(frames, decisions)
    critic_status_value = _require_text("critic_status", critic_status)
    repair_rounds_value = _repair_rounds_value(repair_rounds)

    resolved_modes_by_frame: dict[str, JSONValue] = {
        frame_id: _resolved_modes_for_decision(decision)
        for frame_id, decision in decisions_by_frame.items()
    }
    resolved_modes = _aggregate_resolved_modes(resolved_modes_by_frame)

    route_decision_payloads = [decision.to_dict() for decision in decisions]
    manifest: dict[str, JSONValue] = {
        "schema_version": "v4.4",
        "article_id": article_id_value,
        "frames": frames,
        "requested_modes": requested_modes_payload,
        "resolved_modes": resolved_modes,
        "resolved_modes_by_frame": resolved_modes_by_frame,
        "route_decision_ids": {
            frame_id: decision.route_decision_id
            for frame_id, decision in decisions_by_frame.items()
        },
        "fallbacks": [
            {
                "frame_id": decision.frame_id,
                "route_decision_id": decision.route_decision_id,
                "fallback_target": decision.fallback_target,
                "fallback_reason": decision.fallback_reason,
                "resolution_status": decision.resolution_status,
            }
            for decision in decisions
            if decision.fallback_used or decision.fallback_target is not None
        ],
        "critic_status": critic_status_value,
        "repair_rounds": repair_rounds_value,
        "route_decisions": route_decision_payloads,
    }
    _assert_strict_json(manifest)
    return manifest


def write_v44_prompt_trace_manifest(
    task_dir: str | Path,
    **kwargs: Any,
) -> Path:
    manifest = build_v44_prompt_trace_manifest(**kwargs)
    output_path = Path(task_dir) / "prompt_traces" / "manifest.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def _require_text(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _normalize_frame_ids(frame_ids: Any) -> list[JSONValue]:
    if isinstance(frame_ids, str) or not isinstance(frame_ids, Sequence):
        raise TypeError("frame_ids must be a non-empty sequence of non-empty strings")
    frames = [_require_text("frame_ids", frame_id) for frame_id in frame_ids]
    if not frames:
        raise ValueError("frame_ids must contain at least one non-empty string")
    duplicates = _duplicates(frames)
    if duplicates:
        raise ValueError(
            "frame_ids must not contain duplicates: " + ", ".join(duplicates)
        )
    return frames


def _normalize_requested_modes(requested_modes: Any) -> dict[str, JSONValue]:
    if not isinstance(requested_modes, Mapping):
        raise TypeError("requested_modes must be a mapping")

    copied: dict[str, JSONValue] = {}
    for key, value in requested_modes.items():
        if not isinstance(key, str) or not key.strip():
            raise TypeError("requested_modes keys must be non-empty strings")
        copied[key.strip()] = _json_safe_copy(value, "requested_modes")
    return copied


def _normalize_route_decisions(route_decisions: Any) -> list[VisualPlanningRouteDecision]:
    if isinstance(route_decisions, str) or not isinstance(route_decisions, Sequence):
        raise TypeError("route_decisions must be a sequence of VisualPlanningRouteDecision")
    decisions = list(route_decisions)
    for decision in decisions:
        if not isinstance(decision, VisualPlanningRouteDecision):
            raise TypeError(
                "route_decisions must contain only VisualPlanningRouteDecision instances"
            )
    return decisions


def _route_decisions_by_frame(
    frames: Sequence[str],
    decisions: Sequence[VisualPlanningRouteDecision],
) -> dict[str, VisualPlanningRouteDecision]:
    if not decisions:
        raise ValueError("route_decisions must include one decision for each frame_id")

    expected = set(frames)
    decisions_by_frame: dict[str, VisualPlanningRouteDecision] = {}
    duplicates: list[str] = []
    for decision in decisions:
        if decision.frame_id in decisions_by_frame:
            duplicates.append(decision.frame_id)
        decisions_by_frame[decision.frame_id] = decision
    if duplicates:
        duplicate_list = ", ".join(sorted(set(duplicates)))
        raise ValueError(f"route_decisions contain duplicate frame_id values: {duplicate_list}")

    missing = [frame_id for frame_id in frames if frame_id not in decisions_by_frame]
    extra = [frame_id for frame_id in decisions_by_frame if frame_id not in expected]
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if extra:
            details.append("extra: " + ", ".join(sorted(extra)))
        raise ValueError("route_decisions frame_id coverage must match frame_ids (" + "; ".join(details) + ")")

    return {frame_id: decisions_by_frame[frame_id] for frame_id in frames}


def _duplicates(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _resolved_modes_for_decision(decision: VisualPlanningRouteDecision) -> dict[str, JSONValue]:
    return {
        "primary_lens": decision.resolved_primary_lens.value,
        "visual_planning_mode": decision.resolved_visual_planning_mode.value,
        "visual_role_strategy": decision.resolved_visual_role_strategy.value,
    }


def _aggregate_resolved_modes(
    resolved_modes_by_frame: Mapping[str, JSONValue],
) -> dict[str, JSONValue]:
    if not resolved_modes_by_frame:
        return {
            "aggregation": "none",
            "primary_lens": None,
            "visual_planning_mode": None,
            "visual_role_strategy": None,
            "mixed_fields": [],
        }

    frame_modes = list(resolved_modes_by_frame.values())
    aggregate: dict[str, JSONValue] = {"aggregation": "uniform"}
    mixed_fields: list[JSONValue] = []
    for key in _RESOLVED_MODE_KEYS:
        values = {
            frame_payload[key]
            for frame_payload in frame_modes
            if isinstance(frame_payload, Mapping)
        }
        if len(values) == 1:
            aggregate[key] = next(iter(values))
        else:
            aggregate[key] = None
            mixed_fields.append(key)
    if mixed_fields:
        aggregate["aggregation"] = "mixed"
    aggregate["mixed_fields"] = mixed_fields
    return aggregate


def _repair_rounds_value(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("repair_rounds must be a non-negative integer")
    if value < 0:
        raise ValueError("repair_rounds must be a non-negative integer")
    return value


def _json_safe_copy(value: Any, field_name: str) -> JSONValue:
    if isinstance(value, Enum):
        return _json_safe_copy(value.value, field_name)
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, float):
        _assert_strict_json(value)
        return value
    if isinstance(value, Mapping):
        copied: dict[str, JSONValue] = {}
        for key, item in value.items():
            if isinstance(key, Enum):
                key = key.value
            if not isinstance(key, str):
                raise TypeError(f"{field_name} must have string keys")
            copied[key] = _json_safe_copy(item, field_name)
        return copied
    if isinstance(value, str) or isinstance(value, bytes):
        raise TypeError(f"{field_name} must be JSON-safe")
    if isinstance(value, Sequence):
        return [_json_safe_copy(item, field_name) for item in value]
    raise TypeError(f"{field_name} must be JSON-safe")


def _assert_strict_json(value: Any) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("manifest values must be strict JSON-safe") from exc


__all__ = [
    "build_v44_prompt_trace_manifest",
    "write_v44_prompt_trace_manifest",
]
