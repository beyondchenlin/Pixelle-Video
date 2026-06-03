from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from pixelle_video.architecture.asset_bible_persistence_compat import (
    resolve_series_visual_signature_profile_id_from_payload,
)

_HEX_COLOR_RE = re.compile(r"(?<![0-9a-fA-F])#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-fA-F])")


class IPRenderingStyle(str, Enum):
    STYLE_INHERITED = "style_inherited"
    PHOTOREALISTIC_HUMAN = "photorealistic_human"
    STYLIZED_CHARACTER = "stylized_character"
    FLAT_ILLUSTRATION = "flat_illustration"


class IPStyleScope(str, Enum):
    IP_CHARACTER_ONLY = "ip_character_only"
    IP_WORLD = "ip_world"
    INHERITED = "inherited"


@dataclass(frozen=True)
class IPProfile:
    series_visual_signature_profile_id: str
    workspace_id: str
    project_id: str
    name: str
    logline: str | None = None
    world_hint: str | None = None
    style_hint: str | None = None
    rendering_style: IPRenderingStyle = IPRenderingStyle.STYLE_INHERITED
    style_scope: IPStyleScope = IPStyleScope.IP_CHARACTER_ONLY
    exclusive_visual_layer: bool = False
    style_boundary_rules: tuple[str, ...] = ()
    forbidden_elements: tuple[str, ...] = ()
    identity_lock: tuple[str, ...] = ()
    identity_anchors: tuple[str, ...] = ()
    identity_suppression_rules: tuple[str, ...] = ()
    variable_slots: tuple[str, ...] = ()
    semantic_boundary: tuple[str, ...] = ()
    negative_constraints: tuple[str, ...] = ()
    ip_type: str = ""
    visual_summary: str | None = None
    minimal_traits: tuple[str, ...] = ()
    default_slot_preference: str = "prefer_supporting"
    role_presets: tuple[str, ...] = ()
    presence_spectrum: tuple[str, ...] = ()
    adaptable_slots: tuple[str, ...] = ()
    color_palette: Mapping[str, Any] = field(default_factory=dict)
    image_text_palette: Mapping[str, Any] = field(default_factory=dict)
    visible_text_whitelist: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "series_visual_signature_profile_id", _require_non_empty("series_visual_signature_profile_id", self.series_visual_signature_profile_id))
        object.__setattr__(self, "workspace_id", _require_non_empty("workspace_id", self.workspace_id))
        object.__setattr__(self, "project_id", _require_non_empty("project_id", self.project_id))
        object.__setattr__(self, "name", _require_non_empty("name", self.name))
        object.__setattr__(self, "logline", _optional_prompt_str("logline", self.logline))
        object.__setattr__(self, "world_hint", _optional_prompt_str("world_hint", self.world_hint))
        object.__setattr__(self, "style_hint", _optional_prompt_str("style_hint", self.style_hint))
        object.__setattr__(self, "rendering_style", _coerce_ip_rendering_style(self.rendering_style))
        object.__setattr__(self, "style_scope", _coerce_ip_style_scope(self.style_scope))
        object.__setattr__(self, "exclusive_visual_layer", bool(self.exclusive_visual_layer))
        object.__setattr__(
            self,
            "style_boundary_rules",
            _normalize_prompt_text_tuple("style_boundary_rules", self.style_boundary_rules),
        )
        object.__setattr__(
            self,
            "forbidden_elements",
            _normalize_text_tuple("forbidden_elements", self.forbidden_elements),
        )
        for field_name in (
            "identity_lock",
            "identity_anchors",
            "identity_suppression_rules",
            "variable_slots",
            "semantic_boundary",
            "negative_constraints",
            "visible_text_whitelist",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_prompt_text_tuple(field_name, getattr(self, field_name)),
            )
        object.__setattr__(self, "ip_type", self.ip_type.strip() if self.ip_type else "")
        object.__setattr__(self, "visual_summary", _optional_prompt_str("visual_summary", self.visual_summary))
        object.__setattr__(
            self,
            "minimal_traits",
            _normalize_prompt_text_tuple("minimal_traits", self.minimal_traits),
        )
        object.__setattr__(
            self,
            "default_slot_preference",
            self.default_slot_preference.strip() if self.default_slot_preference else "prefer_supporting",
        )
        object.__setattr__(
            self,
            "role_presets",
            _normalize_prompt_text_tuple("role_presets", self.role_presets),
        )
        object.__setattr__(
            self,
            "presence_spectrum",
            _normalize_prompt_text_tuple("presence_spectrum", self.presence_spectrum),
        )
        object.__setattr__(
            self,
            "adaptable_slots",
            _normalize_prompt_text_tuple("adaptable_slots", self.adaptable_slots),
        )
        object.__setattr__(self, "color_palette", _deep_freeze_mapping(self.color_palette, field_name="color_palette"))
        object.__setattr__(
            self,
            "image_text_palette",
            _deep_freeze_mapping(self.image_text_palette, field_name="image_text_palette"),
        )
        _reject_hex_colors_in_prompt_values(self.color_palette, path="color_palette")
        _reject_hex_colors_in_prompt_values(self.image_text_palette, path="image_text_palette")
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_visual_signature_profile_id": self.series_visual_signature_profile_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "name": self.name,
            "logline": self.logline,
            "world_hint": self.world_hint,
            "style_hint": self.style_hint,
            "rendering_style": self.rendering_style.value,
            "style_scope": self.style_scope.value,
            "exclusive_visual_layer": self.exclusive_visual_layer,
            "style_boundary_rules": list(self.style_boundary_rules),
            "forbidden_elements": list(self.forbidden_elements),
            "identity_lock": list(self.identity_lock),
            "identity_anchors": list(self.identity_anchors),
            "identity_suppression_rules": list(self.identity_suppression_rules),
            "variable_slots": list(self.variable_slots),
            "semantic_boundary": list(self.semantic_boundary),
            "negative_constraints": list(self.negative_constraints),
            "ip_type": self.ip_type,
            "visual_summary": self.visual_summary,
            "minimal_traits": list(self.minimal_traits),
            "default_slot_preference": self.default_slot_preference,
            "role_presets": list(self.role_presets),
            "presence_spectrum": list(self.presence_spectrum),
            "adaptable_slots": list(self.adaptable_slots),
            "color_palette": _json_safe_copy(self.color_palette),
            "image_text_palette": _json_safe_copy(self.image_text_palette),
            "visible_text_whitelist": list(self.visible_text_whitelist),
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IPProfile":
        _require_mapping("IPProfile", payload)
        return cls(
            series_visual_signature_profile_id=resolve_series_visual_signature_profile_id_from_payload(payload),
            workspace_id=payload.get("workspace_id", ""),
            project_id=payload.get("project_id", ""),
            name=payload.get("name", ""),
            logline=payload.get("logline"),
            world_hint=payload.get("world_hint"),
            style_hint=payload.get("style_hint"),
            rendering_style=payload.get("rendering_style", IPRenderingStyle.STYLE_INHERITED.value),
            style_scope=payload.get("style_scope", IPStyleScope.IP_CHARACTER_ONLY.value),
            exclusive_visual_layer=payload.get("exclusive_visual_layer", False),
            style_boundary_rules=_payload_sequence_or_default(payload.get("style_boundary_rules")),
            forbidden_elements=_payload_sequence_or_default(payload.get("forbidden_elements")),
            identity_lock=_payload_sequence_or_default(payload.get("identity_lock")),
            identity_anchors=_payload_sequence_or_default(payload.get("identity_anchors")),
            identity_suppression_rules=_payload_sequence_or_default(payload.get("identity_suppression_rules")),
            variable_slots=_payload_sequence_or_default(payload.get("variable_slots")),
            semantic_boundary=_payload_sequence_or_default(payload.get("semantic_boundary")),
            negative_constraints=_payload_sequence_or_default(payload.get("negative_constraints")),
            ip_type=payload.get("ip_type", ""),
            visual_summary=payload.get("visual_summary"),
            minimal_traits=_payload_sequence_or_default(payload.get("minimal_traits")),
            default_slot_preference=payload.get("default_slot_preference", "prefer_supporting"),
            role_presets=_payload_sequence_or_default(payload.get("role_presets")),
            presence_spectrum=_payload_sequence_or_default(payload.get("presence_spectrum")),
            adaptable_slots=_payload_sequence_or_default(payload.get("adaptable_slots")),
            color_palette=payload.get("color_palette") or {},
            image_text_palette=payload.get("image_text_palette") or {},
            visible_text_whitelist=_payload_sequence_or_default(payload.get("visible_text_whitelist")),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class CharacterProfile:
    character_id: str
    workspace_id: str
    project_id: str
    display_name: str
    role: str | None = None
    visual_description: str | None = None
    personality: str | None = None
    continuity_notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "character_id", _require_non_empty("character_id", self.character_id))
        object.__setattr__(self, "workspace_id", _require_non_empty("workspace_id", self.workspace_id))
        object.__setattr__(self, "project_id", _require_non_empty("project_id", self.project_id))
        object.__setattr__(self, "display_name", _require_non_empty("display_name", self.display_name))
        object.__setattr__(self, "role", _optional_str(self.role))
        object.__setattr__(self, "visual_description", _optional_str(self.visual_description))
        object.__setattr__(self, "personality", _optional_str(self.personality))
        object.__setattr__(
            self,
            "continuity_notes",
            _normalize_text_tuple("continuity_notes", self.continuity_notes),
        )
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "display_name": self.display_name,
            "role": self.role,
            "visual_description": self.visual_description,
            "personality": self.personality,
            "continuity_notes": list(self.continuity_notes),
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CharacterProfile":
        _require_mapping("CharacterProfile", payload)
        return cls(
            character_id=payload.get("character_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            project_id=payload.get("project_id", ""),
            display_name=payload.get("display_name", ""),
            role=payload.get("role"),
            visual_description=payload.get("visual_description"),
            personality=payload.get("personality"),
            continuity_notes=tuple(payload.get("continuity_notes") or ()),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class SceneAsset:
    scene_id: str
    workspace_id: str
    project_id: str
    display_name: str
    visual_description: str | None = None
    environment_notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scene_id", _require_non_empty("scene_id", self.scene_id))
        object.__setattr__(self, "workspace_id", _require_non_empty("workspace_id", self.workspace_id))
        object.__setattr__(self, "project_id", _require_non_empty("project_id", self.project_id))
        object.__setattr__(self, "display_name", _require_non_empty("display_name", self.display_name))
        object.__setattr__(self, "visual_description", _optional_str(self.visual_description))
        object.__setattr__(
            self,
            "environment_notes",
            _normalize_text_tuple("environment_notes", self.environment_notes),
        )
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "display_name": self.display_name,
            "visual_description": self.visual_description,
            "environment_notes": list(self.environment_notes),
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SceneAsset":
        _require_mapping("SceneAsset", payload)
        return cls(
            scene_id=payload.get("scene_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            project_id=payload.get("project_id", ""),
            display_name=payload.get("display_name", ""),
            visual_description=payload.get("visual_description"),
            environment_notes=tuple(payload.get("environment_notes") or ()),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class PropAsset:
    prop_id: str
    workspace_id: str
    project_id: str
    display_name: str
    visual_description: str | None = None
    usage_notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "prop_id", _require_non_empty("prop_id", self.prop_id))
        object.__setattr__(self, "workspace_id", _require_non_empty("workspace_id", self.workspace_id))
        object.__setattr__(self, "project_id", _require_non_empty("project_id", self.project_id))
        object.__setattr__(self, "display_name", _require_non_empty("display_name", self.display_name))
        object.__setattr__(self, "visual_description", _optional_str(self.visual_description))
        object.__setattr__(
            self,
            "usage_notes",
            _normalize_text_tuple("usage_notes", self.usage_notes),
        )
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "prop_id": self.prop_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "display_name": self.display_name,
            "visual_description": self.visual_description,
            "usage_notes": list(self.usage_notes),
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PropAsset":
        _require_mapping("PropAsset", payload)
        return cls(
            prop_id=payload.get("prop_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            project_id=payload.get("project_id", ""),
            display_name=payload.get("display_name", ""),
            visual_description=payload.get("visual_description"),
            usage_notes=tuple(payload.get("usage_notes") or ()),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class StyleProfile:
    style_id: str
    workspace_id: str
    project_id: str
    display_name: str
    visual_style: str
    world_style: str | None = None
    provider_prompt: str | None = None
    negative_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "style_id", _require_non_empty("style_id", self.style_id))
        object.__setattr__(self, "workspace_id", _require_non_empty("workspace_id", self.workspace_id))
        object.__setattr__(self, "project_id", _require_non_empty("project_id", self.project_id))
        object.__setattr__(self, "display_name", _require_non_empty("display_name", self.display_name))
        object.__setattr__(self, "visual_style", _require_non_empty("visual_style", self.visual_style))
        object.__setattr__(self, "world_style", _optional_str(self.world_style))
        object.__setattr__(self, "provider_prompt", _optional_str(self.provider_prompt))
        object.__setattr__(self, "negative_prompt", _optional_str(self.negative_prompt))
        _reject_text_style_keys(self.metadata, path="metadata")
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "style_id": self.style_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "display_name": self.display_name,
            "visual_style": self.visual_style,
            "world_style": self.world_style,
            "provider_prompt": self.provider_prompt,
            "negative_prompt": self.negative_prompt,
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StyleProfile":
        _require_mapping("StyleProfile", payload)
        _reject_text_style_keys(payload)
        return cls(
            style_id=payload.get("style_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            project_id=payload.get("project_id", ""),
            display_name=payload.get("display_name", ""),
            visual_style=payload.get("visual_style", ""),
            world_style=payload.get("world_style"),
            provider_prompt=payload.get("provider_prompt"),
            negative_prompt=payload.get("negative_prompt"),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class AssetBible:
    asset_bible_id: str
    workspace_id: str
    project_id: str
    ip_profiles: tuple[IPProfile, ...] = ()
    character_profiles: tuple[CharacterProfile, ...] = ()
    scene_assets: tuple[SceneAsset, ...] = ()
    prop_assets: tuple[PropAsset, ...] = ()
    style_profiles: tuple[StyleProfile, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_bible_id", _require_non_empty("asset_bible_id", self.asset_bible_id))
        object.__setattr__(self, "workspace_id", _require_non_empty("workspace_id", self.workspace_id))
        object.__setattr__(self, "project_id", _require_non_empty("project_id", self.project_id))
        object.__setattr__(
            self,
            "ip_profiles",
            _normalize_asset_tuple("ip_profiles", self.ip_profiles, IPProfile, "series_visual_signature_profile_id"),
        )
        object.__setattr__(
            self,
            "character_profiles",
            _normalize_asset_tuple(
                "character_profiles",
                self.character_profiles,
                CharacterProfile,
                "character_id",
            ),
        )
        object.__setattr__(
            self,
            "scene_assets",
            _normalize_asset_tuple("scene_assets", self.scene_assets, SceneAsset, "scene_id"),
        )
        object.__setattr__(
            self,
            "prop_assets",
            _normalize_asset_tuple("prop_assets", self.prop_assets, PropAsset, "prop_id"),
        )
        object.__setattr__(
            self,
            "style_profiles",
            _normalize_asset_tuple("style_profiles", self.style_profiles, StyleProfile, "style_id"),
        )
        self._validate_asset_ownership()
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def _validate_asset_ownership(self) -> None:
        for collection_name in (
            "ip_profiles",
            "character_profiles",
            "scene_assets",
            "prop_assets",
            "style_profiles",
        ):
            for asset in getattr(self, collection_name):
                if asset.workspace_id != self.workspace_id:
                    raise ValueError(f"{collection_name} must match asset bible workspace_id")
                if asset.project_id != self.project_id:
                    raise ValueError(f"{collection_name} must match asset bible project_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_bible_id": self.asset_bible_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "ip_profiles": [profile.to_dict() for profile in self.ip_profiles],
            "character_profiles": [
                profile.to_dict()
                for profile in self.character_profiles
            ],
            "scene_assets": [asset.to_dict() for asset in self.scene_assets],
            "prop_assets": [asset.to_dict() for asset in self.prop_assets],
            "style_profiles": [profile.to_dict() for profile in self.style_profiles],
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AssetBible":
        _require_mapping("AssetBible", payload)
        return cls(
            asset_bible_id=payload.get("asset_bible_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            project_id=payload.get("project_id", ""),
            ip_profiles=tuple(
                IPProfile.from_dict(item)
                for item in payload.get("ip_profiles") or ()
            ),
            character_profiles=tuple(
                CharacterProfile.from_dict(item)
                for item in payload.get("character_profiles") or ()
            ),
            scene_assets=tuple(
                SceneAsset.from_dict(item)
                for item in payload.get("scene_assets") or ()
            ),
            prop_assets=tuple(
                PropAsset.from_dict(item)
                for item in payload.get("prop_assets") or ()
            ),
            style_profiles=tuple(
                StyleProfile.from_dict(item)
                for item in payload.get("style_profiles") or ()
            ),
            metadata=payload.get("metadata") or {},
        )


def _require_mapping(type_name: str, payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{type_name} payload must be a mapping")


def _require_non_empty(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _coerce_ip_rendering_style(value: Any) -> IPRenderingStyle:
    if isinstance(value, IPRenderingStyle):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return IPRenderingStyle(value.strip())
        except ValueError as exc:
            raise ValueError(f"unsupported IP rendering_style: {value}") from exc
    return IPRenderingStyle.STYLE_INHERITED


def _coerce_ip_style_scope(value: Any) -> IPStyleScope:
    if isinstance(value, IPStyleScope):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return IPStyleScope(value.strip())
        except ValueError as exc:
            raise ValueError(f"unsupported IP style_scope: {value}") from exc
    return IPStyleScope.IP_CHARACTER_ONLY


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional string fields must be strings")
    stripped = value.strip()
    return stripped or None


def _optional_prompt_str(field_name: str, value: Any) -> str | None:
    normalized = _optional_str(value)
    if normalized is not None:
        _reject_hex_color(field_name, normalized)
    return normalized


def _normalize_text_tuple(field_name: str, value: Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a list or tuple")
    normalized = tuple(_require_non_empty(field_name, item) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _normalize_prompt_text_tuple(field_name: str, value: Sequence[str] | None) -> tuple[str, ...]:
    normalized = _normalize_text_tuple(field_name, value)
    for item in normalized:
        _reject_hex_color(field_name, item)
    return normalized


def _reject_hex_color(field_name: str, value: str) -> None:
    if _HEX_COLOR_RE.search(value):
        raise ValueError(f"{field_name} must use prompt color terms, not hex colors")


def _reject_hex_colors_in_prompt_values(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_name = str(key)
            child_path = f"{path}.{key_name}"
            if _is_palette_prompt_key(key_name):
                _reject_hex_colors_in_string_leaves(item, path=child_path)
                continue
            _reject_hex_colors_in_prompt_values(item, path=child_path)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_hex_colors_in_prompt_values(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        return


def _is_palette_prompt_key(key: str) -> bool:
    return key == "prompt" or key == "color_prompt" or key.endswith("_prompt")


def _reject_hex_colors_in_string_leaves(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_hex_colors_in_string_leaves(item, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_hex_colors_in_string_leaves(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        _reject_hex_color(path, value)


def _normalize_asset_tuple(
    field_name: str,
    value: Sequence[Any] | None,
    expected_type: type,
    id_field: str,
) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a list or tuple")
    normalized = tuple(value)
    if not all(isinstance(item, expected_type) for item in normalized):
        raise ValueError(f"{field_name} must contain {expected_type.__name__} values")
    ids = tuple(getattr(item, id_field) for item in normalized)
    if len(set(ids)) != len(ids):
        raise ValueError(f"{field_name} must not contain duplicate {id_field} values")
    return normalized


def _reject_text_style_keys(payload: Mapping[str, Any], *, path: str = "StyleProfile") -> None:
    disallowed_keys = {
        "caption_style",
        "title_style",
        "overlay_style",
        "font_file",
        "font_family",
        "font_size",
        "background_color",
    }
    present = _find_text_style_keys(payload, disallowed_keys, path)
    if present:
        raise ValueError(
            "StyleProfile must not carry text-rendering style fields: "
            + ", ".join(present)
        )


def _find_text_style_keys(
    payload: Mapping[str, Any],
    disallowed_keys: set[str],
    path: str,
) -> list[str]:
    if not isinstance(payload, Mapping):
        return []
    present: list[str] = []
    for key, item in payload.items():
        key_name = str(key)
        key_path = f"{path}.{key_name}"
        if key_name in disallowed_keys:
            present.append(key_path)
        if isinstance(item, Mapping):
            present.extend(_find_text_style_keys(item, disallowed_keys, key_path))
    return sorted(present)


def _deep_freeze_mapping(value: Mapping[str, Any], *, field_name: str = "metadata") -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return MappingProxyType({
        str(key): _deep_freeze(item)
        for key, item in value.items()
    })


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _deep_freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return deepcopy(value)


def _json_safe_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_copy(item) for item in value]
    return deepcopy(value)


def _payload_sequence_or_default(value: Any) -> Any:
    if value is None:
        return ()
    return value


__all__ = [
    "AssetBible",
    "CharacterProfile",
    "IPProfile",
    "IPRenderingStyle",
    "IPStyleScope",
    "PropAsset",
    "SceneAsset",
    "StyleProfile",
]
