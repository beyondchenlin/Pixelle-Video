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
Workflow capability inspection helpers.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from comfykit.comfyui.workflow_parser import WorkflowParser


@dataclass(frozen=True)
class WorkflowCapabilities:
    supports_negative_prompt: bool = False


def infer_media_domain_from_workflow(workflow: str | None) -> str:
    normalized = (workflow or "").strip().lower()
    filename = Path(normalized).name
    if filename.startswith("video_") or "/video_" in normalized:
        return "video"
    return "image"


def get_workflow_capabilities(workflow_info: dict[str, Any]) -> WorkflowCapabilities:
    if workflow_info["source"] == "selfhost":
        metadata = WorkflowParser().parse_workflow_file(str(workflow_info["path"]))
        return WorkflowCapabilities(
            supports_negative_prompt="negative_prompt" in metadata.params
        )

    wrapper = json.loads(Path(workflow_info["path"]).read_text(encoding="utf-8"))
    declared = (
        wrapper.get("declared_params")
        or wrapper.get("params")
        or wrapper.get("inputs")
        or {}
    )
    return WorkflowCapabilities(
        supports_negative_prompt=bool(declared.get("negative_prompt"))
    )


def get_media_workflow_capabilities(
    media_service,
    workflow: str | None,
    media_type: str | None = None,
) -> WorkflowCapabilities:
    workflow_domain = media_type or infer_media_domain_from_workflow(workflow)
    workflow_info = media_service._resolve_workflow(
        workflow=workflow,
        workflow_domain=workflow_domain,
    )
    return get_workflow_capabilities(workflow_info)
