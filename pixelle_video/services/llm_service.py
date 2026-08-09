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

"""
LLM (Large Language Model) Service - Direct OpenAI SDK implementation

Supports structured output via response_type parameter (Pydantic model).
"""

import hashlib
import json
import math
import re
from collections.abc import Mapping
from time import perf_counter
from types import SimpleNamespace
from typing import Any, Optional, Type, TypeVar, Union
from urllib.parse import urlparse

from loguru import logger
from openai import AsyncOpenAI, BadRequestError
from pydantic import BaseModel, ValidationError

from pixelle_video.models.llm_interaction_trace import (
    LLM_TRACE_REQUIRED_MESSAGE,
    LLMTraceContext,
    LLMTraceRecordingError,
    LLMTraceRequiredError,
    LLMTraceStatus,
    trace_context_with_prompt_template_overlay,
)
from pixelle_video.models.llm_response import (
    LLMEmptyResponseError,
    LLMProviderRequestError,
    LLMResponseContractError,
    normalize_chat_completion,
)
from pixelle_video.prompts.structured_output import (
    render_structured_json_object_prompt,
    render_structured_schema_output_prompt,
)
from pixelle_video.services.llm_capabilities import (
    StructuredOutputCapabilities,
    estimate_input_tokens,
    is_json_object_response_format_unsupported_error,
    structured_output_capabilities,
)
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.services.openai_client_pool import (
    AsyncOpenAIClientPool,
    OpenAIClientSettings,
    create_openai_client,
)
from pixelle_video.utils.json_parsing import parse_llm_json_response
from pixelle_video.utils.network_proxy import resolve_provider_proxy_async

T = TypeVar("T", bound=BaseModel)

_REDACTED_VALUE = "[REDACTED]"
_SENSITIVE_TRACE_KEYS = frozenset(
    {
        "access_key",
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "proxy_authorization",
        "refresh_token",
        "secret",
        "secret_key",
        "set_cookie",
        "token",
        "x_api_key",
    }
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|access[_-]?token|"
    r"refresh[_-]?token|password|authorization|cookie)\b(\s*[:=]\s*)"
    r"([^\s,;]+)"
)
_BEARER_TOKEN_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*")
_URL_USERINFO_RE = re.compile(r"(?i)(https?://)[^/@\s]+@")
_MAX_SAFE_ERROR_CHARS = 1000


