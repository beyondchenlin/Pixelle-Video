from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.content_generation import SmartStoryboardPlanResponse
from pixelle_video.models.storyboard_limits import (
    StoryboardGenerationLimits,
    storyboard_generation_limits_from_config,
)
from pixelle_video.models.storyboard_plan import (
    StoryboardPlan,
    StoryboardPlanFrame,
)
from pixelle_video.prompts.storyboard_generation import (
    _split_into_source_spans,
    build_smart_storyboard_prompt,
)

SMART_STORYBOARD_BASE_MAX_TOKENS = 2000
SMART_STORYBOARD_MAX_TOKENS_PER_SCENE = 350
SMART_STORYBOARD_COMPATIBLE_MAX_TOKENS = 8192
_LITERAL_CONTROL_ESCAPE_PATTERN = re.compile(
    r"(^|[\s。！？.!?,，；;：:])([\\/]+n)(?=\s|$|[A-Za-z0-9\u3400-\u9fff])",
    flags=re.IGNORECASE,
)


SENTENCE_TERMINATORS = "。！？.!?"
CLOSING_PUNCTUATION = "”’\"'）)]}》】」』"


def _is_unicode_punctuation(char: str) -> bool:
    return unicodedata.category(char).startswith("P")


def _normalize_text(text: str) -> str:
    text = _LITERAL_CONTROL_ESCAPE_PATTERN.sub(r"\1 ", text)
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


def _smart_storyboard_max_tokens(max_scene_count: int) -> int:
    requested_tokens = max(
        SMART_STORYBOARD_BASE_MAX_TOKENS,
        max_scene_count * SMART_STORYBOARD_MAX_TOKENS_PER_SCENE,
    )
    return min(requested_tokens, SMART_STORYBOARD_COMPATIBLE_MAX_TOKENS)


def _repair_prompt(original_prompt: str, reason: str) -> str:
    return (
        f"{original_prompt}\n\n"
        "# Repair the previous storyboard response\n"
        f"The previous response was invalid: {reason}\n"
        "Return a corrected JSON object that satisfies the same schema and requirements."
    )


def _assert_no_meaningful_source_gap(source_text: str, start: int, end: int) -> None:
    gap = source_text[start:end]
    if any(not char.isspace() and not _is_unicode_punctuation(char) for char in gap):
        raise ValueError("smart storyboard frames must cover source_text")


def _has_punctuation_source_gap(source_text: str, start: int, end: int) -> bool:
    return any(_is_unicode_punctuation(char) for char in source_text[start:end])


def _extend_frame_source(
    frame: StoryboardPlanFrame,
    *,
    source_text: str,
    end: int,
    start: int | None = None,
) -> StoryboardPlanFrame:
    resolved_start = (
        start
        if start is not None
        else frame.source_start
        if frame.source_start is not None
        else 0
    )
    return StoryboardPlanFrame(
        index=frame.index,
        source_text=source_text[resolved_start:end],
        visual_goal=frame.visual_goal,
        prompt_intent=frame.prompt_intent,
        frame_id=frame.frame_id,
        shot_type=frame.shot_type,
        shot_purpose=frame.shot_purpose,
        primary_subject=frame.primary_subject,
        secondary_subjects=frame.secondary_subjects,
        continuity_anchors=frame.continuity_anchors,
        world_elements=frame.world_elements,
        source_start=resolved_start,
        source_end=end,
        metadata=frame.metadata,
    )


