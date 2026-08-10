from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pixelle_video.models.series_visual_signature import (
    SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION,
    SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION,
    SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS,
    SeriesVisualSignatureRequest,
    is_supported_series_visual_signature_pipeline_version,
)
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
from pixelle_video.utils.bool_parsing import coerce_bool

SERIES_VISUAL_SIGNATURE_CONTROL_OPTION_KEYS = frozenset(
    {
        "series_visual_signature_enabled",
        "series_visual_signature_asset_bible_id",
        "series_visual_signature_profile_id",
        "series_visual_signature_role",
        "series_visual_signature_max_area_ratio",
        "series_visual_signature_user_hint",
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
    """Compatibility adapter for old product-level controls.

    It validates legacy/product controls and produces the canonical
    ``models.series_visual_signature.SeriesVisualSignatureRequest``. This module
    intentionally does not define a second request runtime type or a second set
    of pipeline-version facts.
    """

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
    source_mapping: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

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
            enabled=coerce_bool(mapping.get("series_visual_signature_enabled", False), default=False),
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
            source_mapping=mapping,
        )

    @property
    def effective_signature_mode(self) -> SeriesVisualSignatureMode:
        return self.strategy.effective_signature_mode

    @property
    def has_explicit_v4_fields(self) -> bool:
        return bool(set(self.explicit_fields) & _SERIES_VISUAL_SIGNATURE_V4_OPTION_KEYS)

    def to_generation_dict(self) -> dict[str, Any]:
        if not self.enabled:
            return {}
        return {
            "series_visual_signature_expression_mode": self.expression_mode.value,
            "series_visual_signature_structure_mode": self.structure_mode.value,
            "series_visual_signature_participation_mode": self.participation_mode.value,
            **self.presentation_policy.to_generation_dict(),
        }

    def to_request(self) -> SeriesVisualSignatureRequest:
        payload = {
            **dict(self.source_mapping),
            **self.to_generation_dict(),
            "series_visual_signature_enabled": self.enabled,
        }
        if self.asset_bible_id is not None:
            payload["series_visual_signature_asset_bible_id"] = self.asset_bible_id
        if self.profile_id is not None:
            payload["series_visual_signature_profile_id"] = self.profile_id
        if self.generation_world_hint is not None:
            payload["generation_world_hint"] = self.generation_world_hint
        return SeriesVisualSignatureRequest.from_mapping(
            payload,
            asset_bible_id=self.asset_bible_id,
            profile_id=self.profile_id,
            generation_world_hint=self.generation_world_hint,
        )

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


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


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