class LLMService:
    """
    LLM (Large Language Model) service

    Direct implementation using OpenAI SDK. No capability layer needed.

    Supports all OpenAI SDK compatible providers:
    - OpenAI (gpt-4o, gpt-4o-mini, gpt-3.5-turbo)
    - Alibaba Qwen (qwen-max, qwen-plus, qwen-turbo)
    - Anthropic Claude (claude-sonnet-4-5, claude-opus-4, claude-haiku-4)
    - DeepSeek (deepseek-chat)
    - Moonshot Kimi (moonshot-v1-8k, moonshot-v1-32k, moonshot-v1-128k)
    - Ollama (llama3.2, qwen2.5, mistral, codellama) - FREE & LOCAL!
    - Any custom provider with OpenAI-compatible API

    Usage:
        LLM calls require trace_context and trace_recorder so the exact prompt,
        response, template source, and status are saved. Prefer the pipeline
        helpers that create those trace objects before calling this service.
    """
    
    def __init__(self, config: dict):
        """
        Initialize LLM service
        
        Args:
            config: Full application config dict (kept for backward compatibility)
        """
        # Note: We no longer cache config here to support hot reload
        # Config is read dynamically from config_manager in _get_config_value()
        self._client_pool = AsyncOpenAIClientPool(max_size=4)
    
    def _get_config_value(self, key: str, default=None):
        """
        Get config value dynamically from config_manager (supports hot reload)
        
        Args:
            key: Config key name
            default: Default value if not found
        
        Returns:
            Config value
        """
        from pixelle_video.config import config_manager
        return getattr(config_manager.config.llm, key, default)
    
    async def _create_client(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        *,
        settings: OpenAIClientSettings | None = None,
    ) -> AsyncOpenAI:
        """
        Create OpenAI client
        
        Args:
            api_key: API key (optional, uses config if not provided)
            base_url: Base URL (optional, uses config if not provided)
        
        Returns:
            AsyncOpenAI client instance
        """
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
        final_api_key = api_key or self._get_config_value("api_key") or "dummy-key"
        final_base_url = str(base_url or self._get_config_value("base_url") or "").strip()
        proxy_target_url = final_base_url or "https://api.openai.com/v1"
        return OpenAIClientSettings(
            api_key=str(final_api_key),
            base_url=final_base_url,
            connect_timeout_seconds=float(
                self._get_config_value("connect_timeout_seconds", 10.0)
            ),
            read_timeout_seconds=float(
                self._get_config_value("read_timeout_seconds", 180.0)
            ),
            write_timeout_seconds=float(
                self._get_config_value("write_timeout_seconds", 30.0)
            ),
            pool_timeout_seconds=float(
                self._get_config_value("pool_timeout_seconds", 10.0)
            ),
            max_retries=int(self._get_config_value("max_retries", 1)),
            proxy=await resolve_provider_proxy_async(
                provider_base_url=proxy_target_url
            ),
        )
    
    async def __call__(
        self,
        prompt: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 10000,
        response_type: Optional[Type[T] | Type[dict]] = None,
        trace_context: Optional[LLMTraceContext] = None,
        trace_recorder: Optional[LLMInteractionRecorder] = None,
        **kwargs
    ) -> Union[str, T, dict[str, Any]]:
        """
        Generate text using LLM
        
        Args:
            prompt: The prompt to generate from
            api_key: API key (optional, uses config if not provided)
            base_url: Base URL (optional, uses config if not provided)
            model: Model name (optional, uses config if not provided)
            temperature: Sampling temperature (0.0-2.0). Lower is more deterministic.
            max_tokens: Maximum tokens to generate
            response_type: Optional type for structured output.
                          - If a Pydantic model class is provided, returns parsed model instance
                          - If dict is provided, returns parsed JSON as dictionary
                          - If None, returns raw text string
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated text (str), parsed Pydantic model instance, or dict (depending on response_type)

        Examples:
            LLM calls must pass trace_context and trace_recorder. Pipeline and
            service helpers create these objects before calling this boundary.

            # Structured output with Pydantic model
            class MovieReview(BaseModel):
                title: str
                rating: int
                summary: str

            review = await pixelle_video.llm(
                prompt="Review the movie Inception",
                response_type=MovieReview,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
            print(review.title)  # Structured access

            # Structured output as dict (no model definition needed)
            data = await pixelle_video.llm(
                prompt="Generate a JSON object with 'name' and 'age' fields",
                response_type=dict,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
            print(data["name"])  # Direct dict access
        """
        if trace_context is None or trace_recorder is None:
            raise LLMTraceRequiredError(LLM_TRACE_REQUIRED_MESSAGE)
        _validate_llm_call_arguments(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_type=response_type,
        )
        final_model = (
            model
            or self._get_config_value("model")
            or "gpt-3.5-turbo"  # Default fallback
        )
        if not isinstance(final_model, str) or not final_model.strip():
            raise ValueError("model must resolve to a non-empty string")
        final_model = final_model.strip()
        settings: OpenAIClientSettings | None = None
        entered_pool_lease = False
        try:
            settings = await self._client_settings(api_key=api_key, base_url=base_url)
            async with self._client_pool.acquire(
                fingerprint=settings.fingerprint,
                factory=lambda: self._create_client(settings=settings),
            ) as client:
                entered_pool_lease = True
                return await self._call_with_client(
                    client=client,
                    prompt=prompt,
                    model=final_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_type=response_type,
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                    **kwargs,
                )
        except LLMTraceRecordingError:
            raise
        except Exception as exc:
            if entered_pool_lease:
                raise
            safe_error = _sanitize_error_message(exc)
            await self._record_llm_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=(
                    settings.base_url
                    if settings is not None
                    else str(base_url or self._get_config_value("base_url") or "")
                ),
                model=final_model,
                request_payload=self._build_request_payload(
                    model=final_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_parameters=kwargs,
                ),
                response_payload=None,
                status=LLMTraceStatus.ERROR,
                error_message=safe_error,
            )
            raise LLMProviderRequestError(safe_error) from exc

    async def _call_with_client(
        self,
        *,
        client: AsyncOpenAI,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        response_type: Optional[Type[T] | Type[dict]],
        trace_context: LLMTraceContext,
        trace_recorder: LLMInteractionRecorder,
        **kwargs: Any,
    ) -> Union[str, T, dict[str, Any]]:
        final_model = model
        logger.debug(
            "LLM call: model={} provider={} response_type={}",
            final_model,
            _safe_provider_label(client.base_url),
            response_type,
        )

        # Capabilities are resolved once with configuration overrides and then
        # propagated to every output mode. Re-resolving them inside structured
        # paths previously discarded operator-supplied token limits.
        final_base_url = str(client.base_url or "") if client.base_url else None
        capabilities = structured_output_capabilities(
            base_url=final_base_url,
            model=final_model,
            max_input_tokens_override=self._get_config_value("max_input_tokens"),
            max_output_tokens_override=self._get_config_value("max_output_tokens"),
        )
        if max_tokens > capabilities.max_output_tokens:
            logger.warning(
                f"Requested max_tokens ({max_tokens}) exceeds model "
                f"'{final_model}' max output tokens "
                f"({capabilities.max_output_tokens}); clamping."
            )
            max_tokens = capabilities.max_output_tokens

        try:
            if response_type is not None:
                # Check if response_type is dict (raw JSON dict mode)
                if response_type is dict:
                    return await self._call_with_dict_output(
                        client=client,
                        model=final_model,
                        prompt=prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        trace_context=trace_context,
                        trace_recorder=trace_recorder,
                        capabilities=capabilities,
                        **kwargs
                    )
                # Structured output mode with Pydantic model
                return await self._call_with_structured_output(
                    client=client,
                    model=final_model,
                    prompt=prompt,
                    response_type=response_type,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                    capabilities=capabilities,
                    **kwargs
                )
            else:
                # Standard text output mode
                request_payload = self._build_request_payload(
                    model=final_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_parameters=kwargs,
                )
                await self._validate_request_budget(
                    prompt_text=prompt,
                    capabilities=capabilities,
                    provider=str(client.base_url or ""),
                    model=final_model,
                    request_payload=request_payload,
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                )
                started_at = perf_counter()
                try:
                    response = await client.chat.completions.create(
                        model=final_model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=temperature,
                        max_tokens=max_tokens,
                        **kwargs
                    )
                except Exception as exc:
                    safe_error = _sanitize_error_message(exc)
                    await self._record_llm_trace(
                        trace_context=trace_context,
                        trace_recorder=trace_recorder,
                        provider=str(client.base_url or ""),
                        model=final_model,
                        request_payload=request_payload,
                        response_payload=None,
                        status=LLMTraceStatus.ERROR,
                        elapsed_ms=_elapsed_ms(started_at),
                        error_message=safe_error,
                    )
                    raise LLMProviderRequestError(safe_error) from exc

                normalized, response_payload, elapsed_ms, token_usage = (
                    await self._normalize_response_with_trace(
                        response=response,
                        require_text=True,
                        provider=str(client.base_url or ""),
                        model=final_model,
                        request_payload=request_payload,
                        trace_context=trace_context,
                        trace_recorder=trace_recorder,
                        started_at=started_at,
                    )
                )
                result = normalized.require_text(model=final_model)
                logger.debug(f"LLM response length: {len(result)} chars")
                await self._record_llm_trace(
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                    provider=str(client.base_url or ""),
                    model=final_model,
                    request_payload=request_payload,
                    response_payload=response_payload,
                    status=LLMTraceStatus.SUCCESS,
                    elapsed_ms=elapsed_ms,
                    token_usage=token_usage,
                )
                
                return result
        except Exception as e:
            logger.error(
                "LLM call error: model={} provider={} error_type={} error={}",
                final_model,
                _safe_provider_label(client.base_url),
                type(e).__name__,
                _safe_exception_summary(e),
            )
            raise

    async def aclose(self) -> None:
        """Close cached provider transports and reset the pool for later reuse."""

        pool = self._client_pool
        self._client_pool = AsyncOpenAIClientPool(max_size=4)
        await pool.close()
    
    async def _call_with_structured_output(
        self,
        client: AsyncOpenAI,
        model: str,
        prompt: str,
        response_type: Type[T],
        temperature: float,
        max_tokens: int,
        trace_context: Optional[LLMTraceContext] = None,
        trace_recorder: Optional[LLMInteractionRecorder] = None,
        capabilities: StructuredOutputCapabilities | None = None,
        **kwargs
    ) -> T:
        """
        Call LLM with structured output support

        Prefer provider-native structured output for supported OpenAI models and
        fall back to JSON-schema-in-prompt mode for compatible providers that do
        not support the native parse API.
        
        Args:
            client: OpenAI client
            model: Model name
            prompt: The prompt
            response_type: Pydantic model class
            temperature: Sampling temperature
            max_tokens: Max tokens
            **kwargs: Additional parameters
        
        Returns:
            Parsed Pydantic model instance
        """
        if self._should_use_native_structured_output(client=client, model=model):
            return await self._call_with_native_structured_output(
                client=client,
                model=model,
                prompt=prompt,
                response_type=response_type,
                temperature=temperature,
                max_tokens=max_tokens,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                capabilities=capabilities,
                **kwargs
            )

        return await self._call_with_prompt_schema_structured_output(
            client=client,
            model=model,
            prompt=prompt,
            response_type=response_type,
            temperature=temperature,
            max_tokens=max_tokens,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
            capabilities=capabilities,
            **kwargs
        )

    def _should_use_native_structured_output(self, *, client: AsyncOpenAI, model: str) -> bool:
        base_url = str(client.base_url or "").strip().lower()
        hostname = urlparse(base_url).hostname or ""
        is_openai_provider = not hostname or hostname.endswith("openai.com")
        if not is_openai_provider:
            return False

        normalized_model = (model or "").strip().lower()
        native_prefixes = (
            "gpt-4",
            "gpt-5",
            "chatgpt-4",
            "o1",
            "o3",
            "o4",
        )
        return normalized_model.startswith(native_prefixes)

    async def _call_with_native_structured_output(
        self,
        client: AsyncOpenAI,
        model: str,
        prompt: str,
        response_type: Type[T],
        temperature: float,
        max_tokens: int,
        trace_context: Optional[LLMTraceContext] = None,
        trace_recorder: Optional[LLMInteractionRecorder] = None,
        capabilities: StructuredOutputCapabilities | None = None,
        **kwargs
    ) -> T:
        request_payload = self._build_request_payload(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=self._structured_response_format_payload(response_type),
            extra_parameters=kwargs,
        )
        capabilities = capabilities or self._capabilities_for(client=client, model=model)
        budget_text = "\n".join(
            (
                prompt,
                json.dumps(
                    request_payload.get("response_format") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        )
        await self._validate_request_budget(
            prompt_text=budget_text,
            capabilities=capabilities,
            provider=str(client.base_url or ""),
            model=model,
            request_payload=request_payload,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )
        started_at = perf_counter()
        try:
            response = await client.beta.chat.completions.parse(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format=response_type,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        except Exception as exc:
            safe_error = _sanitize_error_message(exc)
            await self._record_llm_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=str(client.base_url or ""),
                model=model,
                request_payload=request_payload,
                response_payload=None,
                status=LLMTraceStatus.ERROR,
                elapsed_ms=_elapsed_ms(started_at),
                error_message=safe_error,
            )
            raise LLMProviderRequestError(safe_error) from exc
        normalized, response_payload, elapsed_ms, token_usage = (
            await self._normalize_response_with_trace(
                response=response,
                require_text=False,
                provider=str(client.base_url or ""),
                model=model,
                request_payload=request_payload,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                started_at=started_at,
            )
        )
        message = normalized.message
        parsed = getattr(message, "parsed", None)
        if parsed is not None:
            await self._record_llm_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=str(client.base_url or ""),
                model=model,
                request_payload=request_payload,
                response_payload=response_payload,
                status=LLMTraceStatus.SUCCESS,
                elapsed_ms=elapsed_ms,
                token_usage=token_usage,
            )
            return parsed

        refusal = getattr(message, "refusal", None)
        if refusal:
            error_message = f"Structured output request refused by model: {refusal}"
            await self._record_llm_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=str(client.base_url or ""),
                model=model,
                request_payload=request_payload,
                response_payload=response_payload,
                status=LLMTraceStatus.ERROR,
                elapsed_ms=elapsed_ms,
                token_usage=token_usage,
                error_message=error_message,
            )
            raise ValueError(error_message)

        content = normalized.content or ""
        if content:
            try:
                parsed_from_content = self._parse_response_as_model(content, response_type)
            except Exception as exc:
                await self._record_llm_trace(
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                    provider=str(client.base_url or ""),
                    model=model,
                    request_payload=request_payload,
                    response_payload=response_payload,
                    status=_trace_status_for_structured_exception(exc),
                    elapsed_ms=elapsed_ms,
                    token_usage=token_usage,
                    parse_error=_trace_parse_error_message(exc),
                    validation_errors=_validation_error_details(exc),
                )
                raise
            await self._record_llm_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=str(client.base_url or ""),
                model=model,
                request_payload=request_payload,
                response_payload=response_payload,
                status=LLMTraceStatus.SUCCESS,
                elapsed_ms=elapsed_ms,
                token_usage=token_usage,
            )
            return parsed_from_content

        error_message = (
            f"Structured output response from model {model!r} did not include parsed content"
        )
        await self._record_llm_trace(
            trace_context=trace_context,
            trace_recorder=trace_recorder,
            provider=str(client.base_url or ""),
            model=model,
            request_payload=request_payload,
            response_payload=response_payload,
            status=LLMTraceStatus.ERROR,
            elapsed_ms=elapsed_ms,
            token_usage=token_usage,
            error_message=error_message,
        )
        raise LLMEmptyResponseError(error_message, reason="parsed_content_missing")

    async def _call_with_dict_output(
        self,
        client: AsyncOpenAI,
        model: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
        trace_context: Optional[LLMTraceContext] = None,
        trace_recorder: Optional[LLMInteractionRecorder] = None,
        capabilities: StructuredOutputCapabilities | None = None,
        **kwargs
    ) -> dict[str, Any]:
        """
        Call LLM and return response as a parsed JSON dictionary.

        This is useful when you need structured JSON output but don't want
        to define a Pydantic model. The LLM response will be parsed as JSON
        and returned as a Python dict.

        Args:
            client: OpenAI client
            model: Model name
            prompt: The prompt (should instruct model to return JSON)
            temperature: Sampling temperature
            max_tokens: Max tokens
            trace_context: Optional trace context
            trace_recorder: Optional trace recorder
            **kwargs: Additional parameters

        Returns:
            Parsed JSON as dictionary
        """
        rendered_prompt = render_structured_json_object_prompt(prompt)
        trace_context = trace_context_with_prompt_template_overlay(
            trace_context,
            rendered_prompt=rendered_prompt,
        ) if trace_context is not None else None
        enhanced_prompt = rendered_prompt.text

        capabilities = capabilities or self._capabilities_for(client=client, model=model)

        request_kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": enhanced_prompt}],
            "temperature": temperature,
            **kwargs,
        }
        if capabilities.supports_json_object_response_format:
            request_kwargs["response_format"] = {"type": "json_object"}
            if not capabilities.omit_max_tokens_with_json_object:
                request_kwargs["max_tokens"] = max_tokens
        else:
            request_kwargs["max_tokens"] = max_tokens

        request_payload = _trace_safe_copy(request_kwargs)

        await self._validate_request_budget(
            prompt_text=enhanced_prompt,
            capabilities=capabilities,
            provider=str(client.base_url or ""),
            model=model,
            request_payload=request_payload,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )

        started_at = perf_counter()
        try:
            response = await client.chat.completions.create(**request_kwargs)
        except Exception as exc:
            safe_error = _sanitize_error_message(exc)
            await self._record_llm_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=str(client.base_url or ""),
                model=model,
                request_payload=request_payload,
                response_payload=None,
                status=LLMTraceStatus.ERROR,
                elapsed_ms=_elapsed_ms(started_at),
                error_message=safe_error,
            )
            raise LLMProviderRequestError(safe_error) from exc

        normalized, response_payload, elapsed_ms, token_usage = (
            await self._normalize_response_with_trace(
                response=response,
                require_text=True,
                provider=str(client.base_url or ""),
                model=model,
                request_payload=request_payload,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                started_at=started_at,
            )
        )
        content = normalized.require_text(model=model)

        try:
            parsed = parse_llm_json_response(
                content,
                allow_code_fence=True,
                allow_embedded_json=False,
            )
            if isinstance(parsed, dict):
                pass
            elif isinstance(parsed, list):
                logger.warning(
                    "LLM returned JSON array instead of object; "
                    "wrapping in dict directly: model={} base_url={}",
                    model,
                    _safe_provider_label(client.base_url),
                )
                parsed = {"data": parsed}
            else:
                raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")
        except Exception as exc:
            await self._record_llm_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=str(client.base_url or ""),
                model=model,
                request_payload=request_payload,
                response_payload=response_payload,
                status=LLMTraceStatus.ERROR,
                elapsed_ms=elapsed_ms,
                token_usage=token_usage,
                parse_error=_trace_parse_error_message(exc),
            )
            raise

        await self._record_llm_trace(
            trace_context=trace_context,
            trace_recorder=trace_recorder,
            provider=str(client.base_url or ""),
            model=model,
            request_payload=request_payload,
            response_payload=response_payload,
            status=LLMTraceStatus.SUCCESS,
            elapsed_ms=elapsed_ms,
            token_usage=token_usage,
        )

        return parsed

    async def _call_with_prompt_schema_structured_output(
        self,
        client: AsyncOpenAI,
        model: str,
        prompt: str,
        response_type: Type[T],
        temperature: float,
        max_tokens: int,
        trace_context: Optional[LLMTraceContext] = None,
        trace_recorder: Optional[LLMInteractionRecorder] = None,
        capabilities: StructuredOutputCapabilities | None = None,
        **kwargs
    ) -> T:
        rendered_prompt = self._render_structured_schema_prompt(
            prompt=prompt,
            response_type=response_type,
        )
        trace_context = trace_context_with_prompt_template_overlay(
            trace_context,
            rendered_prompt=rendered_prompt,
        ) if trace_context is not None else None
        enhanced_prompt = rendered_prompt.text
        capabilities = capabilities or self._capabilities_for(client=client, model=model)

        request_kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": enhanced_prompt}],
            "temperature": temperature,
            **kwargs,
        }
        json_mode_kwargs = {
            **request_kwargs,
            "response_format": {"type": "json_object"},
        }
        if not capabilities.omit_max_tokens_with_json_object:
            json_mode_kwargs["max_tokens"] = max_tokens

        initial_trace_request = (
            json_mode_kwargs
            if capabilities.supports_json_object_response_format
            else {**request_kwargs, "max_tokens": max_tokens}
        )
        await self._validate_request_budget(
            prompt_text=enhanced_prompt,
            capabilities=capabilities,
            provider=str(client.base_url or ""),
            model=model,
            request_payload=self._build_request_payload_from_kwargs(initial_trace_request),
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )

        started_at = perf_counter()
        if capabilities.supports_json_object_response_format:
            trace_request_kwargs = json_mode_kwargs
            try:
                response = await client.chat.completions.create(**json_mode_kwargs)
            except Exception as exc:
                should_retry_without_json_mode = (
                    isinstance(exc, (BadRequestError, TypeError))
                    and capabilities.retry_prompt_schema_when_json_object_unsupported
                    and is_json_object_response_format_unsupported_error(exc)
                )
                if not should_retry_without_json_mode:
                    safe_error = _sanitize_error_message(exc)
                    await self._record_llm_trace(
                        trace_context=trace_context,
                        trace_recorder=trace_recorder,
                        provider=str(client.base_url or ""),
                        model=model,
                        request_payload=self._build_request_payload_from_kwargs(trace_request_kwargs),
                        response_payload=None,
                        status=LLMTraceStatus.ERROR,
                        elapsed_ms=_elapsed_ms(started_at),
                        error_message=safe_error,
                    )
                    raise LLMProviderRequestError(safe_error) from exc
                safe_error = _sanitize_error_message(exc)
                await self._record_llm_trace(
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                    provider=str(client.base_url or ""),
                    model=model,
                    request_payload=self._build_request_payload_from_kwargs(trace_request_kwargs),
                    response_payload=None,
                    status=LLMTraceStatus.ERROR,
                    elapsed_ms=_elapsed_ms(started_at),
                    error_message=safe_error,
                )
                logger.warning(
                    "Provider rejected JSON mode for structured output; retrying with prompt-only schema: {}",
                    safe_error,
                )
                trace_request_kwargs = {**request_kwargs, "max_tokens": max_tokens}
                started_at = perf_counter()
                try:
                    response = await client.chat.completions.create(**trace_request_kwargs)
                except Exception as retry_exc:
                    safe_retry_error = _sanitize_error_message(retry_exc)
                    await self._record_llm_trace(
                        trace_context=trace_context,
                        trace_recorder=trace_recorder,
                        provider=str(client.base_url or ""),
                        model=model,
                        request_payload=self._build_request_payload_from_kwargs(trace_request_kwargs),
                        response_payload=None,
                        status=LLMTraceStatus.ERROR,
                        elapsed_ms=_elapsed_ms(started_at),
                        error_message=safe_retry_error,
                    )
                    raise LLMProviderRequestError(safe_retry_error) from retry_exc
        else:
            trace_request_kwargs = {**request_kwargs, "max_tokens": max_tokens}
            try:
                response = await client.chat.completions.create(**trace_request_kwargs)
            except Exception as exc:
                safe_error = _sanitize_error_message(exc)
                await self._record_llm_trace(
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                    provider=str(client.base_url or ""),
                    model=model,
                    request_payload=self._build_request_payload_from_kwargs(trace_request_kwargs),
                    response_payload=None,
                    status=LLMTraceStatus.ERROR,
                    elapsed_ms=_elapsed_ms(started_at),
                    error_message=safe_error,
                )
                raise LLMProviderRequestError(safe_error) from exc
        request_payload = self._build_request_payload_from_kwargs(trace_request_kwargs)
        normalized, response_payload, elapsed_ms, token_usage = (
            await self._normalize_response_with_trace(
                response=response,
                require_text=True,
                provider=str(client.base_url or ""),
                model=model,
                request_payload=request_payload,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                started_at=started_at,
            )
        )
        content = normalized.require_text(model=model)

        logger.debug(f"Structured output response length: {len(content)} chars")

        try:
            parsed = self._parse_response_as_model(content, response_type)
        except Exception as exc:
            await self._record_llm_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=str(client.base_url or ""),
                model=model,
                request_payload=request_payload,
                response_payload=response_payload,
                status=_trace_status_for_structured_exception(exc),
                elapsed_ms=elapsed_ms,
                token_usage=token_usage,
                parse_error=_trace_parse_error_message(exc),
                validation_errors=_validation_error_details(exc),
            )
            raise
        await self._record_llm_trace(
            trace_context=trace_context,
            trace_recorder=trace_recorder,
            provider=str(client.base_url or ""),
            model=model,
            request_payload=request_payload,
            response_payload=response_payload,
            status=LLMTraceStatus.SUCCESS,
            elapsed_ms=elapsed_ms,
            token_usage=token_usage,
        )
        return parsed

    def _capabilities_for(
        self,
        *,
        client: AsyncOpenAI,
        model: str,
    ) -> StructuredOutputCapabilities:
        return structured_output_capabilities(
            base_url=str(client.base_url or ""),
            model=model,
            max_input_tokens_override=self._get_config_value("max_input_tokens"),
            max_output_tokens_override=self._get_config_value("max_output_tokens"),
        )

    async def _validate_request_budget(
        self,
        *,
        prompt_text: str,
        capabilities: StructuredOutputCapabilities,
        provider: str,
        model: str,
        request_payload: Mapping[str, Any],
        trace_context: LLMTraceContext,
        trace_recorder: LLMInteractionRecorder,
    ) -> None:
        estimated_tokens = estimate_input_tokens(prompt_text)
        if estimated_tokens <= capabilities.max_input_tokens:
            return

        error_message = (
            f"Estimated input token count ({estimated_tokens}) exceeds model "
            f"{model!r} maximum input tokens ({capabilities.max_input_tokens}). "
            "Reduce the input length or split it into smaller batches."
        )
        await self._record_llm_trace(
            trace_context=trace_context,
            trace_recorder=trace_recorder,
            provider=provider,
            model=model,
            request_payload=request_payload,
            response_payload=None,
            status=LLMTraceStatus.ERROR,
            elapsed_ms=0,
            error_message=error_message,
        )
        raise ValueError(error_message)

    async def _normalize_response_with_trace(
        self,
        *,
        response: Any,
        require_text: bool,
        provider: str,
        model: str,
        request_payload: Mapping[str, Any],
        trace_context: LLMTraceContext,
        trace_recorder: LLMInteractionRecorder,
        started_at: float,
    ):
        elapsed_ms = _elapsed_ms(started_at)
        token_usage = _extract_token_usage(response)
        response_payload = self._build_response_payload(
            response=response,
            content=_first_message_content(response),
        )
        try:
            normalized = normalize_chat_completion(response, model=model)
            if require_text:
                normalized.require_text(model=model)
        except LLMResponseContractError as exc:
            await self._record_llm_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=provider,
                model=model,
                request_payload=request_payload,
                response_payload=response_payload,
                status=LLMTraceStatus.ERROR,
                elapsed_ms=elapsed_ms,
                token_usage=token_usage,
                error_message=str(exc),
            )
            raise
        return normalized, response_payload, elapsed_ms, token_usage

    def _render_structured_schema_prompt(self, *, prompt: str, response_type: Type[T]):
        schema = response_type.model_json_schema()
        schema_str = json.dumps(schema, indent=2, ensure_ascii=False)
        return render_structured_schema_output_prompt(
            prompt=prompt,
            response_type_name=response_type.__name__,
            schema_json=schema_str,
        )

    def _structured_response_format_payload(self, response_type: Type[T]) -> dict[str, Any]:
        schema = response_type.model_json_schema()
        return {
            "type": "pydantic_model",
            "name": response_type.__name__,
            "schema": schema,
        }
    
    def _parse_response_as_model(self, content: str, response_type: Type[T]) -> T:
        """
        Parse LLM response content as Pydantic model
        
        Args:
            content: Raw LLM response text
            response_type: Target Pydantic model class
        
        Returns:
            Parsed model instance
        """
        content_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        logger.debug(
            "Parsing LLM response as {}, content_length={}, content_sha256={}",
            response_type.__name__,
            len(content),
            content_digest,
        )
        
        try:
            data = parse_llm_json_response(
                content,
                allow_code_fence=True,
                allow_embedded_json=False,
            )
            return response_type.model_validate(data)
        except json.JSONDecodeError as e:
            logger.error(
                "JSON decode error for {}: content_length={} content_sha256={} error={}",
                response_type.__name__,
                len(content),
                content_digest,
                _sanitize_error_message(e),
            )
            raise ValueError(
                f"Failed to parse LLM response as {response_type.__name__}; "
                f"content_length={len(content)} content_sha256={content_digest}"
            ) from e
        except ValidationError as e:
            logger.error(
                "Schema validation error for {}: content_length={} content_sha256={} error_count={}",
                response_type.__name__,
                len(content),
                content_digest,
                len(e.errors()),
            )
            raise
        except Exception as e:
            logger.error(
                "Unexpected parse error for {}: content_length={} content_sha256={} "
                "error_type={} error={}",
                response_type.__name__,
                len(content),
                content_digest,
                type(e).__name__,
                _sanitize_error_message(e),
            )
            raise ValueError(
                f"Failed to parse LLM response as {response_type.__name__}; "
                f"content_length={len(content)} content_sha256={content_digest}"
            ) from e

    def _build_request_payload(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        extra_parameters: Mapping[str, Any],
        response_format: Any = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if extra_parameters:
            payload["extra_parameters"] = _trace_safe_copy(extra_parameters)
        return payload

    def _build_request_payload_from_kwargs(self, request_kwargs: Mapping[str, Any]) -> dict[str, Any]:
        return _trace_safe_copy(request_kwargs)

    def _build_response_payload(self, *, response: Any, content: Any) -> dict[str, Any]:
        return {
            "content": content,
            "response": _json_safe_copy(response),
        }

    async def _record_llm_trace(
        self,
        *,
        trace_context: Optional[LLMTraceContext],
        trace_recorder: Optional[LLMInteractionRecorder],
        provider: str,
        model: str,
        request_payload: Mapping[str, Any],
        response_payload: Mapping[str, Any] | None,
        status: LLMTraceStatus,
        elapsed_ms: int | None = None,
        token_usage: Mapping[str, int] | None = None,
        parse_error: str = "",
        error_message: str = "",
        validation_errors: tuple[Mapping[str, Any], ...] = (),
    ) -> None:
        if trace_context is None or trace_recorder is None:
            raise LLMTraceRequiredError(LLM_TRACE_REQUIRED_MESSAGE)
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
                parse_error=parse_error,
                error_message=error_message,
                validation_errors=validation_errors,
            )
        except Exception as exc:
            logger.error(
                "Failed to record mandatory LLM interaction trace: error_type={}",
                type(exc).__name__,
            )
            raise LLMTraceRecordingError(
                "mandatory LLM interaction trace could not be persisted"
            ) from exc
    
    @property
    def active(self) -> str:
        """
        Get active model name
        
        Returns:
            Active model name
        
        Example:
            print(f"Using model: {pixelle_video.llm.active}")
        """
        return self._get_config_value("model", "gpt-3.5-turbo")
    
    def __repr__(self) -> str:
        """String representation"""
        model = self.active
        base_url = self._get_config_value("base_url", "default")
        return f"<LLMService model={model!r} provider={_safe_provider_label(base_url)!r}>"


