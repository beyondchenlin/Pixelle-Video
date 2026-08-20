from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.models.series_visual_signature import (
    FORBIDDEN_TEXT_CHARACTER_ROLES,
    SeriesVisualSignatureContract,
    SeriesVisualSignatureRequest,
    SeriesVisualSignatureRole,
    SignatureReplacementPolicy,
    VisualSignatureProfileSnapshot,
    relative_size_from_max_area_ratio,
)
from pixelle_video.services.series_visual_signature_role_resolver import (
    resolve_series_visual_signature_role,
)

_ROLE_MAX_AREA_RATIO = {
    SeriesVisualSignatureRole.CORE_ACTOR: 0.45,
    SeriesVisualSignatureRole.SILENT_WITNESS: 0.16,
    SeriesVisualSignatureRole.OPERATOR: 0.28,
    SeriesVisualSignatureRole.GUIDE: 0.20,
}

_ROLE_RULES = {
    SeriesVisualSignatureRole.CORE_ACTOR: "The visual signature may lead action only while article-required subjects stay visible.",
    SeriesVisualSignatureRole.SILENT_WITNESS: "The visual signature observes quietly and must not drive the visual explanation.",
    SeriesVisualSignatureRole.OPERATOR: "The visual signature operates a diagram element or process handle without replacing article subjects.",
    SeriesVisualSignatureRole.GUIDE: "The visual signature points to the reading path or relation line as a small guide.",
}


class SeriesVisualSignatureContractBuilder:
    def build(
        self,
        *,
        request: SeriesVisualSignatureRequest | Mapping[str, Any] | None,
        profile: VisualSignatureProfileSnapshot | Mapping[str, Any] | None = None,
        strict_user_mode: bool = False,
        role_context: Mapping[str, Any] | None = None,
    ) -> SeriesVisualSignatureContract:
        normalized_request = (
            request
            if isinstance(request, SeriesVisualSignatureRequest)
            else SeriesVisualSignatureRequest.from_mapping(request)
        )
        if not normalized_request.enabled:
            return SeriesVisualSignatureContract.disabled()
        if normalized_request.profile_id is None:
            raise ValueError(
                "enabled series visual signature requires series_visual_signature_profile_id"
            )

        normalized_profile = self._normalize_profile(profile)
        if normalized_profile is None:
            raise ValueError(
                "enabled series visual signature profile could not be resolved: "
                f"{normalized_request.profile_id}"
            )
        if normalized_profile.profile_id != normalized_request.profile_id:
            raise ValueError(
                "resolved series visual signature profile does not match request profile_id: "
                f"requested={normalized_request.profile_id}, resolved={normalized_profile.profile_id}"
            )

        role = resolve_series_visual_signature_role(
            normalized_request.role,
            context=role_context,
        )
        if role in FORBIDDEN_TEXT_CHARACTER_ROLES:
            raise ValueError(
                "text character role is incompatible with recurring identity: "
                f"{role.value}"
            )
        role_limit = _ROLE_MAX_AREA_RATIO[role]
        requested_area = normalized_request.max_area_ratio
        if requested_area is not None and requested_area > role_limit:
            raise ValueError(
                "series_visual_signature_max_area_ratio exceeds the semantic limit for "
                f"role {role.value}: requested={requested_area}, max={role_limit}"
            )
        max_area_ratio = requested_area if requested_area is not None else role_limit
        return SeriesVisualSignatureContract(
            enabled=True,
            role=role,
            profile=normalized_profile,
            replacement_policy=SignatureReplacementPolicy.NO_SUBJECT_REPLACEMENT,
            max_area_ratio=max_area_ratio,
            relative_size=relative_size_from_max_area_ratio(max_area_ratio),
            participation_rule=_ROLE_RULES[role],
            style_integration_rule=(
                "Draw the signature in the same render surface as the scene; "
                "never photorealistic unless the whole scene is photorealistic."
            ),
            forbidden_behaviors=(
                "do not replace required article subjects",
                "do not appear as a sticker, logo, watermark, or corner badge",
                "do not use photorealistic animal or mascot language in hand-drawn styles",
                "do not exceed the configured relative size",
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
