"""Storyboard routing and planning service."""

from __future__ import annotations

import asyncio
from typing import Any, Mapping, Sequence

from loguru import logger

from pixelle_video.config import config_manager
from pixelle_video.config.storyboard_preset_library import load_shot_preset_map, lookup_world_preset
from pixelle_video.models.content_world import ContentWorldProfile
from pixelle_video.models.llm_interaction_trace import (
    LLMTraceContext,
    trace_context_with_prompt_template,
)
from pixelle_video.models.prompt_context import (
    PromptContextEnvelope,
    PromptContextInput,
    normalize_prompt_contexts,
    slice_prompt_contexts,
)
from pixelle_video.models.storyboard_planning import (
    FramePlan,
    ResolvedContentMode,
    ResolvedShotPreset,
    StoryboardPlanningResponse,
    StoryboardPlanningResult,
)
from pixelle_video.prompt_language import DEFAULT_PROMPT_LANGUAGE, normalize_prompt_language
from pixelle_video.prompts.storyboard_planning import (
    parse_storyboard_frames,
    render_storyboard_planning_prompt,
)
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.services.storyboard_consistency import (
    apply_frame_overrides,
    repair_frame_plan_shots,
)

STORYBOARD_PLANNING_BATCH_SIZE = 10
STORYBOARD_PLANNING_MAX_CONCURRENCY = 4
STORYBOARD_PLANNING_BASE_MAX_TOKENS = 2400
STORYBOARD_PLANNING_MAX_TOKENS_PER_FRAME = 550
LARGE_STORYBOARD_SCENE_COUNT = STORYBOARD_PLANNING_BATCH_SIZE + 1
LARGE_STORYBOARD_SHOT_PRESET_REASON = "large storyboard extends shot preset beyond nominal scene counts"


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


def _chunk_narrations(narrations: Sequence[str], batch_size: int) -> list[tuple[int, list[str]]]:
    """Return narration batches with their zero-based starting index."""
    normalized = [str(narration) for narration in narrations]
    return [
        (start_index, normalized[start_index:start_index + batch_size])
        for start_index in range(0, len(normalized), batch_size)
    ]


def _normalize_prompt_contexts(
    prompt_contexts: PromptContextInput | None,
    expected_count: int,
) -> PromptContextEnvelope | None:
    return normalize_prompt_contexts(
        prompt_contexts,
        expected_count,
        error_prefix="storyboard prompt_contexts",
    )


def _normalize_generation_world_profile(
    generation_world_profile: ContentWorldProfile | Mapping[str, Any] | None,
) -> ContentWorldProfile | None:
    if generation_world_profile is None:
        return None
    if isinstance(generation_world_profile, ContentWorldProfile):
        profile = generation_world_profile
    else:
        profile = ContentWorldProfile.from_dict(generation_world_profile)
    return profile if profile.has_content() else None


def _storyboard_planning_max_tokens(frame_count: int) -> int:
    return max(
        STORYBOARD_PLANNING_BASE_MAX_TOKENS,
        frame_count * STORYBOARD_PLANNING_MAX_TOKENS_PER_FRAME,
    )


def _validate_frame_batch(
    *,
    frame_plans: Sequence[FramePlan],
    expected_narrations: Sequence[str],
    scene_id_start: int,
) -> list[FramePlan]:
    if len(frame_plans) != len(expected_narrations):
        raise ValueError("storyboard planner returned a frame count that does not match the narrations")

    expected_scene_ids = [str(scene_id_start + index) for index in range(len(expected_narrations))]
    actual_scene_ids = [str(plan.scene_id) for plan in frame_plans]
    if actual_scene_ids != expected_scene_ids:
        raise ValueError(
            "storyboard planner returned scene_id values that do not match the requested narration order"
        )

    return list(frame_plans)


def _can_extend_shot_preset_to_scene_count(supported_scene_count: Sequence[int], scene_count: int) -> bool:
    if not supported_scene_count:
        return scene_count >= LARGE_STORYBOARD_SCENE_COUNT
    return scene_count >= LARGE_STORYBOARD_SCENE_COUNT and scene_count > max(supported_scene_count)


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
        extends_large_storyboard = _can_extend_shot_preset_to_scene_count(
            supported_scene_count,
            scene_count,
        )
        if scene_count not in supported_scene_count and not extends_large_storyboard:
            raise ValueError(
                f"shot preset {requested_preset_id} does not support the requested scene count: {scene_count}"
            )
        return ResolvedShotPreset(
            preset_id=requested_preset_id,
            override_policy=str(_read_value(preset, "override_policy", "adaptive")),
            supported_scene_count=supported_scene_count,
            max_consecutive_same=max(1, int(_read_value(preset, "max_consecutive_same", 2))),
            selection_source="user_selected",
            fallback_reason=LARGE_STORYBOARD_SHOT_PRESET_REASON if extends_large_storyboard else None,
        )

    for preset_id in world_preset_default_ids:
        preset = available_presets.get(preset_id)
        if preset is None:
            continue

        supported_scene_count = tuple(_read_value(preset, "supported_scene_count", ()))
        extends_large_storyboard = _can_extend_shot_preset_to_scene_count(
            supported_scene_count,
            scene_count,
        )
        if scene_count in supported_scene_count or extends_large_storyboard:
            return ResolvedShotPreset(
                preset_id=preset_id,
                override_policy=str(_read_value(preset, "override_policy", "adaptive")),
                supported_scene_count=supported_scene_count,
                max_consecutive_same=max(1, int(_read_value(preset, "max_consecutive_same", 2))),
                selection_source="auto_selected",
                fallback_reason=LARGE_STORYBOARD_SHOT_PRESET_REASON if extends_large_storyboard else None,
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
        fallback_reason=(
            LARGE_STORYBOARD_SHOT_PRESET_REASON
            if _can_extend_shot_preset_to_scene_count(
                tuple(_read_value(fallback_preset, "supported_scene_count", ())),
                scene_count,
            )
            else "no world default shot preset supported the requested scene count"
        ),
    )


