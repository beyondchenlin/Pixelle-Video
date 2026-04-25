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
            segments = _split_with_predicate(
                source_text,
                lambda char: char in SENTENCE_TERMINATORS,
            )
            return self._plan_from_segments(
                mode="sentence",
                count_mode=storyboard_count_mode,
                requested_scene_count=storyboard_scene_count,
                source_text=source_text,
                segments=segments,
            )
        raise ValueError("smart storyboard mode is not implemented yet")

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
        max_scene_count = int((self.config or {}).get("max_scene_count", 30))
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
