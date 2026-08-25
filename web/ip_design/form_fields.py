from __future__ import annotations

import types
import typing
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel


class IPProfileFieldKind(str, Enum):
    TEXT_INPUT = "text_input"
    TEXT_AREA = "text_area"
    SELECT_OR_CUSTOM = "select_or_custom"


@dataclass(frozen=True, slots=True)
class IPProfileFormField:
    """Single source of truth for an IPProfileDraft field rendered in Streamlit."""

    name: str
    section_key: str
    label_key: str
    help_key: str
    kind: IPProfileFieldKind = IPProfileFieldKind.TEXT_INPUT
    options: tuple[str, ...] = ()
    option_translation_prefix: str = ""
    custom_translation_key: str = ""
    default: str = ""
    height: int = 68
    multiline_list: bool = False


SECTION_BASIC = "ip_design.asset_bible.section_basic"
SECTION_VISUAL = "ip_design.asset_bible.section_visual"
SECTION_ADAPTABLE = "ip_design.asset_bible.section_adaptable"
SECTION_REPLACEMENT = "ip_design.asset_bible.section_replacement"
SECTION_ROLES = "ip_design.asset_bible.section_roles"
SECTION_CONSTRAINTS = "ip_design.asset_bible.section_constraints"
SECTION_TEXT = "ip_design.asset_bible.section_text"


IP_PROFILE_FORM_SECTIONS: tuple[tuple[str, tuple[IPProfileFormField, ...]], ...] = (
    (
        SECTION_BASIC,
        (
            IPProfileFormField(
                name="ip_type",
                section_key=SECTION_BASIC,
                label_key="ip_design.asset_bible.ip_type",
                help_key="ip_design.help.ip_type",
                kind=IPProfileFieldKind.SELECT_OR_CUSTOM,
                options=(
                    "cartoon_animal",
                    "anime_human",
                    "hybrid_real_anime",
                    "line_drawing",
                    "3d_cartoon",
                ),
                option_translation_prefix="ip_design.ip_type",
                custom_translation_key="ip_design.ip_type.custom",
                default="cartoon_animal",
            ),
            IPProfileFormField(
                "series_visual_signature_profile_id", SECTION_BASIC, "ip_design.asset_bible.series_visual_signature_profile_id",
                "ip_design.help.series_visual_signature_profile_id",
            ),
            IPProfileFormField(
                "name", SECTION_BASIC, "ip_design.asset_bible.ip_name", "ip_design.help.ip_name",
            ),
            IPProfileFormField(
                "logline", SECTION_BASIC, "ip_design.asset_bible.logline",
                "ip_design.help.logline", kind=IPProfileFieldKind.TEXT_AREA, height=68,
            ),
            IPProfileFormField(
                "visual_summary", SECTION_BASIC, "ip_design.asset_bible.visual_summary",
                "ip_design.help.visual_summary", kind=IPProfileFieldKind.TEXT_AREA, height=88,
            ),
        ),
    ),
    (
        SECTION_VISUAL,
        (
            IPProfileFormField(
                "identity_lock", SECTION_VISUAL, "ip_design.asset_bible.identity_lock",
                "ip_design.help.identity_lock",
            ),
            IPProfileFormField(
                "color_palette", SECTION_VISUAL, "ip_design.asset_bible.color_palette",
                "ip_design.help.color_palette",
            ),
            IPProfileFormField(
                "style_hint", SECTION_VISUAL, "ip_design.asset_bible.style_hint",
                "ip_design.help.style_hint", kind=IPProfileFieldKind.TEXT_AREA, height=88,
            ),
            IPProfileFormField(
                "minimal_traits", SECTION_VISUAL, "ip_design.asset_bible.minimal_traits",
                "ip_design.help.minimal_traits",
            ),
        ),
    ),
    (
        SECTION_ADAPTABLE,
        (
            IPProfileFormField(
                "adaptable_slots", SECTION_ADAPTABLE, "ip_design.asset_bible.adaptable_slots",
                "ip_design.help.adaptable_slots",
            ),
        ),
    ),
    (
        SECTION_REPLACEMENT,
        (
            IPProfileFormField(
                name="default_slot_preference",
                section_key=SECTION_REPLACEMENT,
                label_key="ip_design.asset_bible.default_slot_preference",
                help_key="ip_design.help.default_slot_preference",
                kind=IPProfileFieldKind.SELECT_OR_CUSTOM,
                options=("prefer_supporting", "prefer_main", "auto", "minimal"),
                option_translation_prefix="ip_design.slot_preference",
                custom_translation_key="ip_design.slot_preference.custom",
                default="prefer_supporting",
            ),
            IPProfileFormField(
                "presence_spectrum", SECTION_REPLACEMENT,
                "ip_design.asset_bible.presence_spectrum", "ip_design.help.presence_spectrum",
            ),
        ),
    ),
    (
        SECTION_ROLES,
        (
            IPProfileFormField(
                "role_presets", SECTION_ROLES, "ip_design.asset_bible.role_presets",
                "ip_design.help.role_presets", kind=IPProfileFieldKind.TEXT_AREA,
                height=136, multiline_list=True,
            ),
        ),
    ),
    (
        SECTION_CONSTRAINTS,
        (
            IPProfileFormField(
                "negative_constraints", SECTION_CONSTRAINTS,
                "ip_design.asset_bible.negative_constraints", "ip_design.help.negative_constraints",
            ),
            IPProfileFormField(
                "semantic_boundary", SECTION_CONSTRAINTS,
                "ip_design.asset_bible.semantic_boundary", "ip_design.help.semantic_boundary",
            ),
            IPProfileFormField(
                "identity_suppression_rules", SECTION_CONSTRAINTS,
                "ip_design.asset_bible.identity_suppression_rules",
                "ip_design.help.identity_suppression_rules",
            ),
            IPProfileFormField(
                "forbidden_elements", SECTION_CONSTRAINTS,
                "ip_design.asset_bible.forbidden_elements", "ip_design.help.forbidden_elements",
            ),
        ),
    ),
    (
        SECTION_TEXT,
        (
            IPProfileFormField(
                "visible_text_whitelist", SECTION_TEXT,
                "ip_design.asset_bible.visible_text_whitelist",
                "ip_design.help.visible_text_whitelist",
            ),
        ),
    ),
)

