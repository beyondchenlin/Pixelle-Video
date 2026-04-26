from __future__ import annotations

import json
import unicodedata


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


def build_smart_storyboard_prompt(
    *,
    source_text: str,
    count_mode: str,
    requested_scene_count: int | None,
    min_scene_count: int,
    max_scene_count: int,
) -> str:
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

    payload = {
        "task": "create_storyboard_plan_from_complete_source_text",
        "source_text": source_text,
        "sentences": sentence_list,
        "count_instruction": count_instruction,
        "requirements": [
            "Understand the complete source_text before creating frames.",
            "The returned frames must cover the entire source_text in source order.",
            "Do not omit meaningful source_text; only whitespace-only gaps between frames are allowed.",
            "Use sentence_indices to specify which sentences each frame covers.",
            "Frames may cover multiple consecutive sentences (e.g., [0, 1, 2]).",
            "Do not split one sentence across multiple frames when using sentence_indices.",
            "All sentence indices must be covered by exactly one frame (no gaps, no overlaps).",
            "Maintain continuity of style, subjects, and visual logic across all frames.",
            "Do not rewrite or summarize voiceover text; speech and captions are planned separately from source_text.",
            "Do not generate final image prompts.",
            "Return JSON only.",
        ],
        "frame_schema": {
            "source_text": "Text preview covered by this frame (for reference).",
            "visual_goal": "What this frame should communicate visually.",
            "prompt_intent": "Guidance for later image prompt composition.",
            "sentence_indices": "Required: consecutive sentence indices covered by this frame (e.g., [0, 1] or [3]).",
        },
    }
    if use_source_spans:
        payload["source_spans"] = [
            {
                "index": index,
                "text": span_text,
                "source_start": start,
                "source_end": end,
            }
            for index, (span_text, start, end) in enumerate(source_spans)
        ]
        payload["requirements"] = [
            requirement
            for requirement in payload["requirements"]
            if "sentence_indices" not in requirement
            and "sentence indices" not in requirement
        ]
        payload["requirements"].extend(
            [
                "Use source_span_indices, not sentence_indices, because the requested frame count exceeds the sentence count.",
                "Each frame must cover one or more consecutive source_spans.",
                "All source_span_indices must be covered by exactly one frame in source order (no gaps, no overlaps).",
            ]
        )
        payload["frame_schema"].pop("sentence_indices", None)
        payload["frame_schema"]["source_span_indices"] = (
            "Required: consecutive source_spans covered by this frame (e.g., [0] or [1, 2])."
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = ["build_smart_storyboard_prompt", "_split_into_sentences", "_split_into_source_spans"]
