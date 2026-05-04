from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class OmniVoiceLongformBlock:
    id: str
    text: str
    source_start: int
    source_end: int
    char_count: int
    boundary_type: str
    split_reason: str
    source_audio_path: str | None = None
    normalized_audio_path: str | None = None
    duration_ms: int | None = None


@dataclass
class OmniVoiceLongformBlockPlan:
    plan_id: str
    mode: str
    source_text_hash: str
    source_char_count: int
    blocks: list[OmniVoiceLongformBlock] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_omnivoice_longform_block_plan(
    text: str,
    *,
    max_chars_per_block: int = 6000,
    hard_max_chars_per_block: int = 9000,
) -> OmniVoiceLongformBlockPlan:
    source_text = text or ""
    text_hash = hashlib.sha1(source_text.encode("utf-8")).hexdigest()
    blocks: list[OmniVoiceLongformBlock] = []

    cursor = 0
    while cursor < len(source_text):
        target = min(cursor + max_chars_per_block, len(source_text))
        if target >= len(source_text):
            end = len(source_text)
            boundary_type = "end_of_text"
            split_reason = "end_of_text"
        else:
            end = _find_block_boundary(
                source_text,
                cursor,
                target,
                hard_max_chars_per_block,
            )
            boundary_type = "sentence"
            split_reason = "sentence_boundary"

        if end <= cursor:
            end = min(cursor + hard_max_chars_per_block, len(source_text))
            boundary_type = "hard_limit"
            split_reason = "hard_limit"

        segment = source_text[cursor:end]
        blocks.append(
            OmniVoiceLongformBlock(
                id=f"block-{len(blocks) + 1}",
                text=segment,
                source_start=cursor,
                source_end=end,
                char_count=len(segment),
                boundary_type=boundary_type,
                split_reason=split_reason,
            )
        )
        cursor = end

    return OmniVoiceLongformBlockPlan(
        plan_id=text_hash[:12],
        mode="omnivoice_master_track_longform",
        source_text_hash=text_hash,
        source_char_count=len(source_text),
        blocks=blocks,
        config={
            "max_chars_per_block": max_chars_per_block,
            "hard_max_chars_per_block": hard_max_chars_per_block,
        },
    )


def _find_block_boundary(
    text: str,
    cursor: int,
    target: int,
    hard_max_chars_per_block: int,
) -> int:
    hard_end = min(cursor + hard_max_chars_per_block, len(text))
    for index in range(min(hard_end, len(text)) - 1, target - 1, -1):
        if _is_sentence_boundary(text, index):
            return _consume_closing_punctuation(text, index + 1, hard_end)
    for index in range(target - 1, cursor - 1, -1):
        if _is_sentence_boundary(text, index):
            return _consume_closing_punctuation(text, index + 1, hard_end)
    return hard_end


def _is_sentence_boundary(text: str, index: int) -> bool:
    char = text[index]
    if char in "。！？!?":
        return True
    if char != ".":
        return False
    if _is_decimal_period(text, index):
        return False
    if _is_domain_period(text, index):
        return False
    if _is_common_abbreviation_period(text, index):
        return False
    return True


def _is_decimal_period(text: str, index: int) -> bool:
    return (
        index > 0
        and index + 1 < len(text)
        and text[index - 1].isdigit()
        and text[index + 1].isdigit()
    )


def _is_domain_period(text: str, index: int) -> bool:
    return (
        index > 0
        and index + 1 < len(text)
        and text[index - 1].isalnum()
        and text[index + 1].isalnum()
    )


def _is_common_abbreviation_period(text: str, index: int) -> bool:
    start = index
    while start > 0 and text[start - 1].isalpha():
        start -= 1
    token = text[start:index].lower()
    return token in {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc"}


def _consume_closing_punctuation(text: str, index: int, hard_end: int) -> int:
    closing_chars = set("\"'”’）)]} \n\r\t")
    cursor = index
    while cursor < hard_end and text[cursor] in closing_chars:
        cursor += 1
    return cursor
