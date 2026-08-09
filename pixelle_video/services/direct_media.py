from __future__ import annotations

import asyncio
import base64
import binascii
import json
import math
import os
import re
import tempfile
import warnings
from collections.abc import Callable, Mapping
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from loguru import logger
from PIL import Image, UnidentifiedImageError

from pixelle_video.config.schema import DirectMediaConfig, OpenAIImageProviderConfig
from pixelle_video.models.direct_media import (
    DirectMediaDescriptor,
    DirectMediaOutput,
    DirectMediaRequest,
)
from pixelle_video.services.openai_client_pool import (
    AsyncOpenAIClientPool,
    OpenAIClientSettings,
    create_openai_client,
)
from pixelle_video.services.vision_capabilities import sanitize_multimodal_trace_error
from pixelle_video.utils.network_proxy import resolve_provider_proxy_async


class DirectMediaError(Exception):
    """Base error for governed direct media generation."""


class DirectMediaConfigurationError(DirectMediaError, ValueError):
    """Raised when a selected provider is disabled or misconfigured."""


class DirectMediaProviderError(DirectMediaError, RuntimeError):
    """Raised when a provider request fails."""


class DirectMediaResponseError(DirectMediaError, ValueError):
    """Raised when a provider returns an unsafe or unusable media response."""


def load_direct_media_descriptor(path: str | Path) -> DirectMediaDescriptor:
    descriptor_path = Path(path)
    try:
        payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DirectMediaConfigurationError(
            f"direct media descriptor could not be read: {descriptor_path.name}"
        ) from exc
    return DirectMediaDescriptor.model_validate(payload)


class DirectMediaAdapter(Protocol):
    async def generate(
        self,
        *,
        descriptor: DirectMediaDescriptor,
        request: DirectMediaRequest,
        config: DirectMediaConfig,
    ) -> DirectMediaOutput: ...

    async def aclose(self) -> None: ...


AdapterFactory = Callable[[], DirectMediaAdapter]


class DirectMediaProviderRegistry:
    """Allowlisted, lazy adapter registry with deterministic shutdown."""

    def __init__(
        self,
        factories: Mapping[str, AdapterFactory] | None = None,
    ) -> None:
        self._factories = dict(
            factories
            or {
                "openai_image": OpenAIImageAdapter,
            }
        )
        if not self._factories or any(not str(key).strip() for key in self._factories):
            raise ValueError("direct media adapter factories must use non-empty keys")
        self._adapters: dict[str, DirectMediaAdapter] = {}
        self._lock = asyncio.Lock()
        self._idle = asyncio.Event()
        self._idle.set()
        self._active_calls = 0
        self._closed = False

    async def generate(
        self,
        *,
        descriptor: DirectMediaDescriptor,
        request: DirectMediaRequest,
        config: DirectMediaConfig,
    ) -> DirectMediaOutput:
        if descriptor.media_type != request.media_type:
            raise DirectMediaConfigurationError(
                "direct media request type does not match provider descriptor"
            )
        if descriptor.model != request.model:
            raise DirectMediaConfigurationError(
                "direct media request model does not match provider descriptor"
            )
        try:
            normalized_parameters = descriptor.normalize_parameters(request.parameters)
        except ValueError as exc:
            raise DirectMediaConfigurationError(str(exc)) from exc
        normalized_request = DirectMediaRequest(
            workflow_key=request.workflow_key,
            prompt=request.prompt,
            media_type=request.media_type,
            model=request.model,
            output_dir=request.output_dir,
            width=request.width,
            height=request.height,
            negative_prompt=request.negative_prompt,
            parameters=normalized_parameters,
        )
        adapter = await self._acquire_adapter(descriptor.adapter)
        try:
            return await adapter.generate(
                descriptor=descriptor,
                request=normalized_request,
                config=config,
            )
        finally:
            await self._release_adapter()

    async def _acquire_adapter(self, adapter_id: str) -> DirectMediaAdapter:
        async with self._lock:
            if self._closed:
                raise RuntimeError("direct media provider registry is closed")
            existing = self._adapters.get(adapter_id)
            if existing is not None:
                self._active_calls += 1
                self._idle.clear()
                return existing
            factory = self._factories.get(adapter_id)
            if factory is None:
                raise DirectMediaConfigurationError(
                    f"direct media adapter is not allowlisted: {adapter_id}"
                )
            adapter = factory()
            self._adapters[adapter_id] = adapter
            self._active_calls += 1
            self._idle.clear()
            return adapter

    async def _release_adapter(self) -> None:
        async with self._lock:
            self._active_calls -= 1
            if self._active_calls < 0:  # pragma: no cover - internal invariant
                raise RuntimeError("direct media registry active call count underflow")
            if self._active_calls == 0:
                self._idle.set()

    async def aclose(self) -> None:
        async with self._lock:
            self._closed = True
            idle = self._idle
        await idle.wait()
        async with self._lock:
            adapters = list(self._adapters.values())
            self._adapters.clear()
        first_error: Exception | None = None
        for adapter in adapters:
            try:
                await adapter.aclose()
            except Exception as exc:  # pragma: no cover - defensive aggregation
                first_error = first_error or exc
        if first_error is not None:
            raise RuntimeError("failed to close direct media provider adapters") from first_error


