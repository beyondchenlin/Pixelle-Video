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

import json
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
from pixelle_video.prompts.structured_output import (
    render_structured_json_object_prompt,
    render_structured_schema_output_prompt,
)
from pixelle_video.services.llm_capabilities import (
    estimate_input_tokens,
    is_json_object_response_format_unsupported_error,
    structured_output_capabilities,
)
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.utils.json_parsing import parse_llm_json_response
from pixelle_video.utils.network_proxy import apply_adaptive_proxy_env

T = TypeVar("T", bound=BaseModel)


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
        self._client: Optional[AsyncOpenAI] = None
    
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
    
    def _create_client(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> AsyncOpenAI:
        """
        Create OpenAI client
        
        Args:
            api_key: API key (optional, uses config if not provided)
            base_url: Base URL (optional, uses config if not provided)
        
        Returns:
            AsyncOpenAI client instance
        """
        # Get API key (priority: parameter > config)
        final_api_key = (
            api_key
            or self._get_config_value("api_key")
            or "dummy-key"  # Ollama doesn't need real key
        )
        
        # Get base URL (priority: parameter > config)
        final_base_url = (
            base_url
            or self._get_config_value("base_url")
        )
        
        # Create client
        # Best practice: keep proxy behavior adaptive for local development.
        # If a loopback proxy env var points to a closed port, disable it for
        # this process so DashScope/OpenAI-compatible providers can be reached directly.
        apply_adaptive_proxy_env(provider_base_url=final_base_url)
        client_kwargs = {"api_key": final_api_key}
        if final_base_url:
            client_kwargs["base_url"] = final_base_url
        
        return AsyncOpenAI(**client_kwargs)
    
    async def __call__(
        self,
        prompt: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
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

        # Create client (new instance each time to support parameter overrides)
        client = self._create_client(api_key=api_key, base_url=base_url)
        
        # Get model (priority: parameter > config)
        final_model = (
            model
            or self._get_config_value("model")
            or "gpt-3.5-turbo"  # Default fallback
        )
        
        logger.debug(f"LLM call: model={final_model}, base_url={client.base_url}, response_type={response_type}")

        # Pre-flight: reject oversized prompts before wasting an API call
        final_base_url = str(client.base_url or "") if client.base_url else None
        capabilities = structured_output_capabilities(
            base_url=final_base_url,
            model=final_model,
        )
        est_tokens = estimate_input_tokens(prompt)
        if est_tokens > capabilities.max_input_tokens:
            raise ValueError(
                f"Estimated input token count ({est_tokens}) exceeds model "
                f"'{final_model}' maximum input tokens "
                f"({capabilities.max_input_tokens}). "
                "Reduce the input length or split into smaller batches."
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
                    await self._record_llm_trace(
                        trace_context=trace_context,
                        trace_recorder=trace_recorder,
                        provider=str(client.base_url or ""),
                        model=final_model,
                        request_payload=request_payload,
                        response_payload=None,
                        status=LLMTraceStatus.ERROR,
                        elapsed_ms=_elapsed_ms(started_at),
                        error_message=str(exc),
                    )
                    raise
                
                result = response.choices[0].message.content
                logger.debug(f"LLM response length: {len(result)} chars")
                response_payload = self._build_response_payload(
                    response=response,
                    content=result,
                )
                await self._record_llm_trace(
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                    provider=str(client.base_url or ""),
                    model=final_model,
                    request_payload=request_payload,
                    response_payload=response_payload,
                    status=LLMTraceStatus.SUCCESS,
                    elapsed_ms=_elapsed_ms(started_at),
                    token_usage=_extract_token_usage(response),
                )
                
                return result
        except Exception as e:
            logger.error(f"LLM call error (model={final_model}, base_url={client.base_url}): {e}")
            raise
    
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
            await self._record_llm_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=str(client.base_url or ""),
                model=model,
                request_payload=request_payload,
                response_payload=None,
                status=LLMTraceStatus.ERROR,
                elapsed_ms=_elapsed_ms(started_at),
                error_message=str(exc),
            )
            raise
        message = response.choices[0].message
        response_payload = self._build_response_payload(
            response=response,
            content=getattr(message, "content", None) or "",
        )
        elapsed_ms = _elapsed_ms(started_at)
        token_usage = _extract_token_usage(response)
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

        content = getattr(message, "content", None) or ""
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
                    parse_error=str(exc),
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
            f"Structured output response from model {model} did not include parsed content"
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
        raise ValueError(error_message)

    async def _call_with_dict_output(
        self,
        client: AsyncOpenAI,
        model: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
        trace_context: Optional[LLMTraceContext] = None,
        trace_recorder: Optional[LLMInteractionRecorder] = None,
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

        capabilities = structured_output_capabilities(
            base_url=str(client.base_url or ""),
            model=model,
        )

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

        request_payload = _json_safe_copy(request_kwargs)

        started_at = perf_counter()
        try:
            response = await client.chat.completions.create(**request_kwargs)
        except Exception as exc:
            await self._record_llm_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=str(client.base_url or ""),
                model=model,
                request_payload=request_payload,
                response_payload=None,
                status=LLMTraceStatus.ERROR,
                elapsed_ms=_elapsed_ms(started_at),
                error_message=str(exc),
            )
            raise

        content = "{}"
        if response.choices:
            content = response.choices[0].message.content or "{}"
        else:
            logger.warning("LLM response has no choices; using empty dict fallback: model={}", model)

        elapsed_ms = _elapsed_ms(started_at)
        token_usage = _extract_token_usage(response)

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
                    "retrying without response_format: model={} base_url={}",
                    model, client.base_url,
                )
                retry_prompt = enhanced_prompt + (
                    "\n\n## CRITICAL: Return a JSON Object, NOT an Array\n"
                    "You MUST return a JSON object with a named key wrapping your data. "
                    "DO NOT return a raw JSON array."
                )
                retry_request_kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": [{"role": "user", "content": retry_prompt}],
                    "temperature": temperature,
                    **kwargs,
                }
                retry_request_kwargs["max_tokens"] = max_tokens
                retry_response = await client.chat.completions.create(**retry_request_kwargs)
                if retry_response.choices:
                    retry_content = retry_response.choices[0].message.content or "{}"
                else:
                    retry_content = "{}"
                    logger.warning("Retry response has no choices; using empty dict: model={}", model)
                parsed = parse_llm_json_response(
                    retry_content,
                    allow_code_fence=True,
                    allow_embedded_json=False,
                )
                if isinstance(parsed, dict):
                    content = retry_content
                    response = retry_response
                elif isinstance(parsed, list):
                    parsed = {"data": parsed}
                    content = retry_content
                    response = retry_response
                    logger.warning(
                        "Retry also returned array; wrapping in dict as last resort: model={}",
                        model,
                    )
                else:
                    raise ValueError(f"Expected JSON object, got {type(parsed).__name__} (retry)")
            else:
                raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")
        except Exception as exc:
            await self._record_llm_trace(
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                provider=str(client.base_url or ""),
                model=model,
                request_payload=request_payload,
                response_payload=self._build_response_payload(response=response, content=content),
                status=LLMTraceStatus.ERROR,
                elapsed_ms=elapsed_ms,
                token_usage=token_usage,
                parse_error=str(exc),
            )
            raise

        response_payload = self._build_response_payload(response=response, content=content)
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
        capabilities = structured_output_capabilities(
            base_url=str(client.base_url or ""),
            model=model,
        )

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
                    await self._record_llm_trace(
                        trace_context=trace_context,
                        trace_recorder=trace_recorder,
                        provider=str(client.base_url or ""),
                        model=model,
                        request_payload=self._build_request_payload_from_kwargs(trace_request_kwargs),
                        response_payload=None,
                        status=LLMTraceStatus.ERROR,
                        elapsed_ms=_elapsed_ms(started_at),
                        error_message=str(exc),
                    )
                    raise
                await self._record_llm_trace(
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                    provider=str(client.base_url or ""),
                    model=model,
                    request_payload=self._build_request_payload_from_kwargs(trace_request_kwargs),
                    response_payload=None,
                    status=LLMTraceStatus.ERROR,
                    elapsed_ms=_elapsed_ms(started_at),
                    error_message=str(exc),
                )
                logger.warning(
                    "Provider rejected JSON mode for structured output; retrying with prompt-only schema: {}",
                    exc,
                )
                trace_request_kwargs = {**request_kwargs, "max_tokens": max_tokens}
                started_at = perf_counter()
                try:
                    response = await client.chat.completions.create(**trace_request_kwargs)
                except Exception as retry_exc:
                    await self._record_llm_trace(
                        trace_context=trace_context,
                        trace_recorder=trace_recorder,
                        provider=str(client.base_url or ""),
                        model=model,
                        request_payload=self._build_request_payload_from_kwargs(trace_request_kwargs),
                        response_payload=None,
                        status=LLMTraceStatus.ERROR,
                        elapsed_ms=_elapsed_ms(started_at),
                        error_message=str(retry_exc),
                    )
                    raise
        else:
            trace_request_kwargs = {**request_kwargs, "max_tokens": max_tokens}
            try:
                response = await client.chat.completions.create(**trace_request_kwargs)
            except Exception as exc:
                await self._record_llm_trace(
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                    provider=str(client.base_url or ""),
                    model=model,
                    request_payload=self._build_request_payload_from_kwargs(trace_request_kwargs),
                    response_payload=None,
                    status=LLMTraceStatus.ERROR,
                    elapsed_ms=_elapsed_ms(started_at),
                    error_message=str(exc),
                )
                raise
        content = response.choices[0].message.content
        elapsed_ms = _elapsed_ms(started_at)
        token_usage = _extract_token_usage(response)

        logger.debug(f"Structured output response length: {len(content)} chars")

        request_payload = self._build_request_payload_from_kwargs(trace_request_kwargs)
        response_payload = self._build_response_payload(response=response, content=content)
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
                parse_error=str(exc),
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
    
    def _render_structured_schema_prompt(self, *, prompt: str, response_type: Type[T]):
        try:
            schema = response_type.model_json_schema()
            schema_str = json.dumps(schema, indent=2, ensure_ascii=False)
            return render_structured_schema_output_prompt(
                prompt=prompt,
                response_type_name=response_type.__name__,
                schema_json=schema_str,
            )
        except Exception as e:
            logger.warning(f"Failed to generate JSON schema: {e}")
            return render_structured_json_object_prompt(prompt)

    def _structured_response_format_payload(self, response_type: Type[T]) -> dict[str, Any]:
        try:
            schema = response_type.model_json_schema()
        except Exception as exc:
            logger.warning(f"Failed to generate native structured output schema: {exc}")
            schema = {}
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
        logger.debug(f"Parsing LLM response as {response_type.__name__}, content length: {len(content)} chars")
        
        try:
            data = parse_llm_json_response(
                content,
                allow_code_fence=True,
                allow_embedded_json=False,
            )
            return response_type.model_validate(data)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error when parsing LLM response: {e}")
            # 限制日志长度，避免大响应导致日志过大
            max_log_len = 2000
            if len(content) <= max_log_len:
                logger.error(f"Raw response content: {content!r}")
            else:
                logger.error(f"Raw response content (first {max_log_len} chars): {content[:max_log_len]!r}")
                logger.error(f"... (truncated, total length: {len(content)} chars)")
            raise ValueError(f"Failed to parse LLM response as {response_type.__name__}: {content[:200]}...") from e
        except ValidationError as e:
            logger.error(f"Schema validation error when parsing LLM response as {response_type.__name__}: {e}")
            max_log_len = 2000
            if len(content) <= max_log_len:
                logger.error(f"Raw response content: {content!r}")
            else:
                logger.error(f"Raw response content (first {max_log_len} chars): {content[:max_log_len]!r}")
                logger.error(f"... (truncated, total length: {len(content)} chars)")
            raise
        except Exception as e:
            logger.error(f"Unexpected error when parsing LLM response: {type(e).__name__}: {e}")
            max_log_len = 2000
            if len(content) <= max_log_len:
                logger.error(f"Raw response content: {content!r}")
            else:
                logger.error(f"Raw response content (first {max_log_len} chars): {content[:max_log_len]!r}")
                logger.error(f"... (truncated, total length: {len(content)} chars)")
            raise ValueError(f"Failed to parse LLM response as {response_type.__name__}: {content[:200]}...") from e

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
            payload["extra_parameters"] = _json_safe_copy(extra_parameters)
        return payload

    def _build_request_payload_from_kwargs(self, request_kwargs: Mapping[str, Any]) -> dict[str, Any]:
        return _json_safe_copy(request_kwargs)

    def _build_response_payload(self, *, response: Any, content: str) -> dict[str, Any]:
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
                provider=provider,
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
            # Observability must not become a single point of failure for generation.
            # Broken local trace storage is quarantined by the repository layer;
            # remaining recorder failures are logged and generation continues.
            logger.warning(
                "Failed to record LLM interaction trace; generation will continue: %s",
                exc,
            )
            return
    
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
        return f"<LLMService model={model!r} base_url={base_url!r}>"


def _trace_status_for_structured_exception(exc: Exception) -> LLMTraceStatus:
    if isinstance(exc, ValidationError):
        return LLMTraceStatus.VALIDATION_ERROR
    return LLMTraceStatus.PARSE_ERROR


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
