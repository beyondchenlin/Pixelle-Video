from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    SeriesVisualSignatureRequest,
    SeriesVisualSignatureRole,
    SignatureReplacementPolicy,
    VisualSignatureProfileSnapshot,
)

_ROLE_MAX_AREA_RATIO = {
    SeriesVisualSignatureRole.CORE_ACTOR: 0.45,
    SeriesVisualSignatureRole.SILENT_WITNESS: 0.16,
    SeriesVisualSignatureRole.OPERATOR: 0.28,
    SeriesVisualSignatureRole.GUIDE: 0.20,
    SeriesVisualSignatureRole.OBSTACLE: 0.25,
    SeriesVisualSignatureRole.CONTAINER: 0.22,
    SeriesVisualSignatureRole.BACKGROUND_MARK: 0.10,
}

_ROLE_RULES = {
    SeriesVisualSignatureRole.CORE_ACTOR: "The visual signature may lead action only while article-required subjects stay visible.",
    SeriesVisualSignatureRole.SILENT_WITNESS: "The visual signature observes quietly and must not drive the visual explanation.",
    SeriesVisualSignatureRole.OPERATOR: "The visual signature operates a diagram element or process handle without replacing article subjects.",
    SeriesVisualSignatureRole.GUIDE: "The visual signature points to the reading path or relation line as a small guide.",
    SeriesVisualSignatureRole.OBSTACLE: "The visual signature embodies resistance only when the article explicitly needs an obstacle.",
    SeriesVisualSignatureRole.CONTAINER: "The visual signature frames or contains the structure without becoming the subject.",
    SeriesVisualSignatureRole.BACKGROUND_MARK: "The visual signature appears only as a low-weight background recognition mark.",
}


class SeriesVisualSignatureContractBuilder:
    def build(
        self,
        *,
        request: SeriesVisualSignatureRequest | Mapping[str, Any] | None,
        profile: VisualSignatureProfileSnapshot | Mapping[str, Any] | None = None,
        strict_user_mode: bool = False,
    ) -> SeriesVisualSignatureContract:
        normalized_request = (
            request
            if isinstance(request, SeriesVisualSignatureRequest)
            else SeriesVisualSignatureRequest.from_mapping(request)
        )
        if not normalized_request.enabled:
            return SeriesVisualSignatureContract.disabled()

        normalized_request.validate()
        normalized_profile = self._normalize_profile(profile)
        if normalized_profile is None:
            profile_id = normalized_request.profile_id or "<missing>"
            raise ValueError(
                "enabled series visual signature profile could not be resolved: "
                f"{profile_id}"
            )
        if normalized_profile.profile_id != normalized_request.profile_id:
            raise ValueError(
                "resolved series visual signature profile does not match request profile_id: "
                f"requested={normalized_request.profile_id}, resolved={normalized_profile.profile_id}"
            )

        role = self._resolve_role(normalized_request.role)
        requested_area = normalized_request.max_area_ratio
        max_area_ratio = (
            requested_area
            if requested_area is not None
            else _ROLE_MAX_AREA_RATIO[role]
        )
        return SeriesVisualSignatureContract(
            enabled=True,
            role=role,
            profile=normalized_profile,
            replacement_policy=SignatureReplacementPolicy.NO_SUBJECT_REPLACEMENT,
            max_area_ratio=max_area_ratio,
            participation_rule=_ROLE_RULES[role],
            style_integration_rule=(
                "Draw the signature in the same render surface as the scene; "
                "never photorealistic unless the whole scene is photorealistic."
            ),
            forbidden_behaviors=(
                "do not replace required article subjects",
                "do not appear as a sticker, logo, watermark, or corner badge",
                "do not use photorealistic animal or mascot language in hand-drawn styles",
                "do not exceed max_area_ratio",
            ),
        )

    def _normalize_profile(
        self,
        profile: VisualSignatureProfileSnapshot | Mapping[str, Any] | None,
    ) -> VisualSignatureProfileSnapshot | None:
        if isinstance(profile, VisualSignatureProfileSnapshot):
            return profile
        if isinstance(profile, Mapping):
            return VisualSignatureProfileSnapshot.from_mapping(profile)
        return None

    def _resolve_role(self, role: SeriesVisualSignatureRole) -> SeriesVisualSignatureRole:
        # ``none`` used to leak in from article-concretization defaults even when
        # the global visual signature switch was enabled. The global enabled flag
        # owns presence; an unset/none role therefore means automatic role choice.
        if role in {SeriesVisualSignatureRole.NONE, SeriesVisualSignatureRole.AUTO}:
            return SeriesVisualSignatureRole.GUIDE
        return role
