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

try:  # Optional at import time; required only for self-hosted workflow inspection.
    from comfykit.comfyui.workflow_parser import WorkflowParser
except Exception:  # pragma: no cover - exercised in lightweight test environments
    WorkflowParser = None  # type: ignore[assignment]

LocalMemoryProfile = Literal["standard", "high"]
VaeDecodeMode = Literal["standard", "tiled"]

_GGUF_LOADER_CLASS_TYPES = frozenset(
    {
        "UnetLoaderGGUF",
        "CLIPLoaderGGUF",
        "DualCLIPLoaderGGUF",
    }
)
_TILED_VAE_DECODE_CLASS_TYPES = frozenset({"VAEDecodeTiled"})
_STRICT_REFERENCE_IMAGE_PARAM_NAMES = frozenset(
    {
        "reference_image",
        "reference_image_path",
        "ref_image",
        "source_image",
        "init_image",
        "input_image",
        "start_image",
    }
)
_AMBIGUOUS_REFERENCE_IMAGE_PARAM_NAMES = frozenset({"image"})
_REFERENCE_IMAGE_ROLE_VALUES = frozenset(
    {
        "reference_image",
        "reference",
        "control_image",
        "input_image",
        "source_image",
        "init_image",
    }
)


@dataclass(frozen=True)
class WorkflowCapabilities:
    supports_negative_prompt: bool = False
    uses_gguf_loaders: bool = False
    local_memory_profile: LocalMemoryProfile = "standard"
    vae_decode_mode: VaeDecodeMode = "standard"
    prefers_isolated_local_execution: bool = False
    reference_image_param_names: tuple[str, ...] = ()

    @property
    def supports_reference_image(self) -> bool:
        return bool(self.reference_image_param_names)

    @property
    def uses_tiled_vae_decode(self) -> bool:
        return self.vae_decode_mode == "tiled"


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
    declared_params: Any = None,
) -> WorkflowCapabilities:
    resolved_class_types = class_types or set()
    uses_gguf_loaders = bool(resolved_class_types & _GGUF_LOADER_CLASS_TYPES)
    vae_decode_mode: VaeDecodeMode = (
        "tiled"
        if resolved_class_types & _TILED_VAE_DECODE_CLASS_TYPES
        else "standard"
    )
    local_memory_profile: LocalMemoryProfile = "high" if uses_gguf_loaders else "standard"
    reference_image_param_names = (
        _declared_reference_image_param_names(declared_params)
        if declared_params is not None
        else _reference_image_param_names(declared_param_names or ())
    )
    return WorkflowCapabilities(
        supports_negative_prompt=supports_negative_prompt,
        uses_gguf_loaders=uses_gguf_loaders,
        local_memory_profile=local_memory_profile,
        vae_decode_mode=vae_decode_mode,
        prefers_isolated_local_execution=False,
        reference_image_param_names=reference_image_param_names,
    )


def get_workflow_capabilities(workflow_info: dict[str, Any]) -> WorkflowCapabilities:
    if workflow_info["source"] == "selfhost":
        metadata = _workflow_parser().parse_workflow_file(str(workflow_info["path"]))
        declared = getattr(metadata, "params", {})
        declared_names = _declared_param_names(declared)
        return _build_capabilities(
            supports_negative_prompt="negative_prompt" in declared_names,
            class_types=_workflow_class_types(workflow_info["path"]),
            declared_param_names=declared_names,
            declared_params=declared,
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
        declared_params=declared,
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


def _workflow_parser():
    parser_cls = WorkflowParser
    if parser_cls is not None:
        return parser_cls()
    try:
        from comfykit.comfyui.workflow_parser import WorkflowParser as imported_parser
    except Exception as exc:
        raise RuntimeError(
            "Self-hosted workflow capability inspection requires "
            "comfykit.comfyui.workflow_parser. Install the project dependencies or "
            "use a wrapper workflow with declared params."
        ) from exc
    globals()["WorkflowParser"] = imported_parser
    return imported_parser()


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


def _declared_reference_image_param_names(value: Any) -> tuple[str, ...]:
    result: list[str] = []

    def append_if_reference(name: Any, metadata: Any = None) -> None:
        text = str(name or "").strip()
        normalized = text.lower()
        if not text:
            return
        if normalized in _STRICT_REFERENCE_IMAGE_PARAM_NAMES:
            result.append(text)
            return
        if normalized in _AMBIGUOUS_REFERENCE_IMAGE_PARAM_NAMES and _metadata_marks_reference_image(metadata):
            result.append(text)

    if isinstance(value, Mapping):
        for key, item in value.items():
            append_if_reference(key, item)
            if isinstance(item, Mapping):
                append_if_reference(item.get("name") or item.get("param") or item.get("key"), item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            if isinstance(item, Mapping):
                append_if_reference(item.get("name") or item.get("param") or item.get("key"), item)
            else:
                append_if_reference(item)
    return tuple(dict.fromkeys(result))


def _metadata_marks_reference_image(metadata: Any) -> bool:
    if not isinstance(metadata, Mapping):
        return False
    for key in ("role", "purpose", "kind", "semantic", "semantic_role", "type"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip().lower() in _REFERENCE_IMAGE_ROLE_VALUES:
            return True
    tags = metadata.get("tags") or metadata.get("labels")
    if isinstance(tags, Sequence) and not isinstance(tags, (str, bytes, bytearray)):
        return any(str(item or "").strip().lower() in _REFERENCE_IMAGE_ROLE_VALUES for item in tags)
    return False


def _reference_image_param_names(declared_param_names: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for name in declared_param_names:
        text = str(name or "").strip()
        if text and text.lower() in _STRICT_REFERENCE_IMAGE_PARAM_NAMES:
            result.append(text)
    return tuple(dict.fromkeys(result))
