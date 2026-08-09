# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import math
from collections.abc import Mapping
from time import perf_counter
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel

from pixelle_video.models.llm_interaction_trace import (
    LLM_TRACE_REQUIRED_MESSAGE,
    LLMTraceContext,
    LLMTraceRecordingError,
    LLMTraceRequiredError,
    LLMTraceStatus,
)
from pixelle_video.models.llm_response import (
    LLMProviderRequestError,
    LLMResponseContractError,
    normalize_chat_completion,
)
from pixelle_video.services.llm_capabilities import structured_output_capabilities
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.services.openai_client_pool import (
    AsyncOpenAIClientPool,
    OpenAIClientSettings,
    create_openai_client,
)
from pixelle_video.services.vision_capabilities import (
    detect_vision_capabilities,
    estimate_messages_text_tokens,
    redact_multimodal_messages_for_trace,
    sanitize_multimodal_trace_error,
    validate_multimodal_image_limits,
)
from pixelle_video.utils.network_proxy import resolve_provider_proxy_async
from pixelle_video.utils.secret_redaction import is_sensitive_key


def _config_value(config: Any, key: str, default: Any = None) -> Any:
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


class VisionLLMService:
    """Multimodal LLM boundary for reference-image analysis.

    This service is intentionally separate from the main text ``LLMService`` in
    this PR so the existing prompt/structured-output paths remain untouched. It
    records only redacted image summaries in trace payloads while sending the
    original wire messages to the provider.
    """

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self._initial_config = dict(config or {})
        self._client_pool = AsyncOpenAIClientPool(max_size=2)

    def _get_vision_config(self) -> Mapping[str, Any]:
        from pixelle_video.config import config_manager

        configured = config_manager.get("vision_llm", {})
        if isinstance(configured, Mapping):
            merged = dict(configured)
            merged.update(self._initial_config)
            return merged
        return self._initial_config

    async def _create_client(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        settings: OpenAIClientSettings | None = None,
    ) -> AsyncOpenAI:
        resolved = settings
        if resolved is None:
            resolved = await self._client_settings(api_key=api_key, base_url=base_url)
        return await create_openai_client(resolved)

    async def _client_settings(
        self,
        *,
        api_key: str | None,
        base_url: str | None,
    ) -> OpenAIClientSettings:
        config = self._get_vision_config()
        final_api_key = api_key or _config_value(config, "api_key") or "dummy-key"
        final_base_url = str(base_url or _config_value(config, "base_url") or "").strip()
        proxy_target_url = final_base_url or "https://api.openai.com/v1"
        return OpenAIClientSettings(
            api_key=str(final_api_key),
            base_url=final_base_url,
            connect_timeout_seconds=float(
                _config_value(config, "connect_timeout_seconds", 10.0)
            ),
            read_timeout_seconds=float(
                _config_value(config, "read_timeout_seconds", 180.0)
            ),
            write_timeout_seconds=float(
                _config_value(config, "write_timeout_seconds", 30.0)
            ),
            pool_timeout_seconds=float(
                _config_value(config, "pool_timeout_seconds", 10.0)
            ),
            max_retries=int(_config_value(config, "max_retries", 1)),
            proxy=await resolve_provider_proxy_async(
                provider_base_url=proxy_target_url
            ),
        )

    async def chat(
        self,
        *,
        messages: list[Mapping[str, Any]],
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        trace_context: LLMTraceContext | None = None,
        trace_recorder: LLMInteractionRecorder | None = None,
        **kwargs: Any,
    ) -> str:
        """Call a multimodal chat model and record a redacted trace payload."""

        if trace_context is None or trace_recorder is None:
            raise LLMTraceRequiredError(LLM_TRACE_REQUIRED_MESSAGE)
        if not isinstance(messages, list) or not messages:
            raise ValueError("vision messages must be a non-empty list")

        config = self._get_vision_config()
        final_model = model or _config_value(config, "model")
        if not isinstance(final_model, str) or not final_model.strip():
            raise ValueError("vision_llm.model is required for Vision LLM calls")
        final_model = final_model.strip()
        final_temperature = (
            temperature
            if temperature is not None
            else float(_config_value(config, "temperature", 0.2))
        )
        final_max_tokens = (
            max_tokens
            if max_tokens is not None
            else int(_config_value(config, "max_tokens", 1200))
        )
        if (
            isinstance(final_temperature, bool)
            or not isinstance(final_temperature, (int, float))
            or not math.isfinite(float(final_temperature))
            or not 0 <= float(final_temperature) <= 2
        ):
            raise ValueError("vision temperature must be a finite number between 0 and 2")
        if type(final_max_tokens) is not int or final_max_tokens < 1:
            raise ValueError("vision max_tokens must be a positive integer")
        final_base_url = base_url or _config_value(config, "base_url")
        max_image_size_mb = int(_config_value(config, "max_image_size_mb", 5) or 5)
        capabilities = detect_vision_capabilities(
            base_url=final_base_url,
            model=final_model,
            force_supports_vision=_config_value(config, "force_supports_vision"),
            max_image_size_mb=max_image_size_mb,
        )
        if not capabilities.supports_vision_messages:
            raise ValueError(
                "configured vision model does not support image messages: "
                f"model={final_model!r}, reason={capabilities.reason}"
            )

        text_tokens = estimate_messages_text_tokens(messages)
        structured_caps = structured_output_capabilities(
            base_url=final_base_url,
            model=final_model,
        )
        if text_tokens > structured_caps.max_input_tokens:
            raise ValueError(
                f"Estimated text token count ({text_tokens}) exceeds model "
                f"'{final_model}' maximum input tokens ({structured_caps.max_input_tokens})"
            )
        if final_max_tokens > structured_caps.max_output_tokens:
            logger.warning(
                "Requested vision max_tokens ({}) exceeds model '{}' max output tokens ({}); clamping.",
                final_max_tokens,
                final_model,
                structured_caps.max_output_tokens,
            )
            final_max_tokens = structured_caps.max_output_tokens

        validate_multimodal_image_limits(
            messages,
            max_image_size_mb=max_image_size_mb,
        )

        wire_messages = [dict(message) for message in messages]
        trace_messages = redact_multimodal_messages_for_trace(messages)
        request_payload = {
            "model": final_model,
            "messages": trace_messages,
            "temperature": final_temperature,
            "max_tokens": final_max_tokens,
        }
        if kwargs:
            request_payload["extra_parameters"] = _trace_safe_copy(kwargs)

        settings: OpenAIClientSettings | None = None
        started_at = perf_counter()
        entered_pool_lease = False
        try:
            settings = await self._client_settings(
                api_key=api_key,
                base_url=final_base_url,
            )
            async with self._client_pool.acquire(
                fingerprint=settings.fingerprint,
                factory=lambda: self._create_client(settings=settings),
            ) as client:
                entered_pool_lease = True
                try:
                    response = await client.chat.completions.create(
                        model=final_model,
                        messages=wire_messages,
                        temperature=final_temperature,
                        max_tokens=final_max_tokens,
                        **kwargs,
                    )
                except Exception as exc:
                    safe_error = sanitize_multimodal_trace_error(exc)
                    await self._record_trace(
                        trace_context=trace_context,
                        trace_recorder=trace_recorder,
                        provider=str(client.base_url or final_base_url or ""),
                        model=final_model,
                        request_payload=request_payload,
                        response_payload=None,
                        status=LLMTraceStatus.ERROR,
                        elapsed_ms=_elapsed_ms(started_at),
                        error_message=safe_error,
                    )
                    raise LLMProviderRequestError(safe_error) from exc

                response_payload = {
                    "content": _first_message_content(response),
                    "response": _trace_safe_copy(response),
                }
                try:
                    content = normalize_chat_completion(
                        response,
                        model=final_model,
                    ).require_text(model=final_model)
                except LLMResponseContractError as exc:
                    await self._record_trace(
                        trace_context=trace_context,
                        trace_recorder=trace_recorder,
                        provider=str(client.base_url or final_base_url or ""),
                        model=final_model,
                        request_payload=request_payload,
                        response_payload=response_payload,
                        status=LLMTraceStatus.ERROR,
                        elapsed_ms=_elapsed_ms(started_at),
                        error_message=sanitize_multimodal_trace_error(exc),
                    )
                    raise

                response_payload["content"] = content
                await self._record_trace(
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                    provider=str(client.base_url or final_base_url or ""),
                    model=final_model,
                    request_payload=request_payload,
                    response_payload=response_payload,
                    status=LLMTraceStatus.SUCCESS,
                    elapsed_ms=_elapsed_ms(started_at),
                    token_usage=_extract_token_usage(response),
                )
                return content
        except LLMTraceRecordingError:
            raise
        except Exception as exc:
            if entered_pool_lease:
                raise
            safe_error = sanitize_multimodal_trace_error(exc)
            await self._record_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=(
                    settings.base_url
                    if settings is not None
                    else str(final_base_url or "")
                ),
                model=final_model,
                request_payload=request_payload,
                response_payload=None,
                status=LLMTraceStatus.ERROR,
                elapsed_ms=_elapsed_ms(started_at),
                error_message=safe_error,
            )
            raise LLMProviderRequestError(safe_error) from exc

    async def aclose(self) -> None:
        """Close cached provider transports and reset the pool for later reuse."""

        pool = self._client_pool
        self._client_pool = AsyncOpenAIClientPool(max_size=2)
        await pool.close()

    async def _record_trace(
        self,
        *,
        trace_context: LLMTraceContext,
        trace_recorder: LLMInteractionRecorder,
        provider: str,
        model: str,
        request_payload: Mapping[str, Any],
        response_payload: Mapping[str, Any] | None,
        status: LLMTraceStatus,
        elapsed_ms: int | None = None,
        token_usage: Mapping[str, int] | None = None,
        error_message: str = "",
    ) -> None:
        try:
            await trace_recorder.record_interaction(
                context=trace_context,
                provider=_safe_provider_label(provider),
                model=model,
                request_payload=request_payload,
                response_payload=response_payload,
                status=status,
                elapsed_ms=elapsed_ms,
                token_usage=token_usage,
                error_message=error_message,
            )
        except Exception as exc:
            logger.error(
                "Failed to record mandatory Vision LLM interaction trace: error_type={}",
                type(exc).__name__,
            )
            raise LLMTraceRecordingError(
                "mandatory Vision LLM interaction trace could not be persisted"
            ) from exc


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))


