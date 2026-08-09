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
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from loguru import logger
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError

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
from pixelle_video.utils.asyncio_util import await_cancel_safe_cleanup
from pixelle_video.utils.network_proxy import resolve_provider_proxy_async


class DirectMediaError(Exception):
    """Base error for governed direct media generation."""


class DirectMediaConfigurationError(DirectMediaError, ValueError):
    """Raised when a selected provider is disabled or misconfigured."""


class DirectMediaProviderError(DirectMediaError, RuntimeError):
    """Raised when a provider request fails."""


class DirectMediaResponseError(DirectMediaError, ValueError):
    """Raised when a provider returns an unsafe or unusable media response."""


@dataclass(frozen=True)
class _MaterializedImage:
    local_path: Path
    provider_width: int
    provider_height: int
    output_width: int
    output_height: int
    image_format: str
    output_bytes: int


def builtin_direct_media_descriptor_dir() -> Path:
    """Return package-owned provider descriptors included in wheel builds."""

    return Path(__file__).resolve().parents[1] / "resources" / "workflows" / "provider"


def builtin_direct_media_descriptor_path(filename: str) -> Path:
    """Resolve one package-owned descriptor without permitting path traversal."""

    if Path(filename).name != filename or not filename.endswith(".json"):
        raise ValueError("built-in direct media descriptor filename is invalid")
    descriptor_path = (builtin_direct_media_descriptor_dir() / filename).resolve()
    descriptor_path.relative_to(builtin_direct_media_descriptor_dir().resolve())
    if not descriptor_path.is_file():
        raise FileNotFoundError(f"built-in direct media descriptor not found: {filename}")
    return descriptor_path


