"""Lightweight text splitting helpers shared across the pipeline."""

from __future__ import annotations

import re
import unicodedata
from typing import List

_SENTENCE_CLOSE_CHARS = {'"', "'", "”", "’", ")", "]", "}"}
_SENTENCE_PUNCTUATION = {".", "!", "?", "。", "！", "？"}


def _is_sentence_boundary(text: str, index: int) -> bool:
    char = text[index]
    if char not in _SENTENCE_PUNCTUATION:
        return False

    prev_char = text[index - 1] if index > 0 else ""
    next_char = text[index + 1] if index + 1 < len(text) else ""

    if char == "." and prev_char.isdigit() and next_char.isdigit():
        return False

    if char in {"。", "！", "？"}:
        return True

    if not next_char:
        return True

    if next_char.isspace() or next_char in _SENTENCE_CLOSE_CHARS:
        return True

    if next_char.isupper() or next_char.isdigit():
        return True

    return unicodedata.category(next_char).startswith("L") and not next_char.islower()


def split_text_into_sentences(text: str) -> List[str]:
    """
    Split text into sentence-like units while preserving punctuation and closing quotes.

    The heuristic intentionally stays lightweight but handles:
    - decimals like ``2.1``
    - quoted endings like ``"Go."``
    - CJK sentence punctuation
    - no-space English boundaries like ``Wait!Another sentence.``
    """
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return []

    sentences: List[str] = []
    current: List[str] = []
    index = 0

    while index < len(cleaned):
        char = cleaned[index]
        current.append(char)

        if _is_sentence_boundary(cleaned, index):
            next_index = index + 1
            while next_index < len(cleaned) and cleaned[next_index] in _SENTENCE_CLOSE_CHARS:
                current.append(cleaned[next_index])
                next_index += 1

            segment = "".join(current).strip()
            if segment:
                sentences.append(segment)

            current = []
            index = next_index
            while index < len(cleaned) and cleaned[index].isspace():
                index += 1
            continue

        index += 1

    if current:
        segment = "".join(current).strip()
        if segment:
            sentences.append(segment)

    return sentences
