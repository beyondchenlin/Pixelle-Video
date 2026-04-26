from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.models.storyboard_plan import (
    ScriptLengthMode,
    StoryboardCountMode,
    StoryboardGenerationMode,
    StoryboardPlan,
)
from pixelle_video.models.storyboard_limits import (
    DEFAULT_STORYBOARD_GENERATION_LIMITS,
    StoryboardGenerationLimits,
    storyboard_generation_limits_from_config,
)

LEGACY_STANDARD_STORYBOARD_PARAMS = frozenset(
    {
        "n_scenes",
        "split_mode",
        "min_narration_words",
        "max_narration_words",
    }
)

PLAN_FRAME_OVERRIDE_IDENTITY_FIELDS = frozenset(
    {
        "plan_id",
        "plan_revision",
        "frame_id",
        "source_digest",
    }
)
LEGACY_FRAME_OVERRIDE_IDENTITY_FIELDS = frozenset({"scene_id", "snapshot_identity"})
PLAN_FRAME_OVERRIDE_VALUE_FIELDS = frozenset(
    {
        "source_text",
        "visual_goal",
        "prompt_intent",
        "shot_type",
        "shot_purpose",
        "primary_subject",
        "secondary_subjects",
        "world_elements",
        "continuity_anchors",
        "focus_detail",
    }
)
PLAN_FRAME_OVERRIDE_METADATA_FIELDS = PLAN_FRAME_OVERRIDE_IDENTITY_FIELDS | frozenset(
    {
        "locked_fields",
        "override_source",
    }
)
PLAN_FRAME_OVERRIDE_ALLOWED_FIELDS = (
    PLAN_FRAME_OVERRIDE_METADATA_FIELDS | PLAN_FRAME_OVERRIDE_VALUE_FIELDS
)
VIDEO_GENERATION_MODES = frozenset({"generate", "fixed"})
STORYBOARD_GENERATION_LIMITS = DEFAULT_STORYBOARD_GENERATION_LIMITS
STORYBOARD_SCENE_COUNT_MIN = STORYBOARD_GENERATION_LIMITS.min_scene_count
STORYBOARD_SCENE_COUNT_MAX = STORYBOARD_GENERATION_LIMITS.max_scene_count


def validate_standard_video_generation_params(
    params: Mapping[str, Any],
    *,
    config: Any | None = None,
    limits: StoryboardGenerationLimits | None = None,
) -> None:
    effective_limits = limits or storyboard_generation_limits_from_config(config)
    legacy_fields = sorted(
        name
        for name in LEGACY_STANDARD_STORYBOARD_PARAMS
        if name in params and params[name] is not None
    )
    if legacy_fields:
        raise ValueError(
            "legacy storyboard parameter is not supported in standard video generation: "
            + ", ".join(legacy_fields)
        )

    mode = params.get("mode", "generate")
    if mode not in VIDEO_GENERATION_MODES:
        raise ValueError(f"unsupported video generation mode: {mode}")

    storyboard_mode = params.get("storyboard_mode", StoryboardGenerationMode.SMART.value)
    if storyboard_mode not in {item.value for item in StoryboardGenerationMode}:
        raise ValueError(f"unsupported storyboard mode: {storyboard_mode}")

    count_mode = params.get("storyboard_count_mode", StoryboardCountMode.AUTO.value)
    if count_mode not in {item.value for item in StoryboardCountMode}:
        raise ValueError(f"unsupported storyboard count mode: {count_mode}")

    scene_count = params.get("storyboard_scene_count")
    if storyboard_mode == "smart":
        if count_mode == "manual":
            if scene_count is None:
                raise ValueError("storyboard_scene_count is required with smart manual mode")
            if (
                type(scene_count) is not int
                or not effective_limits.min_scene_count
                <= scene_count
                <= effective_limits.max_scene_count
            ):
                raise ValueError(
                    "storyboard_scene_count must be between "
                    f"{effective_limits.min_scene_count} and {effective_limits.max_scene_count}"
                )
        elif scene_count is not None:
            raise ValueError("storyboard_scene_count is valid only with smart manual mode")
    else:
        if count_mode != "auto":
            raise ValueError("deterministic storyboard modes require auto count mode")
        if scene_count is not None:
            raise ValueError("storyboard_scene_count is not valid for deterministic storyboard modes")

    script_length_mode = params.get("script_length_mode", "auto")
    if script_length_mode not in {item.value for item in ScriptLengthMode}:
        raise ValueError(f"unsupported script length mode: {script_length_mode}")

    script_target_words = params.get("script_target_words")
    if mode == "fixed":
        if script_length_mode != "auto":
            raise ValueError("script_length_mode is only configurable in generate mode")
        if script_target_words is not None:
            raise ValueError("script_target_words is only valid in generate mode")
    elif script_length_mode == "custom":
        if script_target_words is None:
            raise ValueError("script_target_words is required with custom script length mode")
        if type(script_target_words) is not int or script_target_words < 1:
            raise ValueError("invalid script_target_words: must be a positive integer")
    elif script_target_words is not None:
        raise ValueError("script_target_words is only valid with custom script length mode")

    validate_plan_frame_override_payloads(params.get("frame_overrides"))


