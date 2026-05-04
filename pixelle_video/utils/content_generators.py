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
from pixelle_video.models.native_prompt import NativePromptHint
from pixelle_video.models.progress import ProgressI18nMessage
from pixelle_video.models.prompt_context import (
    PromptContextEnvelope,
    PromptContextInput,
    normalize_prompt_contexts,
    slice_prompt_contexts,
)
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.models.text_overlay import (
    build_text_rendering_policy,
    build_text_rendering_settings,
)
from pixelle_video.prompt_language import DEFAULT_PROMPT_LANGUAGE, PromptLanguage
from pixelle_video.services.content_world_planner import ContentWorldPlanner
from pixelle_video.services.ip_usage_planner import IPUsagePlanner
from pixelle_video.services.storyboard_planner import plan_storyboard_batch
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
    apply_image_text_policy,
    apply_text_rendering_policy,
    assemble_image_prompt,
    assemble_negative_prompt,
    assemble_storyboard_prompt,
    build_image_prompt,
    build_visible_text_whitelist_clause,
    ip_negative_constraints_from_context,
    ip_visible_text_whitelist_from_context,
    merge_z_image_constraints_into_prompt,
    sanitize_visual_prompt_text,
    select_image_text_negative_prompt,
    select_negative_text_rules,
)
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