class OpenAIImageAdapter:
    """OpenAI-compatible image adapter that accepts only base64 provider output."""

    def __init__(self) -> None:
        self._client_pool = AsyncOpenAIClientPool(max_size=2)

    async def generate(
        self,
        *,
        descriptor: DirectMediaDescriptor,
        request: DirectMediaRequest,
        config: DirectMediaConfig,
    ) -> DirectMediaOutput:
        provider_config = config.openai_image
        _require_openai_image_provider_enabled(config, provider_config)
        if descriptor.adapter != "openai_image" or descriptor.media_type != "image":
            raise DirectMediaConfigurationError(
                "OpenAI image adapter received an incompatible descriptor"
            )
        if request.negative_prompt.strip():
            raise DirectMediaConfigurationError(
                "OpenAI image provider descriptor does not support negative_prompt"
            )

        settings = await _openai_image_client_settings(provider_config)
        api_parameters = dict(request.parameters)
        output_format = str(api_parameters.pop("output_format", "png"))
        if (
            api_parameters.get("background") == "transparent"
            and output_format == "jpeg"
        ):
            raise DirectMediaConfigurationError(
                "transparent image backgrounds require png or webp output"
            )
        size = _openai_image_size(request.width, request.height)
        request_kwargs: dict[str, Any] = {
            "prompt": request.prompt,
            "model": descriptor.model,
            "n": 1,
            "response_format": "b64_json",
            "size": size,
            "output_format": output_format,
            **api_parameters,
        }

        try:
            async with self._client_pool.acquire(
                fingerprint=settings.fingerprint,
                factory=lambda: create_openai_client(settings),
            ) as client:
                response = await client.images.generate(**request_kwargs)
        except DirectMediaError:
            raise
        except Exception as exc:
            safe_error = sanitize_multimodal_trace_error(exc)
            logger.error(
                "Direct image provider request failed: provider={} model={} error_type={}",
                descriptor.provider_id,
                descriptor.model,
                type(exc).__name__,
            )
            raise DirectMediaProviderError(safe_error) from exc

        encoded = _first_base64_image(response)
        raw = _decode_bounded_base64_image(
            encoded,
            max_bytes=provider_config.max_output_size_mb * 1024 * 1024,
        )
        image_format, actual_width, actual_height = _validated_image_info(
            raw,
            max_pixels=provider_config.max_output_pixels,
        )
        expected_format = "JPEG" if output_format == "jpeg" else output_format.upper()
        if image_format != expected_format:
            raise DirectMediaResponseError(
                "image provider output format did not match the requested format"
            )
        local_path = _write_image_atomically(
            request.output_dir,
            raw,
            image_format=image_format,
        )
        return DirectMediaOutput(
            media_type="image",
            local_path=local_path,
            provider_id=descriptor.provider_id,
            model=descriptor.model,
            request_id=_safe_request_id(response),
            provider_metadata={
                "actual_width": actual_width,
                "actual_height": actual_height,
                "format": image_format.lower(),
                "output_bytes": len(raw),
                "requested_size": size,
                "usage": _safe_usage(response),
            },
        )

    async def aclose(self) -> None:
        pool = self._client_pool
        self._client_pool = AsyncOpenAIClientPool(max_size=2)
        await pool.close()


def _require_openai_image_provider_enabled(
    config: DirectMediaConfig,
    provider: OpenAIImageProviderConfig,
) -> None:
    if not config.enabled:
        raise DirectMediaConfigurationError("direct media providers are disabled")
    if not provider.enabled:
        raise DirectMediaConfigurationError("OpenAI image provider is disabled")


