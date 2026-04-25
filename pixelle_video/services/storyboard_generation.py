from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.storyboard_plan import (
    StoryboardPlan,
    StoryboardPlanFrame,
)


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
            raise ValueError("smart storyboard mode is not implemented yet")
        raise ValueError(f"unsupported storyboard mode: {storyboard_mode}")

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
