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
    """Provider adapter for local Z-Image."""
    if not isinstance(bundle, ZImagePromptBundle):
        raise TypeError("project_z_image_prompt_bundle requires a ZImagePromptBundle")
    config = dict(render_config or {})
    reject_deprecated_signature_fields(bundle.metadata, context="z-image bundle metadata")
    reject_deprecated_signature_fields(config, context="z-image render config")
    prompt = _project_prompt(bundle)
    return {
        "provider": "z_image",
        "prompt": prompt,
        "negative_prompt": bundle.negative_prompt,
        "metadata": {
            **dict(bundle.to_dict()["metadata"]),
            "locked_constraints": list(bundle.locked_constraints),
            "locked_constraints_projected": bool(bundle.locked_constraints),
        },
        "render_config": config,
    }


def _project_prompt(bundle: ZImagePromptBundle) -> str:
    base = " ".join(bundle.positive_prompt.split())
    constraints = tuple(
        " ".join(str(item or "").split())
        for item in bundle.locked_constraints
        if str(item or "").strip()
    )
    if not constraints:
        return base
    return f"{base}. Composition requirements: {' '.join(constraints)}"
