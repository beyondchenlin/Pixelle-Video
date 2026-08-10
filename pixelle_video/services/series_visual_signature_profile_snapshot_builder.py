from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.models.series_visual_signature_profile import SeriesVisualSignatureProfile


class SeriesVisualSignatureProfileSnapshotBuilder:
    """Build the canonical runtime profile without inventing identity facts.

    The Asset Bible/IPProfile remains the persisted source. This builder only
    selects explicit identity fields and never derives identity from a profile id,
    display name, world hint, style hint, or free-form prompt paragraph.
    """

    def build(
        self,
        *,
        request: SeriesVisualSignatureRequest,
        ip_profile: Any = None,
        legacy_profile: SeriesVisualSignatureProfile | None = None,
    ) -> VisualSignatureProfileSnapshot:
        if not request.enabled:
            raise ValueError("disabled series visual signature does not require a profile snapshot")
        if request.profile_id is None:
            raise ValueError("enabled series visual signature requires profile_id")

        if legacy_profile is not None:
            return self._from_legacy_profile(request, legacy_profile)
        if ip_profile is not None:
            return self._from_ip_profile(request, ip_profile)
        raise ValueError(
            "enabled series visual signature requires a resolved Asset Bible IPProfile"
        )

    def _from_ip_profile(
        self,
        request: SeriesVisualSignatureRequest,
        ip_profile: Any,
    ) -> VisualSignatureProfileSnapshot:
        profile_id = _text(
            getattr(ip_profile, "series_visual_signature_profile_id", None)
        )
        if profile_id != request.profile_id:
            raise ValueError(
                "resolved IPProfile does not match request profile_id: "
                f"requested={request.profile_id}, resolved={profile_id or '<empty>'}"
            )
        display_name = _text(getattr(ip_profile, "name", None))
        if not display_name:
            raise ValueError("resolved IPProfile must provide a display name")

        identity_traits = _first_non_empty_sequence(
            getattr(ip_profile, "identity_lock", ()),
            getattr(ip_profile, "minimal_traits", ()),
            getattr(ip_profile, "identity_anchors", ()),
        )
        if not identity_traits:
            raise ValueError(
                "resolved IPProfile must provide explicit identity_lock, minimal_traits, "
                "or identity_anchors; identity cannot be inferred from prose"
            )

        forbidden_traits = _safe_forbidden_traits(
            getattr(ip_profile, "forbidden_elements", ()),
        )
        source_asset_ids = _source_asset_ids(getattr(ip_profile, "metadata", {}))
        return VisualSignatureProfileSnapshot(
            profile_id=profile_id,
            display_name=display_name,
            identity_traits=identity_traits,
            style_safe_traits=(),
            forbidden_traits=forbidden_traits,
            source_asset_ids=source_asset_ids,
        )

    def _from_legacy_profile(
        self,
        request: SeriesVisualSignatureRequest,
        profile: SeriesVisualSignatureProfile,
    ) -> VisualSignatureProfileSnapshot:
        if profile.profile_id != request.profile_id:
            raise ValueError(
                "resolved SeriesVisualSignatureProfile does not match request profile_id: "
                f"requested={request.profile_id}, resolved={profile.profile_id}"
            )
        identity_traits = _dedupe(
            profile.identity_contract.required_identity_traits
            or profile.identity_kernel
        )
        if not identity_traits:
            raise ValueError("resolved legacy profile has no explicit identity traits")
        return VisualSignatureProfileSnapshot(
            profile_id=profile.profile_id,
            display_name=profile.display_name,
            identity_traits=identity_traits,
            style_safe_traits=(),
            forbidden_traits=(),
            source_asset_ids=tuple(profile.reference_assets),
        )


def _first_non_empty_sequence(*values: Any) -> tuple[str, ...]:
    for value in values:
        result = _dedupe(value)
        if result:
            return result
    return ()


def _safe_forbidden_traits(values: Any) -> tuple[str, ...]:
    """Keep short appearance nouns only; instruction-like negatives stay upstream."""

    result: list[str] = []
    for value in _sequence(values):
        text = _text(value)
        if not text or len(text) > 64:
            continue
        lowered = text.casefold()
        if any(token in lowered for token in ("do ", "don't", "must ", "should ", "never ", "always ", "prompt")):
            continue
        result.append(text)
    return _dedupe(result)


def _source_asset_ids(metadata: Any) -> tuple[str, ...]:
    if not isinstance(metadata, Mapping):
        return ()
    for key in ("source_asset_ids", "reference_asset_ids", "reference_assets"):
        value = metadata.get(key)
        result = _dedupe(value)
        if result:
            return result
    return ()


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return ()


def _dedupe(value: Any) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for item in _sequence(value):
        text = _text(item)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return tuple(result)


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


__all__ = ["SeriesVisualSignatureProfileSnapshotBuilder"]
