from __future__ import annotations

from dataclasses import dataclass, fields

PREFIX = "ip_design"


@dataclass(frozen=True)
class _AssetBibleKeys:
    select: str = f"{PREFIX}_asset_bible_select"
    asset_bible_id: str = f"{PREFIX}_asset_bible_id"


@dataclass(frozen=True)
class _IPFormKeys:
    ip_profile_select: str = f"{PREFIX}_ip_profile_select"
    ip_profile_id: str = f"{PREFIX}_ip_profile_id"
    name: str = f"{PREFIX}_ip_name"
    ip_type: str = f"{PREFIX}_ip_type"
    logline: str = f"{PREFIX}_logline"
    visual_summary: str = f"{PREFIX}_visual_summary"
    identity_lock: str = f"{PREFIX}_identity_lock"
    color_palette: str = f"{PREFIX}_color_palette"
    minimal_traits: str = f"{PREFIX}_minimal_traits"
    adaptable_slots: str = f"{PREFIX}_adaptable_slots"
    default_slot_preference: str = f"{PREFIX}_default_slot_preference"
    presence_spectrum: str = f"{PREFIX}_presence_spectrum"
    role_presets: str = f"{PREFIX}_role_presets"
    negative_constraints: str = f"{PREFIX}_negative_constraints"
    semantic_boundary: str = f"{PREFIX}_semantic_boundary"
    identity_suppression_rules: str = f"{PREFIX}_identity_suppression_rules"
    forbidden_elements: str = f"{PREFIX}_forbidden_elements"
    visible_text_whitelist: str = f"{PREFIX}_visible_text_whitelist"
    active_asset_tab: str = f"{PREFIX}_active_asset_tab"

    @classmethod
    def all_keys(cls) -> set[str]:
        return {getattr(cls, f.name) for f in fields(cls)}

    @classmethod
    def widget_keys(cls) -> set[str]:
        return {k for k in cls.all_keys() if not k.startswith("_")}


@dataclass(frozen=True)
class _SceneCastKeys:
    select: str = f"{PREFIX}_scene_cast_select"
    scene_cast_id: str = f"{PREFIX}_scene_cast_id"
    storyboard_plan_id: str = f"{PREFIX}_storyboard_plan_id"
    frame_id: str = f"{PREFIX}_frame_id"
    character_ids: str = f"{PREFIX}_character_ids"
    scene_id: str = f"{PREFIX}_scene_id"
    prop_ids: str = f"{PREFIX}_prop_ids"
    style_id: str = f"{PREFIX}_style_id"
    continuity_notes: str = f"{PREFIX}_continuity_notes"

    @classmethod
    def all_keys(cls) -> set[str]:
        return {getattr(cls, f.name) for f in fields(cls)}

    @classmethod
    def widget_keys(cls) -> set[str]:
        return {k for k in cls.all_keys() if not k.startswith("_")}


@dataclass(frozen=True)
class _PresetKeys:
    select: str = f"{PREFIX}_builtin_asset_bible_preset_select"
    import_id: str = f"{PREFIX}_import_asset_bible_id"


@dataclass(frozen=True)
class _MetaKeys:
    ip_profile_populated_for: str = f"{PREFIX}_ip_profile_populated_for"


class IPSessionKeys:
    ASSET_BIBLE = _AssetBibleKeys()
    FORM = _IPFormKeys()
    SCENE_CAST = _SceneCastKeys()
    PRESET = _PresetKeys()
    META = _MetaKeys()


__all__ = ["IPSessionKeys"]
