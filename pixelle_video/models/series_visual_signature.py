from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pixelle_video.architecture.legacy_signature_field_guard import (
    reject_deprecated_signature_fields,
    reject_prompt_paragraph_profile_fields,
)


class SeriesVisualSignatureRole(str, Enum):
    NONE = "none"
    AUTO = "auto"
    CORE_ACTOR = "core_actor"
    SILENT_WITNESS = "silent_witness"
    OPERATOR = "operator"
    GUIDE = "guide"
    OBSTACLE = "obstacle"
    CONTAINER = "container"
    BACKGROUND_MARK = "background_mark"


class SignatureReplacementPolicy(str, Enum):
    NO_SUBJECT_REPLACEMENT = "no_subject_replacement"
    MAY_LEAD_WITH_SUBJECTS_VISIBLE = "may_lead_with_subjects_visible"
    BACKGROUND_ONLY = "background_only"


MAX_TRAIT_CHARS = 64
SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION = "v4_5_single_runtime"
_FORBIDDEN_TRAIT_TERMS = (
    "always",
    "every scene",
    "foreground",
    "photorealistic",
    "realistic fur",
    "highly detailed",
    "best quality",
    "prompt",
    "negative prompt",
    "provider",
    "watermark",
    "logo",
)


@dataclass(frozen=True)
class SeriesVisualSignatureRequest:
    """Canonical request for a recurring visual signature.

    The request is global and provider-agnostic. Compatibility presentation
    controls may still enter through ``compatibility_options`` while callers are
    migrated, but there is only one request type and one role field.
    """

    enabled: bool = False
    profile_id: str | None = None
    role: SeriesVisualSignatureRole | str = SeriesVisualSignatureRole.NONE
    role_was_explicit: bool = False
    max_area_ratio: float | None = None
    user_hint: str | None = None
    asset_bible_id: str | None = None
    generation_world_hint: str | None = None
    compatibility_options: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", _bool_value(self.enabled, "series_visual_signature_enabled"))
        object.__setattr__(self, "profile_id", _optional_text(self.profile_id))
        object.__setattr__(
            self,
            "role",
            _enum_value(
                "series_visual_signature_role",
                self.role,
                SeriesVisualSignatureRole,
                SeriesVisualSignatureRole.AUTO if self.enabled else SeriesVisualSignatureRole.NONE,
            ),
        )
        object.__setattr__(
            self,
            "role_was_explicit",
            _bool_value(self.role_was_explicit, "series_visual_signature_role_was_explicit"),
        )
        object.__setattr__(
            self,
            "max_area_ratio",
            _optional_ratio(self.max_area_ratio, "series_visual_signature_max_area_ratio"),
        )
        object.__setattr__(self, "user_hint", _optional_text(self.user_hint, max_chars=300))
        object.__setattr__(self, "asset_bible_id", _optional_text(self.asset_bible_id))
        object.__setattr__(self, "generation_world_hint", _optional_text(self.generation_world_hint, max_chars=4000))
        object.__setattr__(self, "compatibility_options", dict(self.compatibility_options or {}))

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, Any] | None,
        *,
        asset_bible_id: str | None = None,
        profile_id: str | None = None,
        generation_world_hint: str | None = None,
    ) -> "SeriesVisualSignatureRequest":
        data = dict(source or {})
        reject_deprecated_signature_fields(data, context="series visual signature request")
        nested = data.get("series_visual_signature")
        if isinstance(nested, Mapping):
            reject_deprecated_signature_fields(nested, context="series visual signature request")
            data = {**data, **nested}

        enabled = _bool_value(
            data.get("series_visual_signature_enabled", data.get("enabled", False)),
            "series_visual_signature_enabled",
        )
        role_present = "series_visual_signature_role" in data or "role" in data
        default_role = SeriesVisualSignatureRole.AUTO if enabled else SeriesVisualSignatureRole.NONE
        compatibility_options = {
            str(key): value
            for key, value in data.items()
            if str(key).startswith("series_visual_signature_")
        }
        return cls(
            enabled=enabled,
            asset_bible_id=asset_bible_id
            or data.get("series_visual_signature_asset_bible_id")
            or data.get("asset_bible_id"),
            profile_id=profile_id
            or data.get("series_visual_signature_profile_id")
            or data.get("profile_id"),
            role=data.get("series_visual_signature_role", data.get("role", default_role)),
            role_was_explicit=data.get("series_visual_signature_role_was_explicit", role_present),
            max_area_ratio=data.get("series_visual_signature_max_area_ratio", data.get("max_area_ratio")),
            user_hint=data.get("series_visual_signature_user_hint", data.get("user_hint")),
            generation_world_hint=generation_world_hint
            or data.get("generation_world_hint"),
            compatibility_options=compatibility_options,
        )

    @classmethod
    def disabled(cls) -> "SeriesVisualSignatureRequest":
        return cls(enabled=False, role=SeriesVisualSignatureRole.NONE)

    @property
    def pipeline_version(self) -> str:
        return SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION

    @property
    def presentation_policy(self):
        from pixelle_video.models.series_visual_signature_presentation import (
            SeriesVisualSignaturePresentationPolicy,
        )

        return SeriesVisualSignaturePresentationPolicy.from_mapping(self.compatibility_options)

    @property
    def strategy(self):
        return self.presentation_policy.strategy_controls()

    @property
    def effective_signature_mode(self):
        return self.strategy.effective_signature_mode

    @property
    def expression_mode(self):
        from pixelle_video.models.visual_expression import VisualExpressionMode

        return VisualExpressionMode.from_value(
            self.compatibility_options.get("series_visual_signature_expression_mode")
        )

    @property
    def structure_mode(self):
        from pixelle_video.models.series_visual_signature_identity import (
            SeriesVisualSignatureStructureMode,
        )

        return SeriesVisualSignatureStructureMode.from_value(
            self.compatibility_options.get("series_visual_signature_structure_mode")
        )

    @property
    def participation_mode(self):
        from pixelle_video.models.series_visual_signature_identity import (
            SeriesVisualSignatureParticipationMode,
        )

        return SeriesVisualSignatureParticipationMode.from_value(
            self.compatibility_options.get("series_visual_signature_participation_mode")
        )

    def validate(self) -> None:
        if not self.enabled:
            return
        if self.profile_id is None:
            raise ValueError("series_visual_signature_profile_id is required when visual signature is enabled")

    def to_generation_dict(self) -> dict[str, Any]:
        if not self.enabled:
            return {}
        payload = dict(self.compatibility_options)
        payload.update(
            {
                "series_visual_signature_enabled": True,
                "series_visual_signature_profile_id": self.profile_id,
                "series_visual_signature_role": self.role.value,
            }
        )
        if self.asset_bible_id is not None:
            payload["series_visual_signature_asset_bible_id"] = self.asset_bible_id
        if self.max_area_ratio is not None:
            payload["series_visual_signature_max_area_ratio"] = self.max_area_ratio
        if self.user_hint is not None:
            payload["series_visual_signature_user_hint"] = self.user_hint
        return payload

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "enabled": self.enabled,
            "pipeline_version": self.pipeline_version,
            "series_visual_signature_enabled": self.enabled,
            "series_visual_signature_profile_id": self.profile_id,
            "series_visual_signature_role": self.role.value,
            "series_visual_signature_role_was_explicit": self.role_was_explicit,
            "series_visual_signature_max_area_ratio": self.max_area_ratio,
            "series_visual_signature_user_hint": self.user_hint,
            "series_visual_signature_asset_bible_id": self.asset_bible_id,
            "generation_world_hint": self.generation_world_hint,
        }
        payload.update(self.compatibility_options)
        return payload


