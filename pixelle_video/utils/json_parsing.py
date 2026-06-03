"""Shared helpers for parsing LLM JSON responses with explicit tolerance policies."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_JSON_CODE_BLOCK_PATTERN = re.compile(r"^\s*```(?:json)?\s*([\s\S]+?)\s*```\s*$", re.IGNORECASE)


def _iter_balanced_json_candidates(text: str):
    for start_index, opening_char in enumerate(text):
        if opening_char not in "{[":
            continue

        expected_closers = ["}" if opening_char == "{" else "]"]
        in_string = False
        escape_next = False

        for end_index in range(start_index + 1, len(text)):
            char = text[end_index]
            if in_string:
                if escape_next:
                    escape_next = False
                elif char == "\\":
                    escape_next = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
                continue
            if char == "{":
                expected_closers.append("}")
                continue
            if char == "[":
                expected_closers.append("]")
                continue
            if char in "}]":
                if not expected_closers or char != expected_closers[-1]:
                    break
                expected_closers.pop()
                if not expected_closers:
                    yield text[start_index:end_index + 1]
                    break


def parse_llm_json_response(
    text: str,
    *,
    allow_code_fence: bool = True,
    allow_embedded_json: bool = False,
) -> Any:
    """Parse JSON from an LLM response with configurable tolerance for wrappers."""
    cleaned = text.strip()
    
    if not cleaned:
        logger.error("Empty response after stripping whitespace")
        raise json.JSONDecodeError("No valid JSON found", text, 0)

    last_error: json.JSONDecodeError | None = None

    # Attempt 1: Direct JSON parsing
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        last_error = exc

    # Attempt 2: Extract from Markdown code fence
    if allow_code_fence:
        fence_match = _JSON_CODE_BLOCK_PATTERN.match(cleaned)
        if fence_match:
            fenced_payload = fence_match.group(1).strip()
            try:
                return json.loads(fenced_payload)
            except json.JSONDecodeError as exc:
                last_error = exc

    # Attempt 3: Extract embedded JSON
    if allow_embedded_json:
        for candidate in _iter_balanced_json_candidates(cleaned):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    # All attempts failed - log detailed diagnostics
    logger.error(f"JSON parsing failed. Text length: {len(text)}, cleaned length: {len(cleaned)}")
    preview_len = min(500, len(text))
    logger.error(f"Content preview (first {preview_len} chars): {text[:preview_len]!r}")
    if allow_code_fence and _JSON_CODE_BLOCK_PATTERN.match(cleaned):
        logger.error("Markdown code fence was found but content inside is not valid JSON")
    else:
        logger.error("No Markdown code fence found in response")
    logger.error(f"Last JSON decode error: {last_error}")
    
    raise last_error or json.JSONDecodeError("No valid JSON found", text, 0)


__all__ = ["parse_llm_json_response"]
