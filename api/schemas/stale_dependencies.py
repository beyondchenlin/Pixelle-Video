from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.schemas.asset_bible import reject_unsafe_public_metadata
from api.schemas.storyboard_workbench import validate_public_reference_id


class StaleMarkPayloadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stale_id: str
    workspace_id: str
    project_id: str
    target_type: str
    target_id: str
    reason_code: str
    upstream_type: str
    upstream_id: str
    upstream_version: str
    marked_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "stale_id",
        "workspace_id",
        "project_id",
        "target_type",
        "target_id",
        "reason_code",
        "upstream_type",
        "upstream_id",
        "upstream_version",
    )
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_unsafe_public_metadata("metadata", value)
        return value


class StaleUpstreamRefResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upstream_type: str
    upstream_id: str
    upstream_version: str
    reason_code: str
    source_edge_id: str | None = None
    via_relation: str | None = None

    @field_validator(
        "upstream_type",
        "upstream_id",
        "upstream_version",
        "reason_code",
        "source_edge_id",
        "via_relation",
    )
    @classmethod
    def validate_optional_ids(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return validate_public_reference_id(info.field_name, value)


class TargetStaleSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    project_id: str
    target_type: str
    target_id: str
    is_stale: bool
    stale_marks: list[StaleMarkPayloadResponse] = Field(default_factory=list)
    upstream_refs: list[StaleUpstreamRefResponse] = Field(default_factory=list)
    primary_reasons: list[str] = Field(default_factory=list)

    @field_validator("workspace_id", "project_id", "target_type", "target_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("primary_reasons")
    @classmethod
    def validate_primary_reasons(cls, value: list[str]) -> list[str]:
        return [
            validate_public_reference_id("primary_reasons", item)
            for item in value
        ]


class TargetStaleSummaryApiResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    stale_summary: TargetStaleSummaryResponse


class DependencyEdgePayloadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_id: str
    workspace_id: str
    project_id: str
    upstream_type: str
    upstream_id: str
    upstream_version: str
    downstream_type: str
    downstream_id: str
    relation: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "edge_id",
        "workspace_id",
        "project_id",
        "upstream_type",
        "upstream_id",
        "upstream_version",
        "downstream_type",
        "downstream_id",
        "relation",
    )
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_unsafe_public_metadata("metadata", value)
        return value


class DownstreamRefResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    downstream_type: str
    downstream_id: str
    relation: str
    upstream_version: str

    @field_validator("downstream_type", "downstream_id", "relation", "upstream_version")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)


class UpstreamDownstreamSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    project_id: str
    upstream_type: str
    upstream_id: str
    dependency_edges: list[DependencyEdgePayloadResponse] = Field(default_factory=list)
    downstream_refs: list[DownstreamRefResponse] = Field(default_factory=list)

    @field_validator("workspace_id", "project_id", "upstream_type", "upstream_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)


class UpstreamDownstreamApiResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    downstream: UpstreamDownstreamSummaryResponse


__all__ = [
    "DependencyEdgePayloadResponse",
    "DownstreamRefResponse",
    "StaleMarkPayloadResponse",
    "StaleUpstreamRefResponse",
    "TargetStaleSummaryApiResponse",
    "TargetStaleSummaryResponse",
    "UpstreamDownstreamApiResponse",
    "UpstreamDownstreamSummaryResponse",
]
