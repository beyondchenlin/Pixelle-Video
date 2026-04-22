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

import json
import re
import unicodedata
from typing import Any, List, Literal, Optional

from loguru import logger

from pixelle_video.config import config_manager
from pixelle_video.config.storyboard_preset_library import lookup_world_preset
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.services.storyboard_planner import plan_storyboard_batch
from pixelle_video.utils.prompt_helper import (
    assemble_image_prompt,
    assemble_negative_prompt,
    assemble_storyboard_prompt,
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


async def generate_title(
    llm_service,
    content: str,
    strategy: Literal["auto", "direct", "llm"] = "auto",
    max_length: int = 15
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
    if strategy == "direct":
        content = content.strip()
        return content[:max_length] if len(content) > max_length else content
    
    if strategy == "auto":
        if len(content.strip()) <= 15:
            return content.strip()
        # Fall through to LLM
    
    # Use LLM to generate title
    from pixelle_video.prompts import build_title_generation_prompt
    
    # Pass max_length to prompt so LLM knows the character limit
    prompt = build_title_generation_prompt(content, max_length=max_length)
    response = await llm_service(prompt, temperature=0.7, max_tokens=50)
    
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
    
    logger.debug(f"Generated title: '{title}' (length: {len(title)})")
    return title


async def generate_narrations_from_topic(
    llm_service,
    topic: str,
    n_scenes: int = 5,
    min_words: int = 5,
    max_words: int = 20
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
    
    logger.info(f"Generating {n_scenes} narrations from topic: {topic}")
    
    prompt = build_topic_narration_prompt(
        topic=topic,
        n_storyboard=n_scenes,
        min_words=min_words,
        max_words=max_words
    )
    
    response = await llm_service(
        prompt=prompt,
        temperature=0.8,
        max_tokens=2000
    )
    
    logger.debug(f"LLM response: {response[:200]}...")
    
    # Parse JSON
    result = _parse_json(response)
    
    if "narrations" not in result:
        raise ValueError("Invalid response format: missing 'narrations' key")
    
    narrations = result["narrations"]
    
    # Validate count
    if len(narrations) > n_scenes:
        logger.warning(f"Got {len(narrations)} narrations, taking first {n_scenes}")
        narrations = narrations[:n_scenes]
    elif len(narrations) < n_scenes:
        raise ValueError(f"Expected {n_scenes} narrations, got only {len(narrations)}")
    
    logger.info(f"Generated {len(narrations)} narrations successfully")
    return narrations


async def generate_narrations_from_content(
    llm_service,
    content: str,
    n_scenes: int = 5,
    min_words: int = 5,
    max_words: int = 20
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
    
    logger.info(f"Generating {n_scenes} narrations from content ({len(content)} chars)")
    
    prompt = build_content_narration_prompt(
        content=content,
        n_storyboard=n_scenes,
        min_words=min_words,
        max_words=max_words
    )
    
    response = await llm_service(
        prompt=prompt,
        temperature=0.8,
        max_tokens=2000
    )
    
    # Parse JSON
    result = _parse_json(response)
    
    if "narrations" not in result:
        raise ValueError("Invalid response format: missing 'narrations' key")
    
    narrations = result["narrations"]
    
    # Validate count
    if len(narrations) > n_scenes:
        logger.warning(f"Got {len(narrations)} narrations, taking first {n_scenes}")
        narrations = narrations[:n_scenes]
    elif len(narrations) < n_scenes:
        raise ValueError(f"Expected {n_scenes} narrations, got only {len(narrations)}")
    
    logger.info(f"Generated {len(narrations)} narrations successfully")
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
    logger.info(f"Splitting script (mode={split_mode}, length={len(script)} chars)")
    
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
    
    logger.info(f"Generating image prompts for {len(narrations)} narrations (batch_size={batch_size})")
    
    # Split narrations into batches
    batches = [narrations[i:i + batch_size] for i in range(0, len(narrations), batch_size)]
    logger.info(f"Split into {len(batches)} batches")
    
    all_prompts = []
    
    # Process each batch
    for batch_idx, batch_narrations in enumerate(batches, 1):
        logger.info(f"Processing batch {batch_idx}/{len(batches)} ({len(batch_narrations)} narrations)")
        
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
                
                response = await llm_service(
                    prompt=prompt,
                    temperature=0.7,
                    max_tokens=8192
                )
                
                logger.debug(f"Batch {batch_idx} attempt {attempt}: LLM response length: {len(response)} chars")
                
                # Parse JSON
                result = _parse_json(response)
                
                if "image_prompts" not in result:
                    raise KeyError("Invalid response format: missing 'image_prompts'")
                
                batch_prompts = result["image_prompts"]
                
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
                logger.info(f"鉁?Batch {batch_idx} completed successfully ({len(batch_prompts)} prompts)")
                all_prompts.extend(batch_prompts)
                
                # Report progress
                if progress_callback:
                    progress_callback(
                        len(all_prompts),
                        len(narrations),
                        f"Batch {batch_idx}/{len(batches)} completed"
                    )
                
                break
                
            except json.JSONDecodeError as e:
                logger.error(f"Batch {batch_idx} JSON parse error (attempt {attempt}/{max_retries}): {e}")
                if attempt >= max_retries:
                    raise
                logger.info(f"Retrying batch {batch_idx}...")
    
    logger.info(f"鉁?Generated {len(all_prompts)} image prompts")
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
) -> StyledImagePromptBatch:
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

    source = resolve_style_source(image_config, prompt_prefix_override=prompt_prefix)
    raw_prefix = source.raw_content if source else ""
    resolved_style = None
    style_profile = None
    planning_snapshot = None

    if source is not None:
        try:
            resolved_style = await resolve_style_spec(llm_service, source)
            style_profile = resolved_style.style_profile
        except Exception:
            logger.exception("Style resolution failed, falling back to legacy prefix concatenation")

    storyboard_enabled = _storyboard_controls_enabled()
    planning = None
    normalized_style = None
    if storyboard_enabled:
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
        planning_snapshot = dict(getattr(planning, "planning_snapshot", None) or {})

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

    if planning is not None:
        frame_plans = list(getattr(planning, "frames", ()) or ())
        if len(frame_plans) != len(base_prompts):
            raise ValueError("storyboard planner frames do not match generated base prompt count")

        world_preset = planning_snapshot.get("world_preset") or {}
        final_prompts = [
            assemble_storyboard_prompt(
                base_prompt=base_prompt,
                frame_plan=frame_plans[index],
                world_preset=world_preset,
                normalized_style=normalized_style,
            )
            for index, base_prompt in enumerate(base_prompts)
        ]
    else:
        final_prompts = [
            assemble_image_prompt(base_prompt, raw_prefix=raw_prefix, resolved_style=resolved_style)
            for base_prompt in base_prompts
        ]

    negative_prompt = assemble_negative_prompt(
        resolved_style,
        supports_negative_prompt=capabilities.supports_negative_prompt,
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
    
    logger.info(f"Generating video prompts for {len(narrations)} narrations (batch_size={batch_size})")
    
    # Split narrations into batches
    batches = [narrations[i:i + batch_size] for i in range(0, len(narrations), batch_size)]
    logger.info(f"Split into {len(batches)} batches")
    
    all_prompts = []
    
    # Process each batch
    for batch_idx, batch_narrations in enumerate(batches, 1):
        logger.info(f"Processing batch {batch_idx}/{len(batches)} ({len(batch_narrations)} narrations)")
        
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
                
                response = await llm_service(
                    prompt=prompt,
                    temperature=0.7,
                    max_tokens=8192
                )
                
                logger.debug(f"Batch {batch_idx} attempt {attempt}: LLM response length: {len(response)} chars")
                
                # Parse JSON
                result = _parse_json(response)
                
                if "video_prompts" not in result:
                    raise KeyError("Invalid response format: missing 'video_prompts'")
                
                batch_prompts = result["video_prompts"]
                
                # Validate batch result
                if len(batch_prompts) != len(batch_narrations):
                    raise ValueError(
                        f"Prompt count mismatch: expected {len(batch_narrations)}, got {len(batch_prompts)}"
                    )
                
                # Success - add to all_prompts
                all_prompts.extend(batch_prompts)
                logger.info(f"鉁?Batch {batch_idx} completed: {len(batch_prompts)} video prompts")
                
                # Report progress
                if progress_callback:
                    completed = len(all_prompts)
                    total = len(narrations)
                    progress_callback(completed, total, f"Batch {batch_idx}/{len(batches)} completed")
                
                break  # Success, move to next batch
            
            except Exception as e:
                logger.warning(f"鉁?Batch {batch_idx} attempt {attempt} failed: {e}")
                if attempt >= max_retries:
                    raise
                logger.info(f"Retrying batch {batch_idx}...")
    
    logger.info(f"鉁?Generated {len(all_prompts)} video prompts")
    return all_prompts


def _parse_json(text: str) -> dict:
    """
    Parse JSON from text, with fallback to extract JSON from markdown code blocks
    
    Args:
        text: Text containing JSON
        
    Returns:
        Parsed JSON dict
        
    Raises:
        json.JSONDecodeError: If no valid JSON found
    """
    # Try direct parsing first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON from markdown code block
    json_pattern = r'```(?:json)?\s*([\s\S]+?)\s*```'
    match = re.search(json_pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try to find any JSON object in the text
    json_pattern = r'\{[^{}]*(?:"narrations"|"image_prompts")\s*:\s*\[[^\]]*\][^{}]*\}'
    match = re.search(json_pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    
    # If all fails, raise error
    raise json.JSONDecodeError("No valid JSON found", text, 0)