@dataclass(frozen=True)
class VisualSignatureProfileSnapshot:
    profile_id: str
    display_name: str
    identity_traits: Sequence[str]
    style_safe_traits: Sequence[str] = field(default_factory=tuple)
    forbidden_traits: Sequence[str] = field(default_factory=tuple)
    source_asset_ids: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _require_text("profile_id", self.profile_id))
        object.__setattr__(self, "display_name", _require_text("display_name", self.display_name))
        object.__setattr__(self, "identity_traits", _trait_tuple("identity_traits", self.identity_traits, allow_empty=False))
        object.__setattr__(self, "style_safe_traits", _trait_tuple("style_safe_traits", self.style_safe_traits, allow_empty=True))
        object.__setattr__(self, "forbidden_traits", _trait_tuple("forbidden_traits", self.forbidden_traits, allow_empty=True))
        object.__setattr__(self, "source_asset_ids", _text_tuple("source_asset_ids", self.source_asset_ids, allow_empty=True))

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "VisualSignatureProfileSnapshot":
        data = dict(source)
        reject_deprecated_signature_fields(data, context="visual signature profile")
        reject_prompt_paragraph_profile_fields(data, context="visual signature profile")
        return cls(
            profile_id=data.get("series_visual_signature_profile_id", data.get("profile_id")),
            display_name=data.get("display_name", data.get("name")),
            identity_traits=data.get("identity_traits") or (),
            style_safe_traits=data.get("style_safe_traits") or (),
            forbidden_traits=data.get("forbidden_traits") or (),
            source_asset_ids=data.get("source_asset_ids") or (),
        )

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> "VisualSignatureProfileSnapshot":
        return cls.from_mapping(source)

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_visual_signature_profile_id": self.profile_id,
            "display_name": self.display_name,
            "identity_traits": list(self.identity_traits),
            "style_safe_traits": list(self.style_safe_traits),
            "forbidden_traits": list(self.forbidden_traits),
            "source_asset_ids": list(self.source_asset_ids),
        }


