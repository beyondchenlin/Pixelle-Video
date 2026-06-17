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

from collections.abc import Mapping
from time import perf_counter
from types import SimpleNamespace
from typing import Any

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel

from pixelle_video.models.llm_interaction_trace import (
    LLM_TRACE_REQUIRED_MESSAGE,
    LLMTraceContext,
    LLMTraceRequiredError,
    LLMTraceStatus,
)
from pixelle_video.services.llm_capabilities import structured_output_capabilities
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.services.vision_capabilities import (
    detect_vision_capabilities,
    estimate_messages_text_tokens,
    redact_multimodal_messages_for_trace,
    validate_multimodal_image_limits,
)
from pixelle_video.utils.network_proxy import apply_adaptive_proxy_env


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

    def _get_vision_config(self) -> Mapping[str, Any]:
        from pixelle_video.config import config_manager

        configured = config_manager.get("vision_llm", {})
        if isinstance(configured, Mapping):
            merged = dict(self._initial_config)
            merged.update(dict(configured))
            return merged
        return self._initial_config

    def _create_client(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> AsyncOpenAI:
        config = self._get_vision_config()
        final_api_key = api_key or _config_value(config, "api_key") or "dummy-key"
        final_base_url = base_url or _config_value(config, "base_url")
        apply_adaptive_proxy_env(provider_base_url=final_base_url)
        client_kwargs: dict[str, Any] = {"api_key": final_api_key}
        if final_base_url:
            client_kwargs["base_url"] = final_base_url
        return AsyncOpenAI(**client_kwargs)

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
        if not final_model:
            raise ValueError("vision_llm.model is required for Vision LLM calls")
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

        client = self._create_client(api_key=api_key, base_url=final_base_url)
        wire_messages = [dict(message) for message in messages]
        trace_messages = redact_multimodal_messages_for_trace(messages)
        request_payload = {
            "model": final_model,
            "messages": trace_messages,
            "temperature": final_temperature,
            "max_tokens": final_max_tokens,
        }
        if kwargs:
            request_payload["extra_parameters"] = _json_safe_copy(kwargs)

        started_at = perf_counter()
        try:
            response = await client.chat.completions.create(
                model=final_model,
                messages=wire_messages,
                temperature=final_temperature,
                max_tokens=final_max_tokens,
                **kwargs,
            )
        except Exception as exc:
            await self._record_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=str(client.base_url or final_base_url or ""),
                model=final_model,
                request_payload=request_payload,
                response_payload=None,
                status=LLMTraceStatus.ERROR,
                elapsed_ms=_elapsed_ms(started_at),
                error_message=str(exc),
            )
            raise

        content = ""
        if getattr(response, "choices", None):
            content = response.choices[0].message.content or ""
        response_payload = {
            "content": content,
            "response": _json_safe_copy(response),
        }
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
                provider=provider,
                model=model,
                request_payload=request_payload,
                response_payload=response_payload,
                status=status,
                elapsed_ms=elapsed_ms,
                token_usage=token_usage,
                error_message=error_message,
            )
        except Exception as exc:
            logger.warning(
                "Failed to record Vision LLM interaction trace; generation will continue: %s",
                exc,
            )


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))


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
