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

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "identity_reference_workflow_inspection.v1",
            "workflow_key": self.workflow_key,
            "workflow_version_sha256": self.workflow_version_sha256,
            "workflow_relative_path": self.workflow_relative_path,
            "model_files": list(self.model_files),
            "condition": self.condition.model_dump(mode="json"),
        }


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
        and str(raw_node.get("class_type") or "") == "ReferenceLatent"
    ) != 1:
        raise ValueError(
            "visual-anchor workflow must contain exactly one ReferenceLatent node"
        )
    conditioning_node_id, conditioning_node = conditioning_nodes[0]
    conditioning_class_type = str(conditioning_node.get("class_type") or "").strip()
    if conditioning_class_type != "ReferenceLatent":
        raise ValueError(
            "identity-reference conditioning must use the core ReferenceLatent node"
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
            "reference_image must reach ReferenceLatent through exactly one VAE encoder"
        )
    encoder_node = workflow.get(source_to_condition[1])
    encoder_class_type = (
        str(encoder_node.get("class_type") or "")
        if isinstance(encoder_node, Mapping)
        else ""
    )
    if encoder_class_type not in {"VAEEncode", "VAEEncodeTiled"}:
        raise ValueError(
            "reference_image must be encoded by a VAE node before ReferenceLatent"
        )
    encoder_inputs = encoder_node.get("inputs") if isinstance(encoder_node, Mapping) else None
    if (
        not isinstance(encoder_inputs, Mapping)
        or _linked_node_id(encoder_inputs.get("pixels")) != source_node_id
    ):
        raise ValueError(
            "reference_image LoadImage must enter the VAE encoder pixels input"
        )
    conditioning_inputs = conditioning_node.get("inputs")
    if (
        not isinstance(conditioning_inputs, Mapping)
        or _linked_node_id(conditioning_inputs.get("latent"))
        != source_to_condition[1]
        or _linked_node_id(conditioning_inputs.get("conditioning")) is None
    ):
        raise ValueError(
            "ReferenceLatent must receive the encoded reference and positive conditioning"
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
            "ReferenceLatent must connect directly to the first image sampler"
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
            "ReferenceLatent must enter the sampler's positive conditioning input"
        )
    if "seed" not in sampler_inputs or not _SEED_MARKER_RE.search(sampler_title):
        raise ValueError(
            "visual-anchor sampler must expose the required fixed seed parameter"
        )
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
    "IdentityReferenceWorkflowInspection",
    "inspect_identity_reference_workflow",
]
