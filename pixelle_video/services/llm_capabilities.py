from __future__ import annotations

import math
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class StructuredOutputCapabilities:
    supports_json_object_response_format: bool = True
    omit_max_tokens_with_json_object: bool = False
    retry_prompt_schema_when_json_object_unsupported: bool = True
    max_input_tokens: int = 128000
    max_output_tokens: int = 4096


_MAX_INPUT_TOKENS_BY_MODEL: dict[str, int] = {
    "qwen-max": 30720,
    "qwen-plus": 131072,
    "qwen-turbo": 131072,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "o1": 200000,
    "o3": 200000,
    "deepseek-chat": 65536,
    "deepseek-reasoner": 65536,
    "claude-sonnet-4-5": 200000,
    "claude-sonnet-4": 200000,
    "claude-3-5-sonnet": 200000,
    "claude-3-opus": 200000,
    "claude-3-haiku": 200000,
    "moonshot-v1-8k": 8192,
    "moonshot-v1-32k": 32768,
    "moonshot-v1-128k": 131072,
    "llama3.2": 131072,
    "llama3.1": 131072,
    "llama3": 8192,
}

_MAX_OUTPUT_TOKENS_BY_MODEL: dict[str, int] = {
    "qwen-max": 8192,
    "qwen-plus": 8192,
    "qwen-turbo": 8192,
    "gpt-4o": 16384,
    "gpt-4o-mini": 16384,
    "gpt-4": 8192,
    "deepseek-chat": 8192,
    "deepseek-reasoner": 8192,
    "claude-sonnet-4-5": 8192,
    "claude-3-5-sonnet": 8192,
    "claude-3-opus": 4096,
    "claude-3-haiku": 4096,
    "moonshot-v1-8k": 8192,
    "moonshot-v1-32k": 8192,
    "moonshot-v1-128k": 8192,
}

_DEFAULT_MAX_INPUT_TOKENS = 128000
_DEFAULT_MAX_OUTPUT_TOKENS = 8192


def _resolve_max_model_value(
    model: str | None,
    table: dict[str, int],
    default: int,
) -> int:
    if not model:
        return default
    normalized = model.strip().lower()
    if normalized in table:
        return table[normalized]
    for prefix, limit in sorted(table.items(), key=lambda x: -len(x[0])):
        if normalized.startswith(prefix):
            return limit
    return default


def _resolve_max_input_tokens(model: str | None) -> int:
    return _resolve_max_model_value(model, _MAX_INPUT_TOKENS_BY_MODEL, _DEFAULT_MAX_INPUT_TOKENS)
    if not model:
        return _DEFAULT_MAX_INPUT_TOKENS
    normalized = model.strip().lower()
    if normalized in _MAX_INPUT_TOKENS_BY_MODEL:
        return _MAX_INPUT_TOKENS_BY_MODEL[normalized]
    for prefix, limit in sorted(_MAX_INPUT_TOKENS_BY_MODEL.items(), key=lambda x: -len(x[0])):
        if normalized.startswith(prefix):
            return limit
    return _DEFAULT_MAX_INPUT_TOKENS


def structured_output_capabilities(
    *,
    base_url: str | None,
    model: str | None,
) -> StructuredOutputCapabilities:
    hostname = urlparse(str(base_url or "").strip().lower()).hostname or ""
    normalized_model = str(model or "").strip().lower()
    max_input = _resolve_max_input_tokens(model)
    max_output = _resolve_max_model_value(model, _MAX_OUTPUT_TOKENS_BY_MODEL, _DEFAULT_MAX_OUTPUT_TOKENS)

    if hostname.startswith("dashscope") and hostname.endswith("aliyuncs.com"):
        return StructuredOutputCapabilities(
            omit_max_tokens_with_json_object=True,
            max_input_tokens=max_input,
            max_output_tokens=max_output,
        )

    if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".local"):
        return StructuredOutputCapabilities(max_input_tokens=max_input, max_output_tokens=max_output)

    if normalized_model.startswith(("deepseek-", "moonshot-", "kimi-")):
        return StructuredOutputCapabilities(max_input_tokens=max_input, max_output_tokens=max_output)

    return StructuredOutputCapabilities(max_input_tokens=max_input, max_output_tokens=max_output)


def is_json_object_response_format_unsupported_error(exc: Exception) -> bool:
    message = str(exc).lower()
    unsupported_patterns = (
        "response_format is not supported",
        "response_format not supported",
        "unsupported response_format",
        "response_format unsupported",
        "json mode is not supported",
        "json mode not supported",
        "unsupported json mode",
        "unknown parameter: response_format",
        "unknown param: response_format",
        "unrecognized parameter: response_format",
        "unrecognized param: response_format",
        "unexpected keyword argument 'response_format'",
        'unexpected keyword argument "response_format"',
        "unexpected parameter: response_format",
        "unexpected param: response_format",
    )
    return any(pattern in message for pattern in unsupported_patterns)


def estimate_input_tokens(text: str) -> int:
    """Estimate token count for mixed Chinese/English/JSON text.

    Calibrated conservatively (tends to overestimate) to prevent 400 errors.
    Chinese/CJK characters: ~1.5 chars/token
    Latin/ASCII/JSON: ~3.0 chars/token
    """
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f')
    other_chars = len(text) - chinese_chars
    return math.ceil(chinese_chars / 1.5 + other_chars / 3.0)
