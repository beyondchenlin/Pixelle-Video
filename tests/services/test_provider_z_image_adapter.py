from __future__ import annotations

import pytest

from pixelle_video.architecture.legacy_signature_field_guard import DEPRECATED_RUNTIME_FIELD_NAMES
from pixelle_video.models.z_image_prompt_bundle import ZImagePromptBundle
from pixelle_video.services.provider_z_image_adapter import project_z_image_prompt_bundle


def test_provider_adapter_accepts_only_prompt_bundle() -> None:
    bundle = ZImagePromptBundle(
        positive_prompt="A clean unlabeled relationship map.",
        negative_prompt="readable text",
        metadata={"schema_version": "v4.5-signature"},
    )

    payload = project_z_image_prompt_bundle(bundle=bundle, render_config={"steps": 35})

    assert payload["provider"] == "z_image"
    assert payload["prompt"] == "A clean unlabeled relationship map."
    assert payload["render_config"]["steps"] == 35


def test_provider_adapter_does_not_reinterpret_locked_constraints() -> None:
    bundle = ZImagePromptBundle(
        positive_prompt="Executable source and identity constraints are already compiled here.",
        locked_constraints=(
            "Keep required source subjects visible and primary.",
            "Keep the recurring identity scene-bound.",
        ),
    )

    payload = project_z_image_prompt_bundle(bundle=bundle)

    assert payload["prompt"] == bundle.positive_prompt
    assert payload["metadata"]["locked_constraints"] == list(bundle.locked_constraints)


def test_provider_adapter_rejects_deprecated_metadata_deep() -> None:
    deprecated_profile_key = next(
        key
        for key in DEPRECATED_RUNTIME_FIELD_NAMES
        if key.startswith("ip_") and key.endswith("_id") and "profile" in key
    )
    with pytest.raises(ValueError, match="deprecated visual signature fields"):
        ZImagePromptBundle(
            positive_prompt="A clean unlabeled relationship map.",
            metadata={"nested": {deprecated_profile_key: "dog_1"}},
        )

    bundle = ZImagePromptBundle(positive_prompt="A clean unlabeled relationship map.")
    deprecated_strategy_key = next(
        key
        for key in DEPRECATED_RUNTIME_FIELD_NAMES
        if key.startswith("visual_") and key.endswith("_strategy")
    )
    with pytest.raises(ValueError, match="deprecated visual signature fields"):
        project_z_image_prompt_bundle(bundle=bundle, render_config={"nested": {deprecated_strategy_key: "guide"}})
