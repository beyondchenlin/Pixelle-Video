from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pixelle_video.models.visual_anchor_two_stage import IdentityReferenceCondition

_REFERENCE_MARKER_RE = re.compile(
    r"\$~reference_image\.image!",
    re.IGNORECASE,
)
_CONDITION_MARKER_RE = re.compile(
    r"\[visual-anchor-reference-condition\]",
    re.IGNORECASE,
)
_SAMPLER_NODE_CLASSES = frozenset(
    {"KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced"}
)
_SEED_MARKER_RE = re.compile(r"\$seed\.seed!", re.IGNORECASE)
_PROMPT_MARKER_RE = re.compile(r"\$prompt\.value!", re.IGNORECASE)
IDENTITY_REFERENCE_CONDITION_WIDTH = 32
IDENTITY_REFERENCE_CONDITION_HEIGHT = 32
IDENTITY_REFERENCE_CONDITION_UPSCALE_METHOD = "lanczos"
IDENTITY_REFERENCE_CONDITION_CROP = "disabled"
_MODEL_LOADER_CLASSES = frozenset(
    {
        "CheckpointLoaderSimple",
        "CLIPLoader",
        "CLIPLoaderGGUF",
        "DualCLIPLoader",
        "DualCLIPLoaderGGUF",
        "UNETLoader",
        "UnetLoaderGGUF",
        "VAELoader",
    }
)


@dataclass(frozen=True)
class IdentityReferenceWorkflowInspection:
    condition: IdentityReferenceCondition
    workflow_key: str
    workflow_version_sha256: str
    workflow_relative_path: str
    model_files: tuple[str, ...]
    sampler_defaults: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "identity_reference_workflow_inspection.v2",
            "workflow_key": self.workflow_key,
            "workflow_version_sha256": self.workflow_version_sha256,
            "workflow_relative_path": self.workflow_relative_path,
            "model_files": list(self.model_files),
            "sampler_defaults": dict(self.sampler_defaults),
            "condition": self.condition.model_dump(mode="json"),
        }


@dataclass(frozen=True)
class ImageWorkflowInspection:
    """Immutable execution facts for text-only or reference-image workflows."""

    workflow_key: str
    workflow_version_sha256: str
    workflow_relative_path: str
    model_files: tuple[str, ...]
    sampler_defaults: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "image_workflow_inspection.v1",
            "workflow_key": self.workflow_key,
            "workflow_version_sha256": self.workflow_version_sha256,
            "workflow_relative_path": self.workflow_relative_path,
            "model_files": list(self.model_files),
            "sampler_defaults": dict(self.sampler_defaults),
        }


def inspect_image_workflow(
    *,
    workflow_info: Mapping[str, Any],
    project_root: str | Path,
) -> ImageWorkflowInspection:
    """Inspect the selected local image workflow without inventing reference support."""

    if str(workflow_info.get("source") or "") != "selfhost":
        raise ValueError("visual-anchor generation requires a self-hosted image workflow")
    workflow_path = Path(str(workflow_info.get("path") or "")).resolve()
    root = Path(project_root).resolve()
    if not workflow_path.is_file():
        raise ValueError("visual-anchor workflow file does not exist")
    try:
        workflow_relative_path = workflow_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("visual-anchor workflow must be inside the project") from exc
    workflow_bytes = workflow_path.read_bytes()
    workflow = json.loads(workflow_bytes.decode("utf-8"))
    if not isinstance(workflow, Mapping):
        raise ValueError("visual-anchor workflow must be an API-format node mapping")
    samplers = [
        raw_node
        for raw_node in workflow.values()
        if isinstance(raw_node, Mapping)
        and str(raw_node.get("class_type") or "") in _SAMPLER_NODE_CLASSES
    ]
    if len(samplers) != 1:
        raise ValueError("visual-anchor workflow must contain exactly one image sampler")
    sampler_inputs = samplers[0].get("inputs")
    sampler_title = str((samplers[0].get("_meta") or {}).get("title") or "")
    if not isinstance(sampler_inputs, Mapping):
        raise ValueError("visual-anchor image sampler inputs are missing")
    if "seed" not in sampler_inputs or not _SEED_MARKER_RE.search(sampler_title):
        raise ValueError(
            "visual-anchor sampler must expose the required fixed seed parameter"
        )
    return ImageWorkflowInspection(
        workflow_key=_required_text(workflow_info.get("key"), "workflow key"),
        workflow_version_sha256=hashlib.sha256(workflow_bytes).hexdigest(),
        workflow_relative_path=workflow_relative_path,
        model_files=_workflow_model_files(workflow),
        sampler_defaults=_sampler_defaults(sampler_inputs),
    )