async def _openai_image_client_settings(
    config: OpenAIImageProviderConfig,
) -> OpenAIClientSettings:
    api_key = config.api_key.strip() or str(os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise DirectMediaConfigurationError(
            "OpenAI image provider requires api_key or OPENAI_API_KEY"
        )
    base_url = config.base_url.strip() or "https://api.openai.com/v1"
    return OpenAIClientSettings(
        api_key=api_key,
        base_url=base_url,
        connect_timeout_seconds=config.connect_timeout_seconds,
        read_timeout_seconds=config.read_timeout_seconds,
        write_timeout_seconds=config.write_timeout_seconds,
        pool_timeout_seconds=config.pool_timeout_seconds,
        max_retries=config.max_retries,
        proxy=await resolve_provider_proxy_async(provider_base_url=base_url),
    )


def _openai_image_size(width: int | None, height: int | None) -> str:
    if (width is None) != (height is None):
        raise DirectMediaConfigurationError(
            "direct image width and height must be provided together"
        )
    if width is None or height is None or width == height:
        return "1024x1024"
    return "1536x1024" if width > height else "1024x1536"


def _first_base64_image(response: Any) -> str:
    data = getattr(response, "data", None)
    if not isinstance(data, (list, tuple)) or not data:
        raise DirectMediaResponseError("image provider response did not contain output data")
    encoded = getattr(data[0], "b64_json", None)
    if not isinstance(encoded, str) or not encoded.strip():
        if getattr(data[0], "url", None):
            raise DirectMediaResponseError(
                "image provider returned a remote URL; only base64 output is accepted"
            )
        raise DirectMediaResponseError(
            "image provider response did not contain base64 image data"
        )
    return encoded.strip()


def _decode_bounded_base64_image(encoded: str, *, max_bytes: int) -> bytes:
    maximum_encoded_length = math.ceil(max_bytes / 3) * 4 + 4
    if len(encoded) > maximum_encoded_length:
        raise DirectMediaResponseError("image provider output exceeded configured byte limit")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DirectMediaResponseError("image provider returned invalid base64 data") from exc
    if not raw or len(raw) > max_bytes:
        raise DirectMediaResponseError("image provider output exceeded configured byte limit")
    return raw


def _validated_image_info(raw: bytes, *, max_pixels: int) -> tuple[str, int, int]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                image.verify()
            with Image.open(BytesIO(raw)) as image:
                image_format = str(image.format or "").upper()
                width, height = image.size
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise DirectMediaResponseError("image provider output exceeded safe pixel limits") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise DirectMediaResponseError("image provider output was not a valid image") from exc
    if image_format not in {"PNG", "JPEG", "WEBP"}:
        raise DirectMediaResponseError(
            f"image provider output format is not allowed: {image_format or 'unknown'}"
        )
    if width < 1 or height < 1:
        raise DirectMediaResponseError("image provider output dimensions were invalid")
    if width * height > max_pixels:
        raise DirectMediaResponseError("image provider output exceeded safe pixel limits")
    return image_format, width, height


def _write_image_atomically(output_dir: Path, raw: bytes, *, image_format: str) -> Path:
    extension = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[image_format]
    resolved_dir = Path(output_dir).resolve()
    resolved_dir.mkdir(parents=True, exist_ok=True)
    final_path = resolved_dir / f"image_{uuid4().hex}{extension}"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".provider-image-",
            suffix=".tmp",
            dir=resolved_dir,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, final_path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return final_path


_SAFE_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")


def _safe_request_id(response: Any) -> str:
    candidate = str(
        getattr(response, "_request_id", None)
        or getattr(response, "request_id", None)
        or ""
    ).strip()
    return candidate if _SAFE_REQUEST_ID_RE.fullmatch(candidate) else ""


def _safe_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump(mode="json")
    if not isinstance(usage, Mapping):
        return {}
    return {
        str(key): value
        for key, value in usage.items()
        if type(value) is int and value >= 0
    }


__all__ = [
    "DirectMediaAdapter",
    "DirectMediaConfigurationError",
    "DirectMediaError",
    "DirectMediaProviderError",
    "DirectMediaProviderRegistry",
    "DirectMediaResponseError",
    "OpenAIImageAdapter",
    "load_direct_media_descriptor",
]