@dataclass
class StoryboardGenerationService:
    config: Any | None = None

    @property
    def limits(self) -> StoryboardGenerationLimits:
        return storyboard_generation_limits_from_config(self.config)

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
        limits = self.limits
        min_scene_count = limits.min_scene_count
        max_scene_count = limits.max_scene_count

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
        try:
            frames = await self._generate_smart_frames_with_repair(
                llm_service=llm_service,
                prompt=prompt,
                source_text=normalized_source,
                count_mode=count_mode,
                requested_scene_count=requested_scene_count,
                min_scene_count=min_scene_count,
                max_scene_count=max_scene_count,
            )
        except ValueError as exc:
            if (
                count_mode != "auto"
                or str(exc) != "smart storyboard frame source_text must be traceable"
            ):
                raise
            return self._plan_from_segments(
                mode="smart",
                count_mode=count_mode,
                requested_scene_count=requested_scene_count,
                source_text=normalized_source,
                segments=_sentence_segments(normalized_source),
                frame_strategy="smart_sentence_fallback",
                diagnostics_strategy="smart_sentence_fallback",
                extra_diagnostics={
                    "requested_scene_count": requested_scene_count,
                    "fallback_reason": str(exc),
                },
            )

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

    async def _generate_smart_frames_with_repair(
        self,
        *,
        llm_service,
        prompt: str,
        source_text: str,
        count_mode: str,
        requested_scene_count: int | None,
        min_scene_count: int,
        max_scene_count: int,
    ) -> list[StoryboardPlanFrame]:
        current_prompt = prompt
        temperature = 0.3
        repair_used = False
        while True:
            try:
                response = await llm_service(
                    prompt=current_prompt,
                    response_type=SmartStoryboardPlanResponse,
                    temperature=temperature,
                    max_tokens=_smart_storyboard_max_tokens(max_scene_count),
                )
                self._validate_smart_frame_count(
                    frame_count=len(response.frames),
                    count_mode=count_mode,
                    requested_scene_count=requested_scene_count,
                    min_scene_count=min_scene_count,
                    max_scene_count=max_scene_count,
                )
                frames = self._frames_from_smart_response(
                    response=response,
                    source_text=source_text,
                    count_mode=count_mode,
                    requested_scene_count=requested_scene_count,
                )
                self._validate_smart_frame_count(
                    frame_count=len(frames),
                    count_mode=count_mode,
                    requested_scene_count=requested_scene_count,
                    min_scene_count=min_scene_count,
                    max_scene_count=max_scene_count,
                )
                return frames
            except ValueError as exc:
                if repair_used:
                    raise
                current_prompt = _repair_prompt(prompt, str(exc))
                temperature = 0.2
                repair_used = True

    def _validate_smart_frame_count(
        self,
        *,
        frame_count: int,
        count_mode: str,
        requested_scene_count: int | None,
        min_scene_count: int,
        max_scene_count: int,
    ) -> None:
        if count_mode == "manual" and frame_count != requested_scene_count:
            raise ValueError(f"expected {requested_scene_count} smart storyboard frames")
        if frame_count > max_scene_count:
            raise ValueError("too many storyboard frames")
        if count_mode == "auto" and frame_count < min_scene_count:
            raise ValueError("too few storyboard frames")

    def _frames_from_smart_response(
        self,
        *,
        response: SmartStoryboardPlanResponse,
        source_text: str,
        count_mode: str,
        requested_scene_count: int | None,
    ) -> list[StoryboardPlanFrame]:
        # First, try deterministic source-span indices when the prompt provides
        # spans for exact manual counts that cannot be represented as sentences.
        from pixelle_video.prompts.storyboard_generation import _split_into_sentences

        sentences = _split_into_sentences(source_text)
        should_use_source_spans = (
            count_mode == "manual"
            and requested_scene_count is not None
            and requested_scene_count > len(sentences)
        )
        has_source_span_indices = any(
            frame.source_span_indices is not None and len(frame.source_span_indices) > 0
            for frame in response.frames
        )
        if should_use_source_spans and has_source_span_indices:
            span_count = (
                requested_scene_count
                if count_mode == "manual" and requested_scene_count is not None
                else max(
                    max(frame.source_span_indices or [0])
                    for frame in response.frames
                )
                + 1
            )
            return self._frames_from_source_span_indices(
                response=response,
                source_text=source_text,
                source_spans=_split_into_source_spans(source_text, span_count),
            )

        # Next, try to use sentence_indices if available.
        has_sentence_indices = any(
            frame.sentence_indices is not None and len(frame.sentence_indices) > 0
            for frame in response.frames
        )

        # Only use sentence_indices mode if sentences were successfully extracted
        if has_sentence_indices and sentences:
            return self._frames_from_sentence_indices(
                response=response,
                source_text=source_text,
                sentences=sentences,
            )
        else:
            # Fall back to legacy char-offset based parsing
            return self._frames_from_char_offsets(
                response=response,
                source_text=source_text,
            )

    def _frames_from_sentence_indices(
        self,
        *,
        response: SmartStoryboardPlanResponse,
        source_text: str,
        sentences: list[tuple[str, int, int]],
    ) -> list[StoryboardPlanFrame]:
        """Build frames from sentence indices - more reliable than char offsets."""
        frames: list[StoryboardPlanFrame] = []
        covered_indices: set[int] = set()
        next_expected_index = 0

        for index, frame in enumerate(response.frames, start=1):
            if frame.sentence_indices is None or len(frame.sentence_indices) == 0:
                raise ValueError(f"Frame {index} missing sentence_indices")

            sentence_indices = list(frame.sentence_indices)
            first_idx = min(sentence_indices)
            last_idx = max(sentence_indices)
            if sentence_indices != list(range(first_idx, last_idx + 1)):
                raise ValueError(f"Frame {index} sentence_indices must be consecutive")
            if first_idx != next_expected_index:
                raise ValueError("sentence_indices must cover source_text in source order")

            # Validate indices
            for si in sentence_indices:
                if si < 0 or si >= len(sentences):
                    raise ValueError(f"Frame {index} has invalid sentence index: {si}")
                if si in covered_indices:
                    raise ValueError(f"Frame {index} overlaps: sentence {si} already covered")
                covered_indices.add(si)

            # Calculate source range from sentence indices
            start = sentences[first_idx][1]  # start position of first sentence
            end = sentences[last_idx][2]     # end position of last sentence
            next_expected_index = last_idx + 1

            resolved_source_text = source_text[start:end]

            frames.append(
                StoryboardPlanFrame(
                    index=index,
                    source_text=resolved_source_text,
                    visual_goal=frame.visual_goal,
                    prompt_intent=frame.prompt_intent,
                    source_start=start,
                    source_end=end,
                    metadata={"strategy": "smart", "sentence_indices": sentence_indices},
                )
            )

        # Verify all sentences are covered
        if len(covered_indices) != len(sentences):
            missing = set(range(len(sentences))) - covered_indices
            raise ValueError(f"Some sentences not covered by any frame: {sorted(missing)}")

        return frames

    def _frames_from_source_span_indices(
        self,
        *,
        response: SmartStoryboardPlanResponse,
        source_text: str,
        source_spans: list[tuple[str, int, int]],
    ) -> list[StoryboardPlanFrame]:
        frames: list[StoryboardPlanFrame] = []
        covered_indices: set[int] = set()
        next_expected_index = 0

        for index, frame in enumerate(response.frames, start=1):
            if frame.source_span_indices is None or len(frame.source_span_indices) == 0:
                raise ValueError(f"Frame {index} missing source_span_indices")

            span_indices = list(frame.source_span_indices)
            first_idx = min(span_indices)
            last_idx = max(span_indices)
            if span_indices != list(range(first_idx, last_idx + 1)):
                raise ValueError(f"Frame {index} source_span_indices must be consecutive")
            if first_idx != next_expected_index:
                raise ValueError("source_span_indices must cover source_text in source order")

            for span_index in span_indices:
                if span_index < 0 or span_index >= len(source_spans):
                    raise ValueError(f"Frame {index} has invalid source span index: {span_index}")
                if span_index in covered_indices:
                    raise ValueError(f"Frame {index} overlaps: source span {span_index} already covered")
                covered_indices.add(span_index)

            start = source_spans[first_idx][1]
            end = source_spans[last_idx][2]
            next_expected_index = last_idx + 1

            frames.append(
                StoryboardPlanFrame(
                    index=index,
                    source_text=source_text[start:end],
                    visual_goal=frame.visual_goal,
                    prompt_intent=frame.prompt_intent,
                    source_start=start,
                    source_end=end,
                    metadata={"strategy": "smart_source_spans", "source_span_indices": span_indices},
                )
            )

        if len(covered_indices) != len(source_spans):
            missing = set(range(len(source_spans))) - covered_indices
            raise ValueError(f"Some source spans not covered by any frame: {sorted(missing)}")

        return frames

    def _frames_from_char_offsets(
        self,
        *,
        response: SmartStoryboardPlanResponse,
        source_text: str,
    ) -> list[StoryboardPlanFrame]:
        """Legacy method: build frames from char offsets (may have drift issues)."""
        search_start = 0
        frames: list[StoryboardPlanFrame] = []
        for index, frame in enumerate(response.frames, start=1):
            start = frame.source_start
            end = frame.source_end
            has_explicit_range = start is not None and end is not None
            if not has_explicit_range:
                start = source_text.find(frame.source_text, search_start)
                if start < 0:
                    if source_text.find(frame.source_text) >= 0:
                        raise ValueError("smart storyboard frame source ranges must be ordered")
                    raise ValueError("smart storyboard frame source_text must be traceable")
                end = start + len(frame.source_text)
            if type(start) is not int or type(end) is not int:
                raise ValueError("smart storyboard frame source range must use integer offsets")
            if not 0 <= start <= end <= len(source_text):
                raise ValueError("smart storyboard frame source range must index source_text")
            if start < search_start:
                raise ValueError("smart storyboard frame source ranges must be ordered")

            _assert_no_meaningful_source_gap(source_text, search_start, start)
            if not frames and start > search_start and _has_punctuation_source_gap(
                source_text,
                search_start,
                start,
            ):
                start = search_start
            if frames and start > search_start and _has_punctuation_source_gap(
                source_text,
                search_start,
                start,
            ):
                frames[-1] = _extend_frame_source(
                    frames[-1],
                    source_text=source_text,
                    end=start,
                )
            resolved_source_text = source_text[start:end]
            if has_explicit_range and not resolved_source_text.strip():
                raise ValueError("smart storyboard frame source range must cover text")
            if not has_explicit_range and resolved_source_text != frame.source_text:
                raise ValueError("smart storyboard frame source_text must be traceable")
            search_start = max(search_start, end)
            frames.append(
                StoryboardPlanFrame(
                    index=index,
                    source_text=resolved_source_text,
                    visual_goal=frame.visual_goal,
                    prompt_intent=frame.prompt_intent,
                    source_start=start,
                    source_end=end,
                    metadata={"strategy": "smart"},
                )
            )
        _assert_no_meaningful_source_gap(source_text, search_start, len(source_text))
        if frames and search_start < len(source_text) and _has_punctuation_source_gap(
            source_text,
            search_start,
            len(source_text),
        ):
            frames[-1] = _extend_frame_source(
                frames[-1],
                source_text=source_text,
                end=len(source_text),
            )
        return frames

    def _plan_from_segments(
        self,
        *,
        mode: str,
        count_mode: str,
        requested_scene_count: int | None,
        source_text: str,
        segments: list[tuple[str, int, int]],
        frame_strategy: str | None = None,
        diagnostics_strategy: str | None = None,
        extra_diagnostics: dict[str, Any] | None = None,
    ) -> StoryboardPlan:
        normalized_source = _normalize_text(source_text)
        effective_segments = segments or [(normalized_source, 0, len(normalized_source))]
        max_scene_count = self.limits.max_scene_count
        if len(effective_segments) > max_scene_count:
            raise ValueError(
                "too many storyboard frames; use smart storyboard mode or shorten the text"
            )

        frames = [
            StoryboardPlanFrame(
                index=index,
                source_text=segment,
                visual_goal=f"Visualize storyboard segment {index}.",
                prompt_intent=f"Create a coherent scene that communicates: {segment}",
                source_start=start,
                source_end=end,
                metadata={"strategy": frame_strategy or mode},
            )
            for index, (segment, start, end) in enumerate(effective_segments, start=1)
        ]
        diagnostics = {
            "strategy": diagnostics_strategy or mode,
            "split_count": len(frames),
        }
        if extra_diagnostics:
            diagnostics.update(extra_diagnostics)
        return StoryboardPlan.build(
            mode=mode,
            count_mode=count_mode,
            requested_scene_count=requested_scene_count,
            source_text=normalized_source,
            frames=frames,
            diagnostics=diagnostics,
        )