def inspect_identity_reference_workflow(
    *,
    workflow_info: Mapping[str, Any],
    reference_asset_trace: Mapping[str, Any],
    project_root: str | Path,
) -> IdentityReferenceWorkflowInspection:
    if str(workflow_info.get("source") or "") != "selfhost":
        raise ValueError("visual-anchor identity reference requires a self-hosted workflow")
    workflow_path = Path(str(workflow_info.get("path") or "")).resolve()
    root = Path(project_root).resolve()
    if not workflow_path.is_file():
        raise ValueError("visual-anchor workflow file does not exist")
    try:
        workflow_relative_path = workflow_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("visual-anchor workflow must be inside the project") from exc

    workflow_bytes = workflow_path.read_bytes()
    workflow_sha256 = hashlib.sha256(workflow_bytes).hexdigest()
    workflow = json.loads(workflow_bytes.decode("utf-8"))
    if not isinstance(workflow, Mapping):
        raise ValueError("visual-anchor workflow must be an API-format node mapping")

    reference_nodes = []
    for node_id, raw_node in workflow.items():
        if not isinstance(raw_node, Mapping):
            continue
        title = str((raw_node.get("_meta") or {}).get("title") or "")
        if _REFERENCE_MARKER_RE.search(title):
            reference_nodes.append((str(node_id), raw_node))
    if len(reference_nodes) != 1:
        raise ValueError(
            "visual-anchor workflow must declare exactly one reference_image input node"
        )

    source_node_id, source_node = reference_nodes[0]
    source_class_type = str(source_node.get("class_type") or "").strip()
    if source_class_type != "LoadImage":
        raise ValueError("reference_image workflow input must be a LoadImage node")
    source_inputs = source_node.get("inputs")
    if not isinstance(source_inputs, Mapping) or "image" not in source_inputs:
        raise ValueError("reference_image LoadImage node must expose its image input")

    conditioning_nodes = []
    for node_id, raw_node in workflow.items():
        if not isinstance(raw_node, Mapping):
            continue
        title = str((raw_node.get("_meta") or {}).get("title") or "")
        if _CONDITION_MARKER_RE.search(title):
            conditioning_nodes.append((str(node_id), raw_node))
    if len(conditioning_nodes) != 1:
        raise ValueError(
            "visual-anchor workflow must declare exactly one identity-reference conditioning node"
        )
    if sum(
        1
        for raw_node in workflow.values()
        if isinstance(raw_node, Mapping)
        and str(raw_node.get("class_type") or "") == "TextEncodeZImageOmni"
    ) != 1:
        raise ValueError(
            "visual-anchor workflow must contain exactly one TextEncodeZImageOmni node"
        )
    conditioning_node_id, conditioning_node = conditioning_nodes[0]
    conditioning_class_type = str(conditioning_node.get("class_type") or "").strip()
    if conditioning_class_type != "TextEncodeZImageOmni":
        raise ValueError(
            "identity-reference conditioning must use the core TextEncodeZImageOmni node"
        )

    source_to_condition = _path_between(
        workflow,
        source_node_id=source_node_id,
        target_node_id=conditioning_node_id,
    )
    if source_to_condition is None:
        raise ValueError(
            "reference_image input is not connected to the declared conditioning node"
        )
    if len(source_to_condition) != 3:
        raise ValueError(
            "reference_image must reach TextEncodeZImageOmni through exactly one ImageScale node"
        )
    scale_node_id = source_to_condition[1]
    scale_node = workflow.get(scale_node_id)
    scale_class_type = (
        str(scale_node.get("class_type") or "")
        if isinstance(scale_node, Mapping)
        else ""
    )
    if scale_class_type != "ImageScale":
        raise ValueError(
            "reference_image must be limited by ImageScale before identity conditioning"
        )
    scale_inputs = (
        scale_node.get("inputs") if isinstance(scale_node, Mapping) else None
    )
    if (
        not isinstance(scale_inputs, Mapping)
        or _linked_node_id(scale_inputs.get("image")) != source_node_id
    ):
        raise ValueError(
            "reference_image LoadImage must enter ImageScale directly"
        )
    if (
        scale_inputs.get("width") != IDENTITY_REFERENCE_CONDITION_WIDTH
        or scale_inputs.get("height") != IDENTITY_REFERENCE_CONDITION_HEIGHT
        or scale_inputs.get("crop") != IDENTITY_REFERENCE_CONDITION_CROP
        or scale_inputs.get("upscale_method")
        != IDENTITY_REFERENCE_CONDITION_UPSCALE_METHOD
    ):
        raise ValueError(
            "identity reference conditioning must use the registered 32x32 uncropped Lanczos input"
        )
    conditioning_inputs = conditioning_node.get("inputs")
    if (
        not isinstance(conditioning_inputs, Mapping)
        or _linked_node_id(conditioning_inputs.get("image1")) != scale_node_id
    ):
        raise ValueError(
            "TextEncodeZImageOmni image1 must receive the scaled registered reference"
        )
    if (
        conditioning_inputs.get("image2") is not None
        or conditioning_inputs.get("image3") is not None
        or conditioning_inputs.get("image_encoder") is not None
    ):
        raise ValueError(
            "visual-anchor workflow must condition on exactly one reference image"
        )
    if conditioning_inputs.get("auto_resize_images") is not False:
        raise ValueError(
            "TextEncodeZImageOmni automatic reference resizing must be disabled"
        )
    clip_node_id = _linked_node_id(conditioning_inputs.get("clip"))
    prompt_node_id = _linked_node_id(conditioning_inputs.get("prompt"))
    vae_node_id = _linked_node_id(conditioning_inputs.get("vae"))
    if (
        _node_class_type(workflow, clip_node_id) != "CLIPLoaderGGUF"
        or _node_class_type(workflow, prompt_node_id) != "PrimitiveStringMultiline"
        or _node_class_type(workflow, vae_node_id) != "VAELoader"
    ):
        raise ValueError(
            "identity conditioning must receive the selected GGUF text encoder, final prompt, and VAE"
        )
    prompt_node = workflow.get(prompt_node_id or "")
    prompt_title = (
        str((prompt_node.get("_meta") or {}).get("title") or "")
        if isinstance(prompt_node, Mapping)
        else ""
    )
    if not _PROMPT_MARKER_RE.search(prompt_title):
        raise ValueError(
            "identity conditioning must receive the declared final positive prompt parameter"
        )
    condition_to_sampler = _path_to_sampler(
        workflow,
        source_node_id=conditioning_node_id,
    )
    if condition_to_sampler is None:
        raise ValueError(
            "identity-reference conditioning node is not connected to an image sampler"
        )
    if len(condition_to_sampler) != 2:
        raise ValueError(
            "TextEncodeZImageOmni must connect directly to the first image sampler"
        )
    sampler_node_id = condition_to_sampler[-1]
    sampler_node = workflow[sampler_node_id]
    sampler_class_type = str(sampler_node.get("class_type") or "")
    sampler_inputs = sampler_node.get("inputs")
    sampler_title = str((sampler_node.get("_meta") or {}).get("title") or "")
    if (
        not isinstance(sampler_inputs, Mapping)
        or _linked_node_id(sampler_inputs.get("positive")) != conditioning_node_id
    ):
        raise ValueError(
            "TextEncodeZImageOmni must enter the sampler's positive conditioning input"
        )
    if "seed" not in sampler_inputs or not _SEED_MARKER_RE.search(sampler_title):
        raise ValueError(
            "visual-anchor sampler must expose the required fixed seed parameter"
        )
    sampler_defaults = _sampler_defaults(sampler_inputs)
    path = [*source_to_condition, *condition_to_sampler[1:]]

    condition = IdentityReferenceCondition(
        asset_sha256=_required_sha256(
            reference_asset_trace.get("workflow_sha256")
            or reference_asset_trace.get("sha256"),
            "workflow asset sha256",
        ),
        workflow_asset_relative_path=_required_text(
            reference_asset_trace.get("workflow_asset_relative_path"),
            "workflow asset relative path",
        ),
        mime_type=_required_text(
            reference_asset_trace.get("workflow_mime_type")
            or reference_asset_trace.get("mime_type"),
            "workflow mime type",
        ),
        width=_positive_int(
            reference_asset_trace.get("workflow_width")
            or reference_asset_trace.get("width"),
            "workflow width",
        ),
        height=_positive_int(
            reference_asset_trace.get("workflow_height")
            or reference_asset_trace.get("height"),
            "workflow height",
        ),
        byte_size=_positive_int(
            reference_asset_trace.get("workflow_byte_size")
            or reference_asset_trace.get("byte_size"),
            "workflow byte size",
        ),
        resource_version=(
            "reference-image:"
            + _required_sha256(
                reference_asset_trace.get("workflow_sha256")
                or reference_asset_trace.get("sha256"),
                "workflow asset sha256",
            )
        ),
        workflow_parameter="reference_image",
        workflow_node_id=source_node_id,
        workflow_node_class_type=source_class_type,
        workflow_node_input_field="image",
        conditioning_node_id=conditioning_node_id,
        conditioning_node_class_type=conditioning_class_type,
        sampler_node_id=sampler_node_id,
        sampler_node_class_type=sampler_class_type,
        binding_path_node_ids=path,
    )
    return IdentityReferenceWorkflowInspection(
        condition=condition,
        workflow_key=_required_text(workflow_info.get("key"), "workflow key"),
        workflow_version_sha256=workflow_sha256,
        workflow_relative_path=workflow_relative_path,
        model_files=_workflow_model_files(workflow),
        sampler_defaults=sampler_defaults,
    )