def _first_message_content(response: Any) -> Any:
    choices = getattr(response, "choices", None)
    if not isinstance(choices, (list, tuple)) or not choices:
        return None
    message = getattr(choices[0], "message", None)
    return getattr(message, "content", None) if message is not None else None


def _safe_provider_label(base_url: Any) -> str:
    try:
        parsed = urlparse(str(base_url or ""))
        if not parsed.hostname:
            return "default"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return f"{parsed.scheme or 'https'}://{parsed.hostname}{port}"
    except (TypeError, ValueError):
        return "invalid-provider-url"


def _extract_token_usage(response: Any) -> Mapping[str, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    normalized: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage, key, None)
        if type(value) is int and value >= 0:
            normalized[key] = value
    return normalized or None


def _json_safe_copy(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, SimpleNamespace):
        return {key: _json_safe_copy(item) for key, item in vars(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _json_safe_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_copy(item) for item in value]
    if isinstance(value, type):
        return value.__name__
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _trace_safe_copy(value: Any, *, key: Any = None) -> Any:
    if key is not None and is_sensitive_key(key):
        return "[REDACTED]"
    if isinstance(value, BaseModel):
        return _trace_safe_copy(value.model_dump(mode="json"))
    if isinstance(value, SimpleNamespace):
        return {
            str(item_key): _trace_safe_copy(item, key=item_key)
            for item_key, item in vars(value).items()
        }
    if isinstance(value, Mapping):
        return {
            str(item_key): _trace_safe_copy(item, key=item_key)
            for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_trace_safe_copy(item) for item in value]
    return _json_safe_copy(value)
