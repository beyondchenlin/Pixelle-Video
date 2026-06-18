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

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pixelle_video.services.resource_resolver import RESOURCE_ID_PATTERN

ReferenceImageAnalysisModeRequest = Literal["off", "auto", "required"]
ReferenceImageWorkflowInjectionModeRequest = Literal["off", "auto", "required"]
ReferenceImageProfileMergeModeRequest = Literal["supplement", "override", "strict"]


class ReferenceImageInputRequest(BaseModel):
    """Public reference-image selector for video generation.

    The public API intentionally accepts only upload/artifact identifiers. It
    does not accept server-local paths, URLs, or base64 payloads.
    """

    model_config = ConfigDict(extra="forbid")

    upload_id: str | None = Field(
        None,
        description="Reference image upload ID returned by /api/reference-images/uploads.",
    )
    artifact_id: str | None = Field(
        None,
        description="Reference image artifact ID returned by /api/reference-images/uploads.",
    )
    analysis_mode: ReferenceImageAnalysisModeRequest | None = Field(
        None,
        description="Reference image Vision analysis mode for this generation.",
    )
    workflow_injection_mode: ReferenceImageWorkflowInjectionModeRequest | None = Field(
        None,
        description="Reference image physical workflow injection mode for this generation.",
    )
    profile_merge_mode: ReferenceImageProfileMergeModeRequest | None = Field(
        None,
        description="How reference-image analysis supplements runtime IP/profile context.",
    )

    @model_validator(mode="after")
    def validate_selector(self) -> "ReferenceImageInputRequest":
        if self.upload_id is not None:
            self.upload_id = _validate_public_reference_id("reference_image.upload_id", self.upload_id)
        if self.artifact_id is not None:
            self.artifact_id = _validate_public_reference_id("reference_image.artifact_id", self.artifact_id)
        count = sum(1 for value in (self.upload_id, self.artifact_id) if value)
        if count != 1:
            raise ValueError("reference_image must include exactly one of upload_id or artifact_id")
        return self


class ReferenceImageUploadResponse(BaseModel):
    success: bool = True
    upload_id: str
    artifact_id: str
    sha256: str
    mime_type: str
    width: int
    height: int
    byte_size: int
    original_display_name: str


def _validate_public_reference_id(field_name: str, value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not RESOURCE_ID_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a public reference image ID")
    return value
