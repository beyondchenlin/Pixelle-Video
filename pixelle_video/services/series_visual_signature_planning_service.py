from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.services.series_visual_signature_contract_builder import (
    SeriesVisualSignatureContractBuilder,
)

ProfileResolver = Callable[[str], Mapping[str, Any] | VisualSignatureProfileSnapshot | None]


class SeriesVisualSignaturePlanningService:
    """Cutover target for recurring visual-signature contract planning.

    The service owns canonical request parsing, profile resolution, and contract
    construction. Existing production callers may still use compatibility
    planners until the migration bridge is enabled and validated.
    """

    def __init__(self, *, profile_resolver: ProfileResolver | None = None) -> None:
        self._profile_resolver = profile_resolver
        self._builder = SeriesVisualSignatureContractBuilder()

    def build_contract(
        self,
        *,
        video_params: Mapping[str, Any] | None,
        strict_user_mode: bool = False,
    ) -> SeriesVisualSignatureContract:
        request = SeriesVisualSignatureRequest.from_mapping(video_params)
        profile = self._resolve_profile(request.profile_id, video_params)
        return self._builder.build(
            request=request,
            profile=profile,
            strict_user_mode=strict_user_mode,
            role_context=video_params,
        )

    def _resolve_profile(
        self,
        profile_id: str | None,
        video_params: Mapping[str, Any] | None,
    ) -> Mapping[str, Any] | VisualSignatureProfileSnapshot | None:
        if video_params and isinstance(video_params.get("series_visual_signature_profile"), Mapping):
            return video_params["series_visual_signature_profile"]
        if profile_id and self._profile_resolver:
            return self._profile_resolver(profile_id)
        return None
