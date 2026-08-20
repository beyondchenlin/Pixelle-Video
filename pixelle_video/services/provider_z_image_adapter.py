from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.architecture.legacy_signature_field_guard import (
    reject_deprecated_signature_fields,
)
from pixelle_video.models.z_image_prompt_bundle import ZImagePromptBundle

_UNSUPPORTED_REGION_CONTROL_KEYS = frozenset(
    {
        "bbox",
        "bboxes",
        "bounding_box",
        "bounding_boxes",
        "mask",
        "masks",
        "depth",
        "depth_map",
        "depth_image",
        "pose",
        "poses",
        "pose_map",
        "keypoints",
        "controlnet",
        "conditioning_image",
        "region",
        "regions",
    }
)


def project_z_image_prompt_bundle(
    *,
    bundle: ZImagePromptBundle,
    render_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Provider adapter for local Z-Image.

    The adapter is intentionally mechanical: all executable prompt semantics
    must already be compiled into ``ZImagePromptBundle`` before this boundary.
    """
    if not isinstance(bundle, ZImagePromptBundle):
        raise TypeError("project_z_image_prompt_bundle requires a ZImagePromptBundle")
    config = dict(render_config or {})
    reject_deprecated_signature_fields(bundle.metadata, context="z-image bundle metadata")
    reject_deprecated_signature_fields(config, context="z-image render config")
    _reject_unsupported_region_controls(config)
    return {
        "provider": "z_image",
        "prompt": bundle.positive_prompt,
        "negative_prompt": bundle.negative_prompt,
        "metadata": {
            **dict(bundle.to_dict()["metadata"]),
            "locked_constraints": list(bundle.locked_constraints),
        },
        "render_config": config,
    }


def _reject_unsupported_region_controls(
    value: Any,
    *,
    path: str = "render_config",
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = str(key).strip().casefold().replace("-", "_")
            child_path = f"{path}.{key}"
            if normalized_key in _UNSUPPORTED_REGION_CONTROL_KEYS:
                raise ValueError(
                    "z-image workflow does not declare region control capability: "
                    + child_path
                )
            _reject_unsupported_region_controls(child, path=child_path)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_unsupported_region_controls(child, path=f"{path}[{index}]")


__all__ = ["project_z_image_prompt_bundle"]
