from __future__ import annotations

from typing import Any

from pixelle_video.models.series_visual_signature import SeriesVisualSignatureRequest
from pixelle_video.services.series_visual_signature_profile_snapshot_builder import (
    SeriesVisualSignatureProfileSnapshotBuilder,
)
from pixelle_video.services.visual_prompt_composer import VisualPromptComposer

_LEGACY_SIGNATURE_ARGUMENTS = (
    "series_visual_signature_enabled",
    "series_visual_signature_expression_mode",
    "series_visual_signature_structure_mode",
    "series_visual_signature_participation_mode",
    "series_visual_signature_mode",
    "series_visual_signature_consistency_mode",
    "series_visual_signature_presentation_mode",
    "series_visual_signature_enforcement",
    "series_visual_signature_fallback_enabled",
    "series_visual_signature_fallback_mode",
    "series_visual_signature_min_visibility",
)


class ImagePromptComposer:
    """Compatibility adapter for callers that still use the historical API.

    This class has no prompt implementation. It normalizes historical signature
    controls once and delegates to the canonical ``VisualPromptComposer``. When
    a canonical request is supplied it is authoritative and historical controls
    cannot overwrite it.
    """

    async def compose(self, **kwargs: Any):
        values = dict(kwargs)
        request = values.pop("series_visual_signature_request", None)
        if request is not None and not isinstance(request, SeriesVisualSignatureRequest):
            raise TypeError(
                "series_visual_signature_request must be the canonical SeriesVisualSignatureRequest"
            )

        legacy_profile = values.pop("series_visual_signature_profile", None)
        # Scene casts belonged to the removed recurring-IP planning runtime. They
        # remain accepted only so historical callers do not fail at the boundary.
        values.pop("scene_casts_by_frame", None)

        legacy_controls = {
            key: values.pop(key)
            for key in _LEGACY_SIGNATURE_ARGUMENTS
            if key in values
        }
        if request is None:
            request = _request_from_legacy_controls(
                legacy_controls,
                ip_profile=values.get("ip_profile"),
            )

        profile_snapshot = None
        if request.enabled and legacy_profile is not None:
            profile_snapshot = SeriesVisualSignatureProfileSnapshotBuilder().build(
                request=request,
                legacy_profile=legacy_profile,
            )

        return await VisualPromptComposer().compose(
            **values,
            series_visual_signature_request=request,
            series_visual_signature_profile_snapshot=profile_snapshot,
        )


def _request_from_legacy_controls(
    controls: dict[str, Any],
    *,
    ip_profile: Any,
) -> SeriesVisualSignatureRequest:
    payload = {
        key: value
        for key, value in controls.items()
        if value is not None
    }
    request = SeriesVisualSignatureRequest.from_mapping(
        payload,
        profile_id=getattr(
            ip_profile,
            "series_visual_signature_profile_id",
            None,
        ),
    )
    return request


__all__ = ["ImagePromptComposer", "VisualPromptComposer"]
