from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

MAX_PAYLOAD_PREVIEW_CHARS = 240


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class LLMTraceStatus(str, Enum):
    SUCCESS = "success"
    PARSE_ERROR = "parse_error"
    VALIDATION_ERROR = "validation_error"
    ERROR = "error"


@dataclass(frozen=True)
class LLMTraceContext:
    workspace_id: str
    task_id: str
    operation: str
    stage: str | None = None
    frame_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_id", _require_non_empty("workspace_id", self.workspace_id))
        object.__setattr__(self, "task_id", _require_non_empty("task_id", self.task_id))
        object.__setattr__(self, "operation", _require_non_empty("operation", self.operation))
        object.__setattr__(self, "stage", _optional_str(self.stage))
        object.__setattr__(self, "frame_id", _optional_str(self.frame_id))
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "task_id": self.task_id,
            "operation": self.operation,
            "stage": self.stage,
            "frame_id": self.frame_id,
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LLMTraceContext":
        if not isinstance(payload, Mapping):
            raise ValueError("LLMTraceContext payload must be a mapping")
        return cls(
            workspace_id=payload.get("workspace_id", ""),
            task_id=payload.get("task_id", ""),
            operation=payload.get("operation", ""),
            stage=payload.get("stage"),
            frame_id=payload.get("frame_id"),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class LLMInteractionTrace:
    trace_id: str
    context: LLMTraceContext
    provider: str
    model: str
    status: LLMTraceStatus
    request_payload_key: str
    request_sha256: str
    request_preview: str
    response_payload_key: str | None = None
    response_sha256: str | None = None
    response_preview: str | None = None
    elapsed_ms: int | None = None
    token_usage: Mapping[str, int] | None = None
    parse_error: str = ""
    error_message: str = ""
    validation_errors: tuple[Mapping[str, Any], ...] = ()
    created_at: str = field(default_factory=_utc_timestamp)

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _require_non_empty("trace_id", self.trace_id))
        if not isinstance(self.context, LLMTraceContext):
            object.__setattr__(self, "context", LLMTraceContext.from_dict(self.context))
        object.__setattr__(self, "provider", _require_non_empty("provider", self.provider))
        object.__setattr__(self, "model", _require_non_empty("model", self.model))
        object.__setattr__(self, "status", LLMTraceStatus(self.status))
        object.__setattr__(
            self,
            "request_payload_key",
            _require_non_empty("request_payload_key", self.request_payload_key),
        )
        object.__setattr__(self, "request_sha256", _require_sha256("request_sha256", self.request_sha256))
        object.__setattr__(self, "request_preview", _bounded_preview(self.request_preview))
        object.__setattr__(self, "response_payload_key", _optional_str(self.response_payload_key))
        object.__setattr__(
            self,
            "response_sha256",
            _optional_sha256("response_sha256", self.response_sha256),
        )
        object.__setattr__(self, "response_preview", _optional_preview(self.response_preview))
        object.__setattr__(self, "elapsed_ms", _optional_non_negative_int("elapsed_ms", self.elapsed_ms))
        object.__setattr__(self, "token_usage", _freeze_token_usage(self.token_usage))
        object.__setattr__(self, "parse_error", str(self.parse_error or ""))
        object.__setattr__(self, "error_message", str(self.error_message or ""))
        object.__setattr__(
            self,
            "validation_errors",
            tuple(_deep_freeze_mapping(error) for error in self.validation_errors),
        )
        object.__setattr__(self, "created_at", _require_non_empty("created_at", self.created_at))

    @classmethod
    def create(
        cls,
        *,
        trace_id: str,
        context: LLMTraceContext,
        provider: str,
        model: str,
        request_payload_key: str,
        request_payload: Mapping[str, Any],
        status: LLMTraceStatus | str,
        response_payload_key: str | None = None,
        response_payload: Mapping[str, Any] | None = None,
        elapsed_ms: int | None = None,
        token_usage: Mapping[str, int] | None = None,
        parse_error: str = "",
        error_message: str = "",
        validation_errors: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = (),
        created_at: str | None = None,
    ) -> "LLMInteractionTrace":
        request_text = _canonical_json(request_payload)
        response_text = (
            _canonical_json(response_payload)
            if response_payload is not None
            else None
        )
        return cls(
            trace_id=trace_id,
            context=context,
            provider=provider,
            model=model,
            status=LLMTraceStatus(status),
            request_payload_key=request_payload_key,
            request_sha256=_sha256_text(request_text),
            request_preview=_bounded_preview(request_text),
            response_payload_key=response_payload_key,
            response_sha256=(
                _sha256_text(response_text)
                if response_text is not None
                else None
            ),
            response_preview=(
                _bounded_preview(response_text)
                if response_text is not None
                else None
            ),
            elapsed_ms=elapsed_ms,
            token_usage=token_usage,
            parse_error=parse_error,
            error_message=error_message,
            validation_errors=tuple(validation_errors),
            created_at=created_at or _utc_timestamp(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "context": self.context.to_dict(),
            "provider": self.provider,
            "model": self.model,
            "status": self.status.value,
            "request_payload_key": self.request_payload_key,
            "request_sha256": self.request_sha256,
            "request_preview": self.request_preview,
            "response_payload_key": self.response_payload_key,
            "response_sha256": self.response_sha256,
            "response_preview": self.response_preview,
            "elapsed_ms": self.elapsed_ms,
            "token_usage": (
                dict(self.token_usage)
                if self.token_usage is not None
                else None
            ),
            "parse_error": self.parse_error,
            "error_message": self.error_message,
            "validation_errors": [
                _json_safe_copy(error)
                for error in self.validation_errors
            ],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LLMInteractionTrace":
        if not isinstance(payload, Mapping):
            raise ValueError("LLMInteractionTrace payload must be a mapping")
        return cls(
            trace_id=payload.get("trace_id", ""),
            context=LLMTraceContext.from_dict(payload.get("context") or {}),
            provider=payload.get("provider", ""),
            model=payload.get("model", ""),
            status=payload.get("status", ""),
            request_payload_key=payload.get("request_payload_key", ""),
            request_sha256=payload.get("request_sha256", ""),
            request_preview=payload.get("request_preview", ""),
            response_payload_key=payload.get("response_payload_key"),
            response_sha256=payload.get("response_sha256"),
            response_preview=payload.get("response_preview"),
            elapsed_ms=payload.get("elapsed_ms"),
            token_usage=payload.get("token_usage"),
            parse_error=payload.get("parse_error", ""),
            error_message=payload.get("error_message", ""),
            validation_errors=tuple(payload.get("validation_errors") or ()),
            created_at=payload.get("created_at", ""),
        )


def _require_non_empty(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional string fields must be strings")
    stripped = value.strip()
    return stripped or None


def _optional_non_negative_int(field_name: str, value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _require_sha256(field_name: str, value: Any) -> str:
    digest = _require_non_empty(field_name, value)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{field_name} must be a lowercase sha256 hex digest")
    return digest


def _optional_sha256(field_name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _require_sha256(field_name, value)


def _canonical_json(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping):
        raise ValueError("raw payload must be a mapping")
    return json.dumps(
        _json_safe_copy(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bounded_preview(value: str) -> str:
    if len(value) <= MAX_PAYLOAD_PREVIEW_CHARS:
        return value
    return value[: MAX_PAYLOAD_PREVIEW_CHARS - 3] + "..."


def _optional_preview(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("preview fields must be strings")
    return _bounded_preview(value)


def _freeze_token_usage(value: Mapping[str, int] | None) -> Mapping[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("token_usage must be a mapping")
    normalized = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError("token_usage keys must be non-empty strings")
        if type(item) is not int or item < 0:
            raise ValueError("token_usage values must be non-negative integers")
        normalized[key] = item
    return MappingProxyType(normalized)


def _deep_freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("metadata and validation errors must be mappings")
    return MappingProxyType({
        str(key): _deep_freeze(item)
        for key, item in value.items()
    })


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _deep_freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return deepcopy(value)


def _json_safe_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_copy(item) for item in value]
    return deepcopy(value)


__all__ = [
    "LLMInteractionTrace",
    "LLMTraceContext",
    "LLMTraceStatus",
    "MAX_PAYLOAD_PREVIEW_CHARS",
]