@dataclass(frozen=True)
class SeriesVisualSignatureContract:
    enabled: bool
    role: SeriesVisualSignatureRole | str
    profile: VisualSignatureProfileSnapshot | None
    replacement_policy: SignatureReplacementPolicy | str = SignatureReplacementPolicy.NO_SUBJECT_REPLACEMENT
    max_area_ratio: float = 0.0
    participation_rule: str = "No recurring visual signature is inserted."
    style_integration_rule: str = ""
    forbidden_behaviors: Sequence[str] = field(default_factory=tuple)
    warnings: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", _bool_value(self.enabled, "enabled"))
        object.__setattr__(self, "role", _enum_value("role", self.role, SeriesVisualSignatureRole, SeriesVisualSignatureRole.NONE))
        object.__setattr__(self, "replacement_policy", _enum_value("replacement_policy", self.replacement_policy, SignatureReplacementPolicy, SignatureReplacementPolicy.NO_SUBJECT_REPLACEMENT))
        object.__setattr__(self, "max_area_ratio", _ratio_value(self.max_area_ratio, "max_area_ratio"))
        object.__setattr__(self, "participation_rule", _require_text("participation_rule", self.participation_rule))
        object.__setattr__(self, "style_integration_rule", _optional_text(self.style_integration_rule) or "")
        object.__setattr__(self, "forbidden_behaviors", _text_tuple("forbidden_behaviors", self.forbidden_behaviors, allow_empty=True))
        object.__setattr__(self, "warnings", _text_tuple("warnings", self.warnings, allow_empty=True))
        if self.enabled:
            if self.role in {SeriesVisualSignatureRole.NONE, SeriesVisualSignatureRole.AUTO}:
                raise ValueError("enabled series visual signature requires a concrete role")
            if self.profile is None:
                raise ValueError("enabled series visual signature requires a profile")
            if self.max_area_ratio <= 0.0:
                raise ValueError("enabled series visual signature requires positive max_area_ratio")
        elif self.profile is not None:
            raise ValueError("disabled series visual signature must not carry a profile")

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, Any] | "SeriesVisualSignatureContract" | None,
    ) -> "SeriesVisualSignatureContract":
        if isinstance(source, cls):
            return source
        data = dict(source or {})
        reject_deprecated_signature_fields(data, context="series visual signature contract")
        enabled = _bool_value(data.get("enabled", False), "enabled")
        warnings = data.get("warnings") or ()
        if not enabled:
            return cls.disabled(warnings=warnings)
        raw_profile = data.get("profile")
        if not isinstance(raw_profile, Mapping):
            raise ValueError("enabled serialized series visual signature contract requires profile")
        return cls(
            enabled=True,
            role=data.get("role", SeriesVisualSignatureRole.AUTO),
            profile=VisualSignatureProfileSnapshot.from_mapping(raw_profile),
            replacement_policy=data.get(
                "replacement_policy",
                SignatureReplacementPolicy.NO_SUBJECT_REPLACEMENT,
            ),
            max_area_ratio=data.get("max_area_ratio", 0.0),
            participation_rule=data.get("participation_rule") or "Series visual signature participates in the scene.",
            style_integration_rule=data.get("style_integration_rule") or "",
            forbidden_behaviors=data.get("forbidden_behaviors") or (),
            warnings=warnings,
        )

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> "SeriesVisualSignatureContract":
        return cls.from_mapping(source)

    @classmethod
    def disabled(cls, *, warnings: Sequence[str] = ()) -> "SeriesVisualSignatureContract":
        return cls(
            enabled=False,
            role=SeriesVisualSignatureRole.NONE,
            profile=None,
            max_area_ratio=0.0,
            participation_rule="Series visual signature disabled by request.",
            forbidden_behaviors=(),
            warnings=warnings,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "role": self.role.value,
            "series_visual_signature_profile_id": self.profile.profile_id if self.profile else None,
            "profile": self.profile.to_dict() if self.profile else None,
            "replacement_policy": self.replacement_policy.value,
            "max_area_ratio": self.max_area_ratio,
            "participation_rule": self.participation_rule,
            "style_integration_rule": self.style_integration_rule,
            "forbidden_behaviors": list(self.forbidden_behaviors),
            "warnings": list(self.warnings),
        }


