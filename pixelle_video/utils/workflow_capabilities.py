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
from collections.abc import Mapping, Sequence
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
_REFERENCE_IMAGE_PARAM_ALLOWLIST = frozenset(
    {
        "reference_image",
        "ref_image",
        "source_image",
        "init_image",
        "input_image",
        "start_image",
        "image",
    }
)


@dataclass(frozen=True)
class WorkflowCapabilities:
    supports_negative_prompt: bool = False
    uses_gguf_loaders: bool = False
    local_memory_profile: LocalMemoryProfile = "standard"
    prefers_isolated_local_execution: bool = False
    reference_image_param_names: tuple[str, ...] = ()

    @property
    def supports_reference_image(self) -> bool:
        return bool(self.reference_image_param_names)


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
    declared_param_names: Sequence[str] | None = None,
) -> WorkflowCapabilities:
    resolved_class_types = class_types or set()
    uses_gguf_loaders = bool(resolved_class_types & _GGUF_LOADER_CLASS_TYPES)
    local_memory_profile: LocalMemoryProfile = "high" if uses_gguf_loaders else "standard"
    reference_image_param_names = _reference_image_param_names(declared_param_names or ())
    return WorkflowCapabilities(
        supports_negative_prompt=supports_negative_prompt,
        uses_gguf_loaders=uses_gguf_loaders,
        local_memory_profile=local_memory_profile,
        prefers_isolated_local_execution=False,
        reference_image_param_names=reference_image_param_names,
    )


def get_workflow_capabilities(workflow_info: dict[str, Any]) -> WorkflowCapabilities:
    if workflow_info["source"] == "selfhost":
        metadata = WorkflowParser().parse_workflow_file(str(workflow_info["path"]))
        declared_names = _declared_param_names(getattr(metadata, "params", {}))
        return _build_capabilities(
            supports_negative_prompt="negative_prompt" in declared_names,
            class_types=_workflow_class_types(workflow_info["path"]),
            declared_param_names=declared_names,
        )

    wrapper = json.loads(Path(workflow_info["path"]).read_text(encoding="utf-8"))
    declared = (
        wrapper.get("declared_params")
        or wrapper.get("params")
        or wrapper.get("inputs")
        or {}
    )
    declared_names = _declared_param_names(declared)
    return _build_capabilities(
        supports_negative_prompt=bool("negative_prompt" in declared_names),
        declared_param_names=declared_names,
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


def _declared_param_names(value: Any) -> tuple[str, ...]:
    names: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key or "").strip()
            if key_text:
                names.append(key_text)
            if isinstance(item, Mapping):
                for nested_key in ("name", "param", "key"):
                    nested_value = item.get(nested_key)
                    if isinstance(nested_value, str) and nested_value.strip():
                        names.append(nested_value.strip())
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, Mapping):
                for nested_key in ("name", "param", "key"):
                    nested_value = item.get(nested_key)
                    if isinstance(nested_value, str) and nested_value.strip():
                        names.append(nested_value.strip())
    return tuple(dict.fromkeys(names))


def _reference_image_param_names(declared_param_names: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for name in declared_param_names:
        text = str(name or "").strip()
        if text and text.lower() in _REFERENCE_IMAGE_PARAM_ALLOWLIST:
            result.append(text)
    return tuple(dict.fromkeys(result))
