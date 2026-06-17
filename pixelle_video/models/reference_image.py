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

"""
Reference image data models.

The runtime keeps absolute task-local paths for execution, but persisted trace
payloads should only include relative paths and immutable image summaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ReferenceImageAsset:
    """Task-local reference image asset metadata."""

    source_kind: str
    original_display_name: str
    task_asset_path: str
    task_asset_relative_path: str
    vision_asset_path: str | None
    vision_asset_relative_path: str | None
    workflow_asset_path: str
    workflow_asset_relative_path: str
    sha256: str
    mime_type: str
    width: int
    height: int
    byte_size: int
    normalized_width: int | None = None
    normalized_height: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_trace_dict(self) -> dict[str, Any]:
        """Return a trace-safe representation without user-local absolute paths."""

        return {
            "sha256": self.sha256,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "byte_size": self.byte_size,
            "task_asset_relative_path": self.task_asset_relative_path,
            "vision_asset_relative_path": self.vision_asset_relative_path,
            "workflow_asset_relative_path": self.workflow_asset_relative_path,
            "source_kind": self.source_kind,
        }

    def to_asset_json(self) -> dict[str, Any]:
        """Return task artifact metadata safe to persist under the task directory."""

        return {
            "version": "reference_image_asset/v1",
            "original_display_name": self.original_display_name,
            "asset": self.to_trace_dict(),
            "metadata": dict(self.metadata),
        }
