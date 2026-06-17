from __future__ import annotations

import base64
import binascii
import hashlib
import io
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

from pixelle_video.services.llm_capabilities import estimate_input_tokens


@dataclass(frozen=True)
class VisionCapabilities:
    supports_vision_messages: bool = False
    supports_data_url_images: bool = True
    max_image_size_mb: int | None = None
    reason: str = ""


_DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;,]+)?;base64,(?P<data>.*)$", re.IGNORECASE | re.DOTALL)
_KNOWN_VISION_MODEL_PREFIXES = (
    "gpt-4o",
    "qwen-vl",
    "qwen2-vl",
    "qwen2.5-vl",
    "qwen-omni",
)
_KNOWN_NON_VISION_MODEL_PREFIXES = (
    "deepseek-",
    "moonshot-",
    "kimi-",
    "qwen-max",
    "qwen-plus",
    "qwen-turbo",
)
_REMOTE_URL_SCHEMES = ("http://", "https://")


def detect_vision_capabilities(
    *,
    base_url: str | None = None,
    model: str | None = None,
    force_supports_vision: bool | None = None,
    max_image_size_mb: int | None = None,
) -> VisionCapabilities:
    """Detect whether a configured OpenAI-compatible model should receive image messages.

    The resolver is intentionally conservative: explicit configuration wins, a
    small known vision-model allowlist follows, and unknown models default to not
    supported so callers can choose an ``auto`` skip rather than sending images to
    a text-only model.
    """

    if force_supports_vision is not None:
        return VisionCapabilities(
            supports_vision_messages=bool(force_supports_vision),
            supports_data_url_images=True,
            max_image_size_mb=max_image_size_mb,
            reason="forced_by_config",
        )

    normalized_model = str(model or "").strip().lower()
    if not normalized_model:
        return VisionCapabilities(
            max_image_size_mb=max_image_size_mb,
            reason="missing_model",
        )

    hostname = urlparse(str(base_url or "").strip().lower()).hostname or ""
    if normalized_model.startswith(_KNOWN_NON_VISION_MODEL_PREFIXES):
        return VisionCapabilities(
            max_image_size_mb=max_image_size_mb,
            reason="known_text_only_model",
        )

    if normalized_model.startswith(_KNOWN_VISION_MODEL_PREFIXES):
        return VisionCapabilities(
            supports_vision_messages=True,
            supports_data_url_images=True,
            max_image_size_mb=max_image_size_mb,
            reason="known_vision_model",
        )

    if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".local"):
        return VisionCapabilities(
            max_image_size_mb=max_image_size_mb,
            reason="local_model_requires_explicit_force_supports_vision",
        )

    return VisionCapabilities(
        max_image_size_mb=max_image_size_mb,
        reason="unknown_model",
    )