def _validate_llm_call_arguments(
    *,
    prompt: Any,
    temperature: Any,
    max_tokens: Any,
    response_type: Any,
) -> None:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise ValueError("temperature must be a finite number between 0 and 2")
    if not math.isfinite(float(temperature)) or not 0 <= float(temperature) <= 2:
        raise ValueError("temperature must be a finite number between 0 and 2")
    if type(max_tokens) is not int or max_tokens < 1:
        raise ValueError("max_tokens must be a positive integer")
    if response_type is None or response_type is dict:
        return
    if not isinstance(response_type, type) or not issubclass(response_type, BaseModel):
        raise TypeError("response_type must be dict or a Pydantic BaseModel subclass")


def _first_message_content(response: Any) -> Any:
    choices = getattr(response, "choices", None)
    if not isinstance(choices, (list, tuple)) or not choices:
        return None
    message = getattr(choices[0], "message", None)
    if message is None:
        return None
    return getattr(message, "content", None)


def _normalized_sensitive_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _is_sensitive_trace_key(value: Any) -> bool:
    normalized = _normalized_sensitive_key(value)
    return normalized in _SENSITIVE_TRACE_KEYS or normalized.endswith(
        ("_api_key", "_access_key", "_secret_key", "_password")
    )


def _trace_safe_copy(value: Any, *, key: Any = None) -> Any:
    if key is not None and _is_sensitive_trace_key(key):
        return _REDACTED_VALUE
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


