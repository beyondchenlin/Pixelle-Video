from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pixelle_video.architecture.legacy_signature_field_guard import (
    reject_deprecated_signature_fields,
    reject_prompt_paragraph_profile_fields,
)
from pixelle_video.models.visual_entity_placement import VisualRelativeSize


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


SERIES_VISUAL_SIGNATURE_NATURAL_ROLE_MAP: dict[str, str] = {
    "core_actor": "a functional actor that performs the frame action",
    "silent_witness": "a quiet witness beside the evidence or event structure",
    "operator": "a small operator demonstrating the mechanism",
    "guide": "a guide that points out the path or key structure",
    "obstacle": "a symbolic obstacle inside the metaphor",
    "container": "a small carrier for the structure or concept",
    "background_mark": "a material mark on a real in-scene surface",
}

ALLOWED_TEXT_CHARACTER_ROLES = frozenset(
    {
        SeriesVisualSignatureRole.CORE_ACTOR,
        SeriesVisualSignatureRole.SILENT_WITNESS,
        SeriesVisualSignatureRole.OPERATOR,
        SeriesVisualSignatureRole.GUIDE,
    }
)
FORBIDDEN_TEXT_CHARACTER_ROLES = frozenset(
    {
        SeriesVisualSignatureRole.OBSTACLE,
        SeriesVisualSignatureRole.CONTAINER,
        SeriesVisualSignatureRole.BACKGROUND_MARK,
    }
)

MAX_TRAIT_CHARS = 64
MAX_CANONICAL_IDENTITY_CHARS = 400
SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION = "v4_expression"
SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION = "v4_2_identity_contract"
MANDATORY_CONTENT_BOUND_ANCHOR_CONTRACT_VERSION = (
    "final_visual_prompt_contract.v4_6"
)
SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS = frozenset(
    {
        SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION,
        SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION,
    }
)
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
_FORBIDDEN_NEGATIVE_TRAIT_INSTRUCTION_TERMS = (
    "ignore previous",
    "ignore all",
    "system message",
    "system prompt",
    "assistant message",
    "user message",
    "developer message",
    "follow these instructions",
    "follow my instructions",
    "must render",
    "must show",
    "must include",
    "override instructions",
    "jailbreak",
    "prompt injection",
    "provider instruction",
    "忽略之前",
    "忽略以上",
    "忽略所有",
    "系统消息",
    "系统提示",
    "助手消息",
    "用户消息",
    "开发者消息",
    "遵循这些指令",
    "遵循我的指令",
    "必须渲染",
    "必须显示",
    "必须包含",
    "覆盖指令",
    "越狱",
)


