"""Lightweight text splitting helpers shared across the pipeline."""

from __future__ import annotations

import re
from typing import Iterable, List

_SENTENCE_CLOSE_CHARS = {'"', "'", "\u201d", "\u2019", ")", "]", "}"}
_SENTENCE_PUNCTUATION = {".", "!", "?", "\u3002", "\uff01", "\uff1f"}
_CLAUSE_PUNCTUATION = {",", ";", ":", "\u3001", "\uff0c", "\uff1b", "\uff1a"}
_JOIN_WITHOUT_SPACE_AFTER = {
    "\u3001",
    "\uff0c",
    "\uff1b",
    "\uff1a",
    "\u3002",
    "\uff01",
    "\uff1f",
    "\u2026",
}


def _is_sentence_boundary(text: str, index: int) -> bool:
    char = text[index]
    if char not in _SENTENCE_PUNCTUATION:
        return False

    prev_char = text[index - 1] if index > 0 else ""
    next_char = text[index + 1] if index + 1 < len(text) else ""

    if char == "." and prev_char.isdigit() and next_char.isdigit():
        return False

    if char in {"\u3002", "\uff01", "\uff1f"}:
        return True

    if not next_char:
        return True

    if char == ".":
        return next_char.isspace() or next_char in _SENTENCE_CLOSE_CHARS

    return next_char.isspace() or next_char in _SENTENCE_CLOSE_CHARS or next_char.isupper()


def split_text_into_sentences(text: str) -> List[str]:
    """
    Split text into sentence-like units while preserving punctuation and closing quotes.

    The heuristic intentionally stays lightweight but handles:
    - decimals like ``2.1``
    - quoted endings like ``"Go."``
    - CJK sentence punctuation
    - a narrow no-space English boundary case like ``Wait!Another sentence.``
      after ``!`` or ``?`` when the next sentence starts with an uppercase letter
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


def split_text_into_subtitle_phrases(text: str) -> List[str]:
    """Split subtitle text into shorter phrase units while preserving punctuation."""
    phrases: List[str] = []
    for sentence in split_text_into_sentences(text):
        phrases.extend(_split_sentence_into_clauses(sentence))
    return phrases


def join_text_units(units: Iterable[str]) -> str:
    """Join aligned text units while avoiding artificial spaces after CJK punctuation."""
    cleaned_units = [unit.strip() for unit in units if unit and unit.strip()]
    if not cleaned_units:
        return ""

    joined = " ".join(cleaned_units)
    no_space_after = "".join(sorted(_JOIN_WITHOUT_SPACE_AFTER))
    return re.sub(rf"([{re.escape(no_space_after)}])\s+", r"\1", joined)


def _split_sentence_into_clauses(text: str) -> List[str]:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return []

    clauses: List[str] = []
    current: List[str] = []

    for index, char in enumerate(cleaned):
        current.append(char)
        next_char = cleaned[index + 1] if index + 1 < len(cleaned) else ""
        should_split = char in _CLAUSE_PUNCTUATION and (
            not next_char or next_char not in _CLAUSE_PUNCTUATION
        )
        if should_split:
            segment = "".join(current).strip()
            if segment:
                clauses.append(segment)
            current = []

    if current:
        segment = "".join(current).strip()
        if segment:
            clauses.append(segment)

    return clauses
