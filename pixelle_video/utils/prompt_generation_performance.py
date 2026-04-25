"""Shared request-scoped prompt generation performance parameters."""

from collections.abc import MutableMapping
from typing import Any

LLM_PROMPT_BATCH_SIZE_PARAM = "llm_prompt_batch_size"
LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM = "llm_prompt_batch_concurrent_limit"

PROMPT_BATCH_SIZE_MIN = 1
PROMPT_BATCH_SIZE_MAX = 50
PROMPT_BATCH_CONCURRENT_LIMIT_MIN = 1
PROMPT_BATCH_CONCURRENT_LIMIT_MAX = 10

PROMPT_GENERATION_PERFORMANCE_PARAM_NAMES = (
    LLM_PROMPT_BATCH_SIZE_PARAM,
    LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM,
)


def _read_param(source: Any, param_name: str) -> Any:
    if isinstance(source, MutableMapping):
        return source.get(param_name)
    return getattr(source, param_name, None)


def copy_prompt_generation_performance_params(
    source: Any,
    target: MutableMapping[str, Any],
) -> None:
    """Copy prompt performance overrides only when explicitly present."""
    for param_name in PROMPT_GENERATION_PERFORMANCE_PARAM_NAMES:
        value = _read_param(source, param_name)
        if value is not None:
            target[param_name] = int(value)
