"""Lightweight text splitting helpers shared across the pipeline."""

from __future__ import annotations

import re
from typing import Iterable, List

_SENTENCE_CLOSE_CHARS = {'"', "'", "\u201d", "\u2019", ")", "]", "}"}
_SENTENCE_PUNCTUATION = {".", "!", "?", "\u3002", "\uff01", "\uff1f"}
_CLAUSE_PUNCTUATION = {",", ";", ":", "\u3001", "\uff0c", "\uff1b", "\uff1a"}
_CLAUSE_BREAK_TOKENS = (
    "......",
    "...",
    "\u2026\u2026",
    "\u2026",
    "\u2014\u2014",
    "\u2014",
    ",",
    ";",
    ":",
    "\u3001",
    "\uff0c",
    "\uff1b",
    "\uff1a",
)
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
_TTS_TERMINAL_PUNCTUATION = _SENTENCE_PUNCTUATION | {".", "\u2026"}
_CJK_CHAR_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _is_sentence_boundary(text: str, index: int) -> bool:
    char = text[index]
    if char not in _SENTENCE_PUNCTUATION:
        return False

    if char == "." and _is_ellipsis_dot(text, index):
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


def _is_ellipsis_dot(text: str, index: int) -> bool:
    if text[index] != ".":
        return False
    prev_char = text[index - 1] if index > 0 else ""
    next_char = text[index + 1] if index + 1 < len(text) else ""
    return prev_char == "." or next_char == "."


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


def normalize_tts_sentence_text(text: str) -> str:
    """Ensure TTS sentence-like units end with a strong terminal pause marker."""
    stripped = re.sub(r"\s+", " ", (text or "").strip())
    if not stripped:
        return ""

    suffix_chars: list[str] = []
    while stripped and stripped[-1] in _SENTENCE_CLOSE_CHARS:
        suffix_chars.append(stripped[-1])
        stripped = stripped[:-1].rstrip()

    if not stripped:
        return "".join(reversed(suffix_chars))

    if stripped.endswith("...") or stripped.endswith("\u2026\u2026"):
        return stripped + "".join(reversed(suffix_chars))

    last_char = stripped[-1]
    if last_char in _TTS_TERMINAL_PUNCTUATION:
        return stripped + "".join(reversed(suffix_chars))

    if last_char in _CLAUSE_PUNCTUATION:
        stripped = stripped[:-1].rstrip()

    punctuation = "\u3002" if _CJK_CHAR_PATTERN.search(stripped) else "."
    return stripped + punctuation + "".join(reversed(suffix_chars))


def join_tts_sentence_units(units: Iterable[str]) -> str:
    """Join TTS units after normalizing each one to keep natural pauses."""
    normalized_units = [
        normalize_tts_sentence_text(unit)
        for unit in units
        if unit and unit.strip()
    ]
    return join_text_units(normalized_units)


def _split_sentence_into_clauses(text: str) -> List[str]:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return []

    clauses: List[str] = []
    current: List[str] = []

    index = 0
    while index < len(cleaned):
        token = _match_clause_break_token(cleaned, index)
        if token is not None:
            current.append(token)
            segment = "".join(current).strip()
            if segment:
                clauses.append(segment)
            current = []
            index += len(token)
            while index < len(cleaned) and cleaned[index].isspace():
                index += 1
            continue

        current.append(cleaned[index])
        index += 1

    if current:
        segment = "".join(current).strip()
        if segment:
            clauses.append(segment)

    return clauses


def _match_clause_break_token(text: str, index: int) -> str | None:
    for token in _CLAUSE_BREAK_TOKENS:
        if text.startswith(token, index):
            return token
    char = text[index]
    if char in _CLAUSE_PUNCTUATION:
        return char
    return None
