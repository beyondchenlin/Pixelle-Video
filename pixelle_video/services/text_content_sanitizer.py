from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_ASS_OVERRIDE_PATTERN = re.compile(r"\{\\[^{}]*\}")
_SCRIPT_BLOCK_PATTERN = re.compile(
    r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG_PATTERN = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
_CSS_STYLE_PATTERN = re.compile(
    r"\bstyle\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s;]+;?)",
    re.IGNORECASE,
)
_DRAWTEXT_PREFIX_PATTERN = re.compile(r"\bdrawtext\s*=", re.IGNORECASE)
_ZERO_WIDTH_CHARACTERS = {"\u200b", "\u200c", "\u200d", "\ufeff"}
_HTML_SENSITIVE_CHARACTERS = {"<", ">", "&", '"', "'"}
_ASS_SENSITIVE_CHARACTERS = {"{", "}", "\\"}


@dataclass(frozen=True)
class TextContentSanitizeResult:
    raw_text: str
    display_text: str
    removed_tokens: tuple[str, ...] = ()
    requires_html_escape: bool = False
    requires_ass_escape: bool = False


class TextContentSanitizer:
    def sanitize(self, text: object) -> TextContentSanitizeResult:
        raw_text = "" if text is None else str(text)
        removed_tokens: list[str] = []
        display_text = raw_text

        display_text = _remove_matches(
            display_text, _ASS_OVERRIDE_PATTERN, removed_tokens
        )
        display_text = _remove_script_blocks(display_text, removed_tokens)
        display_text = _remove_matches(display_text, _HTML_TAG_PATTERN, removed_tokens)
        display_text = _remove_matches(
            display_text, _CSS_STYLE_PATTERN, removed_tokens
        )
        display_text = _remove_drawtext_filters(display_text, removed_tokens)
        display_text = _remove_control_characters(display_text, removed_tokens)
        display_text = _normalize_visible_whitespace(display_text)

        removed_html = any(token.lstrip().startswith("<") for token in removed_tokens)
        return TextContentSanitizeResult(
            raw_text=raw_text,
            display_text=display_text,
            removed_tokens=tuple(removed_tokens),
            requires_html_escape=(
                removed_html
                or any(char in _HTML_SENSITIVE_CHARACTERS for char in raw_text)
                or any(char in _HTML_SENSITIVE_CHARACTERS for char in display_text)
            ),
            requires_ass_escape=(
                bool(_ASS_OVERRIDE_PATTERN.search(raw_text))
                or any(char in _ASS_SENSITIVE_CHARACTERS for char in raw_text)
            ),
        )


def _remove_matches(
    text: str, pattern: re.Pattern[str], removed_tokens: list[str]
) -> str:
    def replace(match: re.Match[str]) -> str:
        removed_tokens.append(match.group(0))
        return ""

    return pattern.sub(replace, text)


def _remove_script_blocks(text: str, removed_tokens: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        value = match.group(0)
        start_tag = re.match(r"<\s*script\b[^>]*>", value, re.IGNORECASE)
        end_tag = re.search(r"<\s*/\s*script\s*>", value, re.IGNORECASE)
        if start_tag:
            removed_tokens.append(start_tag.group(0))
        if end_tag:
            removed_tokens.append(end_tag.group(0))
        return ""

    return _SCRIPT_BLOCK_PATTERN.sub(replace, text)


def _remove_drawtext_filters(text: str, removed_tokens: list[str]) -> str:
    result: list[str] = []
    cursor = 0
    while True:
        match = _DRAWTEXT_PREFIX_PATTERN.search(text, cursor)
        if not match:
            result.append(text[cursor:])
            break
        result.append(text[cursor : match.start()])
        end = _scan_drawtext_filter_end(text, match.end())
        removed_tokens.append(text[match.start() : end])
        cursor = end
    return "".join(result)


def _scan_drawtext_filter_end(text: str, start: int) -> int:
    index = start
    quote: str | None = None
    while index < len(text):
        char = text[index]
        if quote is not None:
            if char == quote and not _is_escaped(text, index):
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char.isspace():
            next_index = _skip_whitespace(text, index)
            if _looks_like_drawtext_continuation(text, next_index):
                index = next_index
                continue
            return index
        index += 1
    return index


def _looks_like_drawtext_continuation(text: str, index: int) -> bool:
    if index >= len(text):
        return False
    colon_index = index - 1
    while colon_index >= 0 and text[colon_index].isspace():
        colon_index -= 1
    if colon_index >= 0 and text[colon_index] == ":":
        return True
    return bool(re.match(r"[A-Za-z_][A-Za-z0-9_]*\s*=", text[index:]))


def _skip_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _is_escaped(text: str, index: int) -> bool:
    backslash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslash_count += 1
        cursor -= 1
    return backslash_count % 2 == 1


def _remove_control_characters(text: str, removed_tokens: list[str]) -> str:
    kept: list[str] = []
    for char in text:
        if char in _ZERO_WIDTH_CHARACTERS or (
            unicodedata.category(char).startswith("C") and char not in {"\n", "\t"}
        ):
            removed_tokens.append(char)
            continue
        kept.append(char)
    return "".join(kept)


def _normalize_visible_whitespace(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in normalized.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)
