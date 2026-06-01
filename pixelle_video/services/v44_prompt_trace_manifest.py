from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from pixelle_video.models.mode_resolution import JSONValue, VisualPlanningRouteDecision


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
    requested_modes_payload = _json_safe_copy(requested_modes, "requested_modes")
    decisions = _normalize_route_decisions(route_decisions)
    critic_status_value = _require_text("critic_status", critic_status)
    repair_rounds_value = _repair_rounds_value(repair_rounds)

    first_decision = decisions[0] if decisions else None
    resolved_modes: dict[str, JSONValue] = {
        "primary_lens": (
            first_decision.resolved_primary_lens.value if first_decision else None
        ),
        "visual_planning_mode": (
            first_decision.resolved_visual_planning_mode.value if first_decision else None
        ),
        "visual_role_strategy": (
            first_decision.resolved_visual_role_strategy.value if first_decision else None
        ),
    }

    route_decision_payloads = [decision.to_dict() for decision in decisions]
    manifest: dict[str, JSONValue] = {
        "schema_version": "v4.4",
        "article_id": article_id_value,
        "frames": frames,
        "requested_modes": requested_modes_payload,
        "resolved_modes": resolved_modes,
        "route_decision_ids": {
            decision.frame_id: decision.route_decision_id for decision in decisions
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
    return frames


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
