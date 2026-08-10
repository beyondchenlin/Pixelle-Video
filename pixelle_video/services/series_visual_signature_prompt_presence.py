from __future__ import annotations

import re
from collections.abc import Sequence

_ASCII_WORD_PATTERN = re.compile(r"^[\x00-\x7F]+$")
_ASCII_TOKEN_CHAR = r"A-Za-z0-9"


def normalize_prompt_text(value: str) -> str:
    return " ".join(str(value or "").split())


def prompt_contains_term(prompt: str, term: str) -> bool:
    """Match a protected prompt term without ASCII substring false positives."""

    haystack = normalize_prompt_text(prompt)
    needle = normalize_prompt_text(term)
    if not needle:
        return False
    if _ASCII_WORD_PATTERN.fullmatch(needle):
        pattern = re.compile(
            rf"(?<![{_ASCII_TOKEN_CHAR}]){re.escape(needle)}(?![{_ASCII_TOKEN_CHAR}])",
            flags=re.IGNORECASE,
        )
        return pattern.search(haystack) is not None
    return needle.casefold() in haystack.casefold()


def prompt_presence_map(prompt: str, terms: Sequence[str]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for term in terms:
        normalized = normalize_prompt_text(term)
        if not normalized:
            continue
        result[normalized] = prompt_contains_term(prompt, normalized)
    return result


__all__ = [
    "normalize_prompt_text",
    "prompt_contains_term",
    "prompt_presence_map",
]
