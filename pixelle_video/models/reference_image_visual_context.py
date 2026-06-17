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

from typing import Any, Literal

from pydantic import BaseModel, Field

REFERENCE_IMAGE_VISUAL_CONTEXT_ARTIFACT_VERSION = "reference_image_visual_context/v1"
ReferenceImageProfileMergeMode = Literal["supplement", "override", "strict"]


class ReferenceImageVisualContext(BaseModel):
    """Prompt-level bridge from reference-image analysis into visual planning."""

    version: str = REFERENCE_IMAGE_VISUAL_CONTEXT_ARTIFACT_VERSION
    enabled: bool = False
    asset: dict[str, Any] = Field(default_factory=dict)
    analysis: dict[str, Any] = Field(default_factory=dict)
    merged_ip_profile: dict[str, Any] | None = None
    supplemental_visual_story_context: dict[str, Any] = Field(default_factory=dict)
    prompt_fallback_hint: str = ""
    merge_mode: ReferenceImageProfileMergeMode = "supplement"
    merge_warnings: list[str] = Field(default_factory=list)
    artifact_relative_path: str | None = None

    def to_trace_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
