from __future__ import annotations

from pixelle_video.models.llm_limits import LLM_MAX_OUTPUT_TOKENS


SCRIPT_TARGET_WORDS_MIN = 1
SCRIPT_TARGET_WORDS_MAX = 10000
SCRIPT_GENERATION_AUTO_MAX_TOKENS = 2000
SCRIPT_GENERATION_MIN_MAX_TOKENS = 1200
SCRIPT_GENERATION_TOKENS_PER_TARGET_WORD = 4


def script_generation_max_tokens(target_words: int | None) -> int:
    if target_words is None:
        return SCRIPT_GENERATION_AUTO_MAX_TOKENS
    requested_tokens = max(
        SCRIPT_GENERATION_MIN_MAX_TOKENS,
        int(target_words * SCRIPT_GENERATION_TOKENS_PER_TARGET_WORD),
    )
    return min(requested_tokens, LLM_MAX_OUTPUT_TOKENS)


__all__ = [
    "SCRIPT_GENERATION_AUTO_MAX_TOKENS",
    "SCRIPT_GENERATION_MIN_MAX_TOKENS",
    "SCRIPT_GENERATION_TOKENS_PER_TARGET_WORD",
    "SCRIPT_TARGET_WORDS_MAX",
    "SCRIPT_TARGET_WORDS_MIN",
    "script_generation_max_tokens",
]
