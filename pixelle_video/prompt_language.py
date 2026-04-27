from __future__ import annotations

from typing import Literal

PromptLanguage = Literal["zh_CN", "en_US"]

DEFAULT_PROMPT_LANGUAGE: PromptLanguage = "zh_CN"
CHINESE_PROMPT_LANGUAGE: PromptLanguage = "zh_CN"
ENGLISH_PROMPT_LANGUAGE: PromptLanguage = "en_US"


def normalize_prompt_language(
    value: str | None,
    *,
    default: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
) -> PromptLanguage:
    normalized = str(value or "").strip()
    if normalized == CHINESE_PROMPT_LANGUAGE:
        return CHINESE_PROMPT_LANGUAGE
    if normalized == ENGLISH_PROMPT_LANGUAGE:
        return ENGLISH_PROMPT_LANGUAGE
    return default


def is_chinese_prompt_language(value: str | None) -> bool:
    return normalize_prompt_language(value) == CHINESE_PROMPT_LANGUAGE


__all__ = [
    "PromptLanguage",
    "DEFAULT_PROMPT_LANGUAGE",
    "CHINESE_PROMPT_LANGUAGE",
    "ENGLISH_PROMPT_LANGUAGE",
    "normalize_prompt_language",
    "is_chinese_prompt_language",
]
