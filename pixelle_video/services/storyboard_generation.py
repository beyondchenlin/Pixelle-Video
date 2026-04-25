from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.content_generation import SmartStoryboardPlanResponse
from pixelle_video.models.storyboard_plan import (
    StoryboardPlan,
    StoryboardPlanFrame,
)
from pixelle_video.prompts.storyboard_generation import build_smart_storyboard_prompt


SENTENCE_TERMINATORS = "。！？.!?"
CLOSING_PUNCTUATION = "”’\"'）)]}》】」』"


def _is_unicode_punctuation(char: str) -> bool:
    return unicodedata.category(char).startswith("P")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _split_with_predicate(
    source_text: str,
    predicate: Callable[[str], bool],
) -> list[tuple[str, int, int]]:
    cleaned = _normalize_text(source_text)
    if not cleaned:
        return []

    segments: list[tuple[str, int, int]] = []
    current_start: int | None = None
    has_text = False

    for index, char in enumerate(cleaned):
        if current_start is None:
            if char.isspace():
                continue
            current_start = index

        if not char.isspace() and not _is_unicode_punctuation(char):
            has_text = True

        next_char = cleaned[index + 1] if index + 1 < len(cleaned) else ""
        should_split = has_text and predicate(char) and (
            not next_char or not predicate(next_char)
        )
        if should_split and current_start is not None:
            end = index + 1
            segments.append((cleaned[current_start:end], current_start, end))
            current_start = None
            has_text = False

    if current_start is not None and has_text:
        segments.append((cleaned[current_start:], current_start, len(cleaned)))

    return segments


def _sentence_segments(source_text: str) -> list[tuple[str, int, int]]:
    cleaned = _normalize_text(source_text)
    if not cleaned:
        return []

    segments: list[tuple[str, int, int]] = []
    current_start: int | None = None
    index = 0
    has_text = False
    while index < len(cleaned):
        char = cleaned[index]
        if current_start is None:
            if char.isspace():
                index += 1
                continue
            current_start = index

        if not char.isspace() and not _is_unicode_punctuation(char):
            has_text = True

        if has_text and char in SENTENCE_TERMINATORS:
            end = index + 1
            while end < len(cleaned) and cleaned[end] in SENTENCE_TERMINATORS:
                end += 1
            while end < len(cleaned) and cleaned[end] in CLOSING_PUNCTUATION:
                end += 1
            segments.append((cleaned[current_start:end], current_start, end))
            current_start = None
            has_text = False
            index = end
            continue

        index += 1

    if current_start is not None and has_text:
        segments.append((cleaned[current_start:], current_start, len(cleaned)))

    return segments


def _positive_int_config(config: dict[str, Any] | None, key: str, default: int) -> int:
    value = (config or {}).get(key, default)
    if type(value) is not int or value < 1:
        raise ValueError(f"{key} must be a positive integer")
    return value