def estimate_messages_text_tokens(messages: list[Mapping[str, Any]]) -> int:
    """Estimate text-only tokens for multimodal messages.

    Image data URLs are intentionally ignored here; image payload limits are
    enforced with byte-size checks instead of treating base64 as prompt text.
    """

    text_parts: list[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            if not content.lstrip().lower().startswith("data:image"):
                text_parts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            part_type = str(part.get("type") or "").strip().lower()
            if part_type in {"text", "input_text"}:
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
    return estimate_input_tokens("\n".join(text_parts))


def redact_multimodal_messages_for_trace(messages: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return a trace-safe copy of multimodal messages without image URLs/base64."""

    redacted: list[dict[str, Any]] = []
    for message in messages:
        copied = {
            str(key): _redact_message_value(value)
            for key, value in message.items()
        }
        redacted.append(copied)
    return redacted


def validate_multimodal_image_inputs(messages: list[Mapping[str, Any]]) -> None:
    """Validate first-phase Vision image transport.

    PR2 supports only inline ``data:image/...;base64`` inputs. Remote image URLs
    are intentionally rejected because signed URLs or local-gateway URLs can leak
    secrets into traces, logs, provider calls, and retry payloads.
    """

    for image_url in _iter_image_urls(messages):
        if _is_remote_url(image_url):
            raise ValueError("remote image URLs are not supported for Vision LLM calls in this phase")
        if not _is_image_data_url(image_url):
            raise ValueError("vision image inputs must use data:image base64 URLs in this phase")
        summary = summarize_data_url_image(image_url)
        if summary.get("decode_error"):
            raise ValueError("invalid vision image data URL")


def validate_multimodal_image_limits(
    messages: list[Mapping[str, Any]],
    *,
    max_image_size_mb: int | None,
) -> None:
    validate_multimodal_image_inputs(messages)
    if max_image_size_mb is None:
        return
    max_bytes = max(1, int(max_image_size_mb)) * 1024 * 1024
    for data_url in _iter_image_data_urls(messages):
        summary = summarize_data_url_image(data_url)
        byte_size = summary.get("byte_size")
        if isinstance(byte_size, int) and byte_size > max_bytes:
            raise ValueError(
                "vision image exceeds configured max_image_size_mb "
                f"({max_image_size_mb} MB)"
            )


def summarize_data_url_image(data_url: str) -> dict[str, Any]:
    match = _DATA_URL_RE.match(str(data_url or "").strip())
    if not match:
        return {"url": "<redacted:non-data-url>"}
    mime_type = (match.group("mime") or "application/octet-stream").lower()
    encoded = match.group("data") or ""
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return {
            "url": "<redacted:data-url>",
            "mime_type": mime_type,
            "sha256": "",
            "byte_size": 0,
            "width": None,
            "height": None,
            "decode_error": "invalid_base64",
        }
    width, height = _probe_image_dimensions(raw)
    return {
        "url": "<redacted:data-url>",
        "mime_type": mime_type,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_size": len(raw),
        "width": width,
        "height": height,
    }


def summarize_remote_image_url(url: str) -> dict[str, Any]:
    parsed = urlparse(str(url or "").strip())
    return {
        "url": "<redacted:remote-image-url>",
        "domain": parsed.hostname or "",
        "url_sha256": hashlib.sha256(str(url or "").encode("utf-8")).hexdigest(),
    }


def _redact_message_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        if "url" in value:
            raw_url = value.get("url")
            if _is_image_data_url(raw_url):
                summary = summarize_data_url_image(str(raw_url or ""))
                return {
                    **{str(key): _redact_message_value(item) for key, item in value.items() if key != "url"},
                    **summary,
                }
            if _is_remote_url(raw_url):
                return {
                    **{str(key): _redact_message_value(item) for key, item in value.items() if key != "url"},
                    **summarize_remote_image_url(str(raw_url or "")),
                }
        return {str(key): _redact_message_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_message_value(item) for item in value]
    if isinstance(value, str) and _is_image_data_url(value):
        return summarize_data_url_image(value)
    if isinstance(value, str) and _is_remote_url(value):
        return summarize_remote_image_url(value)
    return value


def _iter_image_urls(messages: list[Mapping[str, Any]]):
    for message in messages:
        content = message.get("content")
        if isinstance(content, str) and (_is_image_data_url(content) or _is_remote_url(content)):
            yield content
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            image_url = part.get("image_url")
            if isinstance(image_url, str):
                yield image_url
            elif isinstance(image_url, Mapping):
                raw_url = image_url.get("url")
                if isinstance(raw_url, str):
                    yield raw_url


def _iter_image_data_urls(messages: list[Mapping[str, Any]]):
    for image_url in _iter_image_urls(messages):
        if _is_image_data_url(image_url):
            yield image_url


def _is_image_data_url(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith("data:image/")


def _is_remote_url(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith(_REMOTE_URL_SCHEMES)


def _probe_image_dimensions(raw: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(io.BytesIO(raw)) as image:
            return image.size
    except (UnidentifiedImageError, OSError, ValueError):
        return None, None
