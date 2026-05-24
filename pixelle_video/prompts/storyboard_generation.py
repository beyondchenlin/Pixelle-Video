from __future__ import annotations

import json
import unicodedata

from pixelle_video.prompt_language import (
    CHINESE_PROMPT_LANGUAGE,
    DEFAULT_PROMPT_LANGUAGE,
    PromptLanguage,
    normalize_prompt_language,
)
from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template


def _split_into_sentences(text: str) -> list[tuple[str, int, int]]:
    """Split text into sentences and return (sentence, start_idx, end_idx) tuples."""
    import re

    # Match sentence-ending punctuation followed by optional closing punctuation
    sentence_end_pattern = r'[。！？.!?]+[\s"\'"\'）)}】」』]*'

    sentences = []
    last_end = 0

    for match in re.finditer(sentence_end_pattern, text):
        end = match.end()
        sentence = text[last_end:end].strip()
        if sentence:
            # Find actual start (skip leading whitespace)
            actual_start = last_end
            while actual_start < end and text[actual_start].isspace():
                actual_start += 1
            sentences.append((sentence, actual_start, end))
        last_end = end

    # Handle remaining text (if no ending punctuation)
    if last_end < len(text):
        remaining = text[last_end:].strip()
        if remaining:
            actual_start = last_end
            while actual_start < len(text) and text[actual_start].isspace():
                actual_start += 1
            sentences.append((remaining, actual_start, len(text)))

    return sentences


def _is_boundary_char(char: str) -> bool:
    return char.isspace() or unicodedata.category(char).startswith("P")


def _nearest_source_span_boundary(text: str, ideal: int, lower: int, upper: int) -> int:
    if upper - lower <= 1:
        return upper

    radius = max(1, len(text) // 20)
    start = max(lower + 1, ideal - radius)
    end = min(upper - 1, ideal + radius)
    candidates: list[int] = []
    for index in range(start, end + 1):
        previous_char = text[index - 1] if index > 0 else ""
        next_char = text[index] if index < len(text) else ""
        if previous_char and _is_boundary_char(previous_char):
            candidates.append(index)
        elif next_char and _is_boundary_char(next_char):
            candidates.append(index)

    if not candidates:
        return min(max(ideal, lower + 1), upper - 1)
    return min(candidates, key=lambda index: abs(index - ideal))


def _split_into_source_spans(text: str, span_count: int) -> list[tuple[str, int, int]]:
    """Split source text into deterministic contiguous spans for exact manual counts."""
    if span_count <= 0 or not text:
        return []
    if span_count == 1:
        return [(text, 0, len(text))]
    if span_count > len(text):
        raise ValueError("requested_scene_count cannot exceed source_text length")

    spans: list[tuple[str, int, int]] = []
    start = 0
    for span_index in range(1, span_count):
        remaining_spans = span_count - span_index
        min_end = start + 1
        max_end = len(text) - remaining_spans
        ideal = round(len(text) * span_index / span_count)
        end = _nearest_source_span_boundary(text, ideal, start, max_end)
        end = min(max(end, min_end), max_end)
        spans.append((text[start:end], start, end))
        start = end
    spans.append((text[start:], start, len(text)))
    return spans


def render_smart_storyboard_prompt(
    *,
    source_text: str,
    count_mode: str,
    requested_scene_count: int | None,
    min_scene_count: int,
    max_scene_count: int,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
) -> RenderedPrompt:
    count_instruction = (
        f"Create exactly {requested_scene_count} storyboard frames."
        if count_mode == "manual"
        else f"Choose the best storyboard frame count between {min_scene_count} and {max_scene_count}."
    )

    sentences = _split_into_sentences(source_text)
    sentence_list = [
        {"index": i, "text": sent[0]}
        for i, sent in enumerate(sentences)
    ]
    use_source_spans = (
        count_mode == "manual"
        and requested_scene_count is not None
        and requested_scene_count > len(sentences)
    )
    source_spans = (
        _split_into_source_spans(source_text, requested_scene_count)
        if use_source_spans
        else []
    )

    resolved_prompt_language = normalize_prompt_language(prompt_language)
    source_span_items = [
        {
            "index": index,
            "text": span_text,
            "source_start": start,
            "source_end": end,
        }
        for index, (span_text, start, end) in enumerate(source_spans)
    ]
    visual_goal_description = (
        "杩欎竴甯ч渶瑕佷紶杈剧殑瑙嗚閲嶇偣"
        if resolved_prompt_language == CHINESE_PROMPT_LANGUAGE
        else "What this frame should communicate visually."
    )
    return render_prompt_template(
        "storyboard_generation",
        {
            "prompt_language_json": json.dumps(resolved_prompt_language, ensure_ascii=False),
            "source_text_json": json.dumps(source_text, ensure_ascii=False),
            "sentences_json": json.dumps(sentence_list, ensure_ascii=False, indent=2),
            "count_instruction_json": json.dumps(count_instruction, ensure_ascii=False),
            "use_source_spans": use_source_spans,
            "use_sentence_indices": not use_source_spans,
            "source_spans_json": json.dumps(source_span_items, ensure_ascii=False, indent=2),
            "write_chinese_fields": resolved_prompt_language == CHINESE_PROMPT_LANGUAGE,
            "visual_goal_description_json": json.dumps(
                visual_goal_description,
                ensure_ascii=False,
            ),
        },
    )


__all__ = ["build_smart_storyboard_prompt", "_split_into_sentences", "_split_into_source_spans"]


def build_smart_storyboard_prompt(
    *,
    source_text: str,
    count_mode: str,
    requested_scene_count: int | None,
    min_scene_count: int,
    max_scene_count: int,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
) -> str:
    return render_smart_storyboard_prompt(
        source_text=source_text,
        count_mode=count_mode,
        requested_scene_count=requested_scene_count,
        min_scene_count=min_scene_count,
        max_scene_count=max_scene_count,
        prompt_language=prompt_language,
    ).text