@dataclass(frozen=True)
class SeriesVisualSignatureRequest:
    """Canonical request for a recurring visual signature.

    Product-level compatibility controls may still enter through
    ``compatibility_options`` while callers migrate, but runtime identity and
    role selection use this single request type. ``pipeline_version`` remains a
    real dataclass field so legacy routing can be represented without creating a
    second request class.
    """

    enabled: bool = False
    profile_id: str | None = None
    role: SeriesVisualSignatureRole | str = SeriesVisualSignatureRole.NONE
    role_was_explicit: bool = False
    max_area_ratio: float | None = None
    user_hint: str | None = None
    asset_bible_id: str | None = None
    generation_world_hint: str | None = None
    pipeline_version: str = SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION
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
        object.__setattr__(
            self,
            "generation_world_hint",
            _optional_text(self.generation_world_hint, max_chars=4000),
        )
        object.__setattr__(self, "pipeline_version", _pipeline_version_value(self.pipeline_version))
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
        raw_role = data.get("series_visual_signature_role", data.get("role"))
        explicit_role_marker = data.get("series_visual_signature_role_was_explicit")
        if explicit_role_marker is None:
            role_was_explicit = raw_role not in (None, "", "none", "auto")
        else:
            role_was_explicit = _bool_value(
                explicit_role_marker,
                "series_visual_signature_role_was_explicit",
            )
        if enabled and raw_role in (None, "", "none") and not role_was_explicit:
            raw_role = SeriesVisualSignatureRole.AUTO
        if raw_role is None:
            raw_role = SeriesVisualSignatureRole.NONE

        compatibility_options = {
            str(key): value
            for key, value in data.items()
            if str(key).startswith("series_visual_signature_")
        }
        if enabled:
            mandatory_anchor = _bool_value(
                data.get("mandatory_content_bound_anchor", True),
                "mandatory_content_bound_anchor",
            )
            if not mandatory_anchor:
                raise ValueError(
                    "enabled series visual signature requires mandatory_content_bound_anchor"
                )
            contract_version = str(
                data.get(
                    "series_visual_signature_contract_version",
                    MANDATORY_CONTENT_BOUND_ANCHOR_CONTRACT_VERSION,
                )
                or ""
            ).strip()
            if contract_version != MANDATORY_CONTENT_BOUND_ANCHOR_CONTRACT_VERSION:
                raise ValueError(
                    "enabled series visual signature requires final visual prompt contract V4.6"
                )
            required_values = {
                "series_visual_signature_presentation_mode": "content_bound_mandatory_ip",
                "series_visual_signature_enforcement": "strict",
                "series_visual_signature_fallback_enabled": False,
                "series_visual_signature_fallback_mode": "disabled",
                "series_visual_signature_min_visibility": "clear",
                "series_visual_signature_output_validation_mode": "required",
                "series_visual_signature_output_max_attempts": 3,
            }
            for field_name, required_value in required_values.items():
                supplied = data.get(field_name)
                if supplied is None:
                    continue
                if isinstance(required_value, bool):
                    supplied = _bool_value(supplied, field_name)
                elif isinstance(required_value, int):
                    if isinstance(supplied, bool) or not isinstance(supplied, int):
                        raise ValueError(f"{field_name} must be an integer")
                else:
                    supplied = str(supplied).strip()
                if supplied != required_value:
                    raise ValueError(
                        f"enabled series visual signature requires {field_name}={required_value}"
                    )
            compatibility_options.update(
                {
                    "mandatory_content_bound_anchor": True,
                    "series_visual_signature_contract_version": contract_version,
                    **required_values,
                }
            )
        return cls(
            enabled=enabled,
            asset_bible_id=asset_bible_id
            or data.get("series_visual_signature_asset_bible_id")
            or data.get("asset_bible_id"),
            profile_id=profile_id
            or data.get("series_visual_signature_profile_id")
            or data.get("profile_id"),
            role=raw_role,
            role_was_explicit=role_was_explicit,
            max_area_ratio=data.get("series_visual_signature_max_area_ratio", data.get("max_area_ratio")),
            user_hint=data.get("series_visual_signature_user_hint", data.get("user_hint")),
            generation_world_hint=generation_world_hint or data.get("generation_world_hint"),
            pipeline_version=data.get(
                "pipeline_version",
                data.get(
                    "series_visual_signature_pipeline_version",
                    SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION,
                ),
            ),
            compatibility_options=compatibility_options,
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
    def from_controls(cls, controls: Any) -> "SeriesVisualSignatureRequest":
        if controls is None:
            return cls.disabled()
        if hasattr(controls, "to_request"):
            request = controls.to_request()
            if isinstance(request, cls):
                return request
        source = controls.to_dict() if hasattr(controls, "to_dict") else controls
        if not isinstance(source, Mapping):
            raise TypeError("controls must expose to_dict() or be a mapping")
        return cls.from_mapping(
            source,
            asset_bible_id=getattr(controls, "asset_bible_id", None),
            profile_id=getattr(controls, "profile_id", None),
            generation_world_hint=getattr(controls, "generation_world_hint", None),
        )

    @classmethod
    def disabled(cls) -> "SeriesVisualSignatureRequest":
        return cls(enabled=False, role=SeriesVisualSignatureRole.NONE)

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

    @property
    def llm_prompt_assembly_enabled(self) -> bool:
        return _bool_value(
            self.compatibility_options.get(
                "series_visual_signature_llm_prompt_assembly_enabled",
                False,
            ),
            "series_visual_signature_llm_prompt_assembly_enabled",
        )

    def validate(self) -> None:
        if not self.enabled:
            return
        if self.asset_bible_id is None:
            raise ValueError("asset_bible_id is required when series visual signature is enabled")
        if self.profile_id is None:
            raise ValueError("profile_id is required when series visual signature is enabled")

    def to_generation_dict(self) -> dict[str, Any]:
        if not self.enabled:
            return {}
        payload = dict(self.compatibility_options)
        payload.update(
            {
                "series_visual_signature_enabled": True,
                "series_visual_signature_profile_id": self.profile_id,
                "series_visual_signature_role": self.role.value,
                "mandatory_content_bound_anchor": True,
                "series_visual_signature_contract_version": (
                    MANDATORY_CONTENT_BOUND_ANCHOR_CONTRACT_VERSION
                ),
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
        payload = dict(self.compatibility_options)
        payload.update(
            {
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
                "mandatory_content_bound_anchor": self.enabled,
                "series_visual_signature_contract_version": (
                    MANDATORY_CONTENT_BOUND_ANCHOR_CONTRACT_VERSION
                    if self.enabled
                    else None
                ),
            }
        )
        return payload


@dataclass(frozen=True)
class VisualSignatureProfileSnapshot:
    profile_id: str
    display_name: str
    identity_traits: Sequence[str] = field(default_factory=tuple)
    style_safe_traits: Sequence[str] = field(default_factory=tuple)
    forbidden_traits: Sequence[str] = field(default_factory=tuple)
    source_asset_ids: Sequence[str] = field(default_factory=tuple)
    core_identity_traits: Sequence[str] = field(default_factory=tuple)
    supporting_identity_traits: Sequence[str] = field(default_factory=tuple)
    canonical_identity_clause: str = ""
    identity_content_sha256: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _require_text("profile_id", self.profile_id))
        object.__setattr__(self, "display_name", _require_text("display_name", self.display_name))
        compatibility_traits = _dedupe_traits(
            _trait_tuple("identity_traits", self.identity_traits, allow_empty=True)
        )
        core_traits = _dedupe_traits(
            _trait_tuple(
                "core_identity_traits",
                self.core_identity_traits,
                allow_empty=True,
            )
        )
        if not core_traits:
            core_traits = compatibility_traits
        if not core_traits:
            raise ValueError("core_identity_traits must not be empty")
        supporting_traits = _dedupe_traits(
            _trait_tuple(
                "supporting_identity_traits",
                self.supporting_identity_traits,
                allow_empty=True,
            ),
            excluded=core_traits,
        )
        combined_traits = (*core_traits, *supporting_traits)
        if compatibility_traits and tuple(compatibility_traits) != tuple(combined_traits):
            compatibility_only = _dedupe_traits(
                compatibility_traits,
                excluded=combined_traits,
            )
            supporting_traits = (*supporting_traits, *compatibility_only)
            combined_traits = (*core_traits, *supporting_traits)
        object.__setattr__(self, "core_identity_traits", tuple(core_traits))
        object.__setattr__(self, "supporting_identity_traits", tuple(supporting_traits))
        object.__setattr__(self, "identity_traits", tuple(combined_traits))
        object.__setattr__(self, "style_safe_traits", _trait_tuple("style_safe_traits", self.style_safe_traits, allow_empty=True))
        forbidden_traits = _dedupe_traits(
            _negative_trait_tuple(
                "forbidden_traits",
                self.forbidden_traits,
                allow_empty=True,
            )
        )
        object.__setattr__(self, "forbidden_traits", tuple(forbidden_traits))
        object.__setattr__(self, "source_asset_ids", _text_tuple("source_asset_ids", self.source_asset_ids, allow_empty=True))
        canonical_clause = canonical_series_visual_signature_identity_clause(
            display_name=self.display_name,
            core_identity_traits=core_traits,
            supporting_identity_traits=supporting_traits,
        )
        supplied_clause = _optional_text(
            self.canonical_identity_clause,
            max_chars=MAX_CANONICAL_IDENTITY_CHARS,
        )
        if supplied_clause is not None and supplied_clause != canonical_clause:
            raise ValueError(
                "canonical_identity_clause must match the deterministic identity compiler"
            )
        object.__setattr__(self, "canonical_identity_clause", canonical_clause)
        identity_hash = series_visual_signature_identity_content_sha256(
            display_name=self.display_name,
            core_identity_traits=core_traits,
            supporting_identity_traits=supporting_traits,
            forbidden_traits=forbidden_traits,
        )
        supplied_hash = str(self.identity_content_sha256 or "").strip().lower()
        if supplied_hash and supplied_hash != identity_hash:
            raise ValueError(
                "identity_content_sha256 must match canonical identity content"
            )
        object.__setattr__(self, "identity_content_sha256", identity_hash)

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
            core_identity_traits=data.get("core_identity_traits") or (),
            supporting_identity_traits=data.get("supporting_identity_traits") or (),
            canonical_identity_clause=data.get("canonical_identity_clause") or "",
            identity_content_sha256=data.get("identity_content_sha256") or "",
        )

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> "VisualSignatureProfileSnapshot":
        return cls.from_mapping(source)

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_visual_signature_profile_id": self.profile_id,
            "display_name": self.display_name,
            "identity_traits": list(self.identity_traits),
            "core_identity_traits": list(self.core_identity_traits),
            "supporting_identity_traits": list(self.supporting_identity_traits),
            "canonical_identity_clause": self.canonical_identity_clause,
            "identity_content_sha256": self.identity_content_sha256,
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
    relative_size: VisualRelativeSize | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", _bool_value(self.enabled, "enabled"))
        object.__setattr__(self, "role", _enum_value("role", self.role, SeriesVisualSignatureRole, SeriesVisualSignatureRole.NONE))
        object.__setattr__(self, "replacement_policy", _enum_value("replacement_policy", self.replacement_policy, SignatureReplacementPolicy, SignatureReplacementPolicy.NO_SUBJECT_REPLACEMENT))
        object.__setattr__(self, "max_area_ratio", _ratio_value(self.max_area_ratio, "max_area_ratio"))
        relative_size = self.relative_size
        if relative_size is None:
            relative_size = relative_size_from_max_area_ratio(self.max_area_ratio)
        normalized_relative_size = _enum_value(
            "relative_size",
            relative_size,
            VisualRelativeSize,
            VisualRelativeSize.SMALL,
        )
        object.__setattr__(
            self,
            "relative_size",
            normalized_relative_size,
        )
        object.__setattr__(self, "participation_rule", _require_text("participation_rule", self.participation_rule))
        object.__setattr__(self, "style_integration_rule", _optional_text(self.style_integration_rule) or "")
        object.__setattr__(self, "forbidden_behaviors", _text_tuple("forbidden_behaviors", self.forbidden_behaviors, allow_empty=True))
        object.__setattr__(self, "warnings", _text_tuple("warnings", self.warnings, allow_empty=True))
        if self.enabled:
            if self.role in {SeriesVisualSignatureRole.NONE, SeriesVisualSignatureRole.AUTO}:
                raise ValueError("enabled series visual signature requires a concrete role")
            if self.role in FORBIDDEN_TEXT_CHARACTER_ROLES:
                raise ValueError(
                    "enabled text character cannot use obstacle, container, or background_mark role"
                )
            if self.profile is None:
                raise ValueError("enabled series visual signature requires a profile")
            if self.max_area_ratio <= 0.0:
                raise ValueError("enabled series visual signature requires positive max_area_ratio")
            expected_relative_size = relative_size_from_max_area_ratio(
                self.max_area_ratio
            )
            if normalized_relative_size is not expected_relative_size:
                raise ValueError(
                    "enabled series visual signature relative_size must match "
                    "the max_area_ratio compatibility mapping"
                )
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
            relative_size=data.get("relative_size"),
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
            relative_size=VisualRelativeSize.SMALL,
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
            "relative_size": self.relative_size.value,
            "participation_rule": self.participation_rule,
            "style_integration_rule": self.style_integration_rule,
            "forbidden_behaviors": list(self.forbidden_behaviors),
            "warnings": list(self.warnings),
        }