def _sanitize_error_message(value: Any) -> str:
    message = str(value or type(value).__name__).strip() or type(value).__name__
    message = _BEARER_TOKEN_RE.sub("Bearer [REDACTED]", message)
    message = _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED_VALUE}",
        message,
    )
    message = _URL_USERINFO_RE.sub(r"\1[REDACTED]@", message)
    if len(message) > _MAX_SAFE_ERROR_CHARS:
        return message[: _MAX_SAFE_ERROR_CHARS - 3] + "..."
    return message


def _safe_exception_summary(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return _trace_parse_error_message(exc)
    return _sanitize_error_message(exc)


def _safe_provider_label(base_url: Any) -> str:
    try:
        parsed = urlparse(str(base_url or ""))
        if not parsed.hostname:
            return "default"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return f"{parsed.scheme or 'https'}://{parsed.hostname}{port}"
    except (TypeError, ValueError):
        return "invalid-provider-url"


def _trace_status_for_structured_exception(exc: Exception) -> LLMTraceStatus:
    if isinstance(exc, ValidationError):
        return LLMTraceStatus.VALIDATION_ERROR
    return LLMTraceStatus.PARSE_ERROR


def _trace_parse_error_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        details = _validation_error_details(exc)
        fields = ", ".join(
            f"{detail['field']}: {detail['message']}"
            for detail in details
        )
        return f"{len(details)} schema validation error(s): {fields}"
    return _sanitize_error_message(exc)


def _validation_error_details(exc: Exception) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(exc, ValidationError):
        return ()
    return tuple(
        {
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "message": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        for error in exc.errors()
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
    if normalized:
        return normalized

    usage_payload = _json_safe_copy(usage)
    if not isinstance(usage_payload, Mapping):
        return None

    for key, value in usage_payload.items():
        if type(value) is int and value >= 0:
            normalized[str(key)] = value
    return normalized or None


def _json_safe_copy(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, SimpleNamespace):
        return {
            key: _json_safe_copy(item)
            for key, item in vars(value).items()
        }
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe_copy(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _json_safe_copy(item)
            for item in value
        ]
    if isinstance(value, type):
        return value.__name__
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