def _enum_value(field_name: str, value: Any, enum_cls: type[Enum], default: Any) -> Any:
    if isinstance(value, enum_cls):
        return value
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a valid {enum_cls.__name__}")
    text = value.strip()
    if not text:
        return default
    for item in enum_cls:
        if text == item.value or text.lower() == item.name.lower():
            return item
    raise ValueError(f"{field_name} must be a valid {enum_cls.__name__}")


def _bool_value(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off", ""}:
            return False
    raise ValueError(f"{field_name} must be a boolean")


def _optional_text(value: Any, *, max_chars: int = 300) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional text fields must be strings")
    text = " ".join(value.strip().split())
    if not text:
        return None
    if len(text) > max_chars:
        raise ValueError(f"optional text fields must be <= {max_chars} characters")
    return text


def _require_text(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return " ".join(value.strip().split())


def _text_tuple(field_name: str, values: Sequence[Any], *, allow_empty: bool) -> tuple[str, ...]:
    if values is None:
        values = ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a sequence of strings")
    result = tuple(_require_text(field_name, value) for value in values)
    if not allow_empty and not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


def _trait_tuple(field_name: str, values: Sequence[Any], *, allow_empty: bool) -> tuple[str, ...]:
    result = _text_tuple(field_name, values, allow_empty=allow_empty)
    for trait in result:
        if len(trait) > MAX_TRAIT_CHARS:
            raise ValueError(f"{field_name} item exceeds {MAX_TRAIT_CHARS} characters")
        lowered = trait.lower()
        if any(term in lowered for term in _FORBIDDEN_TRAIT_TERMS):
            raise ValueError(f"{field_name} item contains prompt instruction language: {trait}")
        if "\n" in trait or ";" in trait or "；" in trait:
            raise ValueError(f"{field_name} item must be a short trait, not a prompt paragraph")
    return result


def _optional_ratio(value: Any, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    return _ratio_value(value, field_name)


def _ratio_value(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if parsed < 0.0 or parsed > 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return parsed


__all__ = [
    "MAX_TRAIT_CHARS",
    "SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION",
    "SeriesVisualSignatureContract",
    "SeriesVisualSignatureRequest",
    "SeriesVisualSignatureRole",
    "SignatureReplacementPolicy",
    "VisualSignatureProfileSnapshot",
]
