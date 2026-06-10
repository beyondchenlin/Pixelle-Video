from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

# This budget is intentionally below common provider limits because the visual
# anchor integration prompt also carries base briefs, policy, IP profile, schema,
# and repair context.
DEFAULT_MAX_TOTAL_CHARS = 9000
DEFAULT_MAX_TEXT_CHARS = 520

_FRAME_KEEP_KEYS = (
    "frame_id",
    "frame_index",
    "source_text",
    "frame_source_text",
    "visual_goal",
    "prompt_intent",
    "primary_subject",
    "secondary_subjects",
    "continuity_anchors",
    "selected_visual_route",
    "visual_story_frame_plan",
    "visual_story_ip_fusion_plan",
)
_MAPPING_PRIORITY_KEYS = (
    "route_id",
    "route_name",
    "route_type",
    "family",
    "visual_premise",
    "why_it_fits_article",
    "frame_system",
    "style_family",
    "recommended_ip_role",
    "scores",
    "frame_id",
    "frame_index",
    "local_claim",
    "visual_task",
    "route_application",
    "required_subjects",
    "forbidden_losses",
    "role",
    "visibility_tier",
    "scene_function",
    "placement_strategy",
    "identity_preservation",
    "style_harmony_rule",
    "negative_rules",
    "reason",
)


def compact_visual_anchor_contexts(
    *,
    frame_contexts: Sequence[Mapping[str, Any]],
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> dict[str, Any]:
    compact_frames = [
        compact_visual_story_frame_context(context)
        for context in frame_contexts
        if isinstance(context, Mapping)
    ]
    selected_route = _first_mapping(compact_frames, "selected_visual_route")
    frame_plans = [_mapping_value(context.get("visual_story_frame_plan")) for context in compact_frames]
    ip_plans = [_mapping_value(context.get("visual_story_ip_fusion_plan")) for context in compact_frames]
    frame_plans = [item for item in frame_plans if item]
    ip_plans = [item for item in ip_plans if item]

    payload = {
        "frame_contexts": compact_frames,
        "selected_visual_route": selected_route,
        "visual_story_frame_plans": frame_plans,
        "visual_story_ip_fusion_plans": ip_plans,
    }
    return _shrink_payload(payload, max_total_chars=max_total_chars)


def compact_visual_story_frame_context(context: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(context)
    compact: dict[str, Any] = {}
    for key in _FRAME_KEEP_KEYS:
        if key in source:
            compact[key] = compact_visual_story_value(source[key])
    return compact


def compact_visual_story_value(value: Any, *, max_text: int = DEFAULT_MAX_TEXT_CHARS, depth: int = 0) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        text = value.strip()
        return text if len(text) <= max_text else f"{text[:max_text].rstrip()}..."
    if isinstance(value, Mapping):
        if depth >= 2:
            return compact_visual_story_value(str(dict(value)), max_text=max_text)
        result: dict[str, Any] = {}
        for key in _MAPPING_PRIORITY_KEYS:
            if key in value:
                result[key] = compact_visual_story_value(value[key], max_text=max_text, depth=depth + 1)
        if result:
            return result
        for index, (key, item) in enumerate(value.items()):
            if index >= 8:
                break
            result[str(key)] = compact_visual_story_value(item, max_text=max_text, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [compact_visual_story_value(item, max_text=max_text, depth=depth + 1) for item in list(value)[:8]]
    text = str(value).strip()
    return text if len(text) <= max_text else f"{text[:max_text].rstrip()}..."


def _shrink_payload(payload: dict[str, Any], *, max_total_chars: int) -> dict[str, Any]:
    if len(str(payload)) <= max_total_chars:
        return payload
    # First pass: trim large source fields more aggressively.
    frames = []
    for frame in payload.get("frame_contexts", []):
        if not isinstance(frame, Mapping):
            continue
        small = dict(frame)
        for key in ("source_text", "frame_source_text", "visual_goal", "prompt_intent"):
            if key in small:
                small[key] = compact_visual_story_value(small[key], max_text=180)
        frames.append(small)
    payload = dict(payload)
    payload["frame_contexts"] = frames
    if len(str(payload)) <= max_total_chars:
        return payload
    # Second pass: keep route plus per-frame plans only.
    payload["frame_contexts"] = [
        {
            "frame_id": frame.get("frame_id"),
            "frame_index": frame.get("frame_index"),
            "visual_story_frame_plan": frame.get("visual_story_frame_plan"),
            "visual_story_ip_fusion_plan": frame.get("visual_story_ip_fusion_plan"),
        }
        for frame in frames
        if isinstance(frame, Mapping)
    ]
    return payload


def _first_mapping(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    for row in rows:
        value = row.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _mapping_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


__all__ = [
    "compact_visual_anchor_contexts",
    "compact_visual_story_frame_context",
    "compact_visual_story_value",
]
