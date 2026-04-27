from __future__ import annotations

import re

_LITERAL_CONTROL_ESCAPE_PATTERN = re.compile(r"[\\/]+n", flags=re.IGNORECASE)
_TRAILING_SLASH_FRAGMENT_PATTERN = re.compile(r"[\\/]+(?=\s|$)")
_UNICODE_ESCAPE_PATTERN = re.compile(r"\\u([0-9a-fA-F]{4})")


def normalize_generated_source_text(text: str) -> str:
    cleaned = _UNICODE_ESCAPE_PATTERN.sub(lambda match: chr(int(match.group(1), 16)), text or "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _LITERAL_CONTROL_ESCAPE_PATTERN.sub(" ", cleaned)
    cleaned = _TRAILING_SLASH_FRAGMENT_PATTERN.sub(" ", cleaned)
    return re.sub(r"\s+", " ", cleaned.strip())


__all__ = ["normalize_generated_source_text"]
