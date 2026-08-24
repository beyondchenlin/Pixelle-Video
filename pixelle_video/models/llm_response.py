from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class LLMServiceError(Exception):
    """Base exception for failures at the LLM provider boundary."""


class LLMProviderRequestError(LLMServiceError, RuntimeError):
    """Raised when the provider request fails before a usable response exists."""


class LLMResponseContractError(LLMServiceError, ValueError):
    """Raised when a provider response violates the chat completion contract."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class LLMEmptyResponseError(LLMResponseContractError):
    """Raised when a response has no non-blank text for a text-required call."""


class LLMResponseShapeError(LLMResponseContractError):
    """Raised when choices or message fields do not match the provider contract."""


@dataclass(frozen=True)
class NormalizedChatCompletion:
    """Validated first-choice view of an OpenAI-compatible chat completion."""

    message: Any
    content: str | None
    choice_count: int
    finish_reason: str | None
    has_tool_calls: bool

    def require_content(self, *, model: str) -> str:
        """Return provider text verbatim, including an empty or whitespace-only string."""

        if self.content is None:
            reason = "tool_call_only" if self.has_tool_calls else "content_missing"
            raise LLMEmptyResponseError(
                _empty_response_message(model=model, reason=reason, finish_reason=self.finish_reason),
                reason=reason,
            )
        return self.content

    def require_text(self, *, model: str) -> str:
        content = self.require_content(model=model)
        if not content.strip():
            raise LLMEmptyResponseError(
                _empty_response_message(
                    model=model,
                    reason="content_blank",
                    finish_reason=self.finish_reason,
                ),
                reason="content_blank",
            )
        return content


def normalize_chat_completion(response: Any, *, model: str) -> NormalizedChatCompletion:
    """Validate the common chat response shape without requiring textual content."""

    choices = getattr(response, "choices", None)
    if not isinstance(choices, (list, tuple)):
        raise LLMResponseShapeError(
            f"LLM response from model {model!r} did not include a choices sequence",
            reason="choices_missing",
        )
    if not choices:
        raise LLMEmptyResponseError(
            f"LLM response from model {model!r} did not include any choices",
            reason="choices_empty",
        )

    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    if message is None:
        raise LLMResponseShapeError(
            f"LLM response from model {model!r} did not include a first-choice message",
            reason="message_missing",
        )

    content = getattr(message, "content", None)
    if content is not None and not isinstance(content, str):
        raise LLMResponseShapeError(
            f"LLM response from model {model!r} returned non-text message content",
            reason="content_type_invalid",
        )

    finish_reason = getattr(first_choice, "finish_reason", None)
    if finish_reason is not None:
        finish_reason = str(finish_reason).strip() or None
    tool_calls = getattr(message, "tool_calls", None)
    return NormalizedChatCompletion(
        message=message,
        content=content,
        choice_count=len(choices),
        finish_reason=finish_reason,
        has_tool_calls=bool(tool_calls),
    )


def _empty_response_message(*, model: str, reason: str, finish_reason: str | None) -> str:
    suffix = f"; finish_reason={finish_reason}" if finish_reason else ""
    return f"LLM response from model {model!r} did not include usable text ({reason}){suffix}"


__all__ = [
    "LLMEmptyResponseError",
    "LLMProviderRequestError",
    "LLMResponseContractError",
    "LLMResponseShapeError",
    "LLMServiceError",
    "NormalizedChatCompletion",
    "normalize_chat_completion",
]
