from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pixelle_video.models.visual_expression import VisualExpressionMode
from pixelle_video.models.visual_role_identity import (
    VisualRoleParticipationMode,
    VisualRoleStructureMode,
)
from pixelle_video.models.visual_role_strategy import VisualRoleMode, VisualRoleStrategyControls

VISUAL_ROLE_LEGACY_PIPELINE_VERSION = "v4_expression"
VISUAL_ROLE_PIPELINE_VERSION = "v4_2_identity_contract"
SUPPORTED_VISUAL_ROLE_PIPELINE_VERSIONS = frozenset(
    {
        VISUAL_ROLE_LEGACY_PIPELINE_VERSION,
        VISUAL_ROLE_PIPELINE_VERSION,
    }
)
VISUAL_ROLE_CONTROL_OPTION_KEYS = frozenset(
    {
        "ip_enabled",
        "ip_asset_bible_id",
        "ip_profile_id",
        "visual_expression_mode",
        "visual_structure_mode",
        "visual_participation_mode",
        "visual_role_mode",
        "visual_consistency_mode",
        "generation_world_hint",
    }
)
_VISUAL_ROLE_V4_OPTION_KEYS = frozenset(
    {
        "visual_expression_mode",
        "visual_structure_mode",
        "visual_participation_mode",
        "visual_role_mode",
        "visual_consistency_mode",
    }
)


@dataclass(frozen=True)
class VisualRoleControlsContract:
    enabled: bool = False
    asset_bible_id: str | None = None
    profile_id: str | None = None
    expression_mode: VisualExpressionMode = VisualExpressionMode.AUTO
    structure_mode: VisualRoleStructureMode = VisualRoleStructureMode.AUTO
    participation_mode: VisualRoleParticipationMode = VisualRoleParticipationMode.AUTO
    strategy: VisualRoleStrategyControls = field(default_factory=VisualRoleStrategyControls)
    generation_world_hint: str | None = None
    explicit_fields: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any] | None) -> "VisualRoleControlsContract":
        mapping = dict(source or {})
        explicit_fields = tuple(
            key
            for key in sorted(VISUAL_ROLE_CONTROL_OPTION_KEYS)
            if key in mapping and mapping.get(key) is not None
        )
        return cls(
            enabled=bool(mapping.get("ip_enabled", False)),
            asset_bible_id=_normalize_optional_string(mapping.get("ip_asset_bible_id")),
            profile_id=_normalize_optional_string(mapping.get("ip_profile_id")),
            expression_mode=VisualExpressionMode.from_value(mapping.get("visual_expression_mode")),
            structure_mode=VisualRoleStructureMode.from_value(mapping.get("visual_structure_mode")),
            participation_mode=VisualRoleParticipationMode.from_value(
                mapping.get("visual_participation_mode")
            ),
            strategy=VisualRoleStrategyControls.from_mapping(mapping),
            generation_world_hint=_normalize_optional_string(mapping.get("generation_world_hint")),
            explicit_fields=explicit_fields,
        )

    @property
    def effective_role_mode(self) -> VisualRoleMode:
        return self.strategy.effective_role_mode

    @property
    def has_explicit_v4_fields(self) -> bool:
        return bool(set(self.explicit_fields) & _VISUAL_ROLE_V4_OPTION_KEYS)

    def to_generation_dict(self) -> dict[str, Any]:
        if not self.enabled and not self.has_explicit_v4_fields:
            return {}
        return {
            "visual_expression_mode": self.expression_mode.value,
            "visual_structure_mode": self.structure_mode.value,
            "visual_participation_mode": self.participation_mode.value,
            **self.strategy.to_dict(),
        }

    def to_request(self) -> "VisualRoleRequest":
        return VisualRoleRequest.from_controls(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "asset_bible_id": self.asset_bible_id,
            "profile_id": self.profile_id,
            "visual_expression_mode": self.expression_mode.value,
            "visual_structure_mode": self.structure_mode.value,
            "visual_participation_mode": self.participation_mode.value,
            **self.strategy.to_dict(),
            "generation_world_hint": self.generation_world_hint,
            "explicit_fields": list(self.explicit_fields),
        }