def _workflow_model_files(workflow: Mapping[str, Any]) -> tuple[str, ...]:
    files: list[str] = []
    for raw_node in workflow.values():
        if not isinstance(raw_node, Mapping):
            continue
        if str(raw_node.get("class_type") or "") not in _MODEL_LOADER_CLASSES:
            continue
        inputs = raw_node.get("inputs")
        if not isinstance(inputs, Mapping):
            continue
        for key, value in inputs.items():
            if str(key).endswith("_name") and isinstance(value, str) and value.strip():
                files.append(value.strip())
    result = tuple(sorted(set(files)))
    if not result:
        raise ValueError("visual-anchor workflow does not declare image model files")
    return result


def _sampler_defaults(inputs: Mapping[str, Any]) -> dict[str, Any]:
    required = (
        "steps",
        "cfg",
        "sampler_name",
        "scheduler",
        "denoise",
    )
    result = {key: inputs.get(key) for key in required}
    if (
        type(result["steps"]) is not int
        or result["steps"] <= 0
        or isinstance(result["cfg"], bool)
        or not isinstance(result["cfg"], (int, float))
        or result["cfg"] < 0
        or not isinstance(result["sampler_name"], str)
        or not result["sampler_name"].strip()
        or not isinstance(result["scheduler"], str)
        or not result["scheduler"].strip()
        or isinstance(result["denoise"], bool)
        or not isinstance(result["denoise"], (int, float))
        or not 0 < result["denoise"] <= 1
    ):
        raise ValueError(
            "visual-anchor workflow sampler defaults are incomplete or invalid"
        )
    result["sampler_name"] = result["sampler_name"].strip()
    result["scheduler"] = result["scheduler"].strip()
    return result


