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
from typing import Any, Literal

from comfykit.comfyui.workflow_parser import WorkflowParser

LocalMemoryProfile = Literal["standard", "high"]

_GGUF_LOADER_CLASS_TYPES = frozenset(
    {
        "UnetLoaderGGUF",
        "CLIPLoaderGGUF",
        "DualCLIPLoaderGGUF",
    }
)


@dataclass(frozen=True)
class WorkflowCapabilities:
    supports_negative_prompt: bool = False
    uses_gguf_loaders: bool = False
    local_memory_profile: LocalMemoryProfile = "standard"
    prefers_isolated_local_execution: bool = False


def infer_media_domain_from_workflow(workflow: str | None) -> str:
    normalized = (workflow or "").strip().lower()
    filename = Path(normalized).name
    if filename.startswith("video_") or "/video_" in normalized:
        return "video"
    return "image"


def _workflow_class_types(workflow_path: str | Path) -> set[str]:
    workflow = json.loads(Path(workflow_path).read_text(encoding="utf-8"))
    if not isinstance(workflow, dict):
        return set()

    return {
        str(node.get("class_type"))
        for node in workflow.values()
        if isinstance(node, dict) and node.get("class_type")
    }


def _build_capabilities(
    *,
    supports_negative_prompt: bool,
    class_types: set[str] | None = None,
) -> WorkflowCapabilities:
    resolved_class_types = class_types or set()
    uses_gguf_loaders = bool(resolved_class_types & _GGUF_LOADER_CLASS_TYPES)
    local_memory_profile: LocalMemoryProfile = "high" if uses_gguf_loaders else "standard"
    return WorkflowCapabilities(
        supports_negative_prompt=supports_negative_prompt,
        uses_gguf_loaders=uses_gguf_loaders,
        local_memory_profile=local_memory_profile,
        prefers_isolated_local_execution=local_memory_profile == "high",
    )


def get_workflow_capabilities(workflow_info: dict[str, Any]) -> WorkflowCapabilities:
    if workflow_info["source"] == "selfhost":
        metadata = WorkflowParser().parse_workflow_file(str(workflow_info["path"]))
        return _build_capabilities(
            supports_negative_prompt="negative_prompt" in metadata.params,
            class_types=_workflow_class_types(workflow_info["path"]),
        )

    wrapper = json.loads(Path(workflow_info["path"]).read_text(encoding="utf-8"))
    declared = (
        wrapper.get("declared_params")
        or wrapper.get("params")
        or wrapper.get("inputs")
        or {}
    )
    return _build_capabilities(
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