IP_PROFILE_FORM_FIELDS: tuple[IPProfileFormField, ...] = tuple(
    field for _, fields in IP_PROFILE_FORM_SECTIONS for field in fields
)


def ip_profile_form_field_names() -> set[str]:
    return {field.name for field in IP_PROFILE_FORM_FIELDS}


def _carrier_type_from_annotation(annotation: Any) -> type:
    origin = typing.get_origin(annotation)
    if origin is list:
        return list
    if origin is dict:
        return dict
    if origin in (typing.Union, types.UnionType):
        non_none_args = [arg for arg in typing.get_args(annotation) if arg is not type(None)]
        if len(non_none_args) == 1:
            return _carrier_type_from_annotation(non_none_args[0])
    if annotation is bool:
        return bool
    return str


def derive_ip_profile_carrier_fields(
    model_cls: type[BaseModel],
    *,
    form_field_names: Iterable[str] | None = None,
) -> list[tuple[str, type]]:
    """Return model fields persisted without direct Streamlit widgets.

    This keeps save payload preservation coupled to the Pydantic model instead of a
    manually maintained list in the component. Adding a new IPProfileDraft field
    becomes safe by default: either add it to IP_PROFILE_FORM_SECTIONS to render it,
    or it will be preserved as a carrier field.
    """
    rendered_field_names = set(form_field_names or ip_profile_form_field_names())
    hints = typing.get_type_hints(model_cls)
    result: list[tuple[str, type]] = []
    for name in model_cls.model_fields:
        if name in rendered_field_names:
            continue
        result.append((name, _carrier_type_from_annotation(hints.get(name, str))))
    return result


__all__ = [
    "IPProfileFieldKind",
    "IPProfileFormField",
    "IP_PROFILE_FORM_SECTIONS",
    "IP_PROFILE_FORM_FIELDS",
    "derive_ip_profile_carrier_fields",
    "ip_profile_form_field_names",
]