def is_supported_series_visual_signature_pipeline_version(value: Any) -> bool:
    return str(value or "").strip() in SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS


def relative_size_from_max_area_ratio(value: Any) -> VisualRelativeSize:
    ratio = _ratio_value(value, "max_area_ratio")
    if ratio <= 0.10:
        return VisualRelativeSize.SMALL
    if ratio <= 0.18:
        return VisualRelativeSize.MEDIUM_SMALL
    if ratio <= 0.30:
        return VisualRelativeSize.MEDIUM
    if ratio <= 0.45:
        return VisualRelativeSize.LARGE
    return VisualRelativeSize.FULL_FRAME


def canonical_series_visual_signature_identity_clause(
    *,
    display_name: str,
    core_identity_traits: Sequence[str],
    supporting_identity_traits: Sequence[str] = (),
) -> str:
    name = _require_text("display_name", display_name)
    core = _dedupe_traits(
        _trait_tuple("core_identity_traits", core_identity_traits, allow_empty=False)
    )
    supporting = _dedupe_traits(
        _trait_tuple(
            "supporting_identity_traits",
            supporting_identity_traits,
            allow_empty=True,
        ),
        excluded=core,
    )
    clause = f"Canonical recurring identity {name}: {', '.join((*core, *supporting))}."
    if len(clause) > MAX_CANONICAL_IDENTITY_CHARS:
        raise ValueError(
            "canonical_identity_clause exceeds 400 characters; reduce identity traits before generation"
        )
    return clause


