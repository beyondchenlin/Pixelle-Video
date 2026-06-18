# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Content generation utility functions

Pure/stateless functions for generating content using LLM.
These functions are reusable across different pipelines.
"""

import re
import unicodedata
from time import perf_counter
from typing import Any, Callable, List, Literal, Mapping, Optional, Sequence

from loguru import logger

from pixelle_video.config import config_manager
from pixelle_video.config.storyboard_preset_library import lookup_world_preset
from pixelle_video.models.content_generation import (
    ImagePromptBatchResponse,
    NarrationBatchResponse,
    VideoPromptBatchResponse,
)
from pixelle_video.models.content_world import ContentWorldProfile
from pixelle_video.models.final_visual_prompt_contract import (
    FinalVisualPromptContract,
    RenderedMediaPrompt,
    join_rendered_negative_prompts,
)
from pixelle_video.models.llm_interaction_trace import (
    LLMTraceContext,
    LLMTraceError,
    trace_context_with_prompt_template,
)
from pixelle_video.models.native_prompt import NativePromptHint
from pixelle_video.models.progress import ProgressI18nMessage
from pixelle_video.models.prompt_context import (
    PromptContextEnvelope,
    PromptContextInput,
    normalize_prompt_contexts,
    slice_prompt_contexts,
)
from pixelle_video.models.series_visual_signature_profile import SeriesVisualSignatureProfile
from pixelle_video.models.series_visual_signature_request import SeriesVisualSignatureRequest
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.models.text_overlay import (
    build_text_rendering_policy,
    build_text_rendering_settings,
)
from pixelle_video.prompt_language import DEFAULT_PROMPT_LANGUAGE, PromptLanguage
from pixelle_video.services.content_world_planner import ContentWorldPlanner
from pixelle_video.services.llm_capabilities import estimate_input_tokens
from pixelle_video.services.ip_profile_readiness import (
    ensure_ip_profile_ready_for_generation,
)
from pixelle_video.services.ip_usage_planner import IPFrameAppearancePlanner
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.services.llm_trace_refs import (
    LLMTraceCollector,
    llm_trace_refs_from_records,
    merge_llm_trace_refs,
)
from pixelle_video.services.series_visual_signature_profile_builder import (
    SeriesVisualSignatureProfileBuilder,
)
from pixelle_video.services.storyboard_planner import plan_storyboard_batch
from pixelle_video.services.visual_prompt_planning_service import VisualPromptPlanningService
from pixelle_video.services.visual_style_contract_resolver import VisualStyleContractResolver
from pixelle_video.utils.logging_util import build_content_observability, emit_stage_event
from pixelle_video.utils.prompt_batching import (
    PromptBatch,
    PromptBatchRunError,
    run_prompt_batches,
)
from pixelle_video.utils.prompt_generation_performance import (
    DEFAULT_PROMPT_BATCH_CONCURRENT_LIMIT,
    DEFAULT_PROMPT_BATCH_SIZE,
)
from pixelle_video.utils.prompt_helper import (
    append_final_visual_prompt_requirements,
    apply_image_text_policy,
    apply_text_rendering_policy,
    build_visible_text_whitelist_clause,
    final_visual_prompt_clause_template_metadata,
    final_visual_prompt_template_metadata,
    ip_negative_constraints_from_context,
    ip_visible_text_whitelist_from_context,
    merge_z_image_constraints_into_prompt,
    sanitize_visual_prompt_text,
    select_image_text_negative_prompt,
    select_negative_text_rules,
)

# Conservative safety margin for pre-flight batch sizing.
# The authoritative guard lives in LLMService.__call__ using per-model limits.
_LLM_BATCH_SAFE_TOKENS = 25000

from pixelle_video.utils.style_resolution import (
    normalize_storyboard_style,
    resolve_style_source,
    resolve_style_spec,
)
from pixelle_video.utils.text_splitting import split_text_into_sentences
from pixelle_video.utils.workflow_capabilities import (
    WorkflowCapabilities,
    get_media_workflow_capabilities,
)


def _resolve_llm_prompt_batch_size(batch_size: Optional[int]) -> int:
    if batch_size is not None:
        return max(1, int(batch_size))
    return DEFAULT_PROMPT_BATCH_SIZE


def _resolve_llm_prompt_batch_concurrency(max_concurrency: Optional[int]) -> int:
    if max_concurrency is not None:
        return max(1, int(max_concurrency))
    return DEFAULT_PROMPT_BATCH_CONCURRENT_LIMIT


def _provider_negative_rules_for_projection(
    *,
    resolved_style: Any = None,
    style_profile: Mapping[str, Any] | None = None,
    text_rendering_settings: Any = None,
    resolved_text_policy: Any = None,
    native_hints: Mapping[int, Sequence[Any]] | None = None,
) -> list[str]:
    rules: list[str] = []

    negative_prompt = getattr(resolved_style, "negative_prompt", "") if resolved_style is not None else ""
    _extend_prompt_rules(rules, negative_prompt)

    if isinstance(style_profile, Mapping):
        _extend_prompt_rules(rules, style_profile.get("negative_rules"))

    has_any_native_hints = any(native_hints.values()) if isinstance(native_hints, Mapping) else False
    native_text_allowed = bool(getattr(resolved_text_policy, "allow_native_text_in_image", False))
    if has_any_native_hints and native_text_allowed and resolved_text_policy is not None:
        _extend_prompt_rules(
            rules,
            select_negative_text_rules(
                policy=resolved_text_policy,
                has_native_hints=True,
            ),
        )
    elif text_rendering_settings is not None:
        _extend_prompt_rules(
            rules,
            select_image_text_negative_prompt(text_rendering_settings.image_text),
        )

    return _dedupe_prompt_rules(rules)


def _extend_prompt_rules(target: list[str], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        for part in value.replace("；", ",").split(","):
            text = part.strip()
            if text:
                target.append(text)
        return
    if isinstance(value, Sequence):
        for item in value:
            text = str(item or "").strip()
            if text:
                target.append(text)


def _dedupe_prompt_rules(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _passthrough_rendered_media_prompt(
    prompt: str,
    *,
    media_type: str,
    frame_index: int,
    negative_rules: Sequence[str] = (),
) -> RenderedMediaPrompt:
    contract = FinalVisualPromptContract(
        scene=str(prompt or "").strip() or "media prompt",
        composition=f"{media_type} prompt passthrough",
        style_assignment="preserve generated media prompt semantics",
        character_layer_style="no image visual anchor projection applied",
        world_layer_style="preserve generated media prompt style",
        integration_priority="preserve prompt content for downstream media workflow",
        negative_rules=tuple(negative_rules),
        metadata={
            "provider_prompt_mode": "passthrough_non_image_media",
            "frame_index": frame_index,
            "media_type": media_type,
        },
    )
    return RenderedMediaPrompt(
        prompt=contract.scene,
        negative_prompt=", ".join(negative_rules) if negative_rules else None,
        prompt_contract=contract,
        renderer_id=f"{media_type}_passthrough_prompt_renderer",
        renderer_version="v1",
        metadata={"provider_prompt_mode": "passthrough_non_image_media"},
    )


def _serialize_storyboard_frame_plan(frame_plan: Any) -> dict[str, Any]:
    if hasattr(frame_plan, "to_prompt_dict"):
        return dict(frame_plan.to_prompt_dict())
    if isinstance(frame_plan, dict):
        return dict(frame_plan)
    return {
        "shot_type": getattr(frame_plan, "shot_type", None),
        "shot_purpose": getattr(frame_plan, "shot_purpose", None),
        "frame_source": getattr(frame_plan, "frame_source", None),
    }


def _snapshot_with_serialized_frame_plans(
    planning_snapshot: Optional[dict[str, Any]],
    frame_plans: list[Any],
) -> Optional[dict[str, Any]]:
    if planning_snapshot is None and not frame_plans:
        return None

    snapshot = dict(planning_snapshot or {})
    if frame_plans:
        snapshot["frames"] = [_serialize_storyboard_frame_plan(frame_plan) for frame_plan in frame_plans]
    return snapshot


def _normalize_prompt_fragments(values: Sequence[Any]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(cleaned)
    return normalized


def _trace_context_for_rendered_prompt(
    trace_context: LLMTraceContext | None,
    *,
    rendered_prompt: Any,
    attempt: int,
    stage: str,
    metadata: Mapping[str, Any] | None = None,
) -> LLMTraceContext | None:
    if trace_context is None:
        return None
    return trace_context_with_prompt_template(
        trace_context,
        rendered_prompt=rendered_prompt,
        attempt=attempt,
        stage=stage,
        metadata=metadata,
    )


def _trace_status_value(trace: Any) -> str:
    status = getattr(trace, "status", "")
    return str(getattr(status, "value", status) or "")


def _prompt_generation_trace_refs_by_index(
    records: Sequence[Any],
    *,
    stage: str,
) -> list[dict[str, Any]]:
    refs_by_index: dict[int, dict[str, Any]] = {}
    for trace in records:
        trace_id = getattr(trace, "trace_id", None)
        context = getattr(trace, "context", None)
        if not trace_id or getattr(context, "stage", None) != stage:
            continue
        if _trace_status_value(trace) != "success":
            continue
        metadata = getattr(context, "metadata", {}) or {}
        try:
            batch_start_index = int(metadata.get("batch_start_index", 0))
            batch_size = int(metadata.get("batch_size", 1))
        except (TypeError, ValueError):
            continue
        if batch_size <= 0:
            continue
        for prompt_index in range(batch_start_index, batch_start_index + batch_size):
            refs_by_index[prompt_index] = {
                "prompt_index": prompt_index,
                "trace_id": str(trace_id),
                "stage": stage,
            }
    return [refs_by_index[index] for index in sorted(refs_by_index)]


def _normalize_prompt_contexts(
    prompt_contexts: Optional[PromptContextInput],
    expected_count: int,
) -> Optional[PromptContextEnvelope]:
    return normalize_prompt_contexts(prompt_contexts, expected_count)


def _style_context_payload(
    *,
    resolved_style: Any,
    normalized_style: dict[str, Any] | None,
    style_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    if normalized_style is not None:
        return {
            "style_kind": normalized_style.get("style_kind"),
            "style_profile": normalized_style.get("style_profile"),
            "visual_suffix": normalized_style.get("visual_suffix"),
        }
    if resolved_style is not None:
        return {
            "style_kind": getattr(resolved_style, "style_kind", None),
            "source_identity": getattr(resolved_style, "source_identity", None),
            "style_profile": style_profile,
        }
    return {"style_profile": style_profile}


def _enrich_prompt_contexts_with_ip(
    prompt_contexts: PromptContextEnvelope | None,
    *,
    expected_count: int,
    packages: Sequence[Any],
    style_context: dict[str, Any],
) -> PromptContextEnvelope:
    frame_contexts = [
        dict(context)
        for context in (
            prompt_contexts.frame_contexts
            if prompt_contexts is not None
            else tuple({} for _ in range(expected_count))
        )
    ]
    if len(frame_contexts) != expected_count:
        raise ValueError("prompt_contexts must match storyboard frame count")
    if len(packages) != expected_count:
        raise ValueError("IP adaptation package count must match storyboard frame count")

    for index, package in enumerate(packages):
        package_dict = (
            package.to_dict()
            if hasattr(package, "to_dict")
            else dict(package)
            if isinstance(package, Mapping)
            else {}
        )
        frame_contexts[index]["ip_adaptation"] = package_dict
        frame_contexts[index]["ip_scene_description"] = (
            getattr(package, "appearance_description", "") or ""
        )
        frame_contexts[index]["ip_negative_constraints"] = list(
            getattr(package, "negative_constraints", ())
        )
        image_text_plan = getattr(package, "image_text_plan", None)
        frame_contexts[index]["ip_image_text_plan"] = (
            image_text_plan.to_dict()
            if image_text_plan is not None and hasattr(image_text_plan, "to_dict")
            else {}
        )
        frame_contexts[index]["style_context"] = style_context

    return PromptContextEnvelope(
        plan_context=prompt_contexts.plan_context if prompt_contexts is not None else {},
        frame_contexts=frame_contexts,
    )


def _strip_ip_prompt_context_fields(
    prompt_contexts: PromptContextEnvelope | None,
) -> PromptContextEnvelope | None:
    if prompt_contexts is None:
        return None

    _IP_FIELD_NAMES = (
        "ip_adaptation",
        "ip_presence_options",
        "ip_scene_description",
        "ip_negative_constraints",
        "ip_image_text_plan",
    )
    frame_contexts: list[dict[str, Any]] = []
    for context in prompt_contexts.frame_contexts:
        cleaned = dict(context)
        for field in _IP_FIELD_NAMES:
            cleaned.pop(field, None)
        frame_contexts.append(cleaned)
    return PromptContextEnvelope(
        plan_context=prompt_contexts.plan_context,
        frame_contexts=frame_contexts,
    )


def _with_generation_world_profile_context(
    prompt_contexts: PromptContextEnvelope | None,
    *,
    generation_world_profile: ContentWorldProfile | None,
    expected_count: int,
) -> PromptContextEnvelope | None:
    if generation_world_profile is None:
        return prompt_contexts
    plan_context = (
        dict(prompt_contexts.plan_context)
        if prompt_contexts is not None
        else {}
    )
    plan_context["generation_world_profile"] = generation_world_profile.to_dict()
    frame_contexts = (
        tuple(dict(context) for context in prompt_contexts.frame_contexts)
        if prompt_contexts is not None
        else tuple({} for _ in range(expected_count))
    )
    return PromptContextEnvelope(
        plan_context=plan_context,
        frame_contexts=frame_contexts,
    )


def _add_generation_world_snapshot(
    planning_snapshot: dict[str, Any] | None,
    *,
    generation_world_hint: str | None,
    generation_world_profile: ContentWorldProfile | None,
) -> dict[str, Any] | None:
    if generation_world_profile is None:
        return planning_snapshot
    snapshot = dict(planning_snapshot or {})
    snapshot["generation_world_hint"] = (
        generation_world_hint.strip()
        if generation_world_hint
        else None
    )
    snapshot["generation_world_profile"] = generation_world_profile.to_dict()
    snapshot["generation_world_hint_source"] = generation_world_profile.hint_source.value
    return snapshot


def _should_plan_generation_world_profile(
    *,
    generation_world_hint: str | None,
    ip_profile: Any,
    storyboard_enabled: bool,
) -> bool:
    return any(
        (
            bool(str(generation_world_hint).strip()) if generation_world_hint is not None else False,
            bool(str(getattr(ip_profile, "world_hint", "") or "").strip()),
            storyboard_enabled,
        )
    )


def _frame_contexts_for_final_prompts(
    prompt_contexts: PromptContextEnvelope | None,
    prompt_count: int,
) -> tuple[Mapping[str, Any], ...]:
    if prompt_contexts is None:
        return tuple({} for _ in range(prompt_count))
    return prompt_contexts.frame_contexts




def _read_string_items(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _ip_adaptations_by_frame(
    *,
    packages: Sequence[Any],
    storyboard_plan: Any,
) -> dict[str, dict[str, Any]]:
    frame_ids = [
        getattr(frame, "frame_id", "") or f"frame_{index + 1:04d}"
        for index, frame in enumerate(getattr(storyboard_plan, "frames", ()) or ())
    ]
    snapshot: dict[str, dict[str, Any]] = {}
    for index, package in enumerate(packages):
        payload = package.to_dict() if hasattr(package, "to_dict") else dict(package)
        frame_id = str(payload.get("frame_id") or getattr(package, "frame_id", "") or "")
        if not frame_id and index < len(frame_ids):
            frame_id = frame_ids[index]
        if not frame_id:
            frame_id = f"frame_{index + 1:04d}"
        snapshot[frame_id] = payload
    return snapshot


def _slice_prompt_contexts(
    prompt_contexts: Optional[PromptContextEnvelope],
    start_index: int,
    item_count: int,
) -> Optional[PromptContextEnvelope]:
    return slice_prompt_contexts(prompt_contexts, start_index, item_count)


def _native_prompt_fragment(hint: NativePromptHint | str) -> str:
    if isinstance(hint, NativePromptHint):
        return hint.prompt_fragment
    return str(hint)


def _native_prompt_source_candidate_ids(
    hints_by_frame: Mapping[int, Sequence[NativePromptHint | str]],
) -> list[str]:
    candidate_ids: list[str] = []
    for hints in hints_by_frame.values():
        for hint in hints:
            if not isinstance(hint, NativePromptHint):
                continue
            candidate_ids.extend(hint.source_candidate_ids)
    return candidate_ids


async def generate_title(
    llm_service,
    content: str,
    strategy: Literal["auto", "direct", "llm"] = "auto",
    max_length: int = 15,
    stage_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    *,
    trace_context: LLMTraceContext | None = None,
    trace_recorder: LLMInteractionRecorder | None = None,
) -> str:
    """
    Generate title from content
    
    Args:
        llm_service: LLM service instance
        content: Source content (topic or script)
        strategy: Generation strategy
            - "auto": Auto-decide based on content length (default)
            - "direct": Use content directly (truncated if needed)
            - "llm": Always use LLM to generate title
        max_length: Maximum title length (default: 15)
    
    Returns:
        Generated title
    """
    start_time = perf_counter()
    stripped_content = content.strip()
    logger.info(
        f"Starting title generation (strategy={strategy}, input_length={len(stripped_content)}, max_length={max_length})"
    )
    emit_stage_event(
        channel="ai_creation",
        stage="title_generation",
        event="start",
        message="title generation started",
        callback=stage_callback,
        strategy=strategy,
        content=build_content_observability(stripped_content),
    )

    if strategy == "direct":
        title = stripped_content[:max_length] if len(stripped_content) > max_length else stripped_content
        elapsed_ms = round((perf_counter() - start_time) * 1000)
        emit_stage_event(
            channel="ai_creation",
            stage="title_generation",
            event="end",
            message="title generation completed",
            callback=stage_callback,
            status="success",
            latency_ms=elapsed_ms,
            llm_call_count=0,
            retry_count=0,
            strategy=strategy,
        )
        logger.info(
            f"Title generation completed via direct strategy in {perf_counter() - start_time:.2f}s"
        )
        return title
    
    if strategy == "auto":
        if len(stripped_content) <= 15:
            elapsed_ms = round((perf_counter() - start_time) * 1000)
            emit_stage_event(
                channel="ai_creation",
                stage="title_generation",
                event="end",
                message="title generation completed",
                callback=stage_callback,
                status="success",
                latency_ms=elapsed_ms,
                llm_call_count=0,
                retry_count=0,
                strategy="auto_direct",
            )
            logger.info(
                f"Title generation completed via auto-direct shortcut in {perf_counter() - start_time:.2f}s"
            )
            return stripped_content
        # Fall through to LLM
    
    # Use LLM to generate title
    from pixelle_video.prompts.title_generation import render_title_generation_prompt
    
    # Pass max_length to prompt so LLM knows the character limit
    rendered_prompt = render_title_generation_prompt(content, max_length=max_length)
    try:
        response = await llm_service(
            rendered_prompt.text,
            temperature=0.7,
            max_tokens=50,
            trace_context=_trace_context_for_rendered_prompt(
                trace_context,
                rendered_prompt=rendered_prompt,
                attempt=1,
                stage="title_generation",
            ),
            trace_recorder=trace_recorder,
        )
    except Exception:
        emit_stage_event(
            channel="ai_creation",
            stage="title_generation",
            event="fail",
            message="title generation failed",
            callback=stage_callback,
            status="failed",
            latency_ms=round((perf_counter() - start_time) * 1000),
            llm_call_count=1,
            retry_count=0,
            strategy=strategy,
        )
        raise
    
    # Clean up response
    title = response.strip()
    
    # Remove quotes if present
    if title.startswith('"') and title.endswith('"'):
        title = title[1:-1]
    if title.startswith("'") and title.endswith("'"):
        title = title[1:-1]
    
    # Remove trailing punctuation
    title = title.rstrip('.,!?;:\'"')
    
    # Safety: if still over limit, truncate smartly
    if len(title) > max_length:
        # Try to truncate at word boundary
        truncated = title[:max_length]
        last_space = truncated.rfind(' ')
        
        # Only use word boundary if it's not too far back (at least 60% of max_length)
        if last_space > max_length * 0.6:
            title = truncated[:last_space]
        else:
            title = truncated
        
        # Remove any trailing punctuation after truncation
        title = title.rstrip('.,!?;:\'"')
    
    elapsed = perf_counter() - start_time
    emit_stage_event(
        channel="ai_creation",
        stage="title_generation",
        event="end",
        message="title generation completed",
        callback=stage_callback,
        status="success",
        latency_ms=round(elapsed * 1000),
        llm_call_count=1,
        retry_count=0,
        strategy=strategy,
    )
    logger.info(f"Title generation completed in {elapsed:.2f}s")
    logger.debug(f"Generated title: '{title}' (length: {len(title)})")
    return title


async def generate_narrations_from_topic(
    llm_service,
    topic: str,
    n_scenes: int = 5,
    min_words: int = 5,
    max_words: int = 20,
    stage_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    preserve_natural_punctuation: bool = True,
    *,
    trace_context: LLMTraceContext | None = None,
    trace_recorder: LLMInteractionRecorder | None = None,
) -> List[str]:
    """
    Generate narrations from topic using LLM
    
    Args:
        llm_service: LLM service instance
        topic: Topic/theme to generate narrations from
        n_scenes: Number of narrations to generate
        min_words: Minimum narration length
        max_words: Maximum narration length
    
    Returns:
        List of narration texts
    """
    from pixelle_video.prompts.topic_narration import render_topic_narration_prompt
    
    start_time = perf_counter()
    logger.bind(
        channel="runtime",
        content=build_content_observability(topic),
        narration_count=n_scenes,
    ).info("generating narrations from topic")
    emit_stage_event(
        channel="ai_creation",
        stage="narration_generation",
        event="start",
        message="narration generation started",
        callback=stage_callback,
        narration_count=n_scenes,
        content=build_content_observability(topic),
    )
    
    rendered_prompt = render_topic_narration_prompt(
        topic=topic,
        n_storyboard=n_scenes,
        min_words=min_words,
        max_words=max_words,
        preserve_natural_punctuation=preserve_natural_punctuation,
    )
    
    try:
        response: NarrationBatchResponse = await llm_service(
            prompt=rendered_prompt.text,
            response_type=NarrationBatchResponse,
            temperature=0.8,
            max_tokens=10000,
            trace_context=_trace_context_for_rendered_prompt(
                trace_context,
                rendered_prompt=rendered_prompt,
                attempt=1,
                stage="narration_generation",
            ),
            trace_recorder=trace_recorder,
        )

        narrations = list(response.narrations)

        # Validate count
        if len(narrations) > n_scenes:
            logger.warning(f"Got {len(narrations)} narrations, taking first {n_scenes}")
            narrations = narrations[:n_scenes]
        elif len(narrations) < n_scenes:
            raise ValueError(f"Expected {n_scenes} narrations, got only {len(narrations)}")
    except Exception:
        emit_stage_event(
            channel="ai_creation",
            stage="narration_generation",
            event="fail",
            message="narration generation failed",
            callback=stage_callback,
            status="failed",
            latency_ms=round((perf_counter() - start_time) * 1000),
            llm_call_count=1,
            retry_count=0,
            narration_count=n_scenes,
        )
        raise
    
    emit_stage_event(
        channel="ai_creation",
        stage="narration_generation",
        event="end",
        message="narration generation completed",
        callback=stage_callback,
        status="success",
        latency_ms=round((perf_counter() - start_time) * 1000),
        llm_call_count=1,
        retry_count=0,
        narration_count=len(narrations),
    )
    logger.info(
        f"Generated {len(narrations)} narrations successfully in {perf_counter() - start_time:.2f}s"
    )
    return narrations


async def generate_narrations_from_content(
    llm_service,
    content: str,
    n_scenes: int = 5,
    min_words: int = 5,
    max_words: int = 20,
    stage_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    preserve_natural_punctuation: bool = True,
    *,
    trace_context: LLMTraceContext | None = None,
    trace_recorder: LLMInteractionRecorder | None = None,
) -> List[str]:
    """
    Generate narrations from user-provided content using LLM
    
    Args:
        llm_service: LLM service instance
        content: User-provided content
        n_scenes: Number of narrations to generate
        min_words: Minimum narration length
        max_words: Maximum narration length
    
    Returns:
        List of narration texts
    """
    from pixelle_video.prompts.content_narration import render_content_narration_prompt
    
    start_time = perf_counter()
    logger.info(f"Generating {n_scenes} narrations from content ({len(content)} chars)")
    emit_stage_event(
        channel="ai_creation",
        stage="narration_generation",
        event="start",
        message="narration generation started",
        callback=stage_callback,
        narration_count=n_scenes,
        content=build_content_observability(content),
    )
    
    rendered_prompt = render_content_narration_prompt(
        content=content,
        n_storyboard=n_scenes,
        min_words=min_words,
        max_words=max_words,
        preserve_natural_punctuation=preserve_natural_punctuation,
    )
    
    try:
        response: NarrationBatchResponse = await llm_service(
            prompt=rendered_prompt.text,
            response_type=NarrationBatchResponse,
            temperature=0.8,
            max_tokens=10000,
            trace_context=_trace_context_for_rendered_prompt(
                trace_context,
                rendered_prompt=rendered_prompt,
                attempt=1,
                stage="narration_generation",
            ),
            trace_recorder=trace_recorder,
        )

        narrations = list(response.narrations)

        # Validate count
        if len(narrations) > n_scenes:
            logger.warning(f"Got {len(narrations)} narrations, taking first {n_scenes}")
            narrations = narrations[:n_scenes]
        elif len(narrations) < n_scenes:
            raise ValueError(f"Expected {n_scenes} narrations, got only {len(narrations)}")
    except Exception:
        emit_stage_event(
            channel="ai_creation",
            stage="narration_generation",
            event="fail",
            message="narration generation failed",
            callback=stage_callback,
            status="failed",
            latency_ms=round((perf_counter() - start_time) * 1000),
            llm_call_count=1,
            retry_count=0,
            narration_count=n_scenes,
        )
        raise
    
    emit_stage_event(
        channel="ai_creation",
        stage="narration_generation",
        event="end",
        message="narration generation completed",
        callback=stage_callback,
        status="success",
        latency_ms=round((perf_counter() - start_time) * 1000),
        llm_call_count=1,
        retry_count=0,
        narration_count=len(narrations),
    )
    logger.info(
        f"Generated {len(narrations)} narrations successfully in {perf_counter() - start_time:.2f}s"
    )
    return narrations


def _split_text_by_delimiters(script: str, delimiters: str) -> List[str]:
    """Split text while keeping the matched delimiter sequence on each segment."""
    cleaned = re.sub(r"\s+", " ", script.strip())
    if not cleaned:
        return []

    pattern = rf".+?(?:[{re.escape(delimiters)}]+|$)"
    return [segment.strip() for segment in re.findall(pattern, cleaned) if segment.strip()]


def _is_unicode_punctuation(char: str) -> bool:
    """Return True when the character belongs to any Unicode punctuation category."""
    return unicodedata.category(char).startswith("P")


def _split_text_by_unicode_punctuation(script: str) -> List[str]:
    """Split text on any Unicode punctuation while keeping delimiter runs attached."""
    cleaned = re.sub(r"\s+", " ", script.strip())
    if not cleaned:
        return []

    narrations: List[str] = []
    current: List[str] = []
    has_text = False

    for index, char in enumerate(cleaned):
        current.append(char)
        if not char.isspace() and not _is_unicode_punctuation(char):
            has_text = True

        next_char = cleaned[index + 1] if index + 1 < len(cleaned) else ""
        should_split = (
            has_text
            and _is_unicode_punctuation(char)
            and (not next_char or not _is_unicode_punctuation(next_char))
        )
        if should_split:
            segment = "".join(current).strip()
            if segment:
                narrations.append(segment)
            current = []
            has_text = False

    if current:
        segment = "".join(current).strip()
        if segment:
            narrations.append(segment)

    return narrations


async def split_narration_script(
    script: str,
    split_mode: Literal["paragraph", "line", "sentence", "punctuation"] = "paragraph",
    stage_callback: Optional[Callable[[dict[str, Any]], None]] = None,
) -> List[str]:
    """
    Split user-provided narration script into segments
    
    Args:
        script: Fixed narration script
        split_mode: Splitting strategy
            - "paragraph": Split by double newline (\\n\\n), preserve single newlines within paragraphs
            - "line": Split by single newline (\\n), each line is a segment
            - "sentence": Split by sentence-ending punctuation (Chinese and English)
            - "punctuation": Split by any Unicode punctuation (Chinese and English)
    
    Returns:
        List of narration segments
    """
    start_time = perf_counter()
    logger.info(f"Splitting script (mode={split_mode}, length={len(script)} chars)")
    emit_stage_event(
        channel="ai_creation",
        stage="narration_split",
        event="start",
        message="narration split started",
        callback=stage_callback,
        split_mode=split_mode,
        content=build_content_observability(script),
    )
    
    narrations = []
    
    if split_mode == "paragraph":
        # Split by double newline (paragraph mode)
        # Preserve single newlines within paragraphs
        paragraphs = re.split(r'\n\s*\n', script)
        for para in paragraphs:
            # Only strip leading/trailing whitespace, preserve internal newlines
            cleaned = para.strip()
            if cleaned:
                narrations.append(para)
        logger.info(f"鉁?Split script into {len(narrations)} segments (by paragraph)")
    
    elif split_mode == "line":
        # Split by single newline (original behavior)
        narrations = [line.strip() for line in script.split('\n') if line.strip()]
        logger.info(f"鉁?Split script into {len(narrations)} segments (by line)")
    
    elif split_mode == "sentence":
        narrations = split_text_into_sentences(script)
        logger.info(f"鉁?Split script into {len(narrations)} segments (by sentence)")

    elif split_mode == "punctuation":
        # Split by any Unicode punctuation for the finest-grained storyboard generation
        narrations = _split_text_by_unicode_punctuation(script)
        logger.info(f"鉁?Split script into {len(narrations)} segments (by punctuation)")

    else:
        # Fallback to line mode
        logger.warning(f"Unknown split_mode '{split_mode}', falling back to 'line'")
        narrations = [line.strip() for line in script.split('\n') if line.strip()]
    
    # Log statistics
    if narrations:
        lengths = [len(s) for s in narrations]
        logger.info(f"   Min: {min(lengths)} chars, Max: {max(lengths)} chars, Avg: {sum(lengths)//len(lengths)} chars")
    
    emit_stage_event(
        channel="ai_creation",
        stage="narration_split",
        event="end",
        message="narration split completed",
        callback=stage_callback,
        status="success",
        latency_ms=round((perf_counter() - start_time) * 1000),
        llm_call_count=0,
        retry_count=0,
        narration_count=len(narrations),
    )
    return narrations


async def generate_image_prompts(
    llm_service,
    narrations: List[str],
    min_words: int = 30,
    max_words: int = 60,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
    batch_size: Optional[int] = None,
    max_concurrency: Optional[int] = None,
    max_retries: int = 3,
    progress_callback: Optional[Callable[[int, int, ProgressI18nMessage], None]] = None,
    style_profile: Optional[dict] = None,
    prompt_contexts: Optional[PromptContextInput] = None,
    stage_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    *,
    trace_context: LLMTraceContext | None = None,
    trace_recorder: LLMInteractionRecorder | None = None,
) -> List[str]:
    """
    Generate image prompts from narrations (with batching and retry)
    
    Args:
        llm_service: LLM service instance
        narrations: List of narrations
        min_words: Min image prompt length
        max_words: Max image prompt length
        batch_size: Max narrations per batch (default: 10)
        max_concurrency: Max concurrent LLM prompt batches (default: prompt performance default)
        max_retries: Max retry attempts per batch (default: 3)
        progress_callback: Optional callback(completed, total, message_token) for progress updates
    
    Returns:
        List of image prompts (base prompts, without prefix applied)
    """
    from pixelle_video.prompts.image_generation import render_image_prompt_prompt
    
    resolved_batch_size = _resolve_llm_prompt_batch_size(batch_size)
    resolved_max_concurrency = _resolve_llm_prompt_batch_concurrency(max_concurrency)
    normalized_prompt_contexts = _normalize_prompt_contexts(prompt_contexts, len(narrations))
    batch_total = (
        (len(narrations) + resolved_batch_size - 1) // resolved_batch_size
        if narrations
        else 0
    )
    start_time = perf_counter()
    logger.info(
        "Generating image prompts for "
        f"{len(narrations)} narrations "
        f"(batch_size={resolved_batch_size}, max_concurrency={resolved_max_concurrency})"
    )
    emit_stage_event(
        channel="ai_creation",
        stage="image_prompt_batch",
        event="start",
        message="image prompt batch started",
        callback=stage_callback,
        narration_count=len(narrations),
        batch_size=resolved_batch_size,
        max_concurrency=resolved_max_concurrency,
    )

    if resolved_batch_size > 1 and narrations:
        sample_items = narrations[:resolved_batch_size]
        sample_prompt = render_image_prompt_prompt(
            narrations=sample_items,
            min_words=min_words,
            max_words=max_words,
            style_profile=style_profile,
            prompt_contexts=_slice_prompt_contexts(normalized_prompt_contexts, 0, len(sample_items)),
            prompt_language=prompt_language,
        )
        est_tokens = estimate_input_tokens(sample_prompt.text)
        if est_tokens > _LLM_BATCH_SAFE_TOKENS:
            new_size = max(1, int(resolved_batch_size * _LLM_BATCH_SAFE_TOKENS / est_tokens))
            if new_size < resolved_batch_size:
                logger.warning(
                    f"Estimated prompt {est_tokens}tok exceeds safety margin "
                    f"{_LLM_BATCH_SAFE_TOKENS}tok; "
                    f"reducing batch_size from {resolved_batch_size} to {new_size}"
                )
                resolved_batch_size = new_size
                batch_total = (
                    (len(narrations) + resolved_batch_size - 1) // resolved_batch_size
                    if narrations
                    else 0
                )

    logger.info(f"Split into {batch_total} batches")
    async def run_batch(batch: PromptBatch[str], attempt: int) -> list[str]:
        logger.info(
            f"Processing batch {batch.index}/{batch_total} "
            f"({len(batch.items)} narrations, attempt {attempt}/{max_retries})"
        )
        batch_start_time = perf_counter()
        rendered_prompt = render_image_prompt_prompt(
            narrations=batch.items,
            min_words=min_words,
            max_words=max_words,
            style_profile=style_profile,
            prompt_contexts=_slice_prompt_contexts(
                normalized_prompt_contexts,
                batch.start_index,
                len(batch.items),
            ),
            prompt_language=prompt_language,
        )

        response: ImagePromptBatchResponse = await llm_service(
            prompt=rendered_prompt.text,
            response_type=ImagePromptBatchResponse,
            temperature=0.7,
            max_tokens=8192,
            trace_context=_trace_context_for_rendered_prompt(
                trace_context,
                rendered_prompt=rendered_prompt,
                attempt=attempt,
                stage="image_prompt_batch",
                metadata={
                    "batch_index": batch.index,
                    "batch_start_index": batch.start_index,
                    "batch_size": len(batch.items),
                },
            ),
            trace_recorder=trace_recorder,
        )

        batch_prompts = list(response.image_prompts)
        if len(batch_prompts) != len(batch.items):
            error_msg = (
                f"Batch {batch.index} prompt count mismatch (attempt {attempt}/{max_retries}):\n"
                f"  Expected: {len(batch.items)} prompts\n"
                f"  Got: {len(batch_prompts)} prompts"
            )
            logger.warning(error_msg)
            raise ValueError(error_msg)

        logger.info(
            f"Batch {batch.index} completed successfully ({len(batch_prompts)} prompts) in "
            f"{perf_counter() - batch_start_time:.2f}s"
        )
        return batch_prompts

    try:
        batch_result = await run_prompt_batches(
            items=narrations,
            batch_size=resolved_batch_size,
            max_concurrency=resolved_max_concurrency,
            max_retries=max_retries,
            run_batch=run_batch,
            progress_callback=progress_callback,
        )
    except PromptBatchRunError as exc:
        emit_stage_event(
            channel="ai_creation",
            stage="image_prompt_batch",
            event="fail",
            message="image prompt batch failed",
            callback=stage_callback,
            status="failed",
            latency_ms=round((perf_counter() - start_time) * 1000),
            llm_call_count=exc.call_count,
            retry_count=exc.retry_count,
            batch_index=exc.failed_batch_index,
            batch_total=exc.batch_total,
            narration_count=len(narrations),
            batch_size=resolved_batch_size,
            max_concurrency=resolved_max_concurrency,
        )
        if exc.__cause__ is not None:
            raise exc.__cause__ from exc
        raise
    except Exception:
        emit_stage_event(
            channel="ai_creation",
            stage="image_prompt_batch",
            event="fail",
            message="image prompt batch failed",
            callback=stage_callback,
            status="failed",
            latency_ms=round((perf_counter() - start_time) * 1000),
            llm_call_count=0,
            retry_count=0,
            batch_total=batch_total,
            narration_count=len(narrations),
            batch_size=resolved_batch_size,
            max_concurrency=resolved_max_concurrency,
        )
        raise
    
    emit_stage_event(
        channel="ai_creation",
        stage="image_prompt_batch",
        event="end",
        message="image prompt batch completed",
        callback=stage_callback,
        status="success",
        latency_ms=round((perf_counter() - start_time) * 1000),
        llm_call_count=batch_result.call_count,
        retry_count=batch_result.retry_count,
        batch_total=batch_result.batch_total,
        narration_count=len(narrations),
        batch_size=resolved_batch_size,
        max_concurrency=resolved_max_concurrency,
    )
    logger.info(
        f"Generated {len(batch_result.outputs)} image prompts in {perf_counter() - start_time:.2f}s"
    )
    return batch_result.outputs


async def generate_styled_image_prompt_batch(
    llm_service,
    narrations: List[str],
    image_config,
    prompt_contexts: Optional[PromptContextInput] = None,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
    prompt_prefix: Optional[str] = None,
    workflow: Optional[str] = None,
    media_service=None,
    media_type: Literal["image", "video"] = "image",
    min_words: int = 30,
    max_words: int = 60,
    batch_size: Optional[int] = None,
    max_concurrency: Optional[int] = None,
    max_retries: int = 3,
    progress_callback: Optional[Callable[[int, int, ProgressI18nMessage], None]] = None,
    world_preset_id: Optional[str] = None,
    generation_world_hint: Optional[str] = None,
    shot_preset_id: Optional[str] = None,
    consistency_strength: str = "standard",
    content_mode: Optional[str] = None,
    role_strategy: Optional[str] = None,
    role_locking_strength: Optional[str] = None,
    shot_strategy: Optional[str] = None,
    frame_overrides: Optional[list[dict[str, Any]]] = None,
    text_rendering: Optional[Mapping[str, Any]] = None,
    native_prompt_hints_by_frame: Optional[
        Mapping[int, Sequence[NativePromptHint | str]]
    ] = None,
    storyboard_plan=None,
    series_visual_signature_enabled: bool = False,
    ip_profile=None,
    series_visual_signature_profile: SeriesVisualSignatureProfile | None = None,
    scene_casts_by_frame=None,
    stage_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    upstream_llm_trace_refs: Optional[Sequence[Mapping[str, str]]] = None,
    *,
    trace_context: LLMTraceContext | None = None,
    trace_recorder: LLMInteractionRecorder | None = None,
    series_visual_signature_expression_mode: str | None = None,
    series_visual_signature_structure_mode: str | None = None,
    series_visual_signature_participation_mode: str | None = None,
    series_visual_signature_request: SeriesVisualSignatureRequest | None = None,
    series_visual_signature_mode: str | None = None,
    series_visual_signature_consistency_mode: str | None = None,
) -> StyledImagePromptBatch:
    start_time = perf_counter()
    progress_total = max(len(narrations), 1)
    normalized_prompt_contexts = _normalize_prompt_contexts(prompt_contexts, len(narrations))
    resolved_series_visual_signature_request = series_visual_signature_request or SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": series_visual_signature_enabled,
            "series_visual_signature_expression_mode": series_visual_signature_expression_mode,
            "series_visual_signature_structure_mode": series_visual_signature_structure_mode,
            "series_visual_signature_participation_mode": series_visual_signature_participation_mode,
            "series_visual_signature_mode": series_visual_signature_mode,
            "series_visual_signature_consistency_mode": series_visual_signature_consistency_mode,
        },
        profile_id=getattr(ip_profile, "series_visual_signature_profile_id", None),
        generation_world_hint=generation_world_hint,
    )
    ip_prompt_chain_enabled = resolved_series_visual_signature_request.enabled and media_type == "image"
    resolved_series_visual_signature_profile = series_visual_signature_profile
    if ip_prompt_chain_enabled and storyboard_plan is None:
        raise ValueError("storyboard_plan is required when series_visual_signature_enabled=True")
    if ip_prompt_chain_enabled:
        ensure_ip_profile_ready_for_generation(ip_profile)
        if resolved_series_visual_signature_profile is None:
            resolved_series_visual_signature_profile = SeriesVisualSignatureProfileBuilder().build(ip_profile)
    text_rendering_settings = build_text_rendering_settings(text_rendering)
    image_text_payload = (
        text_rendering.get("image_text")
        if isinstance(text_rendering, Mapping)
        else None
    )
    explicit_image_text_positive_prompt = (
        str(image_text_payload.get("positive_prompt") or "").strip()
        if isinstance(image_text_payload, Mapping)
        and "positive_prompt" in image_text_payload
        else ""
    )
    native_hints = dict(native_prompt_hints_by_frame or {})
    resolved_text_policy = build_text_rendering_policy(text_rendering_settings.overlay)
    trace_collector = (
        LLMTraceCollector(trace_recorder)
        if trace_recorder is not None
        else None
    )
    active_trace_recorder = trace_collector or trace_recorder

    def _storyboard_controls_enabled() -> bool:
        return any(
            [
                world_preset_id is not None,
                shot_preset_id is not None,
                content_mode is not None,
                role_strategy is not None,
                role_locking_strength is not None,
                shot_strategy is not None,
                bool(frame_overrides),
                consistency_strength != "standard",
            ]
        )

    storyboard_enabled = _storyboard_controls_enabled()
    storyboard_world_preset = (
        lookup_world_preset(
            config_manager.get_storyboard_world_preset_library(),
            world_preset_id,
        )
        if storyboard_enabled
        else None
    )
    source = resolve_style_source(image_config, prompt_prefix_override=prompt_prefix)
    resolved_style = None
    style_profile = None
    planning_snapshot = None
    generation_world_profile = (
        await ContentWorldPlanner().plan(
            llm_service=llm_service,
            source_text="\n".join(str(narration) for narration in narrations),
            generation_world_hint=generation_world_hint,
            ip_world_hint=getattr(ip_profile, "world_hint", None),
            world_preset=storyboard_world_preset,
            trace_context=trace_context,
            trace_recorder=active_trace_recorder,
        )
        if _should_plan_generation_world_profile(
            generation_world_hint=generation_world_hint,
            ip_profile=ip_profile,
            storyboard_enabled=storyboard_enabled,
        )
        else None
    )
    normalized_prompt_contexts = _with_generation_world_profile_context(
        normalized_prompt_contexts,
        generation_world_profile=generation_world_profile,
        expected_count=len(narrations),
    )

    if source is not None:
        style_resolution_start = perf_counter()
        try:
            if progress_callback:
                progress_callback(
                    0,
                    progress_total,
                    ProgressI18nMessage(
                        key="progress.detail.style_resolution",
                        fallback="resolving style profile",
                    ),
                )
            emit_stage_event(
                channel="ai_creation",
                stage="style_resolution",
                event="start",
                message="style resolution started",
                callback=stage_callback,
                provider=getattr(source, "provider", None),
            )
            resolved_style = await resolve_style_spec(
                llm_service,
                source,
                trace_context=trace_context,
                trace_recorder=active_trace_recorder,
            )
            style_profile = resolved_style.style_profile
            emit_stage_event(
                channel="ai_creation",
                stage="style_resolution",
                event="end",
                message="style resolution completed",
                callback=stage_callback,
                status="success",
                latency_ms=round((perf_counter() - style_resolution_start) * 1000),
                llm_call_count=1,
                retry_count=0,
            )
            logger.info(
                "Style resolution completed in "
                f"{perf_counter() - style_resolution_start:.2f}s "
                f"(source={source.source_identity}, media_type={media_type})"
            )
        except LLMTraceError:
            raise
        except Exception:
            emit_stage_event(
                channel="ai_creation",
                stage="style_resolution",
                event="fail",
                message="style resolution failed",
                callback=stage_callback,
                status="failed",
                latency_ms=round((perf_counter() - style_resolution_start) * 1000),
                llm_call_count=1,
                retry_count=0,
            )
            logger.exception("Style resolution failed; aborting prompt generation")
            raise
    else:
        emit_stage_event(
            channel="ai_creation",
            stage="style_resolution",
            event="skip",
            message="style resolution skipped",
            callback=stage_callback,
            status="skipped",
            latency_ms=0,
            llm_call_count=0,
            retry_count=0,
            reason="no style source",
        )

    planning = None
    normalized_style = None
    frame_plans: list[Any] = []
    if storyboard_enabled:
        if progress_callback:
            progress_callback(
                0,
                progress_total,
                ProgressI18nMessage(
                    key="progress.detail.storyboard_planning",
                    fallback="planning storyboard",
                ),
            )
        normalized_style = normalize_storyboard_style(
            resolved_style=resolved_style,
            world_preset=storyboard_world_preset,
        )
        if normalized_style is not None:
            style_profile = normalized_style["style_profile"]

        planning_start = perf_counter()
        emit_stage_event(
            channel="ai_creation",
            stage="storyboard_planning",
            event="start",
            message="storyboard planning started",
            callback=stage_callback,
            narration_count=len(narrations),
        )
        try:
            planning = await plan_storyboard_batch(
                llm_service=llm_service,
                narrations=narrations,
                prompt_language=prompt_language,
                image_config=image_config,
                prompt_prefix=prompt_prefix,
                world_preset_id=world_preset_id,
                shot_preset_id=shot_preset_id,
                workflow=workflow,
                media_service=media_service,
                media_type=media_type,
                consistency_strength=consistency_strength,
                content_mode=content_mode,
                role_strategy=role_strategy,
                role_locking_strength=role_locking_strength,
                shot_strategy=shot_strategy,
                prompt_contexts=normalized_prompt_contexts,
                generation_world_profile=generation_world_profile,
                frame_overrides=frame_overrides,
                trace_context=trace_context,
                trace_recorder=active_trace_recorder,
            )
        except Exception:
            emit_stage_event(
                channel="ai_creation",
                stage="storyboard_planning",
                event="fail",
                message="storyboard planning failed",
                callback=stage_callback,
                status="failed",
                latency_ms=round((perf_counter() - planning_start) * 1000),
                llm_call_count=1,
                retry_count=0,
                narration_count=len(narrations),
            )
            raise
        emit_stage_event(
            channel="ai_creation",
            stage="storyboard_planning",
            event="end",
            message="storyboard planning completed",
            callback=stage_callback,
            status="success",
            latency_ms=round((perf_counter() - planning_start) * 1000),
            llm_call_count=1,
            retry_count=0,
            narration_count=len(narrations),
        )
        logger.info(
            "Storyboard planning completed in "
            f"{perf_counter() - planning_start:.2f}s "
            f"(frames={len(narrations)}, consistency_strength={consistency_strength})"
        )
        frame_plans = list(getattr(planning, "frames", ()) or ())
        planning_snapshot = _snapshot_with_serialized_frame_plans(
            getattr(planning, "planning_snapshot", None),
            frame_plans,
        )
    else:
        emit_stage_event(
            channel="ai_creation",
            stage="storyboard_planning",
            event="skip",
            message="storyboard planning skipped",
            callback=stage_callback,
            status="skipped",
            latency_ms=0,
            llm_call_count=0,
            retry_count=0,
            narration_count=len(narrations),
            reason="storyboard controls disabled",
        )
    planning_snapshot = _add_generation_world_snapshot(
        planning_snapshot,
        generation_world_hint=generation_world_hint,
        generation_world_profile=generation_world_profile,
    )

    # Base prompt generation is intentionally anchor-free. The recurring visual
    # anchor is placed only after the subject-first base scene exists.
    style_context = None
    ip_adaptation_packages = []
    prompt_contexts_for_generation = _strip_ip_prompt_context_fields(normalized_prompt_contexts)
    if ip_prompt_chain_enabled:
        style_context = _style_context_payload(
            resolved_style=resolved_style,
            normalized_style=normalized_style,
            style_profile=style_profile,
        )
        ip_adaptation_packages = await IPFrameAppearancePlanner(llm_client=llm_service).plan_batch(
            storyboard_plan=storyboard_plan,
            ip_profile=ip_profile,
            resolved_style=resolved_style if normalized_style is None else normalized_style,
            scene_casts_by_frame=scene_casts_by_frame,
            generation_world_profile=generation_world_profile,
            trace_context=trace_context,
            trace_recorder=active_trace_recorder,
        )
        planning_snapshot = dict(planning_snapshot or {})
        planning_snapshot["initial_ip_adaptations_by_frame"] = _ip_adaptations_by_frame(
            packages=ip_adaptation_packages,
            storyboard_plan=storyboard_plan,
        )
        if ip_adaptation_packages:
            prompt_contexts_for_generation = _enrich_prompt_contexts_with_ip(
                prompt_contexts_for_generation,
                expected_count=len(narrations),
                packages=tuple(ip_adaptation_packages),
                style_context=style_context or {},
            )

    if media_type == "video":
        base_prompts = await generate_video_prompts(
            llm_service=llm_service,
            narrations=narrations,
            min_words=min_words,
            max_words=max_words,
            prompt_language=prompt_language,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            max_retries=max_retries,
            progress_callback=progress_callback,
            style_profile=style_profile,
            prompt_contexts=prompt_contexts_for_generation,
            stage_callback=stage_callback,
            trace_context=trace_context,
            trace_recorder=active_trace_recorder,
        )
    else:
        base_prompts = await generate_image_prompts(
            llm_service=llm_service,
            narrations=narrations,
            min_words=min_words,
            max_words=max_words,
            prompt_language=prompt_language,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            max_retries=max_retries,
            progress_callback=progress_callback,
            style_profile=style_profile,
            prompt_contexts=prompt_contexts_for_generation,
            stage_callback=stage_callback,
            trace_context=trace_context,
            trace_recorder=active_trace_recorder,
        )

    if trace_collector is not None:
        trace_stage = "video_prompt_batch" if media_type == "video" else "image_prompt_batch"
        prompt_trace_refs = _prompt_generation_trace_refs_by_index(
            trace_collector.records,
            stage=trace_stage,
        )
        if prompt_trace_refs:
            planning_snapshot = dict(planning_snapshot or {})
            planning_snapshot["prompt_generation_trace_refs_by_index"] = prompt_trace_refs
    llm_trace_refs = merge_llm_trace_refs(
        upstream_llm_trace_refs,
        llm_trace_refs_from_records(trace_collector.records)
        if trace_collector is not None
        else (),
    )
    if llm_trace_refs:
        planning_snapshot = dict(planning_snapshot or {})
        planning_snapshot["llm_trace_refs"] = llm_trace_refs

    capabilities = WorkflowCapabilities()
    if media_service is not None:
        try:
            capabilities = get_media_workflow_capabilities(
                media_service,
                workflow=workflow,
                media_type=media_type,
            )
        except Exception as exc:
            logger.warning(
                f"Workflow capability probe failed, falling back to default workflow capabilities: {exc}"
            )

    prompt_assembly_start = perf_counter()
    emit_stage_event(
        channel="ai_creation",
        stage="prompt_assembly",
        event="start",
        message="prompt assembly started",
        callback=stage_callback,
        narration_count=len(narrations),
    )

    if planning is not None and len(frame_plans) != len(base_prompts):
        raise ValueError("storyboard planner frames do not match generated base prompt count")

    world_preset = (planning_snapshot or {}).get("world_preset") or {}
    frame_contexts_for_contract = _frame_contexts_for_final_prompts(
        prompt_contexts_for_generation,
        len(base_prompts),
    )
    active_style_item = None
    if isinstance(image_config, Mapping):
        prefix_library = image_config.get("prompt_prefix_library") or {}
        active_prefix_id = prefix_library.get("active_prefix_id") if isinstance(prefix_library, Mapping) else None
        for item in prefix_library.get("items", ()) if isinstance(prefix_library, Mapping) else ():
            if isinstance(item, Mapping) and item.get("id") == active_prefix_id:
                active_style_item = item
                break
    visual_style_contract = VisualStyleContractResolver().resolve(
        resolved_style=resolved_style,
        active_style_item=active_style_item,
        fallback_to_default_world=bool(generation_world_profile or world_preset),
    )
    provider_negative_rules = _provider_negative_rules_for_projection(
        resolved_style=resolved_style,
        style_profile=style_profile,
        text_rendering_settings=text_rendering_settings,
        resolved_text_policy=resolved_text_policy,
        native_hints=native_hints,
    )
    if media_type == "image":
        visual_planning_result = await VisualPromptPlanningService().plan_image_prompts(
            base_prompts=base_prompts,
            frame_contexts=frame_contexts_for_contract,
            frame_plans=frame_plans,
            visual_style_contract=visual_style_contract,
            generation_world_profile=generation_world_profile,
            world_preset=world_preset,
            visual_anchor_enabled=ip_prompt_chain_enabled,
            anchor_profile=ip_profile if ip_prompt_chain_enabled else None,
            base_anchor_packages=tuple(ip_adaptation_packages),
            workflow=workflow,
            capabilities=capabilities,
            extra_negative_rules=provider_negative_rules,
            llm_service=llm_service,
            trace_context=trace_context,
            trace_recorder=active_trace_recorder,
            series_visual_signature_expression_mode=series_visual_signature_expression_mode or resolved_series_visual_signature_request.expression_mode.value,
            series_visual_signature_structure_mode=series_visual_signature_structure_mode or resolved_series_visual_signature_request.structure_mode.value,
            series_visual_signature_participation_mode=series_visual_signature_participation_mode or resolved_series_visual_signature_request.participation_mode.value,
            series_visual_signature_request=resolved_series_visual_signature_request if ip_prompt_chain_enabled else None,
            series_visual_signature_profile=resolved_series_visual_signature_profile,
            series_visual_signature_mode=series_visual_signature_mode,
            series_visual_signature_consistency_mode=series_visual_signature_consistency_mode,
        )
        rendered_media_prompts = list(visual_planning_result.rendered_prompts)
        final_prompts = [rendered.prompt for rendered in rendered_media_prompts]
        planning_snapshot = dict(planning_snapshot or {})
        planning_snapshot.update(visual_planning_result.planning_snapshot())
        context_packages = (
            visual_planning_result.anchor_packages
            if visual_planning_result.anchor_packages
            else tuple(ip_adaptation_packages)
        )
        if ip_prompt_chain_enabled and context_packages:
            prompt_contexts_for_generation = _enrich_prompt_contexts_with_ip(
                normalized_prompt_contexts,
                expected_count=len(narrations),
                packages=context_packages,
                style_context=style_context or {},
            )
            planning_snapshot["ip_adaptations_by_frame"] = _ip_adaptations_by_frame(
                packages=context_packages,
                storyboard_plan=storyboard_plan,
            )
    else:
        rendered_media_prompts = [
            _passthrough_rendered_media_prompt(
                prompt,
                media_type=media_type,
                frame_index=index,
                negative_rules=provider_negative_rules,
            )
            for index, prompt in enumerate(base_prompts)
        ]
        final_prompts = [rendered.prompt for rendered in rendered_media_prompts]

    if native_hints:
        final_prompts = [
            append_final_visual_prompt_requirements(
                prompt,
                [
                    _native_prompt_fragment(hint)
                    for hint in native_hints.get(index, ())
                ],
            )
            for index, prompt in enumerate(final_prompts)
        ]
        final_prompts = [
            (
                apply_text_rendering_policy(
                    prompt,
                    policy=resolved_text_policy,
                    has_native_hints=True,
                )
                if native_hints.get(index)
                else prompt
            )
            for index, prompt in enumerate(final_prompts)
        ]

    if progress_callback:
        progress_callback(
            progress_total,
            progress_total,
            ProgressI18nMessage(
                key="progress.detail.prompt_assembly",
                fallback="assembling final prompts",
            ),
        )

    has_any_native_hints = any(native_hints.values())
    native_text_allowed = resolved_text_policy.allow_native_text_in_image
    frame_contexts_for_final_prompts = (
        _frame_contexts_for_final_prompts(
            prompt_contexts_for_generation,
            len(final_prompts),
        )
        if ip_prompt_chain_enabled
        else tuple({} for _ in range(len(final_prompts)))
    )
    ip_visible_text_whitelists = (
        [
            ip_visible_text_whitelist_from_context(frame_context)
            for frame_context in frame_contexts_for_final_prompts
        ]
        if ip_prompt_chain_enabled
        else [() for _ in final_prompts]
    )
    resolved_final_prompts: list[str] = []
    for index, prompt in enumerate(final_prompts):
        has_native_text_hint = native_text_allowed and bool(native_hints.get(index))
        if (
            ip_visible_text_whitelists[index]
            and not has_native_text_hint
            and not (media_type == "image" and not capabilities.supports_negative_prompt)
        ):
            requirements = [
                build_visible_text_whitelist_clause(
                    ip_visible_text_whitelists[index]
                )
            ]
            if explicit_image_text_positive_prompt:
                requirements.append(explicit_image_text_positive_prompt)
            resolved_final_prompts.append(
                append_final_visual_prompt_requirements(
                    prompt,
                    requirements,
                )
            )
            continue
        if has_native_text_hint:
            if explicit_image_text_positive_prompt:
                resolved_final_prompts.append(
                    append_final_visual_prompt_requirements(
                        prompt,
                        [explicit_image_text_positive_prompt],
                    )
                )
            else:
                resolved_final_prompts.append(prompt)
            continue
        resolved_final_prompts.append(
            apply_image_text_policy(prompt, text_rendering_settings.image_text)
        )
    final_prompts = resolved_final_prompts

    shared_negative_rules: list[str] = []
    if has_any_native_hints and native_text_allowed:
        native_negative_rules = select_negative_text_rules(
            policy=resolved_text_policy,
            has_native_hints=True,
        )
        if native_negative_rules is not None:
            shared_negative_rules.extend(native_negative_rules)
    else:
        image_text_negative_prompt = select_image_text_negative_prompt(
            text_rendering_settings.image_text
        )
        if image_text_negative_prompt is not None:
            shared_negative_rules.extend(image_text_negative_prompt)

    ip_negative_rules_by_frame = (
        [
            ip_negative_constraints_from_context(frame_context)
            for frame_context in frame_contexts_for_final_prompts
        ]
        if ip_prompt_chain_enabled
        else [() for _ in final_prompts]
    )

    if media_type == "image" and not capabilities.supports_negative_prompt:
        final_prompts = [
            merge_z_image_constraints_into_prompt(
                prompt,
                extra_constraints=[
                    *shared_negative_rules,
                    *ip_negative_rules_by_frame[index],
                ],
                visible_text_whitelist=ip_visible_text_whitelists[index],
            )
            for index, prompt in enumerate(final_prompts)
        ]
        shared_negative_rules = []
        ip_negative_rules_by_frame = [() for _ in final_prompts]

    final_prompts = [
        sanitize_visual_prompt_text(prompt)
        for prompt in final_prompts
    ]
    rendered_media_prompts = [
        rendered.with_prompt(final_prompts[index])
        for index, rendered in enumerate(rendered_media_prompts)
    ]
    negative_prompt = join_rendered_negative_prompts(rendered_media_prompts)
    batch_negative_rules = list(shared_negative_rules)
    for frame_rules in ip_negative_rules_by_frame:
        batch_negative_rules.extend(frame_rules)
    if batch_negative_rules:
        merged_negative_rules = _dedupe_prompt_rules(
            [
                *(negative_prompt.split(",") if negative_prompt else ()),
                *batch_negative_rules,
            ]
        )
        negative_prompt = ", ".join(merged_negative_rules) if merged_negative_rules else None
    if planning_snapshot is not None:
        planning_snapshot = dict(planning_snapshot)
        planning_snapshot["final_visual_prompt_template"] = (
            final_visual_prompt_template_metadata()
        )
        planning_snapshot["final_visual_prompt_clause_template"] = (
            final_visual_prompt_clause_template_metadata()
        )
    if native_prompt_hints_by_frame is not None or text_rendering_settings.overlay.enabled:
        planning_snapshot = dict(planning_snapshot or {})
        planning_snapshot.setdefault(
            "final_visual_prompt_template",
            final_visual_prompt_template_metadata(),
        )
        planning_snapshot.setdefault(
            "final_visual_prompt_clause_template",
            final_visual_prompt_clause_template_metadata(),
        )
        planning_snapshot["text_rendering_policy"] = resolved_text_policy.to_dict()
        planning_snapshot["native_prompt_hint_count"] = sum(
            len(items) for items in native_hints.values()
        )
        planning_snapshot["frames_with_native_hints"] = sorted(native_hints)
        planning_snapshot["native_prompt_source_candidate_ids"] = (
            _native_prompt_source_candidate_ids(native_hints)
        )
    emit_stage_event(
        channel="ai_creation",
        stage="prompt_assembly",
        event="end",
        message="prompt assembly completed",
        callback=stage_callback,
        status="success",
        latency_ms=round((perf_counter() - prompt_assembly_start) * 1000),
        llm_call_count=0,
        retry_count=0,
        narration_count=len(narrations),
    )
    logger.info(
        "Styled prompt batch completed in "
        f"{perf_counter() - start_time:.2f}s "
        f"(media_type={media_type}, narrations={len(narrations)}, storyboard_enabled={storyboard_enabled})"
    )
    return StyledImagePromptBatch(
        prompts=final_prompts,
        negative_prompt=negative_prompt,
        resolved_style=resolved_style,
        planning_snapshot=planning_snapshot,
        rendered_prompts=rendered_media_prompts,
    )


async def generate_video_prompts(
    llm_service,
    narrations: List[str],
    min_words: int = 30,
    max_words: int = 60,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
    batch_size: Optional[int] = None,
    max_concurrency: Optional[int] = None,
    max_retries: int = 3,
    progress_callback: Optional[Callable[[int, int, ProgressI18nMessage], None]] = None,
    style_profile: Optional[dict] = None,
    prompt_contexts: Optional[PromptContextInput] = None,
    stage_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    *,
    trace_context: LLMTraceContext | None = None,
    trace_recorder: LLMInteractionRecorder | None = None,
) -> List[str]:
    """
    Generate video prompts from narrations (with batching and retry)
    
    Args:
        llm_service: LLM service instance
        narrations: List of narrations
        min_words: Min video prompt length
        max_words: Max video prompt length
        batch_size: Max narrations per batch (default: 10)
        max_concurrency: Max concurrent LLM prompt batches (default: prompt performance default)
        max_retries: Max retry attempts per batch (default: 3)
        progress_callback: Optional callback(completed, total, message_token) for progress updates
    
    Returns:
        List of video prompts (base prompts, without prefix applied)
    """
    from pixelle_video.prompts.video_generation import render_video_prompt_prompt
    
    resolved_batch_size = _resolve_llm_prompt_batch_size(batch_size)
    resolved_max_concurrency = _resolve_llm_prompt_batch_concurrency(max_concurrency)
    normalized_prompt_contexts = _normalize_prompt_contexts(prompt_contexts, len(narrations))
    batch_total = (
        (len(narrations) + resolved_batch_size - 1) // resolved_batch_size
        if narrations
        else 0
    )
    start_time = perf_counter()
    logger.info(
        "Generating video prompts for "
        f"{len(narrations)} narrations "
        f"(batch_size={resolved_batch_size}, max_concurrency={resolved_max_concurrency})"
    )
    emit_stage_event(
        channel="ai_creation",
        stage="video_prompt_batch",
        event="start",
        message="video prompt batch started",
        callback=stage_callback,
        narration_count=len(narrations),
        batch_size=resolved_batch_size,
        max_concurrency=resolved_max_concurrency,
    )

    if resolved_batch_size > 1 and narrations:
        sample_items = narrations[:resolved_batch_size]
        sample_prompt = render_video_prompt_prompt(
            narrations=sample_items,
            min_words=min_words,
            max_words=max_words,
            style_profile=style_profile,
            prompt_contexts=_slice_prompt_contexts(normalized_prompt_contexts, 0, len(sample_items)),
            prompt_language=prompt_language,
        )
        est_tokens = estimate_input_tokens(sample_prompt.text)
        if est_tokens > _LLM_BATCH_SAFE_TOKENS:
            new_size = max(1, int(resolved_batch_size * _LLM_BATCH_SAFE_TOKENS / est_tokens))
            if new_size < resolved_batch_size:
                logger.warning(
                    f"Estimated prompt {est_tokens}tok exceeds safety margin "
                    f"{_LLM_BATCH_SAFE_TOKENS}tok; "
                    f"reducing batch_size from {resolved_batch_size} to {new_size}"
                )
                resolved_batch_size = new_size
                batch_total = (
                    (len(narrations) + resolved_batch_size - 1) // resolved_batch_size
                    if narrations
                    else 0
                )

    logger.info(f"Split into {batch_total} batches")
    async def run_batch(batch: PromptBatch[str], attempt: int) -> list[str]:
        logger.info(
            f"Processing batch {batch.index}/{batch_total} "
            f"({len(batch.items)} narrations, attempt {attempt}/{max_retries})"
        )
        batch_start_time = perf_counter()
        rendered_prompt = render_video_prompt_prompt(
            narrations=batch.items,
            min_words=min_words,
            max_words=max_words,
            style_profile=style_profile,
            prompt_contexts=_slice_prompt_contexts(
                normalized_prompt_contexts,
                batch.start_index,
                len(batch.items),
            ),
            prompt_language=prompt_language,
        )

        response: VideoPromptBatchResponse = await llm_service(
            prompt=rendered_prompt.text,
            response_type=VideoPromptBatchResponse,
            temperature=0.7,
            max_tokens=8192,
            trace_context=_trace_context_for_rendered_prompt(
                trace_context,
                rendered_prompt=rendered_prompt,
                attempt=attempt,
                stage="video_prompt_batch",
                metadata={
                    "batch_index": batch.index,
                    "batch_start_index": batch.start_index,
                    "batch_size": len(batch.items),
                },
            ),
            trace_recorder=trace_recorder,
        )

        batch_prompts = list(response.video_prompts)
        if len(batch_prompts) != len(batch.items):
            raise ValueError(
                f"Prompt count mismatch: expected {len(batch.items)}, got {len(batch_prompts)}"
            )

        logger.info(
            f"鉁?Batch {batch.index} completed: {len(batch_prompts)} video prompts in "
            f"{perf_counter() - batch_start_time:.2f}s"
        )
        return batch_prompts

    try:
        batch_result = await run_prompt_batches(
            items=narrations,
            batch_size=resolved_batch_size,
            max_concurrency=resolved_max_concurrency,
            max_retries=max_retries,
            run_batch=run_batch,
            progress_callback=progress_callback,
        )
    except PromptBatchRunError as exc:
        emit_stage_event(
            channel="ai_creation",
            stage="video_prompt_batch",
            event="fail",
            message="video prompt batch failed",
            callback=stage_callback,
            status="failed",
            latency_ms=round((perf_counter() - start_time) * 1000),
            llm_call_count=exc.call_count,
            retry_count=exc.retry_count,
            batch_index=exc.failed_batch_index,
            batch_total=exc.batch_total,
            narration_count=len(narrations),
            batch_size=resolved_batch_size,
            max_concurrency=resolved_max_concurrency,
        )
        if exc.__cause__ is not None:
            raise exc.__cause__ from exc
        raise
    except Exception:
        emit_stage_event(
            channel="ai_creation",
            stage="video_prompt_batch",
            event="fail",
            message="video prompt batch failed",
            callback=stage_callback,
            status="failed",
            latency_ms=round((perf_counter() - start_time) * 1000),
            llm_call_count=0,
            retry_count=0,
            batch_total=batch_total,
            narration_count=len(narrations),
            batch_size=resolved_batch_size,
            max_concurrency=resolved_max_concurrency,
        )
        raise
    
    emit_stage_event(
        channel="ai_creation",
        stage="video_prompt_batch",
        event="end",
        message="video prompt batch completed",
        callback=stage_callback,
        status="success",
        latency_ms=round((perf_counter() - start_time) * 1000),
        llm_call_count=batch_result.call_count,
        retry_count=batch_result.retry_count,
        batch_total=batch_result.batch_total,
        narration_count=len(narrations),
        batch_size=resolved_batch_size,
        max_concurrency=resolved_max_concurrency,
    )
    logger.info(
        f"鉁?Generated {len(batch_result.outputs)} video prompts in {perf_counter() - start_time:.2f}s"
    )
    return batch_result.outputs

