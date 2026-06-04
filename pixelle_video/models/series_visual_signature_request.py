from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pixelle_video.models.series_visual_signature_identity import (
    SeriesVisualSignatureParticipationMode,
    SeriesVisualSignatureStructureMode,
)
from pixelle_video.models.series_visual_signature_presentation import (
    PRESENTATION_CONTROL_OPTION_KEYS,
    SeriesVisualSignaturePresentationPolicy,
)
from pixelle_video.models.series_visual_signature_strategy import (
    SeriesVisualSignatureMode,
    SeriesVisualSignatureStrategyControls,
)
from pixelle_video.models.visual_expression import VisualExpressionMode

SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION = "v4_expression"
SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION = "v4_2_identity_contract"
SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS = frozenset(
    {
        SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION,
        SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION,
    }
)
SERIES_VISUAL_SIGNATURE_CONTROL_OPTION_KEYS = frozenset(
    {
        "series_visual_signature_enabled",
        "series_visual_signature_asset_bible_id",
        "series_visual_signature_profile_id",
        "series_visual_signature_expression_mode",
        "series_visual_signature_structure_mode",
        "series_visual_signature_participation_mode",
        "series_visual_signature_mode",
        "series_visual_signature_consistency_mode",
        "generation_world_hint",
        *PRESENTATION_CONTROL_OPTION_KEYS,
    }
)
_SERIES_VISUAL_SIGNATURE_V4_OPTION_KEYS = frozenset(
    {
        "series_visual_signature_expression_mode",
        "series_visual_signature_structure_mode",
        "series_visual_signature_participation_mode",
        "series_visual_signature_mode",
        "series_visual_signature_consistency_mode",
        *PRESENTATION_CONTROL_OPTION_KEYS,
    }
)


@dataclass(frozen=True)
class SeriesVisualSignatureControlsContract:
    enabled: bool = False
    asset_bible_id: str | None = None
    profile_id: str | None = None
    expression_mode: VisualExpressionMode = VisualExpressionMode.AUTO
    structure_mode: SeriesVisualSignatureStructureMode = SeriesVisualSignatureStructureMode.AUTO
    participation_mode: SeriesVisualSignatureParticipationMode = SeriesVisualSignatureParticipationMode.AUTO
    strategy: SeriesVisualSignatureStrategyControls = field(default_factory=SeriesVisualSignatureStrategyControls)
    presentation_policy: SeriesVisualSignaturePresentationPolicy = field(default_factory=SeriesVisualSignaturePresentationPolicy)
    generation_world_hint: str | None = None
    explicit_fields: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any] | None) -> "SeriesVisualSignatureControlsContract":
        mapping = dict(source or {})
        explicit_fields = tuple(
            key
            for key in sorted(SERIES_VISUAL_SIGNATURE_CONTROL_OPTION_KEYS)
            if key in mapping and mapping.get(key) is not None
        )
        presentation_policy = SeriesVisualSignaturePresentationPolicy.from_mapping(mapping)
        return cls(
            enabled=bool(mapping.get("series_visual_signature_enabled", False)),
            asset_bible_id=_normalize_optional_string(mapping.get("series_visual_signature_asset_bible_id")),
            profile_id=_normalize_optional_string(mapping.get("series_visual_signature_profile_id")),
            expression_mode=VisualExpressionMode.from_value(mapping.get("series_visual_signature_expression_mode")),
            structure_mode=SeriesVisualSignatureStructureMode.from_value(mapping.get("series_visual_signature_structure_mode")),
            participation_mode=SeriesVisualSignatureParticipationMode.from_value(
                mapping.get("series_visual_signature_participation_mode")
            ),
            strategy=presentation_policy.strategy_controls(),
            presentation_policy=presentation_policy,
            generation_world_hint=_normalize_optional_string(mapping.get("generation_world_hint")),
            explicit_fields=explicit_fields,
        )

    @property
    def effective_signature_mode(self) -> SeriesVisualSignatureMode:
        return self.strategy.effective_signature_mode

    @property
    def has_explicit_v4_fields(self) -> bool:
        return bool(set(self.explicit_fields) & _SERIES_VISUAL_SIGNATURE_V4_OPTION_KEYS)

    def to_generation_dict(self) -> dict[str, Any]:
        if not self.enabled and not self.has_explicit_v4_fields:
            return {}
        return {
            "series_visual_signature_expression_mode": self.expression_mode.value,
            "series_visual_signature_structure_mode": self.structure_mode.value,
            "series_visual_signature_participation_mode": self.participation_mode.value,
            **self.presentation_policy.to_generation_dict(),
        }

    def to_request(self) -> "SeriesVisualSignatureRequest":
        return SeriesVisualSignatureRequest.from_controls(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "asset_bible_id": self.asset_bible_id,
            "profile_id": self.profile_id,
            "series_visual_signature_expression_mode": self.expression_mode.value,
            "series_visual_signature_structure_mode": self.structure_mode.value,
            "series_visual_signature_participation_mode": self.participation_mode.value,
            **self.presentation_policy.to_dict(),
            "generation_world_hint": self.generation_world_hint,
            "explicit_fields": list(self.explicit_fields),
        }


