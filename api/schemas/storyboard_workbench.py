from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from pixelle_video.services.public_ids import validate_public_reference_id


class StoryboardImageCandidateResponse(BaseModel):
    artifact_id: str
    version_id: str
    frame_id: str
    prompt_plan_id: str
    storage_key: str
    status: str
    provider: str | None = None
    url: str | None = None
    width: int | None = None
    height: int | None = None
    trace_event_id: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoryboardImageCandidateListResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    workspace_id: str
    storyboard_id: str
    frame_id: str
    artifact_id: str
    candidates: list[StoryboardImageCandidateResponse] = Field(default_factory=list)


class StoryboardWorkbenchCapabilitiesResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    can_regenerate_frame_image: bool
    regenerate_unavailable_reason: str | None = None


class SelectStoryboardImageRequest(BaseModel):
    workspace_id: str
    artifact_id: str
    version_id: str
    actor_id: str | None = None
    allow_locked: bool = False

    @field_validator("workspace_id", "artifact_id", "version_id")
    @classmethod
    def validate_resource_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)


class StoryboardFrameWorkbenchStateResponse(BaseModel):
    frame_id: str
    prompt_plan_id: str | None = None
    selected_image_artifact_id: str | None = None
    selected_image_version_id: str | None = None
    candidate_image_version_ids: list[str] = Field(default_factory=list)
    lock_policy: str
    stale_flags: list[str] = Field(default_factory=list)
    last_generation_job_id: str | None = None


class SelectStoryboardImageResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    workspace_id: str
    storyboard_id: str
    frame_id: str
    state: StoryboardFrameWorkbenchStateResponse


class RegenerateStoryboardFrameImageRequest(BaseModel):
    workspace_id: str
    artifact_id: str
    provider: str | None = None
    model: str | None = None

    @field_validator("workspace_id", "artifact_id")
    @classmethod
    def validate_resource_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)


class RegenerateStoryboardFrameImageResponse(BaseModel):
    success: bool = True
    message: str = "Frame image regeneration task created"
    workspace_id: str
    storyboard_id: str
    frame_id: str
    artifact_id: str
    task_id: str
    task_type: str
    created: bool
    reused_reason: str | None = None
    generation_fingerprint: str


__all__ = [
    "RegenerateStoryboardFrameImageRequest",
    "RegenerateStoryboardFrameImageResponse",
    "SelectStoryboardImageRequest",
    "SelectStoryboardImageResponse",
    "StoryboardFrameWorkbenchStateResponse",
    "StoryboardWorkbenchCapabilitiesResponse",
    "StoryboardImageCandidateListResponse",
    "StoryboardImageCandidateResponse",
    "validate_public_reference_id",
]