def _ip_presence_options() -> list[str]:
    return [
        "strong_identity",
        "balanced_narrative",
        "scene_integrated",
        "low_intrusion",
        "symbolic_only",
        "absent",
    ]


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
        package_payload = package.to_dict() if hasattr(package, "to_dict") else dict(package)
        frame_contexts[index]["ip_adaptation"] = package_payload
        frame_contexts[index]["ip_presence_options"] = _ip_presence_options()
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

    frame_contexts: list[dict[str, Any]] = []
    for context in prompt_contexts.frame_contexts:
        cleaned = dict(context)
        cleaned.pop("ip_adaptation", None)
        cleaned.pop("ip_presence_options", None)
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
    from pixelle_video.prompts import build_title_generation_prompt
    
    # Pass max_length to prompt so LLM knows the character limit
    prompt = build_title_generation_prompt(content, max_length=max_length)
    try:
        response = await llm_service(prompt, temperature=0.7, max_tokens=50)
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
    from pixelle_video.prompts import build_topic_narration_prompt
    
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
    
    prompt = build_topic_narration_prompt(
        topic=topic,
        n_storyboard=n_scenes,
        min_words=min_words,
        max_words=max_words,
        preserve_natural_punctuation=preserve_natural_punctuation,
    )
    
    try:
        response: NarrationBatchResponse = await llm_service(
            prompt=prompt,
            response_type=NarrationBatchResponse,
            temperature=0.8,
            max_tokens=2000
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
    from pixelle_video.prompts import build_content_narration_prompt
    
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
    
    prompt = build_content_narration_prompt(
        content=content,
        n_storyboard=n_scenes,
        min_words=min_words,
        max_words=max_words,
        preserve_natural_punctuation=preserve_natural_punctuation,
    )
    
    try:
        response: NarrationBatchResponse = await llm_service(
            prompt=prompt,
            response_type=NarrationBatchResponse,
            temperature=0.8,
            max_tokens=2000
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
    from pixelle_video.prompts import build_image_prompt_prompt
    
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

    logger.info(f"Split into {batch_total} batches")
    async def run_batch(batch: PromptBatch[str], attempt: int) -> list[str]:
        logger.info(
            f"Processing batch {batch.index}/{batch_total} "
            f"({len(batch.items)} narrations, attempt {attempt}/{max_retries})"
        )
        batch_start_time = perf_counter()
        prompt = build_image_prompt_prompt(
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
            prompt=prompt,
            response_type=ImagePromptBatchResponse,
            temperature=0.7,
            max_tokens=8192
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
            f"鉁?Batch {batch.index} completed successfully ({len(batch_prompts)} prompts) in "
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
        f"鉁?Generated {len(batch_result.outputs)} image prompts in {perf_counter() - start_time:.2f}s"
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
    ip_enabled: bool = False,
    ip_profile=None,
    scene_casts_by_frame=None,
    stage_callback: Optional[Callable[[dict[str, Any]], None]] = None,
) -> StyledImagePromptBatch:
    start_time = perf_counter()
    progress_total = max(len(narrations), 1)
    normalized_prompt_contexts = _normalize_prompt_contexts(prompt_contexts, len(narrations))
    ip_prompt_chain_enabled = ip_enabled and media_type == "image"
    if ip_prompt_chain_enabled and storyboard_plan is None:
        raise ValueError("storyboard_plan is required when ip_enabled=True")
    if ip_prompt_chain_enabled and ip_profile is None:
        raise ValueError("ip_profile is required when ip_enabled=True")
    text_rendering_settings = build_text_rendering_settings(text_rendering)
    native_hints = dict(native_prompt_hints_by_frame or {})
    resolved_text_policy = build_text_rendering_policy(text_rendering_settings.overlay)

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
    style_resolution_failed = False
    source = resolve_style_source(image_config, prompt_prefix_override=prompt_prefix)
    raw_prefix = source.raw_content if source else ""
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
            style_resolution_start = perf_counter()
            emit_stage_event(
                channel="ai_creation",
                stage="style_resolution",
                event="start",
                message="style resolution started",
                callback=stage_callback,
                provider=getattr(source, "provider", None),
            )
            resolved_style = await resolve_style_spec(llm_service, source)
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
        except Exception:
            style_resolution_failed = True
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
            logger.exception("Style resolution failed, falling back to legacy prefix concatenation")
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

    prompt_contexts_for_generation = (
        normalized_prompt_contexts
        if ip_prompt_chain_enabled
        else _strip_ip_prompt_context_fields(normalized_prompt_contexts)
    )
    if ip_prompt_chain_enabled:
        style_context = _style_context_payload(
            resolved_style=resolved_style,
            normalized_style=normalized_style,
            style_profile=style_profile,
        )
        ip_adaptation_packages = IPUsagePlanner().plan_batch(
            storyboard_plan=storyboard_plan,
            ip_profile=ip_profile,
            resolved_style=resolved_style if normalized_style is None else normalized_style,
            scene_casts_by_frame=scene_casts_by_frame,
        )
        prompt_contexts_for_generation = _enrich_prompt_contexts_with_ip(
            normalized_prompt_contexts,
            expected_count=len(narrations),
            packages=ip_adaptation_packages,
            style_context=style_context,
        )
        planning_snapshot = dict(planning_snapshot or {})
        planning_snapshot["ip_adaptations_by_frame"] = _ip_adaptations_by_frame(
            packages=ip_adaptation_packages,
            storyboard_plan=storyboard_plan,
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
        )

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

    if planning is not None:
        if len(frame_plans) != len(base_prompts):
            raise ValueError("storyboard planner frames do not match generated base prompt count")

        world_preset = planning_snapshot.get("world_preset") or {}
        final_prompts = [
            build_image_prompt(
                assemble_storyboard_prompt(
                    base_prompt=base_prompt,
                    frame_plan=frame_plans[index],
                    world_preset=world_preset,
                    normalized_style=normalized_style,
                ),
                raw_prefix if style_resolution_failed else "",
            )
            for index, base_prompt in enumerate(base_prompts)
        ]
    else:
        final_prompts = [
            assemble_image_prompt(base_prompt, raw_prefix=raw_prefix, resolved_style=resolved_style)
            for base_prompt in base_prompts
        ]

    if native_hints:
        final_prompts = [
            ", ".join(
                _normalize_prompt_fragments(
                    [
                        prompt,
                        *[
                            _native_prompt_fragment(hint)
                            for hint in native_hints.get(index, ())
                        ],
                    ]
                )
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
    final_prompts = [
        (
            prompt
            if native_text_allowed and bool(native_hints.get(index))
            else ", ".join(
                _normalize_prompt_fragments(
                    [
                        prompt,
                        build_visible_text_whitelist_clause(
                            ip_visible_text_whitelists[index]
                        ),
                    ]
                )
            )
            if ip_visible_text_whitelists[index]
            and not (media_type == "image" and not capabilities.supports_negative_prompt)
            else apply_image_text_policy(prompt, text_rendering_settings.image_text)
        )
        for index, prompt in enumerate(final_prompts)
    ]

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

    negative_prompt = assemble_negative_prompt(
        resolved_style,
        supports_negative_prompt=capabilities.supports_negative_prompt,
        extra_negative_rules=shared_negative_rules or None,
    )
    final_prompts = [
        sanitize_visual_prompt_text(prompt)
        for prompt in final_prompts
    ]
    if media_type == "image" and not capabilities.supports_negative_prompt:
        final_prompts = [
            merge_z_image_constraints_into_prompt(
                prompt,
                extra_constraints=[
                    *(resolved_style.negative_prompt if resolved_style is not None else "",),
                    *shared_negative_rules,
                    *ip_negative_rules_by_frame[index],
                ],
                visible_text_whitelist=ip_visible_text_whitelists[index],
            )
            for index, prompt in enumerate(final_prompts)
        ]
    if native_prompt_hints_by_frame is not None or text_rendering_settings.overlay.enabled:
        planning_snapshot = dict(planning_snapshot or {})
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
    from pixelle_video.prompts.video_generation import build_video_prompt_prompt
    
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

    logger.info(f"Split into {batch_total} batches")
    async def run_batch(batch: PromptBatch[str], attempt: int) -> list[str]:
        logger.info(
            f"Processing batch {batch.index}/{batch_total} "
            f"({len(batch.items)} narrations, attempt {attempt}/{max_retries})"
        )
        batch_start_time = perf_counter()
        prompt = build_video_prompt_prompt(
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
            prompt=prompt,
            response_type=VideoPromptBatchResponse,
            temperature=0.7,
            max_tokens=8192
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