@dataclass(frozen=True)
class SeriesVisualSignatureRequest:
    enabled: bool
    asset_bible_id: str | None = None
    profile_id: str | None = None
    strategy: SeriesVisualSignatureStrategyControls = field(default_factory=SeriesVisualSignatureStrategyControls)
    presentation_policy: SeriesVisualSignaturePresentationPolicy = field(default_factory=SeriesVisualSignaturePresentationPolicy)
    expression_mode: VisualExpressionMode = VisualExpressionMode.AUTO
    structure_mode: SeriesVisualSignatureStructureMode = SeriesVisualSignatureStructureMode.AUTO
    participation_mode: SeriesVisualSignatureParticipationMode = SeriesVisualSignatureParticipationMode.AUTO
    generation_world_hint: str | None = None
    pipeline_version: str = SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION

    @classmethod
    def disabled(cls) -> "SeriesVisualSignatureRequest":
        return cls(enabled=False)

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, Any] | None,
        *,
        asset_bible_id: str | None = None,
        profile_id: str | None = None,
        generation_world_hint: str | None = None,
    ) -> "SeriesVisualSignatureRequest":
        controls = SeriesVisualSignatureControlsContract.from_mapping(source)
        return cls(
            enabled=controls.enabled,
            asset_bible_id=asset_bible_id or controls.asset_bible_id,
            profile_id=profile_id or controls.profile_id,
            strategy=controls.strategy,
            presentation_policy=controls.presentation_policy,
            expression_mode=controls.expression_mode,
            structure_mode=controls.structure_mode,
            participation_mode=controls.participation_mode,
            generation_world_hint=generation_world_hint or controls.generation_world_hint,
            pipeline_version=SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION,
        )

    @classmethod
    def from_legacy_params(
        cls,
        source: Mapping[str, Any] | None,
        *,
        asset_bible_id: str | None = None,
        profile_id: str | None = None,
        generation_world_hint: str | None = None,
    ) -> "SeriesVisualSignatureRequest":
        return cls.from_mapping(
            source,
            asset_bible_id=asset_bible_id,
            profile_id=profile_id,
            generation_world_hint=generation_world_hint,
        )

    @classmethod
    def from_controls(cls, controls: SeriesVisualSignatureControlsContract) -> "SeriesVisualSignatureRequest":
        return cls(
            enabled=controls.enabled,
            asset_bible_id=controls.asset_bible_id,
            profile_id=controls.profile_id,
            strategy=controls.strategy,
            presentation_policy=controls.presentation_policy,
            expression_mode=controls.expression_mode,
            structure_mode=controls.structure_mode,
            participation_mode=controls.participation_mode,
            generation_world_hint=controls.generation_world_hint,
            pipeline_version=SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION,
        )

    @property
    def effective_signature_mode(self) -> SeriesVisualSignatureMode:
        return self.strategy.effective_signature_mode

    def validate(self) -> None:
        if not self.enabled:
            return
        if self.asset_bible_id is None:
            raise ValueError("asset_bible_id is required when series visual signature is enabled")
        if self.profile_id is None:
            raise ValueError("profile_id is required when series visual signature is enabled")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "enabled": self.enabled,
            "pipeline_version": self.pipeline_version,
            "series_visual_signature_expression_mode": self.expression_mode.value,
            "series_visual_signature_structure_mode": self.structure_mode.value,
            "series_visual_signature_participation_mode": self.participation_mode.value,
            **self.presentation_policy.to_dict(),
        }
        if self.asset_bible_id is not None:
            payload["asset_bible_id"] = self.asset_bible_id
        if self.profile_id is not None:
            payload["profile_id"] = self.profile_id
        if self.generation_world_hint is not None:
            payload["generation_world_hint"] = self.generation_world_hint
        return payload


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def is_supported_series_visual_signature_pipeline_version(value: Any) -> bool:
    return str(value or "").strip() in SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS


SeriesVisualSignatureRequestContract = SeriesVisualSignatureControlsContract

__all__ = [
    "SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS",
    "SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION",
    "SERIES_VISUAL_SIGNATURE_CONTROL_OPTION_KEYS",
    "SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION",
    "SeriesVisualSignatureControlsContract",
    "SeriesVisualSignatureRequest",
    "SeriesVisualSignatureRequestContract",
    "is_supported_series_visual_signature_pipeline_version",
]