def load_direct_media_descriptor(path: str | Path) -> DirectMediaDescriptor:
    descriptor_path = Path(path)
    try:
        payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DirectMediaConfigurationError(
            f"direct media descriptor could not be read: {descriptor_path.name}"
        ) from exc
    try:
        return DirectMediaDescriptor.model_validate(payload)
    except ValidationError:
        raise DirectMediaConfigurationError(
            f"direct media descriptor validation failed: {descriptor_path.name}"
        ) from None


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
            await await_cancel_safe_cleanup(self._release_adapter())

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

        api_parameters = dict(request.parameters)
        output_format = str(api_parameters.pop("output_format", "png"))
        if (
            api_parameters.get("background") == "transparent"
            and output_format == "jpeg"
        ):
            raise DirectMediaConfigurationError(
                "transparent image backgrounds require png or webp output"
            )
        _validate_requested_output_dimensions(
            request.width,
            request.height,
            max_pixels=provider_config.max_output_pixels,
            max_edge_px=provider_config.max_output_edge_px,
        )
        size = _openai_image_size(request.width, request.height)
        settings = await _openai_image_client_settings(provider_config)
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
        materialized = await asyncio.to_thread(
            _materialize_openai_image,
            encoded=encoded,
            output_dir=request.output_dir,
            requested_format=output_format,
            provider_size=size,
            target_width=request.width,
            target_height=request.height,
            max_bytes=provider_config.max_output_size_mb * 1024 * 1024,
            max_pixels=provider_config.max_output_pixels,
        )
        return DirectMediaOutput(
            media_type="image",
            local_path=materialized.local_path,
            provider_id=descriptor.provider_id,
            model=descriptor.model,
            request_id=_safe_request_id(response),
            provider_metadata={
                "actual_width": materialized.output_width,
                "actual_height": materialized.output_height,
                "provider_width": materialized.provider_width,
                "provider_height": materialized.provider_height,
                "format": materialized.image_format.lower(),
                "output_bytes": materialized.output_bytes,
                "requested_size": size,
                "transformed": (
                    materialized.provider_width != materialized.output_width
                    or materialized.provider_height != materialized.output_height
                ),
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


def _validate_requested_output_dimensions(
    width: int | None,
    height: int | None,
    *,
    max_pixels: int,
    max_edge_px: int,
) -> None:
    if width is None or height is None:
        return
    if width > max_edge_px or height > max_edge_px:
        raise DirectMediaConfigurationError(
            "direct image target dimensions exceeded the configured edge limit"
        )
    if width * height > max_pixels:
        raise DirectMediaConfigurationError(
            "direct image target dimensions exceeded the configured pixel limit"
        )


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


def _materialize_openai_image(
    *,
    encoded: str,
    output_dir: Path,
    requested_format: str,
    provider_size: str,
    target_width: int | None,
    target_height: int | None,
    max_bytes: int,
    max_pixels: int,
) -> _MaterializedImage:
    raw = _decode_bounded_base64_image(encoded, max_bytes=max_bytes)
    expected_format = "JPEG" if requested_format == "jpeg" else requested_format.upper()
    expected_provider_size = {
        "1024x1024": (1024, 1024),
        "1536x1024": (1536, 1024),
        "1024x1536": (1024, 1536),
    }[provider_size]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                image_format = str(image.format or "").upper()
                provider_width, provider_height = image.size
                if image_format not in {"PNG", "JPEG", "WEBP"}:
                    raise DirectMediaResponseError(
                        "image provider output format is not allowed"
                    )
                if image_format != expected_format:
                    raise DirectMediaResponseError(
                        "image provider output format did not match the requested format"
                    )
                if provider_width < 1 or provider_height < 1:
                    raise DirectMediaResponseError(
                        "image provider output dimensions were invalid"
                    )
                if provider_width * provider_height > max_pixels:
                    raise DirectMediaResponseError(
                        "image provider output exceeded safe pixel limits"
                    )
                if (provider_width, provider_height) != expected_provider_size:
                    raise DirectMediaResponseError(
                        "image provider output dimensions did not match the requested provider size"
                    )
                image.load()
                normalized_image = ImageOps.exif_transpose(image).copy()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise DirectMediaResponseError("image provider output exceeded safe pixel limits") from exc
    except DirectMediaResponseError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise DirectMediaResponseError("image provider output was not a valid image") from exc

    output_width = target_width or provider_width
    output_height = target_height or provider_height
    if normalized_image.size != (output_width, output_height):
        normalized_image = ImageOps.fit(
            normalized_image,
            (output_width, output_height),
            method=Image.Resampling.LANCZOS,
        )
    normalized_image = _normalized_image_mode(normalized_image, image_format=image_format)
    output_buffer = BytesIO()
    save_kwargs: dict[str, Any] = {}
    if image_format == "JPEG":
        save_kwargs["quality"] = 95
    elif image_format == "WEBP":
        save_kwargs["quality"] = 95
        save_kwargs["method"] = 4
    normalized_image.save(output_buffer, format=image_format, **save_kwargs)
    normalized_raw = output_buffer.getvalue()
    if not normalized_raw or len(normalized_raw) > max_bytes:
        raise DirectMediaResponseError(
            "normalized image provider output exceeded configured byte limit"
        )
    local_path = _write_image_atomically(
        output_dir,
        normalized_raw,
        image_format=image_format,
    )
    return _MaterializedImage(
        local_path=local_path,
        provider_width=provider_width,
        provider_height=provider_height,
        output_width=output_width,
        output_height=output_height,
        image_format=image_format,
        output_bytes=len(normalized_raw),
    )


def _normalized_image_mode(image: Image.Image, *, image_format: str) -> Image.Image:
    if image_format == "JPEG":
        return image if image.mode in {"L", "RGB"} else image.convert("RGB")
    if image.mode in {"1", "L", "LA", "RGB", "RGBA"}:
        return image
    if image.mode == "P" and "transparency" in image.info:
        return image.convert("RGBA")
    return image.convert("RGB")


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
    "builtin_direct_media_descriptor_dir",
    "builtin_direct_media_descriptor_path",
    "load_direct_media_descriptor",
]