def series_visual_signature_identity_content_sha256(
    *,
    display_name: str,
    core_identity_traits: Sequence[str],
    supporting_identity_traits: Sequence[str],
    forbidden_traits: Sequence[str],
) -> str:
    core = _dedupe_traits(
        _trait_tuple(
            "core_identity_traits",
            core_identity_traits,
            allow_empty=False,
        )
    )
    supporting = _dedupe_traits(
        _trait_tuple(
            "supporting_identity_traits",
            supporting_identity_traits,
            allow_empty=True,
        ),
        excluded=core,
    )
    forbidden = _dedupe_traits(
        _negative_trait_tuple(
            "forbidden_traits",
            forbidden_traits,
            allow_empty=True,
        )
    )
    payload = {
        "display_name": _require_text("display_name", display_name),
        "core_identity_traits": list(core),
        "supporting_identity_traits": list(supporting),
        "forbidden_traits": list(forbidden),
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _pipeline_version_value(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("pipeline_version must be a supported series visual signature pipeline version")
    normalized = value.strip()
    if normalized not in SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS:
        raise ValueError("pipeline_version must be a supported series visual signature pipeline version")
    return normalized


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
    text = unicodedata.normalize("NFC", " ".join(value.strip().split()))
    if not text:
        return None
    if len(text) > max_chars:
        raise ValueError(f"optional text fields must be <= {max_chars} characters")
    return text


def _require_text(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return unicodedata.normalize("NFC", " ".join(value.strip().split()))


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
    for index, trait in enumerate(result):
        if len(trait) > MAX_TRAIT_CHARS:
            raise ValueError(
                f"{field_name} item exceeds {MAX_TRAIT_CHARS} characters at index {index}"
            )
        lowered = trait.lower()
        if any(term in lowered for term in _FORBIDDEN_TRAIT_TERMS):
            raise ValueError(
                f"{field_name} item contains prompt instruction language at index {index}"
            )
        if "\n" in trait or ";" in trait or "；" in trait:
            raise ValueError(
                f"{field_name} item must be a short trait, not a prompt paragraph at index {index}"
            )
    return result


def _negative_trait_tuple(
    field_name: str,
    values: Sequence[Any],
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    """Validate negative appearance facts without rejecting their subject matter.

    Words such as ``logo`` and ``watermark`` are valid forbidden appearance
    facts. Only instruction-shaped content is rejected at this boundary.
    """

    result = _text_tuple(field_name, values, allow_empty=allow_empty)
    for index, trait in enumerate(result):
        if len(trait) > MAX_TRAIT_CHARS:
            raise ValueError(
                f"{field_name} item exceeds {MAX_TRAIT_CHARS} characters at index {index}"
            )
        lowered = trait.casefold()
        if any(
            term.casefold() in lowered
            for term in _FORBIDDEN_NEGATIVE_TRAIT_INSTRUCTION_TERMS
        ):
            raise ValueError(
                f"{field_name} item contains instruction language at index {index}"
            )
        if "\n" in trait or ";" in trait or "；" in trait:
            raise ValueError(
                f"{field_name} item must be a short trait, not a prompt paragraph at index {index}"
            )
    return result


def _dedupe_traits(
    values: Sequence[str],
    *,
    excluded: Sequence[str] = (),
) -> tuple[str, ...]:
    seen = {value.casefold() for value in excluded}
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return tuple(result)


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
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} must be finite")
    if parsed < 0.0 or parsed > 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return parsed


__all__ = [
    "ALLOWED_TEXT_CHARACTER_ROLES",
    "FORBIDDEN_TEXT_CHARACTER_ROLES",
    "MAX_CANONICAL_IDENTITY_CHARS",
    "MANDATORY_CONTENT_BOUND_ANCHOR_CONTRACT_VERSION",
    "MAX_TRAIT_CHARS",
    "SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION",
    "SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION",
    "SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS",
    "SeriesVisualSignatureContract",
    "SeriesVisualSignatureRequest",
    "SeriesVisualSignatureRole",
    "SignatureReplacementPolicy",
    "VisualSignatureProfileSnapshot",
    "canonical_series_visual_signature_identity_clause",
    "is_supported_series_visual_signature_pipeline_version",
    "relative_size_from_max_area_ratio",
    "series_visual_signature_identity_content_sha256",
]
