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

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ReferenceImageAnalysisMode = Literal["off", "auto", "required"]
ReferenceImageAnalysisStatus = Literal["success", "skipped", "failed"]
REFERENCE_IMAGE_ANALYSIS_ARTIFACT_VERSION = "reference_image_analysis/v1"
REFERENCE_IMAGE_ANALYSIS_PROMPT_VERSION = "reference-image-analysis-prompt/v1"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ReferenceImageAnalysis(BaseModel):
    """Structured visual analysis for prompt-only reference image consistency."""

    subject_summary: str = Field(default="")
    style_summary: str = Field(default="")
    color_atmosphere: str = Field(default="")
    composition_summary: str = Field(default="")
    identity_anchors: list[str] = Field(default_factory=list)
    style_anchors: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)
    prompt_hint_en: str = ""
    prompt_hint_zh: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)


class ReferenceImageAnalysisResult(BaseModel):
    """Task artifact and pipeline-safe wrapper around reference image analysis."""

    version: str = REFERENCE_IMAGE_ANALYSIS_ARTIFACT_VERSION
    status: ReferenceImageAnalysisStatus
    analysis_mode: ReferenceImageAnalysisMode
    image_sha256: str = ""
    vision_model: str = ""
    prompt_version: str = REFERENCE_IMAGE_ANALYSIS_PROMPT_VERSION
    analysis_language: str = ""
    analysis: ReferenceImageAnalysis | None = None
    reason: str = ""
    error: str = ""
    warnings: list[str] = Field(default_factory=list)
    artifact_relative_path: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == "success" and self.analysis is not None

    def to_trace_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        # The analysis itself is structured text only; leave it in the artifact
        # and status payload for observability. No image bytes or user paths live here.
        return payload