async def plan_storyboard_batch(
    *,
    llm_service,
    narrations: Sequence[str],
    prompt_language: str = DEFAULT_PROMPT_LANGUAGE,
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
    prompt_contexts: PromptContextInput | None = None,
    generation_world_profile: ContentWorldProfile | Mapping[str, Any] | None = None,
    frame_overrides: Sequence[Mapping[str, Any]] | None = None,
    world_preset_library: Any | None = None,
    shot_preset_library: Any | None = None,
    classifier_result: Mapping[str, Any] | None = None,
    default_threshold: float = 0.7,
    planner_version: str = "1.0",
    trace_context: LLMTraceContext | None = None,
    trace_recorder: LLMInteractionRecorder | None = None,
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
    resolved_prompt_language = normalize_prompt_language(
        prompt_language,
        default=DEFAULT_PROMPT_LANGUAGE,
    )
    normalized_prompt_contexts = _normalize_prompt_contexts(
        prompt_contexts,
        len(narrations),
    )
    world_profile = _normalize_generation_world_profile(generation_world_profile)
    world_profile_payload = world_profile.to_dict() if world_profile is not None else None

    narration_batches = _chunk_narrations(narrations, STORYBOARD_PLANNING_BATCH_SIZE)
    planning_semaphore = asyncio.Semaphore(STORYBOARD_PLANNING_MAX_CONCURRENCY)

    async def plan_batch(
        start_index: int,
        batch_narrations: list[str],
        attempt: int = 1,
    ) -> tuple[int, list[FramePlan]]:
        scene_id_start = start_index + 1
        batch_prompt_contexts = slice_prompt_contexts(
            normalized_prompt_contexts,
            start_index,
            len(batch_narrations),
        )
        rendered_prompt = render_storyboard_planning_prompt(
            narrations=batch_narrations,
            prompt_contexts=batch_prompt_contexts,
            generation_world_profile=world_profile_payload,
            world_preset=world_preset,
            shot_preset=shot_preset_map.get(resolved_shot_preset.preset_id, {}),
            resolved_mode=resolved_mode.mode,
            consistency_strength=consistency_strength,
            role_strategy=resolved_role_strategy,
            role_locking_strength=selected_role_locking_strength,
            shot_strategy=selected_shot_strategy,
            scene_id_start=scene_id_start,
            prompt_language=resolved_prompt_language,
        )
        async with planning_semaphore:
            try:
                llm_response = await llm_service(
                    prompt=rendered_prompt.text,
                    response_type=StoryboardPlanningResponse,
                    temperature=0.2,
                    max_tokens=_storyboard_planning_max_tokens(len(batch_narrations)),
                    trace_context=(
                        trace_context_with_prompt_template(
                            trace_context,
                            rendered_prompt=rendered_prompt,
                            attempt=attempt,
                            stage="storyboard_planning",
                            metadata={
                                "batch_start_index": start_index,
                                "batch_size": len(batch_narrations),
                            },
                        )
                        if trace_context is not None
                        else None
                    ),
                    trace_recorder=trace_recorder,
                )
            except ValueError as exc:
                if len(batch_narrations) <= 1:
                    raise
                logger.warning(
                    "Token limit exceeded for batch size %d; splitting in half "
                    "and retrying (attempt=%d, error=%s)",
                    len(batch_narrations), attempt, exc,
                )
                mid = len(batch_narrations) // 2
                left_half = batch_narrations[:mid]
                right_half = batch_narrations[mid:]
                left_result = await plan_batch(start_index, left_half, attempt + 1)
                right_result = await plan_batch(start_index + mid, right_half, attempt + 1)
                _, left_frames = left_result
                _, right_frames = right_result
                return start_index, left_frames + right_frames
        frame_batch = _validate_frame_batch(
            frame_plans=_coerce_storyboard_frame_plans(llm_response),
            expected_narrations=batch_narrations,
            scene_id_start=scene_id_start,
        )
        return start_index, frame_batch

    planned_batches = await asyncio.gather(
        *(plan_batch(start_index, batch) for start_index, batch in narration_batches)
    )
    frame_plans = [
        frame
        for _, batch in sorted(planned_batches, key=lambda item: item[0])
        for frame in batch
    ]

    applied_overrides = apply_frame_overrides(
        frame_plans=frame_plans,
        frame_overrides=frame_overrides or [],
        prompt_contexts=normalized_prompt_contexts,
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
        "storyboard_prompt_language": resolved_prompt_language,
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
        "planning_batch_size": STORYBOARD_PLANNING_BATCH_SIZE,
        "planning_batch_count": len(narration_batches),
        "planning_max_concurrency": STORYBOARD_PLANNING_MAX_CONCURRENCY,
        "planner_version": planner_version,
    }
    if world_profile_payload is not None:
        snapshot["generation_world_profile"] = world_profile_payload
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
