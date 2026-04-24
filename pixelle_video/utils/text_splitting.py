"""Lightweight text splitting helpers shared across the pipeline."""

from __future__ import annotations

import math
import re
import unicodedata
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
_TTS_JOIN_DIRECT_AFTER = _TTS_TERMINAL_PUNCTUATION | {"!", "?", "\uff01", "\uff1f"}
_CAPTION_TERMINAL_CLOSING_CHARS = _SENTENCE_CLOSE_CHARS | {
    "\u3009",
    "\u300b",
    "\u300d",
    "\u300f",
    "\u3011",
    "\u3015",
    "\u3017",
    "\u3019",
    "\u301b",
    "\uff09",
    "\uff3d",
    "\uff5d",
}
_CAPTION_TERMINAL_WRAPPER_CHARS = _CAPTION_TERMINAL_CLOSING_CHARS | {
    "\u2018",
    "\u201c",
    "\u3008",
    "\u300a",
    "\u300c",
    "\u300e",
    "\u3010",
    "\u3014",
    "\u3016",
    "\u3018",
    "\u301a",
    "\uff08",
    "\uff3b",
    "\uff5b",
    "(",
    "[",
    "{",
}
_CJK_CHAR_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ASCII_WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")
SUPPORTED_TTS_SENTENCE_JOINER_MODES = ("direct", "space")
DEFAULT_TTS_SENTENCE_JOINER_MODE = "direct"
SUPPORTED_CAPTION_PUNCTUATION_MODES = ("strip_all", "strip_terminal", "preserve")
DEFAULT_CAPTION_PUNCTUATION_MODE = "strip_all"


def validate_tts_sentence_joiner_mode(value: str | None) -> str:
    normalized = (value or DEFAULT_TTS_SENTENCE_JOINER_MODE).strip().lower()
    if normalized in SUPPORTED_TTS_SENTENCE_JOINER_MODES:
        return normalized
    supported = ", ".join(SUPPORTED_TTS_SENTENCE_JOINER_MODES)
    raise ValueError(f"tts_sentence_joiner_mode must be one of: {supported}")


def validate_caption_punctuation_mode(value: str | None) -> str:
    normalized = (value or DEFAULT_CAPTION_PUNCTUATION_MODE).strip().lower()
    if normalized in SUPPORTED_CAPTION_PUNCTUATION_MODES:
        return normalized
    supported = ", ".join(SUPPORTED_CAPTION_PUNCTUATION_MODES)
    raise ValueError(f"caption_punctuation_mode must be one of: {supported}")


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


def split_text_into_tts_phrases(text: str) -> List[str]:
    """Split TTS text into phrase units around natural punctuation pauses."""
    return split_text_into_subtitle_phrases(text)


def estimate_tts_text_budget_length(text: str) -> int:
    """
    Estimate a conservative TTS budget length for mixed-script text.

    Rules of thumb:
    - CJK characters count as 1
    - ASCII word runs count as roughly half-length, rounded up
    - punctuation/whitespace are treated as preferred break hints, not budget drivers
    """
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return 0

    total = 0
    index = 0
    while index < len(cleaned):
        char = cleaned[index]
        if char.isspace():
            index += 1
            continue

        cjk_match = _CJK_CHAR_PATTERN.match(cleaned, index)
        if cjk_match is not None:
            total += len(cjk_match.group(0))
            index = cjk_match.end()
            continue

        ascii_match = _ASCII_WORD_PATTERN.match(cleaned, index)
        if ascii_match is not None:
            total += max(1, math.ceil(len(ascii_match.group(0)) * 0.5))
            index = ascii_match.end()
            continue

        if char.isalpha() or char.isdigit():
            total += 1
        index += 1

    return total


def join_text_units(units: Iterable[str]) -> str:
    """Join aligned text units while avoiding artificial spaces after CJK punctuation."""
    cleaned_units = [unit.strip() for unit in units if unit and unit.strip()]
    if not cleaned_units:
        return ""

    joined = " ".join(cleaned_units)
    no_space_after = "".join(sorted(_JOIN_WITHOUT_SPACE_AFTER))
    return re.sub(rf"([{re.escape(no_space_after)}])\s+", r"\1", joined)


def normalize_tts_sentence_text(text: str, *, final_in_block: bool = True) -> str:
    """Ensure TTS units preserve natural pauses and end blocks with a terminal marker."""
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
        if not final_in_block:
            return stripped + "".join(reversed(suffix_chars))
        stripped = stripped[:-1].rstrip()

    if stripped.endswith("\u2014\u2014") or stripped.endswith("\u2014"):
        if not final_in_block:
            return stripped + "".join(reversed(suffix_chars))
        stripped = stripped.rstrip("\u2014").rstrip()

    punctuation = "\u3002" if _CJK_CHAR_PATTERN.search(stripped) else "."
    return stripped + punctuation + "".join(reversed(suffix_chars))


def join_tts_sentence_units(
    units: Iterable[str],
    *,
    joiner_mode: str = DEFAULT_TTS_SENTENCE_JOINER_MODE,
) -> str:
    """Join TTS units after normalizing each one to keep natural pauses."""
    joiner_mode = validate_tts_sentence_joiner_mode(joiner_mode)
    cleaned_units = [unit.strip() for unit in units if unit and unit.strip()]
    normalized_units = [
        normalize_tts_sentence_text(
            unit,
            final_in_block=index == len(cleaned_units) - 1,
        )
        for index, unit in enumerate(cleaned_units)
    ]
    joined = join_text_units(normalized_units)
    if joiner_mode == "space":
        return joined

    direct_after = "".join(sorted(_TTS_JOIN_DIRECT_AFTER))
    closing_chars = "".join(sorted(_SENTENCE_CLOSE_CHARS))
    return re.sub(
        rf"([{re.escape(direct_after)}]([{re.escape(closing_chars)}]*)\s+)",
        lambda match: match.group(1).rstrip(),
        joined,
    )


def format_caption_text(
    text: str,
    *,
    punctuation_mode: str = DEFAULT_CAPTION_PUNCTUATION_MODE,
) -> str:
    """Format caption display text without mutating the source speech text."""
    punctuation_mode = validate_caption_punctuation_mode(punctuation_mode)
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized or punctuation_mode == "preserve":
        return normalized

    if punctuation_mode == "strip_terminal":
        return _strip_terminal_punctuation(normalized)

    stripped = "".join(
        "" if _is_unicode_punctuation(char) else char
        for char in normalized
    )
    return re.sub(r"\s+", " ", stripped).strip()


def _strip_terminal_punctuation(text: str) -> str:
    stripped = text.rstrip()
    suffix_chars: list[str] = []
    while stripped and stripped[-1] in _CAPTION_TERMINAL_CLOSING_CHARS:
        suffix_chars.append(stripped[-1])
        stripped = stripped[:-1].rstrip()

    while (
        stripped
        and _is_unicode_punctuation(stripped[-1])
        and stripped[-1] not in _CAPTION_TERMINAL_WRAPPER_CHARS
    ):
        stripped = stripped[:-1].rstrip()

    return stripped + "".join(reversed(suffix_chars))


def _is_unicode_punctuation(char: str) -> bool:
    return unicodedata.category(char).startswith("P")


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
