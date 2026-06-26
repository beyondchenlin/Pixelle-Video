from __future__ import annotations

from dataclasses import replace
from typing import Any

from pixelle_video.models.series_visual_signature_presentation import (
    SeriesVisualSignaturePresentationMode,
    SeriesVisualSignaturePresentationPolicy,
)
from pixelle_video.models.visual_anchor_planning import AnchorCarrierType
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy


_VISIBLE_CHARACTER_CARRIERS = (
    AnchorCarrierType.MINOR_SUPPORTING_CHARACTER.value,
    AnchorCarrierType.LIVING_CHARACTER.value,
)

_PRIMARY_CHARACTER_CARRIERS = (
    AnchorCarrierType.LIVING_CHARACTER.value,
)

_LEGACY_MARK_CARRIERS = (
    AnchorCarrierType.BOOKPLATE_OR_STAMP.value,
    AnchorCarrierType.PRINTED_MARK.value,
    AnchorCarrierType.EMBOSSED_MARK.value,
    AnchorCarrierType.ENGRAVED_MARK.value,
    AnchorCarrierType.SURFACE_GRAPHIC.value,
    AnchorCarrierType.DECORATIVE_OBJECT.value,
    AnchorCarrierType.WEARABLE_SYMBOL.value,
    AnchorCarrierType.SMALL_SUPPORTING_PROP.value,
    AnchorCarrierType.MINOR_SUPPORTING_CHARACTER.value,
)


def policy_for_presentation_mode(
    base_policy: VisualSignaturePolicy,
    presentation_policy: SeriesVisualSignaturePresentationPolicy | None,
) -> VisualSignaturePolicy:
    """Resolve the runtime projection policy for a product presentation mode."""

    if presentation_policy is None:
        return base_policy

    mode = presentation_policy.presentation_mode
    if mode in {
        SeriesVisualSignaturePresentationMode.CONTENT_BOUND_MANDATORY_IP,
        SeriesVisualSignaturePresentationMode.FUNCTION_BOUND_IP_ACTOR,
        SeriesVisualSignaturePresentationMode.AUTO,
    }:
        return base_policy

    if mode is SeriesVisualSignaturePresentationMode.VISIBLE_SUPPORTING_CHARACTER:
        return replace(
            base_policy,
            version="visual_signature_policy.v2_visible_supporting_character",
            fallback_strategy="inject_safe_carrier",
            allowed_visible_carrier_types=_VISIBLE_CHARACTER_CARRIERS,
        )

    if mode is SeriesVisualSignaturePresentationMode.PRIMARY_CHARACTER:
        return replace(
            base_policy,
            version="visual_signature_policy.v2_primary_character",
            fallback_strategy="inject_safe_carrier",
            allowed_visible_carrier_types=_PRIMARY_CHARACTER_CARRIERS,
        )

    if mode in {
        SeriesVisualSignaturePresentationMode.EMBEDDED_SCENE_MARK,
        SeriesVisualSignaturePresentationMode.LEGACY_VISUAL_MARK,
    }:
        return replace(
            base_policy,
            version="visual_signature_policy.v1_legacy_visual_mark",
            fallback_strategy="inject_safe_carrier",
            allowed_visible_carrier_types=_LEGACY_MARK_CARRIERS,
            final_prompt_forbidden_terms=(),
        )

    return base_policy


def is_content_bound_presentation(value: Any) -> bool:
    mode = getattr(value, "presentation_mode", value)
    return mode in {
        SeriesVisualSignaturePresentationMode.CONTENT_BOUND_MANDATORY_IP,
        SeriesVisualSignaturePresentationMode.FUNCTION_BOUND_IP_ACTOR,
        SeriesVisualSignaturePresentationMode.AUTO,
    }


__all__ = ["is_content_bound_presentation", "policy_for_presentation_mode"]
