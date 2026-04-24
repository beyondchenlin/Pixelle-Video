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
from typing import Any, Callable, List, Literal, Optional

from loguru import logger

from pixelle_video.config import config_manager
from pixelle_video.config.storyboard_preset_library import lookup_world_preset
from pixelle_video.models.content_generation import (
    ImagePromptBatchResponse,
    NarrationBatchResponse,
    VideoPromptBatchResponse,
)
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.services.storyboard_planner import plan_storyboard_batch
from pixelle_video.utils.prompt_helper import (
    NO_TEXT_NEGATIVE_RULES,
    apply_no_text_policy,
    assemble_image_prompt,
    assemble_negative_prompt,
    assemble_storyboard_prompt,
    build_image_prompt,
)
from pixelle_video.utils.logging_util import build_content_observability, emit_stage_event
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
        max_words=max_words
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
        max_words=max_words
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
    batch_size: int = 10,
    max_retries: int = 3,
    progress_callback: Optional[callable] = None,
    style_profile: Optional[dict] = None,
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
        max_retries: Max retry attempts per batch (default: 3)
        progress_callback: Optional callback(completed, total, message) for progress updates
    
    Returns:
        List of image prompts (base prompts, without prefix applied)
    """
    from pixelle_video.prompts import build_image_prompt_prompt
    
    start_time = perf_counter()
    logger.info(f"Generating image prompts for {len(narrations)} narrations (batch_size={batch_size})")
    emit_stage_event(
        channel="ai_creation",
        stage="image_prompt_batch",
        event="start",
        message="image prompt batch started",
        callback=stage_callback,
        narration_count=len(narrations),
    )
    
    # Split narrations into batches
    batches = [narrations[i:i + batch_size] for i in range(0, len(narrations), batch_size)]
    logger.info(f"Split into {len(batches)} batches")
    
    all_prompts = []
    stage_llm_calls = 0
    
    # Process each batch
    for batch_idx, batch_narrations in enumerate(batches, 1):
        logger.info(f"Processing batch {batch_idx}/{len(batches)} ({len(batch_narrations)} narrations)")
        batch_start_time = perf_counter()
        
        # Retry logic for this batch
        for attempt in range(1, max_retries + 1):
            try:
                # Generate prompts for this batch
                prompt = build_image_prompt_prompt(
                    narrations=batch_narrations,
                    min_words=min_words,
                    max_words=max_words,
                    style_profile=style_profile,
                )
                
                stage_llm_calls += 1
                response: ImagePromptBatchResponse = await llm_service(
                    prompt=prompt,
                    response_type=ImagePromptBatchResponse,
                    temperature=0.7,
                    max_tokens=8192
                )

                batch_prompts = list(response.image_prompts)
                
                # Validate count
                if len(batch_prompts) != len(batch_narrations):
                    error_msg = (
                        f"Batch {batch_idx} prompt count mismatch (attempt {attempt}/{max_retries}):\n"
                        f"  Expected: {len(batch_narrations)} prompts\n"
                        f"  Got: {len(batch_prompts)} prompts"
                    )
                    logger.warning(error_msg)
                    
                    if attempt < max_retries:
                        logger.info(f"Retrying batch {batch_idx}...")
                        continue
                    else:
                        raise ValueError(error_msg)
                
                # Success!
                logger.info(
                    f"鉁?Batch {batch_idx} completed successfully ({len(batch_prompts)} prompts) in "
                    f"{perf_counter() - batch_start_time:.2f}s"
                )
                all_prompts.extend(batch_prompts)
                
                # Report progress
                if progress_callback:
                    progress_callback(
                        len(all_prompts),
                        len(narrations),
                        f"Batch {batch_idx}/{len(batches)} completed"
                    )
                
                break
                
            except Exception as e:
                logger.error(f"Batch {batch_idx} generation error (attempt {attempt}/{max_retries}): {e}")
                if attempt >= max_retries:
                    emit_stage_event(
                        channel="ai_creation",
                        stage="image_prompt_batch",
                        event="fail",
                        message="image prompt batch failed",
                        callback=stage_callback,
                        status="failed",
                        latency_ms=round((perf_counter() - start_time) * 1000),
                        llm_call_count=stage_llm_calls,
                        retry_count=max(stage_llm_calls - batch_idx, 0),
                        batch_index=batch_idx,
                        batch_total=len(batches),
                        narration_count=len(narrations),
                    )
                    raise
                logger.info(f"Retrying batch {batch_idx}...")
    
    emit_stage_event(
        channel="ai_creation",
        stage="image_prompt_batch",
        event="end",
        message="image prompt batch completed",
        callback=stage_callback,
        status="success",
        latency_ms=round((perf_counter() - start_time) * 1000),
        llm_call_count=stage_llm_calls,
        retry_count=max(stage_llm_calls - len(batches), 0),
        batch_total=len(batches),
        narration_count=len(narrations),
    )
    logger.info(
        f"鉁?Generated {len(all_prompts)} image prompts in {perf_counter() - start_time:.2f}s"
    )
    return all_prompts


async def generate_styled_image_prompt_batch(
    llm_service,
    narrations: List[str],
    image_config,
    prompt_prefix: Optional[str] = None,
    workflow: Optional[str] = None,
    media_service=None,
    media_type: Literal["image", "video"] = "image",
    min_words: int = 30,
    max_words: int = 60,
    batch_size: int = 10,
    max_retries: int = 3,
    progress_callback: Optional[callable] = None,
    world_preset_id: Optional[str] = None,
    shot_preset_id: Optional[str] = None,
    consistency_strength: str = "standard",
    content_mode: Optional[str] = None,
    role_strategy: Optional[str] = None,
    role_locking_strength: Optional[str] = None,
    shot_strategy: Optional[str] = None,
    frame_overrides: Optional[list[dict[str, Any]]] = None,
    forbid_embedded_text_in_image: bool = True,
    stage_callback: Optional[Callable[[dict[str, Any]], None]] = None,
) -> StyledImagePromptBatch:
    start_time = perf_counter()
    progress_total = max(len(narrations), 1)

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

    style_resolution_failed = False
    source = resolve_style_source(image_config, prompt_prefix_override=prompt_prefix)
    raw_prefix = source.raw_content if source else ""
    resolved_style = None
    style_profile = None
    planning_snapshot = None

    if source is not None:
        try:
            if progress_callback:
                progress_callback(0, progress_total, "progress.detail.style_resolution")
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

    storyboard_enabled = _storyboard_controls_enabled()
    planning = None
    normalized_style = None
    frame_plans: list[Any] = []
    if storyboard_enabled:
        if progress_callback:
            progress_callback(0, progress_total, "progress.detail.storyboard_planning")
        storyboard_world_preset = lookup_world_preset(
            config_manager.get_storyboard_world_preset_library(),
            world_preset_id,
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

    prompt_generator = generate_video_prompts if media_type == "video" else generate_image_prompts
    base_prompts = await prompt_generator(
        llm_service=llm_service,
        narrations=narrations,
        min_words=min_words,
        max_words=max_words,
        batch_size=batch_size,
        max_retries=max_retries,
        progress_callback=progress_callback,
        style_profile=style_profile,
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

    final_prompts = [
        apply_no_text_policy(prompt, enabled=forbid_embedded_text_in_image)
        for prompt in final_prompts
    ]

    if progress_callback:
        progress_callback(progress_total, progress_total, "progress.detail.prompt_assembly")

    negative_prompt = assemble_negative_prompt(
        resolved_style,
        supports_negative_prompt=capabilities.supports_negative_prompt,
        extra_negative_rules=NO_TEXT_NEGATIVE_RULES if forbid_embedded_text_in_image else None,
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
    batch_size: int = 10,
    max_retries: int = 3,
    progress_callback: Optional[callable] = None,
    style_profile: Optional[dict] = None,
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
        max_retries: Max retry attempts per batch (default: 3)
        progress_callback: Optional callback(completed, total, message) for progress updates
    
    Returns:
        List of video prompts (base prompts, without prefix applied)
    """
    from pixelle_video.prompts.video_generation import build_video_prompt_prompt
    
    start_time = perf_counter()
    logger.info(f"Generating video prompts for {len(narrations)} narrations (batch_size={batch_size})")
    emit_stage_event(
        channel="ai_creation",
        stage="video_prompt_batch",
        event="start",
        message="video prompt batch started",
        callback=stage_callback,
        narration_count=len(narrations),
    )
    
    # Split narrations into batches
    batches = [narrations[i:i + batch_size] for i in range(0, len(narrations), batch_size)]
    logger.info(f"Split into {len(batches)} batches")
    
    all_prompts = []
    stage_llm_calls = 0
    
    # Process each batch
    for batch_idx, batch_narrations in enumerate(batches, 1):
        logger.info(f"Processing batch {batch_idx}/{len(batches)} ({len(batch_narrations)} narrations)")
        batch_start_time = perf_counter()
        
        # Retry logic for this batch
        for attempt in range(1, max_retries + 1):
            try:
                # Generate prompts for this batch
                prompt = build_video_prompt_prompt(
                    narrations=batch_narrations,
                    min_words=min_words,
                    max_words=max_words,
                    style_profile=style_profile,
                )
                
                stage_llm_calls += 1
                response: VideoPromptBatchResponse = await llm_service(
                    prompt=prompt,
                    response_type=VideoPromptBatchResponse,
                    temperature=0.7,
                    max_tokens=8192
                )

                batch_prompts = list(response.video_prompts)
                
                # Validate batch result
                if len(batch_prompts) != len(batch_narrations):
                    raise ValueError(
                        f"Prompt count mismatch: expected {len(batch_narrations)}, got {len(batch_prompts)}"
                    )
                
                # Success - add to all_prompts
                all_prompts.extend(batch_prompts)
                logger.info(
                    f"鉁?Batch {batch_idx} completed: {len(batch_prompts)} video prompts in "
                    f"{perf_counter() - batch_start_time:.2f}s"
                )
                
                # Report progress
                if progress_callback:
                    completed = len(all_prompts)
                    total = len(narrations)
                    progress_callback(completed, total, f"Batch {batch_idx}/{len(batches)} completed")
                
                break  # Success, move to next batch
            
            except Exception as e:
                logger.warning(f"鉁?Batch {batch_idx} attempt {attempt} failed: {e}")
                if attempt >= max_retries:
                    emit_stage_event(
                        channel="ai_creation",
                        stage="video_prompt_batch",
                        event="fail",
                        message="video prompt batch failed",
                        callback=stage_callback,
                        status="failed",
                        latency_ms=round((perf_counter() - start_time) * 1000),
                        llm_call_count=stage_llm_calls,
                        retry_count=max(stage_llm_calls - batch_idx, 0),
                        batch_index=batch_idx,
                        batch_total=len(batches),
                        narration_count=len(narrations),
                    )
                    raise
                logger.info(f"Retrying batch {batch_idx}...")
    
    emit_stage_event(
        channel="ai_creation",
        stage="video_prompt_batch",
        event="end",
        message="video prompt batch completed",
        callback=stage_callback,
        status="success",
        latency_ms=round((perf_counter() - start_time) * 1000),
        llm_call_count=stage_llm_calls,
        retry_count=max(stage_llm_calls - len(batches), 0),
        batch_total=len(batches),
        narration_count=len(narrations),
    )
    logger.info(
        f"鉁?Generated {len(all_prompts)} video prompts in {perf_counter() - start_time:.2f}s"
    )
    return all_prompts


