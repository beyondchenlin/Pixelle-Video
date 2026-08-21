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
    return _prompt_term_pattern(needle).search(haystack) is not None


def prompt_term_count(prompt: str, term: str) -> int:
    """Count a protected term with the same token-boundary rules as presence checks."""

    haystack = normalize_prompt_text(prompt)
    needle = normalize_prompt_text(term)
    if not needle:
        return 0
    return len(_prompt_term_pattern(needle).findall(haystack))


def remove_prompt_term(prompt: str, term: str) -> str:
    """Remove a protected term using the same boundaries as prompt validation."""

    haystack = normalize_prompt_text(prompt)
    needle = normalize_prompt_text(term)
    if not needle:
        return haystack
    return normalize_prompt_text(_prompt_term_pattern(needle).sub(" ", haystack))


def _prompt_term_pattern(needle: str) -> re.Pattern[str]:
    if _ASCII_WORD_PATTERN.fullmatch(needle):
        return re.compile(
            rf"(?<![{_ASCII_TOKEN_CHAR}]){re.escape(needle)}(?![{_ASCII_TOKEN_CHAR}])",
            flags=re.IGNORECASE,
        )
    return re.compile(re.escape(needle), flags=re.IGNORECASE)


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
    "prompt_term_count",
    "remove_prompt_term",
]
