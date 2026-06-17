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

REFERENCE_IMAGE_WORKFLOW_BINDING_VERSION = "reference_image_workflow_binding/v1"
ReferenceImageWorkflowInjectionMode = Literal["off", "auto", "required"]
ReferenceImageWorkflowBindingStatus = Literal["injected", "skipped", "failed"]


class ReferenceImageWorkflowBinding(BaseModel):
    """Trace-safe workflow reference-image binding result."""

    version: str = REFERENCE_IMAGE_WORKFLOW_BINDING_VERSION
    status: ReferenceImageWorkflowBindingStatus
    injection_mode: ReferenceImageWorkflowInjectionMode
    workflow_key: str = ""
    media_type: str = ""
    injected_params: dict[str, str] = Field(default_factory=dict)
    workflow_param_trace_values: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    error: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)

    @property
    def injected(self) -> bool:
        return self.status == "injected" and bool(self.injected_params)

    def to_trace_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("injected_params", None)
        return payload
