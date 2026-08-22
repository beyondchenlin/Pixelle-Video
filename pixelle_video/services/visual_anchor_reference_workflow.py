from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pixelle_video.utils.workflow_capabilities import get_workflow_capabilities

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


def resolve_visual_anchor_reference_workflow_key(
    *,
    media_service: Any,
    workflow: str | None,
) -> str:
    """Resolve a reference-capable sibling without changing the selected model files."""

    base_info = media_service._resolve_workflow(
        workflow=workflow,
        workflow_domain="image",
    )
    if str(base_info.get("source") or "") != "selfhost":
        raise ValueError(
            "visual-anchor identity reference requires the selected local image workflow"
        )
    if get_workflow_capabilities(dict(base_info)).supports_reference_image:
        return _required_text(base_info.get("key"), "workflow key")

    base_path = Path(_required_text(base_info.get("path"), "workflow path")).resolve()
    variant_name = f"{base_path.stem}_reference{base_path.suffix}"
    variant_key = f"selfhost/{variant_name}"
    variant_info = media_service._resolve_workflow(
        workflow=variant_key,
        workflow_domain="image",
    )
    if not get_workflow_capabilities(dict(variant_info)).supports_reference_image:
        raise ValueError(
            "the selected image workflow reference variant does not declare a reference image input"
        )
    variant_path = Path(
        _required_text(variant_info.get("path"), "reference workflow path")
    ).resolve()
    if _model_loader_signature(base_path) != _model_loader_signature(variant_path):
        raise ValueError(
            "visual-anchor reference workflow must preserve the selected image model files"
        )
    base_signature, variant_signature = _reference_neutral_workflow_signature(
        base_path,
        variant_path,
    )
    if base_signature != variant_signature:
        raise ValueError(
            "visual-anchor reference workflow must preserve the selected sampler, dimensions, model wiring, and output configuration"
        )
    return _required_text(variant_info.get("key"), "reference workflow key")


def _model_loader_signature(path: Path) -> tuple[tuple[str, str, str], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("image workflow must be an API-format node mapping")
    signature: list[tuple[str, str, str]] = []
    for raw_node in payload.values():
        if not isinstance(raw_node, Mapping):
            continue
        class_type = str(raw_node.get("class_type") or "")
        if class_type not in _MODEL_LOADER_CLASSES:
            continue
        inputs = raw_node.get("inputs")
        if not isinstance(inputs, Mapping):
            continue
        for key, value in inputs.items():
            if not str(key).endswith("_name") or not isinstance(value, str):
                continue
            signature.append((class_type, str(key), value))
    if not signature:
        raise ValueError("image workflow does not declare model loader files")
    return tuple(sorted(signature))


def _reference_neutral_workflow_signature(
    base_path: Path,
    variant_path: Path,
) -> tuple[str, str]:
    base = _workflow_mapping(base_path)
    variant = _workflow_mapping(variant_path)
    base_sampler_id, base_positive_id = _single_sampler_and_positive(base)
    variant_sampler_id, variant_positive_id = _single_sampler_and_positive(variant)
    if base_sampler_id != variant_sampler_id:
        raise ValueError(
            "visual-anchor reference workflow must preserve the selected sampler node"
        )
    base_positive = base.get(base_positive_id)
    if (
        not isinstance(base_positive, Mapping)
        or str(base_positive.get("class_type") or "") != "CLIPTextEncode"
    ):
        raise ValueError(
            "selected image workflow must use a single direct positive text encoder"
        )
    variant_positive = variant.get(variant_positive_id)
    if (
        not isinstance(variant_positive, Mapping)
        or str(variant_positive.get("class_type") or "")
        != "TextEncodeZImageOmni"
    ):
        raise ValueError(
            "visual-anchor reference workflow must replace only the positive text encoder with identity conditioning"
        )

    base_only_ids = set(base) - set(variant)
    variant_only_ids = set(variant) - set(base)
    if base_only_ids != {base_positive_id}:
        raise ValueError(
            "visual-anchor reference workflow changed unrelated base nodes"
        )
    if variant_positive_id not in variant_only_ids:
        raise ValueError(
            "visual-anchor reference conditioning must be isolated from base node ids"
        )
    variant_only_classes = sorted(
        str(variant[node_id].get("class_type") or "")
        for node_id in variant_only_ids
        if isinstance(variant.get(node_id), Mapping)
    )
    if variant_only_classes != [
        "ImageScale",
        "LoadImage",
        "TextEncodeZImageOmni",
    ]:
        raise ValueError(
            "visual-anchor reference workflow may add only one reference input, one scale node, and one identity conditioner"
        )

    normalized_base = {
        node_id: json.loads(json.dumps(node))
        for node_id, node in base.items()
        if node_id != base_positive_id
    }
    normalized_variant = {
        node_id: json.loads(json.dumps(node))
        for node_id, node in variant.items()
        if node_id not in variant_only_ids
    }
    for normalized in (normalized_base, normalized_variant):
        sampler = normalized[base_sampler_id]
        sampler["inputs"]["positive"] = ["__positive_condition__", 0]
        sampler.setdefault("_meta", {})["title"] = "__sampler__"
    return (
        json.dumps(normalized_base, ensure_ascii=False, sort_keys=True),
        json.dumps(normalized_variant, ensure_ascii=False, sort_keys=True),
    )


def _workflow_mapping(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("image workflow must be an API-format node mapping")
    return {
        str(node_id): dict(node)
        for node_id, node in payload.items()
        if isinstance(node, Mapping)
    }


def _single_sampler_and_positive(
    workflow: Mapping[str, Any],
) -> tuple[str, str]:
    samplers = [
        (str(node_id), node)
        for node_id, node in workflow.items()
        if isinstance(node, Mapping)
        and str(node.get("class_type") or "") == "KSampler"
    ]
    if len(samplers) != 1:
        raise ValueError("image workflow must contain exactly one KSampler")
    sampler_id, sampler = samplers[0]
    inputs = sampler.get("inputs")
    positive = inputs.get("positive") if isinstance(inputs, Mapping) else None
    if (
        not isinstance(positive, list)
        or len(positive) != 2
        or not isinstance(positive[0], (str, int))
    ):
        raise ValueError("image workflow sampler must have one positive input")
    return sampler_id, str(positive[0])


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


__all__ = ["resolve_visual_anchor_reference_workflow_key"]
