"""Storyboard frame consistency helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, Mapping, Sequence

from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.models.storyboard_planning import FramePlan
from pixelle_video.models.video_generation_contract import (
    PLAN_FRAME_OVERRIDE_IDENTITY_FIELDS,
    PLAN_FRAME_OVERRIDE_VALUE_FIELDS,
    normalize_plan_frame_overrides,
)

_USER_OVERRIDE_FIELDS = {
    "narration_fragment",
    "knowledge_goal",
    "shot_type",
    "shot_purpose",
    "primary_subject",
    "secondary_subjects",
    "world_elements",
    "continuity_anchors",
    "focus_detail",
    "prompt_intent",
}
_OVERRIDE_METADATA_FIELDS = {"scene_id", "snapshot_identity", "locked_fields", "override_source"}
_PLAN_OVERRIDE_TO_FRAME_PLAN_FIELD = {
    "source_text": "narration_fragment",
    "visual_goal": "knowledge_goal",
    "prompt_intent": "prompt_intent",
    "shot_type": "shot_type",
    "shot_purpose": "shot_purpose",
    "primary_subject": "primary_subject",
    "secondary_subjects": "secondary_subjects",
    "world_elements": "world_elements",
    "continuity_anchors": "continuity_anchors",
    "focus_detail": "focus_detail",
}
_MANDATORY_ANCHOR_OVERRIDE_FIELDS = (
    PLAN_FRAME_OVERRIDE_VALUE_FIELDS - set(_PLAN_OVERRIDE_TO_FRAME_PLAN_FIELD)
)
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


def _ensure_override_sequence(field_name: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"frame override field {field_name} must be a list or tuple of strings")

    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"frame override field {field_name} must contain non-empty strings")
        normalized.append(item)
    return tuple(normalized)


def _ensure_override_scalar(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"frame override field {field_name} must be a non-empty string")
    return value


def _merge_locked_fields(*, original: FramePlan, override_locked_fields: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()

    for field_name in (*original.locked_fields, *override_locked_fields):
        if field_name in _USER_OVERRIDE_FIELDS and field_name not in seen:
            merged.append(field_name)
            seen.add(field_name)

    return tuple(merged)


def _build_frame_plan_snapshot_identity(frame_plans: Sequence[FramePlan]) -> str:
    canonical_payload = json.dumps(
        [frame.to_prompt_dict() for frame in frame_plans],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    fingerprint = hashlib.sha1(canonical_payload.encode("utf-8")).hexdigest()
    return f"storyboard_snapshot_{fingerprint}"


def _get_max_consecutive_same(shot_rules: Any) -> int:
    if isinstance(shot_rules, Mapping):
        value = shot_rules.get("max_consecutive_same")
        if value is not None:
            return max(1, int(value))

    value = getattr(shot_rules, "max_consecutive_same", None)
    if value is not None:
        return max(1, int(value))

    return 2


def _is_shot_locked(frame: FramePlan) -> bool:
    return "shot_type" in frame.locked_fields


def _max_consecutive_run_length(shot_types: Sequence[str]) -> int:
    max_run = 0
    current = None
    run_length = 0

    for shot_type in shot_types:
        if shot_type == current:
            run_length += 1
        else:
            current = shot_type
            run_length = 1
        max_run = max(max_run, run_length)

    return max_run


def _candidate_repair_shot_types(previous_shot_type: str | None, next_shot_type: str | None, current_shot_type: str) -> tuple[str, ...]:
    preferred: list[str] = []
    fallback: list[str] = []

    for candidate in _REPAIR_SHOT_TYPE_PRIORITY:
        if candidate == current_shot_type:
            continue
        if candidate == previous_shot_type or candidate == next_shot_type:
            continue
        preferred.append(candidate)

    if preferred:
        return tuple(preferred)

    for candidate in _REPAIR_SHOT_TYPE_PRIORITY:
        if candidate != current_shot_type:
            fallback.append(candidate)

    return tuple(fallback)


def _try_repair_run(
    repaired: list[FramePlan],
    *,
    run_start: int,
    run_end: int,
    max_consecutive_same: int,
) -> bool:
    unlocked_indices = [index for index in range(run_end - 1, run_start - 1, -1) if not _is_shot_locked(repaired[index])]
    if not unlocked_indices:
        return False

    for repair_index in unlocked_indices:
        previous_shot_type = repaired[repair_index - 1].shot_type if repair_index > 0 else None
        next_shot_type = repaired[repair_index + 1].shot_type if repair_index + 1 < len(repaired) else None
        current_shot_type = repaired[repair_index].shot_type

        for candidate_shot_type in _candidate_repair_shot_types(
            previous_shot_type,
            next_shot_type,
            current_shot_type,
        ):
            candidate_frames = list(repaired)
            candidate_frames[repair_index] = replace(
                repaired[repair_index],
                shot_type=candidate_shot_type,
                frame_source="repair_adjusted",
            )
            if _max_consecutive_run_length(frame.shot_type for frame in candidate_frames) <= max_consecutive_same:
                repaired[repair_index] = candidate_frames[repair_index]
                return True

    return False


def apply_frame_overrides(
    *,
    frame_plans: Sequence[FramePlan],
    frame_overrides: Sequence[Mapping[str, Any]] | None,
    prompt_contexts: PromptContextEnvelope | None = None,
) -> list[FramePlan]:
    """Apply preview/user overrides to the matching frame plans."""

    if not frame_overrides:
        return list(frame_plans)

    current_snapshot_identity = _build_frame_plan_snapshot_identity(frame_plans)
    by_scene_id = {frame.scene_id: frame for frame in frame_plans}
    ordered_scene_ids = [frame.scene_id for frame in frame_plans]
    plan_context = dict((prompt_contexts.plan_context if prompt_contexts is not None else {}) or {})
    frame_ids_by_scene_id = _frame_ids_by_scene_id(
        frame_plans=frame_plans,
        prompt_contexts=prompt_contexts,
    )

    for override in frame_overrides:
        if not isinstance(override, Mapping):
            raise ValueError("frame override must be a mapping")

        if PLAN_FRAME_OVERRIDE_IDENTITY_FIELDS <= set(override.keys()):
            _apply_plan_identity_override(
                by_scene_id=by_scene_id,
                frame_ids_by_scene_id=frame_ids_by_scene_id,
                plan_context=plan_context,
                override=override,
            )
        else:
            _apply_legacy_override(
                by_scene_id=by_scene_id,
                current_snapshot_identity=current_snapshot_identity,
                override=override,
            )

    return [by_scene_id[scene_id] for scene_id in ordered_scene_ids]


def _frame_ids_by_scene_id(
    *,
    frame_plans: Sequence[FramePlan],
    prompt_contexts: PromptContextEnvelope | None,
) -> dict[str, str]:
    if prompt_contexts is None:
        return {}
    frame_contexts = tuple(prompt_contexts.frame_contexts)
    if len(frame_contexts) != len(frame_plans):
        raise ValueError("prompt_contexts must match frame plan count")

    mapping: dict[str, str] = {}
    for frame_plan, frame_context in zip(frame_plans, frame_contexts):
        frame_id = frame_context.get("frame_id")
        if frame_id is not None:
            mapping[frame_plan.scene_id] = _ensure_override_scalar("frame_id", frame_id)
    return mapping


def _apply_legacy_override(
    *,
    by_scene_id: dict[str, FramePlan],
    current_snapshot_identity: str,
    override: Mapping[str, Any],
) -> str:
    invalid_keys = set(override.keys()) - _USER_OVERRIDE_FIELDS - _OVERRIDE_METADATA_FIELDS
    if invalid_keys:
        raise ValueError(f"unsupported frame override field: {sorted(invalid_keys)[0]}")

    scene_id = _ensure_override_scalar("scene_id", override.get("scene_id"))
    snapshot_identity = _ensure_override_scalar("snapshot_identity", override.get("snapshot_identity"))
    if snapshot_identity != current_snapshot_identity:
        raise ValueError("frame override snapshot_identity does not match current frame plans")

    original = by_scene_id.get(scene_id)
    if original is None:
        raise ValueError(f"frame override scene_id does not match any frame plan: {scene_id}")

    by_scene_id[scene_id] = _replace_frame_plan_values(
        original=original,
        requested_locked_fields=_ensure_legacy_locked_fields(override.get("locked_fields")),
        override=override,
    )
    return scene_id


def _apply_plan_identity_override(
    *,
    by_scene_id: dict[str, FramePlan],
    frame_ids_by_scene_id: Mapping[str, str],
    plan_context: Mapping[str, Any],
    override: Mapping[str, Any],
) -> str:
    if not frame_ids_by_scene_id:
        raise ValueError("plan-identity frame overrides require prompt_contexts with frame_id values")

    override = normalize_plan_frame_overrides([override])[0]

    invalid_keys = (
        set(override.keys())
        - PLAN_FRAME_OVERRIDE_IDENTITY_FIELDS
        - PLAN_FRAME_OVERRIDE_VALUE_FIELDS
        - {"locked_fields", "override_source"}
    )
    if invalid_keys:
        raise ValueError(f"unsupported frame override field: {sorted(invalid_keys)[0]}")

    plan_id = _ensure_override_scalar("plan_id", override.get("plan_id"))
    if _ensure_override_scalar("plan_id", plan_context.get("plan_id")) != plan_id:
        raise ValueError("frame override plan_id does not match current prompt contexts")

    plan_revision = override.get("plan_revision")
    if type(plan_revision) is not int or plan_revision < 1:
        raise ValueError("frame override plan_revision must be a positive integer")
    current_plan_revision = plan_context.get("plan_revision")
    if type(current_plan_revision) is not int or current_plan_revision != plan_revision:
        raise ValueError("frame override plan_revision does not match current prompt contexts")

    source_digest = _ensure_override_scalar("source_digest", override.get("source_digest"))
    if _ensure_override_scalar("source_digest", plan_context.get("source_digest")) != source_digest:
        raise ValueError("frame override source_digest does not match current prompt contexts")

    frame_id = _ensure_override_scalar("frame_id", override.get("frame_id"))
    scene_id = next(
        (candidate_scene_id for candidate_scene_id, candidate_frame_id in frame_ids_by_scene_id.items() if candidate_frame_id == frame_id),
        None,
    )
    if scene_id is None:
        raise ValueError("frame override frame_id does not match current prompt contexts")

    original = by_scene_id.get(scene_id)
    if original is None:
        raise ValueError(f"frame override frame_id does not match any frame plan: {frame_id}")

    raw_locked_fields = _ensure_override_sequence(
        "locked_fields", override.get("locked_fields")
    )
    for field_name in _MANDATORY_ANCHOR_OVERRIDE_FIELDS:
        if field_name in override and field_name not in raw_locked_fields:
            raise ValueError(
                f"frame override field {field_name} must be listed in locked_fields"
            )
    requested_locked_fields = _ensure_plan_locked_fields(raw_locked_fields)
    translated_override = {
        _PLAN_OVERRIDE_TO_FRAME_PLAN_FIELD[field_name]: override[field_name]
        for field_name in PLAN_FRAME_OVERRIDE_VALUE_FIELDS
        if field_name in override and field_name in _PLAN_OVERRIDE_TO_FRAME_PLAN_FIELD
    }
    if "override_source" in override:
        translated_override["override_source"] = override["override_source"]
    if not requested_locked_fields:
        override_source = translated_override.get("override_source")
        if override_source is not None and override_source != "user_preview":
            raise ValueError("unsupported frame override_source")
        return scene_id
    by_scene_id[scene_id] = _replace_frame_plan_values(
        original=original,
        requested_locked_fields=requested_locked_fields,
        override=translated_override,
    )
    return scene_id


def _ensure_legacy_locked_fields(value: Any) -> tuple[str, ...]:
    requested_locked_fields = _ensure_override_sequence("locked_fields", value)
    invalid_locked_fields = [
        field_name for field_name in requested_locked_fields if field_name not in _USER_OVERRIDE_FIELDS
    ]
    if invalid_locked_fields:
        raise ValueError(f"unsupported locked frame field: {invalid_locked_fields[0]}")
    return requested_locked_fields


def _ensure_plan_locked_fields(value: Any) -> tuple[str, ...]:
    requested_locked_fields = _ensure_override_sequence("locked_fields", value)
    invalid_locked_fields = [
        field_name
        for field_name in requested_locked_fields
        if field_name not in _PLAN_OVERRIDE_TO_FRAME_PLAN_FIELD
        and field_name not in _MANDATORY_ANCHOR_OVERRIDE_FIELDS
    ]
    if invalid_locked_fields:
        raise ValueError(f"unsupported locked frame field: {invalid_locked_fields[0]}")
    return tuple(
        _PLAN_OVERRIDE_TO_FRAME_PLAN_FIELD[field_name]
        for field_name in requested_locked_fields
        if field_name in _PLAN_OVERRIDE_TO_FRAME_PLAN_FIELD
    )


def _replace_frame_plan_values(
    *,
    original: FramePlan,
    requested_locked_fields: tuple[str, ...],
    override: Mapping[str, Any],
) -> FramePlan:
    provided_override_fields = [
        field_name for field_name in override.keys() if field_name in _USER_OVERRIDE_FIELDS
    ]
    for field_name in provided_override_fields:
        if field_name not in requested_locked_fields:
            raise ValueError(f"frame override field {field_name} must be listed in locked_fields")

    locked_fields = _merge_locked_fields(
        original=original,
        override_locked_fields=requested_locked_fields,
    )
    override_source = override.get("override_source", original.override_source)
    if override_source is not None:
        override_source = _ensure_override_scalar("override_source", override_source)
        if override_source != "user_preview":
            raise ValueError("unsupported frame override_source")

    replacement_values: dict[str, Any] = {
        "locked_fields": locked_fields,
        "override_source": override_source,
        "frame_source": "user_edited",
    }

    for field_name in requested_locked_fields:
        if field_name not in override:
            continue

        value = override[field_name]
        if field_name in {"secondary_subjects", "world_elements", "continuity_anchors"}:
            replacement_values[field_name] = _ensure_override_sequence(field_name, value)
        else:
            replacement_values[field_name] = _ensure_override_scalar(field_name, value)

    return replace(original, **replacement_values)


def repair_frame_plan_shots(
    *,
    frame_plans: Sequence[FramePlan],
    shot_rules: Any,
) -> list[FramePlan]:
    """Repair overlong same-shot runs by adjusting unlocked frames only."""

    if not frame_plans:
        return []

    max_consecutive_same = _get_max_consecutive_same(shot_rules)
    repaired = list(frame_plans)

    while True:
        changed = False
        run_start = 0

        for index in range(1, len(repaired) + 1):
            run_ended = index == len(repaired) or repaired[index].shot_type != repaired[run_start].shot_type
            if not run_ended:
                continue

            run_length = index - run_start
            if run_length > max_consecutive_same and _try_repair_run(
                repaired,
                run_start=run_start,
                run_end=index,
                max_consecutive_same=max_consecutive_same,
            ):
                changed = True
                break

            run_start = index

        if not changed:
            break

    return repaired


__all__ = [
    "apply_frame_overrides",
    "repair_frame_plan_shots",
]
