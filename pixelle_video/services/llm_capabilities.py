from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class StructuredOutputCapabilities:
    supports_json_object_response_format: bool = True
    omit_max_tokens_with_json_object: bool = False
    retry_prompt_schema_when_json_object_unsupported: bool = True


def structured_output_capabilities(
    *,
    base_url: str | None,
    model: str | None,
) -> StructuredOutputCapabilities:
    hostname = urlparse(str(base_url or "").strip().lower()).hostname or ""
    normalized_model = str(model or "").strip().lower()

    if hostname.startswith("dashscope") and hostname.endswith("aliyuncs.com"):
        return StructuredOutputCapabilities(omit_max_tokens_with_json_object=True)

    if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".local"):
        return StructuredOutputCapabilities()

    if normalized_model.startswith(("deepseek-", "moonshot-", "kimi-")):
        return StructuredOutputCapabilities()

    return StructuredOutputCapabilities()


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