@dataclass
class StoryboardGenerationService:
    config: dict[str, Any] | None = None

    async def generate(
        self,
        *,
        llm_service,
        source_text: str,
        storyboard_mode: str,
        storyboard_count_mode: str,
        storyboard_scene_count: int | None,
    ) -> StoryboardPlan:
        if not _normalize_text(source_text):
            raise ValueError("source_text must not be empty")
        if storyboard_mode == "punctuation":
            segments = _split_with_predicate(source_text, _is_unicode_punctuation)
            return self._plan_from_segments(
                mode="punctuation",
                count_mode=storyboard_count_mode,
                requested_scene_count=storyboard_scene_count,
                source_text=source_text,
                segments=segments,
            )
        if storyboard_mode == "sentence":
            segments = _sentence_segments(source_text)
            return self._plan_from_segments(
                mode="sentence",
                count_mode=storyboard_count_mode,
                requested_scene_count=storyboard_scene_count,
                source_text=source_text,
                segments=segments,
            )
        if storyboard_mode == "smart":
            return await self._generate_smart(
                llm_service=llm_service,
                source_text=source_text,
                count_mode=storyboard_count_mode,
                requested_scene_count=storyboard_scene_count,
            )
        raise ValueError(f"unsupported storyboard mode: {storyboard_mode}")

    async def _generate_smart(
        self,
        *,
        llm_service,
        source_text: str,
        count_mode: str,
        requested_scene_count: int | None,
    ) -> StoryboardPlan:
        if llm_service is None:
            raise ValueError("smart storyboard mode requires llm_service")

        normalized_source = _normalize_text(source_text)
        min_scene_count = _positive_int_config(self.config, "min_scene_count", 1)
        max_scene_count = _positive_int_config(self.config, "max_scene_count", 30)
        if min_scene_count > max_scene_count:
            raise ValueError("min_scene_count must not exceed max_scene_count")

        if count_mode not in {"auto", "manual"}:
            raise ValueError(f"unsupported storyboard count mode: {count_mode}")
        if count_mode == "manual":
            if type(requested_scene_count) is not int:
                raise ValueError("storyboard_scene_count is required with manual count mode")
            if not min_scene_count <= requested_scene_count <= max_scene_count:
                raise ValueError("storyboard_scene_count must be within configured bounds")
        elif requested_scene_count is not None:
            raise ValueError("storyboard_scene_count is valid only with manual count mode")

        prompt = build_smart_storyboard_prompt(
            source_text=normalized_source,
            count_mode=count_mode,
            requested_scene_count=requested_scene_count,
            min_scene_count=min_scene_count,
            max_scene_count=max_scene_count,
        )
        response = await llm_service(
            prompt=prompt,
            response_type=SmartStoryboardPlanResponse,
            temperature=0.3,
            max_tokens=max(2000, max_scene_count * 350),
        )

        frame_count = len(response.frames)
        if count_mode == "manual" and frame_count != requested_scene_count:
            raise ValueError(f"expected {requested_scene_count} smart storyboard frames")
        if frame_count > max_scene_count:
            raise ValueError("too many storyboard frames")
        if count_mode == "auto" and frame_count < min_scene_count:
            raise ValueError("too few storyboard frames")

        frames = [
            StoryboardPlanFrame(
                index=index,
                source_text=frame.source_text,
                narration_text=frame.narration_text,
                visual_goal=frame.visual_goal,
                prompt_intent=frame.prompt_intent,
                source_start=frame.source_start,
                source_end=frame.source_end,
                metadata={"strategy": "smart"},
            )
            for index, frame in enumerate(response.frames, start=1)
        ]
        return StoryboardPlan.build(
            mode="smart",
            count_mode=count_mode,
            requested_scene_count=requested_scene_count,
            source_text=normalized_source,
            frames=frames,
            diagnostics={
                "strategy": "smart",
                "requested_scene_count": requested_scene_count,
                "split_count": len(frames),
            },
        )

    def _plan_from_segments(
        self,
        *,
        mode: str,
        count_mode: str,
        requested_scene_count: int | None,
        source_text: str,
        segments: list[tuple[str, int, int]],
    ) -> StoryboardPlan:
        normalized_source = _normalize_text(source_text)
        effective_segments = segments or [(normalized_source, 0, len(normalized_source))]
        max_scene_count = _positive_int_config(self.config, "max_scene_count", 30)
        if len(effective_segments) > max_scene_count:
            raise ValueError(
                "too many storyboard frames; use smart storyboard mode or shorten the text"
            )

        frames = [
            StoryboardPlanFrame(
                index=index,
                source_text=segment,
                narration_text=segment,
                visual_goal=f"Visualize storyboard segment {index}.",
                prompt_intent=f"Create a coherent scene that communicates: {segment}",
                source_start=start,
                source_end=end,
                metadata={"strategy": mode},
            )
            for index, (segment, start, end) in enumerate(effective_segments, start=1)
        ]
        return StoryboardPlan.build(
            mode=mode,
            count_mode=count_mode,
            requested_scene_count=requested_scene_count,
            source_text=normalized_source,
            frames=frames,
            diagnostics={"strategy": mode, "split_count": len(frames)},
        )
