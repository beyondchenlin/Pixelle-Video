from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ArtifactStatus(str, Enum):
    ACTIVE = "active"
    FAILED = "failed"
    ARCHIVED = "archived"


class ArtifactVersionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    workspace_id: str
    artifact_type: str
    frame_id: str
    source_prompt_plan_id: str
    status: ArtifactStatus | str = ArtifactStatus.ACTIVE
    selected_version_id: str | None = None
    candidate_version_ids: tuple[str, ...] = ()
    created_at: str = field(default_factory=_utc_timestamp)
    updated_at: str = field(default_factory=_utc_timestamp)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", _require_non_empty("artifact_id", self.artifact_id))
        object.__setattr__(self, "workspace_id", _require_non_empty("workspace_id", self.workspace_id))
        object.__setattr__(self, "artifact_type", _require_non_empty("artifact_type", self.artifact_type))
        object.__setattr__(self, "frame_id", _require_non_empty("frame_id", self.frame_id))
        object.__setattr__(
            self,
            "source_prompt_plan_id",
            _require_non_empty("source_prompt_plan_id", self.source_prompt_plan_id),
        )
        object.__setattr__(self, "status", ArtifactStatus(self.status))
        object.__setattr__(self, "selected_version_id", _optional_str(self.selected_version_id))
        object.__setattr__(
            self,
            "candidate_version_ids",
            _normalize_id_tuple("candidate_version_ids", self.candidate_version_ids),
        )
        object.__setattr__(self, "created_at", _require_non_empty("created_at", self.created_at))
        object.__setattr__(self, "updated_at", _require_non_empty("updated_at", self.updated_at))
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def select_version(self, version_id: str) -> "Artifact":
        selected_version_id = _require_non_empty("version_id", version_id)
        candidate_version_ids = self.candidate_version_ids
        if selected_version_id not in candidate_version_ids:
            candidate_version_ids = (*candidate_version_ids, selected_version_id)
        return replace(
            self,
            selected_version_id=selected_version_id,
            candidate_version_ids=candidate_version_ids,
            updated_at=_utc_timestamp(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "workspace_id": self.workspace_id,
            "artifact_type": self.artifact_type,
            "frame_id": self.frame_id,
            "source_prompt_plan_id": self.source_prompt_plan_id,
            "status": self.status.value,
            "selected_version_id": self.selected_version_id,
            "candidate_version_ids": list(self.candidate_version_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Artifact":
        if not isinstance(payload, Mapping):
            raise ValueError("Artifact payload must be a mapping")
        return cls(
            artifact_id=payload.get("artifact_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            artifact_type=payload.get("artifact_type", ""),
            frame_id=payload.get("frame_id", ""),
            source_prompt_plan_id=payload.get("source_prompt_plan_id", ""),
            status=payload.get("status", ArtifactStatus.ACTIVE),
            selected_version_id=payload.get("selected_version_id"),
            candidate_version_ids=tuple(payload.get("candidate_version_ids") or ()),
            created_at=payload.get("created_at", ""),
            updated_at=payload.get("updated_at", ""),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class ArtifactVersion:
    version_id: str
    artifact_id: str
    workspace_id: str
    frame_id: str
    source_prompt_plan_id: str
    storage_key: str
    status: ArtifactVersionStatus | str
    provider: str | None = None
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)
    width: int | None = None
    height: int | None = None
    trace_event_id: str | None = None
    created_at: str = field(default_factory=_utc_timestamp)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "version_id", _require_non_empty("version_id", self.version_id))
        object.__setattr__(self, "artifact_id", _require_non_empty("artifact_id", self.artifact_id))
        object.__setattr__(self, "workspace_id", _require_non_empty("workspace_id", self.workspace_id))
        object.__setattr__(self, "frame_id", _require_non_empty("frame_id", self.frame_id))
        object.__setattr__(
            self,
            "source_prompt_plan_id",
            _require_non_empty("source_prompt_plan_id", self.source_prompt_plan_id),
        )
        object.__setattr__(self, "storage_key", _validate_storage_key(self.storage_key))
        object.__setattr__(self, "status", ArtifactVersionStatus(self.status))
        object.__setattr__(self, "provider", _optional_str(self.provider))
        object.__setattr__(self, "provider_metadata", _deep_freeze_mapping(self.provider_metadata))
        object.__setattr__(self, "width", _optional_positive_int("width", self.width))
        object.__setattr__(self, "height", _optional_positive_int("height", self.height))
        object.__setattr__(self, "trace_event_id", _optional_str(self.trace_event_id))
        object.__setattr__(self, "created_at", _require_non_empty("created_at", self.created_at))
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "artifact_id": self.artifact_id,
            "workspace_id": self.workspace_id,
            "frame_id": self.frame_id,
            "source_prompt_plan_id": self.source_prompt_plan_id,
            "storage_key": self.storage_key,
            "status": self.status.value,
            "provider": self.provider,
            "provider_metadata": _json_safe_copy(self.provider_metadata),
            "width": self.width,
            "height": self.height,
            "trace_event_id": self.trace_event_id,
            "created_at": self.created_at,
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactVersion":
        if not isinstance(payload, Mapping):
            raise ValueError("ArtifactVersion payload must be a mapping")
        return cls(
            version_id=payload.get("version_id", ""),
            artifact_id=payload.get("artifact_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            frame_id=payload.get("frame_id", ""),
            source_prompt_plan_id=payload.get("source_prompt_plan_id", ""),
            storage_key=payload.get("storage_key", ""),
            status=payload.get("status", ""),
            provider=payload.get("provider"),
            provider_metadata=payload.get("provider_metadata") or {},
            width=payload.get("width"),
            height=payload.get("height"),
            trace_event_id=payload.get("trace_event_id"),
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


def _optional_positive_int(field_name: str, value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _normalize_id_tuple(field_name: str, value: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list or tuple")
    normalized = tuple(_require_non_empty(field_name, item) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _validate_storage_key(value: Any) -> str:
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
        raise ValueError("metadata fields must be mappings")
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
    "Artifact",
    "ArtifactStatus",
    "ArtifactVersion",
    "ArtifactVersionStatus",
]
