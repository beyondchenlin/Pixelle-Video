from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.architecture.legacy_signature_field_guard import (
    reject_deprecated_signature_fields,
)
from pixelle_video.models.z_image_prompt_bundle import ZImagePromptBundle


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
