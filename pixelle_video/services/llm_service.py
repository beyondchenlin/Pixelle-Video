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
from types import SimpleNamespace
from typing import Any, Optional, Type, TypeVar, Union
from urllib.parse import urlparse

from loguru import logger
from openai import AsyncOpenAI, BadRequestError
from pydantic import BaseModel, ValidationError

from pixelle_video.models.llm_interaction_trace import LLMTraceContext, LLMTraceStatus
from pixelle_video.services.llm_capabilities import (
    is_json_object_response_format_unsupported_error,
    structured_output_capabilities,
)
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.utils.json_parsing import parse_llm_json_response

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
        # Direct call
        answer = await pixelle_video.llm("Explain atomic habits")
        
        # With parameters
        answer = await pixelle_video.llm(
            prompt="Explain atomic habits in 3 sentences",
            temperature=0.7,
            max_tokens=2000
        )
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
        response_type: Optional[Type[T]] = None,
        trace_context: Optional[LLMTraceContext] = None,
        trace_recorder: Optional[LLMInteractionRecorder] = None,
        **kwargs
    ) -> Union[str, T]:
        """
        Generate text using LLM
        
        Args:
            prompt: The prompt to generate from
            api_key: API key (optional, uses config if not provided)
            base_url: Base URL (optional, uses config if not provided)
            model: Model name (optional, uses config if not provided)
            temperature: Sampling temperature (0.0-2.0). Lower is more deterministic.
            max_tokens: Maximum tokens to generate
            response_type: Optional Pydantic model class for structured output.
                          If provided, returns parsed model instance instead of string.
            **kwargs: Additional provider-specific parameters
        
        Returns:
            Generated text (str) or parsed Pydantic model instance (if response_type provided)
        
        Examples:
            # Basic text generation
            answer = await pixelle_video.llm("Explain atomic habits")
            
            # Structured output with Pydantic model
            class MovieReview(BaseModel):
                title: str
                rating: int
                summary: str
            
            review = await pixelle_video.llm(
                prompt="Review the movie Inception",
                response_type=MovieReview
            )
            print(review.title)  # Structured access
        """
        # Create client (new instance each time to support parameter overrides)
        client = self._create_client(api_key=api_key, base_url=base_url)
        
        # Get model (priority: parameter > config)
        final_model = (
            model
            or self._get_config_value("model")
            or "gpt-3.5-turbo"  # Default fallback
        )
        
        logger.debug(f"LLM call: model={final_model}, base_url={client.base_url}, response_type={response_type}")
        
        try:
            if response_type is not None:
                # Structured output mode
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
                response = await client.chat.completions.create(
                    model=final_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs
                )
                
                result = response.choices[0].message.content
                logger.debug(f"LLM response length: {len(result)} chars")
                await self._record_llm_trace(
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                    provider=str(client.base_url or ""),
                    model=final_model,
                    request_payload=request_payload,
                    response_payload=self._build_response_payload(
                        response=response,
                        content=result,
                    ),
                    status=LLMTraceStatus.SUCCESS,
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
            response_format=response_type.__name__,
            extra_parameters=kwargs,
        )
        response = await client.beta.chat.completions.parse(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format=response_type,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        message = response.choices[0].message
        response_payload = self._build_response_payload(
            response=response,
            content=getattr(message, "content", None) or "",
        )
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
            )
            return parsed

        refusal = getattr(message, "refusal", None)
        if refusal:
            raise ValueError(f"Structured output request refused by model: {refusal}")

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
            )
            return parsed_from_content

        raise ValueError(
            f"Structured output response from model {model} did not include parsed content"
        )

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
        json_schema_instruction = self._get_json_schema_instruction(response_type)
        enhanced_prompt = f"{prompt}\n\n{json_schema_instruction}"
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

        if capabilities.supports_json_object_response_format:
            try:
                response = await client.chat.completions.create(**json_mode_kwargs)
                trace_request_kwargs = json_mode_kwargs
            except (BadRequestError, TypeError) as exc:
                if (
                    not capabilities.retry_prompt_schema_when_json_object_unsupported
                    or not is_json_object_response_format_unsupported_error(exc)
                ):
                    raise
                logger.warning(
                    "Provider rejected JSON mode for structured output; retrying with prompt-only schema: {}",
                    exc,
                )
                response = await client.chat.completions.create(
                    **request_kwargs,
                    max_tokens=max_tokens,
                )
                trace_request_kwargs = {**request_kwargs, "max_tokens": max_tokens}
        else:
            response = await client.chat.completions.create(
                **request_kwargs,
                max_tokens=max_tokens,
            )
            trace_request_kwargs = {**request_kwargs, "max_tokens": max_tokens}
        content = response.choices[0].message.content

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
        )
        return parsed
    
    def _get_json_schema_instruction(self, response_type: Type[T]) -> str:
        """
        Generate JSON schema instruction for LLM fallback mode
        
        Args:
            response_type: Pydantic model class
        
        Returns:
            Formatted instruction string with JSON schema
        """
        try:
            # Get JSON schema from Pydantic model
            schema = response_type.model_json_schema()
            schema_str = json.dumps(schema, indent=2, ensure_ascii=False)
            
            return f"""## IMPORTANT: JSON Output Format Required
You MUST respond with ONLY a valid JSON object (no markdown, no extra text).
The JSON must strictly follow this schema:

```json
{schema_str}
```

Output ONLY the JSON object, nothing else."""
        except Exception as e:
            logger.warning(f"Failed to generate JSON schema: {e}")
            return """## IMPORTANT: JSON Output Format Required
You MUST respond with ONLY a valid JSON object (no markdown, no extra text)."""
    
    def _parse_response_as_model(self, content: str, response_type: Type[T]) -> T:
        """
        Parse LLM response content as Pydantic model
        
        Args:
            content: Raw LLM response text
            response_type: Target Pydantic model class
        
        Returns:
            Parsed model instance
        """
        try:
            data = parse_llm_json_response(
                content,
                allow_code_fence=True,
                allow_embedded_json=False,
            )
            return response_type.model_validate(data)
        except json.JSONDecodeError:
            pass
        
        raise ValueError(f"Failed to parse LLM response as {response_type.__name__}: {content[:200]}...")

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
        parse_error: str = "",
        validation_errors: tuple[Mapping[str, Any], ...] = (),
    ) -> None:
        if trace_context is None or trace_recorder is None:
            return
        try:
            await trace_recorder.record_interaction(
                context=trace_context,
                provider=provider,
                model=model,
                request_payload=request_payload,
                response_payload=response_payload,
                status=status,
                parse_error=parse_error,
                validation_errors=validation_errors,
            )
        except Exception as exc:
            logger.warning("Failed to record LLM interaction trace: {}", exc)
    
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
