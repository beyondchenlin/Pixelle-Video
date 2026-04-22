"""Storyboard routing and planning service."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from pixelle_video.config import config_manager
from pixelle_video.config.storyboard_preset_library import load_shot_preset_map, lookup_world_preset
from pixelle_video.models.storyboard_planning import (
    FramePlan,
    ResolvedContentMode,
    ResolvedShotPreset,
    StoryboardPlanningResponse,
    StoryboardPlanningResult,
)
from pixelle_video.prompts.storyboard_planning import (
    build_storyboard_planning_prompt,
    parse_storyboard_frames,
)
from pixelle_video.services.storyboard_consistency import (
    apply_frame_overrides,
    repair_frame_plan_shots,
)


def _read_value(container: Any, key: str, default: Any = None) -> Any:
    if isinstance(container, Mapping):
        return container.get(key, default)
    return getattr(container, key, default)


def _normalize_supported_modes(world_preset: Any) -> set[str]:
    supported_modes = _read_value(world_preset, "supported_modes", ())
    return {str(mode) for mode in supported_modes}


def _resolve_world_preset_library(world_preset_library: Any | None) -> Any:
    if world_preset_library is not None:
        return world_preset_library
    return config_manager.get_storyboard_world_preset_library()


def _resolve_shot_preset_library(shot_preset_library: Any | None) -> Any:
    if shot_preset_library is not None:
        return shot_preset_library
    return config_manager.get_storyboard_shot_preset_library()


def _normalize_override_payloads(frame_overrides: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for override in frame_overrides or []:
        payload = dict(override)
        locked_fields = payload.get("locked_fields")
        if locked_fields is not None:
            if isinstance(locked_fields, tuple):
                payload["locked_fields"] = list(locked_fields)
            elif isinstance(locked_fields, list):
                payload["locked_fields"] = list(locked_fields)
            else:
                payload["locked_fields"] = [locked_fields]
        normalized.append(payload)
    return normalized


def _coerce_storyboard_frame_plans(llm_response: Any) -> list[FramePlan]:
    if isinstance(llm_response, StoryboardPlanningResponse):
        return llm_response.to_frame_plans()
    if isinstance(llm_response, Mapping):
        return StoryboardPlanningResponse.model_validate(llm_response).to_frame_plans()
    if isinstance(llm_response, str):
        return parse_storyboard_frames(llm_response)
    raise ValueError("storyboard planner returned an unsupported response type")


def resolve_content_mode(
    *,
    user_mode: str | None,
    classifier_result: Mapping[str, Any] | None,
    world_preset: Any,
    default_threshold: float,
) -> ResolvedContentMode:
    """Resolve the content mode using forced mode, user override, classifier, then fallback."""

    supported_modes = _normalize_supported_modes(world_preset)
    forced_mode = _read_value(world_preset, "forced_mode", None)
    conservative_fallback_mode = _read_value(world_preset, "conservative_fallback_mode", "concept_explainer")
    classifier_result = classifier_result or {}
    classifier_mode = classifier_result.get("mode")
    classifier_confidence = float(classifier_result.get("confidence", 0.0) or 0.0)

    if forced_mode is not None:
        resolved = ResolvedContentMode(
            mode=str(forced_mode),
            confidence=1.0,
            mixed_content_flag=bool(classifier_result.get("mixed_content_flag", False)),
            dominant_anchor_type=str(classifier_result.get("dominant_anchor_type", "")),
            reason_summary="world preset forced_mode",
            selection_source="forced_mode",
        )
        return resolved

    if user_mode is not None:
        if supported_modes and user_mode not in supported_modes:
            raise ValueError("requested content mode is not supported by the selected world preset")

        resolved = ResolvedContentMode(
            mode=str(user_mode),
            confidence=1.0,
            mixed_content_flag=bool(classifier_result.get("mixed_content_flag", False)),
            dominant_anchor_type=str(classifier_result.get("dominant_anchor_type", "")),
            reason_summary="user requested content mode",
            selection_source="user_selected",
        )
        return resolved

    if classifier_mode is not None and (
        not supported_modes or str(classifier_mode) in supported_modes
    ) and classifier_confidence >= float(default_threshold):
        resolved = ResolvedContentMode(
            mode=str(classifier_mode),
            confidence=classifier_confidence,
            mixed_content_flag=bool(classifier_result.get("mixed_content_flag", False)),
            dominant_anchor_type=str(classifier_result.get("dominant_anchor_type", "")),
            reason_summary=str(classifier_result.get("reason_summary", "classifier result")),
            selection_source="classifier",
        )
        return resolved

    resolved = ResolvedContentMode(
        mode=str(conservative_fallback_mode),
        confidence=min(classifier_confidence, float(default_threshold)) if classifier_result else 0.0,
        mixed_content_flag=bool(classifier_result.get("mixed_content_flag", False)),
        dominant_anchor_type=str(classifier_result.get("dominant_anchor_type", "")),
        reason_summary="conservative fallback mode",
        selection_source="fallback_mode",
    )
    return resolved


def resolve_role_strategy(*, resolved_mode: str, role_strategy: str | None) -> str:
    """Resolve the role strategy for the resolved content mode."""

    strategy = (role_strategy or "auto").strip()
    if strategy == "auto":
        return "theme_mapping" if resolved_mode == "theme_mapping" else "stable_explainer_cast"

    if strategy == "theme_mapping" and resolved_mode != "theme_mapping":
        raise ValueError("role strategy conflicts with resolved content mode")

    if strategy == "stable_explainer_cast" and resolved_mode != "concept_explainer":
        raise ValueError("role strategy conflicts with resolved content mode")

    if strategy not in {"theme_mapping", "stable_explainer_cast"}:
        raise ValueError("unknown role strategy")

    return strategy


def resolve_shot_preset(
    *,
    requested_preset_id: str | None,
    scene_count: int,
    world_preset_default_ids: Sequence[str],
    available_presets: Mapping[str, Mapping[str, Any]],
) -> ResolvedShotPreset:
    """Resolve the shot preset from an explicit request or the world preset defaults."""

    if requested_preset_id:
        preset = available_presets.get(requested_preset_id)
        if preset is None:
            raise ValueError(f"unknown shot preset id: {requested_preset_id}")

        supported_scene_count = tuple(_read_value(preset, "supported_scene_count", ()))
        if scene_count not in supported_scene_count:
            raise ValueError(
                f"shot preset {requested_preset_id} does not support the requested scene count: {scene_count}"
            )
        return ResolvedShotPreset(
            preset_id=requested_preset_id,
            override_policy=str(_read_value(preset, "override_policy", "adaptive")),
            supported_scene_count=supported_scene_count,
            max_consecutive_same=max(1, int(_read_value(preset, "max_consecutive_same", 2))),
            selection_source="user_selected",
        )

    for preset_id in world_preset_default_ids:
        preset = available_presets.get(preset_id)
        if preset is None:
            continue

        supported_scene_count = tuple(_read_value(preset, "supported_scene_count", ()))
        if scene_count in supported_scene_count:
            return ResolvedShotPreset(
                preset_id=preset_id,
                override_policy=str(_read_value(preset, "override_policy", "adaptive")),
                supported_scene_count=supported_scene_count,
                max_consecutive_same=max(1, int(_read_value(preset, "max_consecutive_same", 2))),
                selection_source="auto_selected",
            )

    fallback_preset = available_presets.get("balanced_explainer")
    if fallback_preset is None:
        raise ValueError("balanced_explainer shot preset is not available")

    return ResolvedShotPreset(
        preset_id="balanced_explainer",
        override_policy=str(_read_value(fallback_preset, "override_policy", "adaptive")),
        supported_scene_count=tuple(_read_value(fallback_preset, "supported_scene_count", ())),
        max_consecutive_same=max(1, int(_read_value(fallback_preset, "max_consecutive_same", 2))),
        selection_source="fallback_substituted",
        fallback_reason="no world default shot preset supported the requested scene count",
    )


async def plan_storyboard_batch(
    *,
    llm_service,
    narrations: Sequence[str],
    image_config: Any | None = None,
    prompt_prefix: str | None = None,
    world_preset_id: str | None = None,
    shot_preset_id: str | None = None,
    workflow: str | None = None,
    media_service: Any | None = None,
    media_type: str = "image",
    consistency_strength: str = "standard",
    content_mode: str | None = None,
    role_strategy: str | None = None,
    role_locking_strength: str | None = None,
    shot_strategy: str | None = None,
    frame_overrides: Sequence[Mapping[str, Any]] | None = None,
    world_preset_library: Any | None = None,
    shot_preset_library: Any | None = None,
    classifier_result: Mapping[str, Any] | None = None,
    default_threshold: float = 0.7,
    planner_version: str = "1.0",
    **unused: Any,
) -> StoryboardPlanningResult:
    """Plan a storyboard batch and attach a replayable snapshot."""

    del image_config, prompt_prefix, workflow, media_service, media_type, unused

    world_preset_library = _resolve_world_preset_library(world_preset_library)
    shot_preset_library = _resolve_shot_preset_library(shot_preset_library)
    shot_preset_map = load_shot_preset_map(shot_preset_library)

    world_preset = lookup_world_preset(world_preset_library, world_preset_id)
    resolved_mode = resolve_content_mode(
        user_mode=content_mode,
        classifier_result=classifier_result,
        world_preset=world_preset,
        default_threshold=default_threshold,
    )
    resolved_mode_source = resolved_mode.selection_source

    resolved_shot_preset = resolve_shot_preset(
        requested_preset_id=shot_preset_id,
        scene_count=len(narrations),
        world_preset_default_ids=tuple(_read_value(world_preset, "default_shot_preset_ids", ())),
        available_presets=shot_preset_map,
    )

    resolved_role_strategy = resolve_role_strategy(
        resolved_mode=resolved_mode.mode,
        role_strategy=role_strategy,
    )
    selected_role_locking_strength = role_locking_strength or consistency_strength
    selected_shot_strategy = shot_strategy or resolved_shot_preset.override_policy

    planner_prompt = build_storyboard_planning_prompt(
        narrations=list(narrations),
        world_preset=world_preset,
        shot_preset=shot_preset_map.get(resolved_shot_preset.preset_id, {}),
        resolved_mode=resolved_mode.mode,
        consistency_strength=consistency_strength,
        role_strategy=resolved_role_strategy,
        role_locking_strength=selected_role_locking_strength,
        shot_strategy=selected_shot_strategy,
    )
    llm_response = await llm_service(
        prompt=planner_prompt,
        response_type=StoryboardPlanningResponse,
        temperature=0.2,
        max_tokens=2400,
    )
    frame_plans = _coerce_storyboard_frame_plans(llm_response)
    if len(frame_plans) != len(narrations):
        raise ValueError("storyboard planner returned a frame count that does not match the narrations")

    applied_overrides = apply_frame_overrides(
        frame_plans=frame_plans,
        frame_overrides=frame_overrides or [],
    )
    repaired_frame_plans = repair_frame_plan_shots(
        frame_plans=applied_overrides,
        shot_rules=resolved_shot_preset,
    )

    snapshot = {
        "world_preset_id": str(_read_value(world_preset, "preset_id", "")),
        "world_preset_selection_source": "user_selected" if world_preset_id is not None else "auto_defaulted",
        "requested_shot_preset_id": shot_preset_id,
        "effective_final_shot_preset": resolved_shot_preset.preset_id,
        "resolved_content_mode": resolved_mode.mode,
        "resolved_mode_selection_source": resolved_mode_source,
        "selected_consistency_strength": consistency_strength,
        "resolved_role_strategy": resolved_role_strategy,
        "selected_role_locking_strength": selected_role_locking_strength,
        "selected_shot_strategy": selected_shot_strategy,
        "frame_overrides": _normalize_override_payloads(frame_overrides),
        "resolved_content_mode_details": resolved_mode.to_dict(),
        "resolved_shot_preset_details": resolved_shot_preset.to_dict(),
        "world_preset": dict(world_preset),
        "shot_preset": dict(shot_preset_map.get(resolved_shot_preset.preset_id, {})),
        "planner_version": planner_version,
    }
    return StoryboardPlanningResult(
        requested_content_mode=content_mode,
        resolved_content_mode=resolved_mode,
        world_preset_id=str(_read_value(world_preset, "preset_id", "")),
        resolved_shot_preset=resolved_shot_preset,
        planning_snapshot=snapshot,
        frames=tuple(repaired_frame_plans),
        scene_count=len(narrations),
        consistency_strength=consistency_strength,
        role_strategy=resolved_role_strategy,
        warnings=(),
        planner_version=planner_version,
    )


__all__ = [
    "plan_storyboard_batch",
    "resolve_content_mode",
    "resolve_role_strategy",
    "resolve_shot_preset",
]