def is_plan_frame_override_payload(override: Mapping[str, Any]) -> bool:
    return PLAN_FRAME_OVERRIDE_IDENTITY_FIELDS <= set(override.keys())


def validate_plan_frame_override_payloads(
    frame_overrides: Sequence[Mapping[str, Any]] | None,
) -> None:
    normalize_plan_frame_overrides(frame_overrides)


def normalize_plan_frame_overrides(
    frame_overrides: Sequence[Mapping[str, Any]] | None,
    *,
    storyboard_plan: StoryboardPlan | None = None,
) -> list[dict[str, Any]]:
    if not frame_overrides:
        return []

    frame_ids = (
        {frame.frame_id for frame in storyboard_plan.frames}
        if storyboard_plan is not None
        else None
    )
    normalized: list[dict[str, Any]] = []
    for override in frame_overrides:
        if not isinstance(override, Mapping):
            raise ValueError("frame override must be a mapping")
        if set(override.keys()) & LEGACY_FRAME_OVERRIDE_IDENTITY_FIELDS:
            raise ValueError("legacy frame override identity is not supported")
        missing = PLAN_FRAME_OVERRIDE_IDENTITY_FIELDS - set(override.keys())
        if missing:
            raise ValueError(f"frame override missing identity field: {sorted(missing)[0]}")
        invalid_keys = set(override.keys()) - PLAN_FRAME_OVERRIDE_ALLOWED_FIELDS
        if invalid_keys:
            raise ValueError(f"unsupported frame override field: {sorted(invalid_keys)[0]}")

        normalized_override = dict(override)
        _validate_identity_scalar("plan_id", normalized_override["plan_id"])
        _validate_identity_scalar("frame_id", normalized_override["frame_id"])
        _validate_source_digest(normalized_override["source_digest"])
        if type(normalized_override["plan_revision"]) is not int or normalized_override["plan_revision"] < 1:
            raise ValueError("frame override plan_revision must be a positive integer")

        locked_fields = _normalize_locked_fields(normalized_override.get("locked_fields"))
        normalized_override["locked_fields"] = locked_fields
        provided_fields = [
            field_name
            for field_name in PLAN_FRAME_OVERRIDE_VALUE_FIELDS
            if field_name in normalized_override and normalized_override[field_name] is not None
        ]
        for field_name in provided_fields:
            if field_name not in locked_fields:
                raise ValueError(f"frame override field {field_name} must be listed in locked_fields")

        if storyboard_plan is not None:
            if normalized_override["plan_id"] != storyboard_plan.plan_id:
                raise ValueError("frame override plan_id does not match current storyboard plan")
            if normalized_override["plan_revision"] != storyboard_plan.revision:
                raise ValueError("frame override plan_revision does not match current storyboard plan")
            if normalized_override["source_digest"] != storyboard_plan.source_digest:
                raise ValueError("frame override source_digest does not match current storyboard plan")
            if normalized_override["frame_id"] not in frame_ids:
                raise ValueError("frame override frame_id does not match current storyboard plan")

        normalized.append(normalized_override)

    return normalized


def _validate_identity_scalar(field_name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"frame override {field_name} must be a non-empty string")


def _validate_source_digest(value: Any) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError("frame override source_digest must be a SHA-256 hex digest")


def _normalize_locked_fields(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("frame override locked_fields must be a non-empty list")

    locked_fields: list[str] = []
    for item in value:
        if item not in PLAN_FRAME_OVERRIDE_VALUE_FIELDS:
            raise ValueError(f"unsupported locked frame field: {item}")
        if item not in locked_fields:
            locked_fields.append(item)
    return locked_fields