@dataclass(frozen=True)
class VisualRoleRequest:
    enabled: bool
    asset_bible_id: str | None = None
    profile_id: str | None = None
    strategy: VisualRoleStrategyControls = field(default_factory=VisualRoleStrategyControls)
    expression_mode: VisualExpressionMode = VisualExpressionMode.AUTO
    structure_mode: VisualRoleStructureMode = VisualRoleStructureMode.AUTO
    participation_mode: VisualRoleParticipationMode = VisualRoleParticipationMode.AUTO
    generation_world_hint: str | None = None
    pipeline_version: str = VISUAL_ROLE_PIPELINE_VERSION

    @classmethod
    def disabled(cls) -> "VisualRoleRequest":
        return cls(enabled=False)

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, Any] | None,
        *,
        asset_bible_id: str | None = None,
        profile_id: str | None = None,
        generation_world_hint: str | None = None,
    ) -> "VisualRoleRequest":
        controls = VisualRoleControlsContract.from_mapping(source)
        return cls(
            enabled=controls.enabled,
            asset_bible_id=asset_bible_id or controls.asset_bible_id,
            profile_id=profile_id or controls.profile_id,
            strategy=controls.strategy,
            expression_mode=controls.expression_mode,
            structure_mode=controls.structure_mode,
            participation_mode=controls.participation_mode,
            generation_world_hint=generation_world_hint or controls.generation_world_hint,
            pipeline_version=VISUAL_ROLE_PIPELINE_VERSION,
        )

    @classmethod
    def from_legacy_params(
        cls,
        source: Mapping[str, Any] | None,
        *,
        asset_bible_id: str | None = None,
        profile_id: str | None = None,
        generation_world_hint: str | None = None,
    ) -> "VisualRoleRequest":
        return cls.from_mapping(
            source,
            asset_bible_id=asset_bible_id,
            profile_id=profile_id,
            generation_world_hint=generation_world_hint,
        )

    @classmethod
    def from_controls(cls, controls: VisualRoleControlsContract) -> "VisualRoleRequest":
        return cls(
            enabled=controls.enabled,
            asset_bible_id=controls.asset_bible_id,
            profile_id=controls.profile_id,
            strategy=controls.strategy,
            expression_mode=controls.expression_mode,
            structure_mode=controls.structure_mode,
            participation_mode=controls.participation_mode,
            generation_world_hint=controls.generation_world_hint,
            pipeline_version=VISUAL_ROLE_PIPELINE_VERSION,
        )

    @property
    def effective_role_mode(self) -> VisualRoleMode:
        return self.strategy.effective_role_mode

    def validate(self) -> None:
        if not self.enabled:
            return
        if self.asset_bible_id is None:
            raise ValueError("asset_bible_id is required when visual role is enabled")
        if self.profile_id is None:
            raise ValueError("profile_id is required when visual role is enabled")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "enabled": self.enabled,
            "pipeline_version": self.pipeline_version,
            "visual_expression_mode": self.expression_mode.value,
            "visual_structure_mode": self.structure_mode.value,
            "visual_participation_mode": self.participation_mode.value,
            **self.strategy.to_dict(),
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


def is_supported_visual_role_pipeline_version(value: Any) -> bool:
    return str(value or "").strip() in SUPPORTED_VISUAL_ROLE_PIPELINE_VERSIONS


VisualRoleRequestContract = VisualRoleControlsContract


__all__ = [
    "SUPPORTED_VISUAL_ROLE_PIPELINE_VERSIONS",
    "VISUAL_ROLE_LEGACY_PIPELINE_VERSION",
    "VISUAL_ROLE_CONTROL_OPTION_KEYS",
    "VISUAL_ROLE_PIPELINE_VERSION",
    "VisualRoleControlsContract",
    "VisualRoleRequest",
    "VisualRoleRequestContract",
    "is_supported_visual_role_pipeline_version",
]
