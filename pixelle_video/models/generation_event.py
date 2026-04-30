from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class GenerationEventAction(str, Enum):
    GENERATE = "generate"
    FAIL = "fail"
    SELECT = "select"
    REGENERATE = "regenerate"
    STALE_MARK = "stale_mark"


@dataclass(frozen=True)
class GenerationEvent:
    event_id: str
    workspace_id: str
    action: GenerationEventAction | str
    frame_id: str
    prompt_plan_id: str
    artifact_id: str
    artifact_version_id: str | None = None
    storage_key: str | None = None
    task_id: str | None = None
    llm_trace_id: str | None = None
    error_message: str = ""
    stale_reason: str = ""
    created_at: str = field(default_factory=_utc_timestamp)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _require_non_empty("event_id", self.event_id))
        object.__setattr__(self, "workspace_id", _require_non_empty("workspace_id", self.workspace_id))
        object.__setattr__(self, "action", GenerationEventAction(self.action))
        object.__setattr__(self, "frame_id", _require_non_empty("frame_id", self.frame_id))
        object.__setattr__(self, "prompt_plan_id", _require_non_empty("prompt_plan_id", self.prompt_plan_id))
        object.__setattr__(self, "artifact_id", _require_non_empty("artifact_id", self.artifact_id))
        object.__setattr__(self, "artifact_version_id", _optional_str(self.artifact_version_id))
        object.__setattr__(self, "storage_key", _optional_storage_key(self.storage_key))
        object.__setattr__(self, "task_id", _optional_str(self.task_id))
        object.__setattr__(self, "llm_trace_id", _optional_str(self.llm_trace_id))
        object.__setattr__(self, "error_message", str(self.error_message or ""))
        object.__setattr__(self, "stale_reason", str(self.stale_reason or ""))
        object.__setattr__(self, "created_at", _require_non_empty("created_at", self.created_at))
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "workspace_id": self.workspace_id,
            "action": self.action.value,
            "frame_id": self.frame_id,
            "prompt_plan_id": self.prompt_plan_id,
            "artifact_id": self.artifact_id,
            "artifact_version_id": self.artifact_version_id,
            "storage_key": self.storage_key,
            "task_id": self.task_id,
            "llm_trace_id": self.llm_trace_id,
            "error_message": self.error_message,
            "stale_reason": self.stale_reason,
            "created_at": self.created_at,
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GenerationEvent":
        if not isinstance(payload, Mapping):
            raise ValueError("GenerationEvent payload must be a mapping")
        return cls(
            event_id=payload.get("event_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            action=payload.get("action", ""),
            frame_id=payload.get("frame_id", ""),
            prompt_plan_id=payload.get("prompt_plan_id", ""),
            artifact_id=payload.get("artifact_id", ""),
            artifact_version_id=payload.get("artifact_version_id"),
            storage_key=payload.get("storage_key"),
            task_id=payload.get("task_id"),
            llm_trace_id=payload.get("llm_trace_id"),
            error_message=payload.get("error_message", ""),
            stale_reason=payload.get("stale_reason", ""),
            created_at=payload.get("created_at", ""),
            metadata=payload.get("metadata") or {},
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


def _optional_storage_key(value: Any) -> str | None:
    if value is None:
        return None
    storage_key = _require_non_empty("storage_key", value)
    posix_key = PurePosixPath(storage_key)
    parts = posix_key.parts
    if (
        storage_key != posix_key.as_posix()
        or storage_key.startswith("/")
        or "\\" in storage_key
        or ":" in storage_key
        or "://" in storage_key
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("storage_key must be an object-store key, not a local path")
    return storage_key


def _deep_freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
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
    "GenerationEvent",
    "GenerationEventAction",
]
