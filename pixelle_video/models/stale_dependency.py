from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

ALLOWED_DEPENDENCY_TYPES = {
    "asset_bible",
    "scene_cast",
    "prompt_plan",
    "image_artifact",
    "video_segment",
    "final_video",
}


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class DependencyEdge:
    edge_id: str
    workspace_id: str
    project_id: str
    upstream_type: str
    upstream_id: str
    upstream_version: str
    downstream_type: str
    downstream_id: str
    relation: str
    created_at: str = field(default_factory=utc_timestamp)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "edge_id", _public_id("edge_id", self.edge_id))
        object.__setattr__(self, "workspace_id", _public_id("workspace_id", self.workspace_id))
        object.__setattr__(self, "project_id", _public_id("project_id", self.project_id))
        object.__setattr__(self, "upstream_type", _dependency_type("upstream_type", self.upstream_type))
        object.__setattr__(self, "upstream_id", _public_id("upstream_id", self.upstream_id))
        object.__setattr__(self, "upstream_version", _public_id("upstream_version", self.upstream_version))
        object.__setattr__(self, "downstream_type", _dependency_type("downstream_type", self.downstream_type))
        object.__setattr__(self, "downstream_id", _public_id("downstream_id", self.downstream_id))
        object.__setattr__(self, "relation", _relation("relation", self.relation))
        object.__setattr__(self, "created_at", _required_text("created_at", self.created_at))
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "upstream_type": self.upstream_type,
            "upstream_id": self.upstream_id,
            "upstream_version": self.upstream_version,
            "downstream_type": self.downstream_type,
            "downstream_id": self.downstream_id,
            "relation": self.relation,
            "created_at": self.created_at,
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DependencyEdge:
        _require_mapping("DependencyEdge", payload)
        return cls(
            edge_id=payload.get("edge_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            project_id=payload.get("project_id", ""),
            upstream_type=payload.get("upstream_type", ""),
            upstream_id=payload.get("upstream_id", ""),
            upstream_version=payload.get("upstream_version", ""),
            downstream_type=payload.get("downstream_type", ""),
            downstream_id=payload.get("downstream_id", ""),
            relation=payload.get("relation", ""),
            created_at=payload.get("created_at", ""),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class StaleMark:
    stale_id: str
    workspace_id: str
    target_type: str
    target_id: str
    reason_code: str
    upstream_type: str
    upstream_id: str
    upstream_version: str
    marked_at: str = field(default_factory=utc_timestamp)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "stale_id", _public_id("stale_id", self.stale_id))
        object.__setattr__(self, "workspace_id", _public_id("workspace_id", self.workspace_id))
        object.__setattr__(self, "target_type", _dependency_type("target_type", self.target_type))
        object.__setattr__(self, "target_id", _public_id("target_id", self.target_id))
        object.__setattr__(self, "reason_code", _relation("reason_code", self.reason_code))
        object.__setattr__(self, "upstream_type", _dependency_type("upstream_type", self.upstream_type))
        object.__setattr__(self, "upstream_id", _public_id("upstream_id", self.upstream_id))
        object.__setattr__(self, "upstream_version", _public_id("upstream_version", self.upstream_version))
        object.__setattr__(self, "marked_at", _required_text("marked_at", self.marked_at))
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "stale_id": self.stale_id,
            "workspace_id": self.workspace_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "reason_code": self.reason_code,
            "upstream_type": self.upstream_type,
            "upstream_id": self.upstream_id,
            "upstream_version": self.upstream_version,
            "marked_at": self.marked_at,
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> StaleMark:
        _require_mapping("StaleMark", payload)
        return cls(
            stale_id=payload.get("stale_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            target_type=payload.get("target_type", ""),
            target_id=payload.get("target_id", ""),
            reason_code=payload.get("reason_code", ""),
            upstream_type=payload.get("upstream_type", ""),
            upstream_id=payload.get("upstream_id", ""),
            upstream_version=payload.get("upstream_version", ""),
            marked_at=payload.get("marked_at", ""),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class UpstreamChangeEvent:
    workspace_id: str
    project_id: str
    upstream_type: str
    upstream_id: str
    upstream_version: str
    reason_code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_id", _public_id("workspace_id", self.workspace_id))
        object.__setattr__(self, "project_id", _public_id("project_id", self.project_id))
        object.__setattr__(self, "upstream_type", _dependency_type("upstream_type", self.upstream_type))
        object.__setattr__(self, "upstream_id", _public_id("upstream_id", self.upstream_id))
        object.__setattr__(self, "upstream_version", _public_id("upstream_version", self.upstream_version))
        object.__setattr__(self, "reason_code", _relation("reason_code", self.reason_code))

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "upstream_type": self.upstream_type,
            "upstream_id": self.upstream_id,
            "upstream_version": self.upstream_version,
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> UpstreamChangeEvent:
        _require_mapping("UpstreamChangeEvent", payload)
        return cls(
            workspace_id=payload.get("workspace_id", ""),
            project_id=payload.get("project_id", ""),
            upstream_type=payload.get("upstream_type", ""),
            upstream_id=payload.get("upstream_id", ""),
            upstream_version=payload.get("upstream_version", ""),
            reason_code=payload.get("reason_code", ""),
        )


@dataclass(frozen=True)
class StalePropagationSummary:
    workspace_id: str
    upstream_type: str
    upstream_id: str
    upstream_version: str
    visited_edge_count: int
    stale_created_count: int
    stale_existing_count: int
    marked_target_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_id", _public_id("workspace_id", self.workspace_id))
        object.__setattr__(self, "upstream_type", _dependency_type("upstream_type", self.upstream_type))
        object.__setattr__(self, "upstream_id", _public_id("upstream_id", self.upstream_id))
        object.__setattr__(self, "upstream_version", _public_id("upstream_version", self.upstream_version))
        object.__setattr__(self, "visited_edge_count", _non_negative("visited_edge_count", self.visited_edge_count))
        object.__setattr__(self, "stale_created_count", _non_negative("stale_created_count", self.stale_created_count))
        object.__setattr__(self, "stale_existing_count", _non_negative("stale_existing_count", self.stale_existing_count))
        object.__setattr__(
            self,
            "marked_target_ids",
            tuple(_public_id("marked_target_id", target_id) for target_id in self.marked_target_ids),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "upstream_type": self.upstream_type,
            "upstream_id": self.upstream_id,
            "upstream_version": self.upstream_version,
            "visited_edge_count": self.visited_edge_count,
            "stale_created_count": self.stale_created_count,
            "stale_existing_count": self.stale_existing_count,
            "marked_target_ids": list(self.marked_target_ids),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> StalePropagationSummary:
        _require_mapping("StalePropagationSummary", payload)
        return cls(
            workspace_id=payload.get("workspace_id", ""),
            upstream_type=payload.get("upstream_type", ""),
            upstream_id=payload.get("upstream_id", ""),
            upstream_version=payload.get("upstream_version", ""),
            visited_edge_count=payload.get("visited_edge_count", 0),
            stale_created_count=payload.get("stale_created_count", 0),
            stale_existing_count=payload.get("stale_existing_count", 0),
            marked_target_ids=tuple(payload.get("marked_target_ids") or ()),
        )


def _require_mapping(name: str, payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError(f"{name} payload must be a mapping")


def _required_text(field_name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value.strip()


def _public_id(field_name: str, value: object) -> str:
    text = _required_text(field_name, value)
    lowered = text.lower()
    if (
        ":\\" in text
        or "://" in text
        or "\\" in text
        or "/" in text
        or text.startswith("/")
        or ".." in text
        or lowered.startswith("workflows/")
    ):
        raise ValueError(f"{field_name} must be a public ID, not a path, URL, or workflow path")
    return text


def _dependency_type(field_name: str, value: object) -> str:
    text = _required_text(field_name, value)
    if text not in ALLOWED_DEPENDENCY_TYPES:
        raise ValueError(f"{field_name} must be one of {sorted(ALLOWED_DEPENDENCY_TYPES)}")
    return text


def _relation(field_name: str, value: object) -> str:
    text = _required_text(field_name, value)
    if ":" in text or "/" in text or "\\" in text or ".." in text:
        raise ValueError(f"{field_name} must be a safe relation or reason code")
    return text


def _non_negative(field_name: str, value: object) -> int:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _deep_freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(_json_safe_copy(value))


def _json_safe_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    return deepcopy(dict(value))