def _path_between(
    workflow: Mapping[str, Any],
    *,
    source_node_id: str,
    target_node_id: str,
) -> list[str] | None:
    outgoing = _outgoing_edges(workflow)
    queue: deque[list[str]] = deque([[source_node_id]])
    visited = {source_node_id}
    while queue:
        path = queue.popleft()
        for target_id in outgoing.get(path[-1], []):
            if target_id in visited:
                continue
            next_path = [*path, target_id]
            if target_id == target_node_id:
                return next_path
            visited.add(target_id)
            queue.append(next_path)
    return None


def _path_to_sampler(
    workflow: Mapping[str, Any],
    *,
    source_node_id: str,
) -> list[str] | None:
    outgoing = _outgoing_edges(workflow)
    queue: deque[list[str]] = deque([[source_node_id]])
    visited = {source_node_id}
    while queue:
        path = queue.popleft()
        for target_id in outgoing.get(path[-1], []):
            if target_id in visited:
                continue
            next_path = [*path, target_id]
            target = workflow.get(target_id)
            if isinstance(target, Mapping) and str(target.get("class_type") or "") in (
                _SAMPLER_NODE_CLASSES
            ):
                return next_path
            visited.add(target_id)
            queue.append(next_path)
    return None


def _outgoing_edges(workflow: Mapping[str, Any]) -> dict[str, list[str]]:
    outgoing: dict[str, list[str]] = {}
    for target_id, raw_node in workflow.items():
        if not isinstance(raw_node, Mapping):
            continue
        inputs = raw_node.get("inputs")
        if not isinstance(inputs, Mapping):
            continue
        for value in inputs.values():
            upstream_id = _linked_node_id(value)
            if upstream_id is not None:
                outgoing.setdefault(upstream_id, []).append(str(target_id))
    return outgoing


def _linked_node_id(value: Any) -> str | None:
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
    ):
        return str(value[0])
    return None


def _node_class_type(
    workflow: Mapping[str, Any],
    node_id: str | None,
) -> str:
    if node_id is None:
        return ""
    node = workflow.get(node_id)
    if not isinstance(node, Mapping):
        return ""
    return str(node.get("class_type") or "").strip()


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _required_sha256(value: object, field_name: str) -> str:
    text = _required_text(value, field_name).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError(f"{field_name} must be a sha256 digest")
    return text


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer") from exc
    if result <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return result


__all__ = [
    "IDENTITY_REFERENCE_CONDITION_CROP",
    "IDENTITY_REFERENCE_CONDITION_HEIGHT",
    "IDENTITY_REFERENCE_CONDITION_UPSCALE_METHOD",
    "IDENTITY_REFERENCE_CONDITION_WIDTH",
    "ImageWorkflowInspection",
    "IdentityReferenceWorkflowInspection",
    "inspect_image_workflow",
    "inspect_identity_reference_workflow",
]
