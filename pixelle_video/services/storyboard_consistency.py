"""Storyboard frame consistency helpers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from pixelle_video.models.storyboard_planning import FramePlan

_FRAME_FIELDS = set(FramePlan.__dataclass_fields__.keys())
_REPAIR_SHOT_TYPE_PRIORITY = (
    "close_up",
    "medium_shot",
    "wide_shot",
    "full_shot",
    "detail_close_up",
    "extreme_close_up",
    "long_shot",
    "establishing_shot",
)


def _to_tuple(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _get_max_consecutive_same(shot_rules: Any) -> int:
    if isinstance(shot_rules, Mapping):
        value = shot_rules.get("max_consecutive_same")
        if value is not None:
            return max(1, int(value))

    value = getattr(shot_rules, "max_consecutive_same", None)
    if value is not None:
        return max(1, int(value))

    return 2


def _select_repair_shot_type(previous_shot_type: str, next_shot_type: str | None) -> str:
    for candidate in _REPAIR_SHOT_TYPE_PRIORITY:
        if candidate == previous_shot_type:
            continue
        if next_shot_type is not None and candidate == next_shot_type:
            continue
        return candidate

    for candidate in _REPAIR_SHOT_TYPE_PRIORITY:
        if candidate != previous_shot_type:
            return candidate

    return "medium_shot"


def apply_frame_overrides(
    *,
    frame_plans: Sequence[FramePlan],
    frame_overrides: Sequence[Mapping[str, Any]] | None,
) -> list[FramePlan]:
    """Apply preview/user overrides to the matching frame plans."""

    if not frame_overrides:
        return list(frame_plans)

    by_scene_id = {frame.scene_id: frame for frame in frame_plans}
    ordered_scene_ids = [frame.scene_id for frame in frame_plans]

    for override in frame_overrides:
        scene_id = override.get("scene_id")
        if scene_id is None:
            continue

        original = by_scene_id.get(str(scene_id))
        if original is None:
            continue

        locked_fields = tuple(
            field_name for field_name in _to_tuple(override.get("locked_fields")) if field_name in _FRAME_FIELDS
        )
        replacement_values: dict[str, Any] = {
            "locked_fields": locked_fields,
            "override_source": override.get("override_source", original.override_source),
            "frame_source": "user_edited",
        }

        for field_name in locked_fields:
            if field_name in override:
                value = override[field_name]
                if field_name in {"secondary_subjects", "world_elements", "continuity_anchors", "locked_fields"}:
                    value = _to_tuple(value)
                replacement_values[field_name] = value

        by_scene_id[str(scene_id)] = replace(original, **replacement_values)

    return [by_scene_id[scene_id] for scene_id in ordered_scene_ids]


def repair_frame_plan_shots(
    *,
    frame_plans: Sequence[FramePlan],
    shot_rules: Any,
) -> list[FramePlan]:
    """Repair overlong same-shot runs by converting later frames to close_up."""

    if not frame_plans:
        return []

    max_consecutive_same = _get_max_consecutive_same(shot_rules)
    repaired = list(frame_plans)

    run_start = 0
    for index in range(1, len(repaired) + 1):
        run_ended = index == len(repaired) or repaired[index].shot_type != repaired[run_start].shot_type
        if not run_ended:
            continue

        run_length = index - run_start
        if run_length > max_consecutive_same:
            for repair_index in range(run_start + max_consecutive_same, index):
                previous_shot_type = repaired[repair_index - 1].shot_type
                next_shot_type = repaired[repair_index + 1].shot_type if repair_index + 1 < len(repaired) else None
                repaired[repair_index] = replace(
                    repaired[repair_index],
                    shot_type=_select_repair_shot_type(previous_shot_type, next_shot_type),
                    frame_source="repair_adjusted",
                )

        run_start = index

    return repaired


__all__ = [
    "apply_frame_overrides",
    "repair_frame_plan_shots",
]
