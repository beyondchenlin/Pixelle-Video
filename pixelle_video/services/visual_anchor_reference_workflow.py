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


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


__all__ = ["resolve_visual_anchor_reference_workflow_key"]
