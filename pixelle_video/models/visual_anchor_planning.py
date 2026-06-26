from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pixelle_video.models.ip_prompt_planning import (
    IPFrameAdaptationPackage,
    IPPresenceType,
    IPRoleSlot,
)


class AnchorFunction(str, Enum):
    PRIMARY_CARRIER = "primary_carrier"
    CO_PRESENT_SUPPORT = "co_present_support"
    EXPLAINER_POINTER = "explainer_pointer"
    ENVIRONMENTAL_SIGNATURE = "environmental_signature"
    EMBEDDED_MARK = "embedded_mark"
    MATERIAL_SIGNATURE = "material_signature"
    SCENE_BOUND_PROP = "scene_bound_prop"
    CONTENT_BOUND_PARTICIPANT = "content_bound_participant"
    CONTENT_EXPLANATION_DIRECTOR = "content_explanation_director"
    MICRO_CAMEO = "micro_cameo"
    SUPPRESSED = "suppressed"


class AnchorCarrierType(str, Enum):
    LIVING_CHARACTER = "living_character"
    BACKGROUND_EXTRA = "background_extra"
    PROP_OBJECT = "prop_object"
    FIGURINE = "figurine"
    EMBEDDED_MARK = "embedded_mark"
    WALL_ART = "wall_art"
    SCREEN_MARK = "screen_mark"
    PAGE_MARK = "page_mark"
    ENVIRONMENT_DETAIL = "environment_detail"
    PARTIAL_DETAIL = "partial_detail"
    PRINTED_MARK = "printed_mark"
    BOOKPLATE_OR_STAMP = "bookplate_or_stamp"
    EMBOSSED_MARK = "embossed_mark"
    ENGRAVED_MARK = "engraved_mark"
    SURFACE_GRAPHIC = "surface_graphic"
    DECORATIVE_OBJECT = "decorative_object"
    WEARABLE_SYMBOL = "wearable_symbol"
    SMALL_SUPPORTING_PROP = "small_supporting_prop"
    MINOR_SUPPORTING_CHARACTER = "minor_supporting_character"
    CONTENT_BOUND_IP_ACTOR = "content_bound_ip_actor"
    CONTENT_BOUND_SYSTEM_COMPONENT = "content_bound_system_component"
    CONTENT_BOUND_SCALE_REFERENCE = "content_bound_scale_reference"
    CONTENT_BOUND_EXPLANATION_DIRECTOR = "content_bound_explanation_director"
    SUPPRESSED = "suppressed"


class AnchorStyleRelation(str, Enum):
    BLENDED = "blended"
    ACCENTED = "accented"
    CONTRASTING = "contrasting"
    INDEPENDENT = "independent"


class AnchorProminence(str, Enum):
    HIDDEN = "hidden"
    EMBEDDED_MARK = "embedded_mark"
    TINY_PROP = "tiny_prop"
    MICRO_CAMEO = "micro_cameo"
    SMALL_SIDE_CHARACTER = "small_side_character"
    CONTENT_PARTICIPANT = "content_participant"
    PRIMARY_CARRIER = "primary_carrier"


@dataclass(frozen=True)
class VisualAnchorPlacementPlan:
    frame_id: str
    anchor_function: AnchorFunction
    anchor_carrier_type: AnchorCarrierType
    placement_zone: str
    support_anchor: str
    scale_ratio: str
    depth_layer: str
    contact_relation: str
    interaction_target: str
    occlusion_relation: str
    style_relation: AnchorStyleRelation
    image_prompt_clause: str
    anchor_prominence: AnchorProminence = AnchorProminence.TINY_PROP
    visual_weight_clause: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = "visual_anchor_placement_plan.v3_1_scene_bound"

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _require_non_empty("frame_id", self.frame_id))
        object.__setattr__(self, "anchor_function", AnchorFunction(self.anchor_function))
        object.__setattr__(self, "anchor_carrier_type", AnchorCarrierType(self.anchor_carrier_type))
        object.__setattr__(self, "style_relation", AnchorStyleRelation(self.style_relation))
        object.__setattr__(self, "anchor_prominence", AnchorProminence(self.anchor_prominence))
        for field_name in (
            "placement_zone",
            "support_anchor",
            "scale_ratio",
            "depth_layer",
            "contact_relation",
            "interaction_target",
            "occlusion_relation",
            "image_prompt_clause",
            "visual_weight_clause",
        ):
            object.__setattr__(self, field_name, _optional_text(getattr(self, field_name)))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        object.__setattr__(self, "version", _require_non_empty("version", self.version))

    @property
    def visible(self) -> bool:
        return (
            self.anchor_function is not AnchorFunction.SUPPRESSED
            and self.anchor_carrier_type is not AnchorCarrierType.SUPPRESSED
            and self.anchor_prominence is not AnchorProminence.HIDDEN
            and bool(self.image_prompt_clause)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "frame_id": self.frame_id,
            "anchor_function": self.anchor_function.value,
            "anchor_carrier_type": self.anchor_carrier_type.value,
            "anchor_prominence": self.anchor_prominence.value,
            "visual_weight_clause": self.visual_weight_clause,
            "placement_zone": self.placement_zone,
            "support_anchor": self.support_anchor,
            "scale_ratio": self.scale_ratio,
            "depth_layer": self.depth_layer,
            "contact_relation": self.contact_relation,
            "interaction_target": self.interaction_target,
            "occlusion_relation": self.occlusion_relation,
            "style_relation": self.style_relation.value,
            "image_prompt_clause": self.image_prompt_clause,
            "metadata": dict(self.metadata),
        }

    def to_ip_frame_adaptation_package(self, base_package: IPFrameAdaptationPackage) -> IPFrameAdaptationPackage:
        if not self.visible:
            return IPFrameAdaptationPackage(
                frame_id=base_package.frame_id,
                ip_presence_type=IPPresenceType.ABSENT,
                presence_mode="absent",
                semantic_reason="visual anchor integration suppressed for this frame",
                must_not_replace=base_package.must_not_replace,
                identity_anchors_visible=(),
                identity_anchors_suppressed=base_package.identity_anchors_visible + base_package.identity_anchors_suppressed,
                identity_color_terms=base_package.identity_color_terms,
                appearance_description=None,
                visual_identity=base_package.visual_identity,
                role_slot=IPRoleSlot.ABSENT,
                image_text_plan=base_package.image_text_plan,
                prompt_weight=0.0,
                negative_constraints=base_package.negative_constraints,
            )
        return IPFrameAdaptationPackage(
            frame_id=base_package.frame_id,
            ip_presence_type=base_package.ip_presence_type,
            presence_mode=base_package.presence_mode,
            semantic_reason=f"visual anchor integration: {self.anchor_carrier_type.value}, prominence: {self.anchor_prominence.value}",
            must_not_replace=base_package.must_not_replace,
            identity_anchors_visible=base_package.identity_anchors_visible,
            identity_anchors_suppressed=base_package.identity_anchors_suppressed,
            identity_color_terms=base_package.identity_color_terms,
            outfit_theme=base_package.outfit_theme,
            outfit_condition=base_package.outfit_condition,
            accessories=base_package.accessories,
            action=base_package.action,
            expression=base_package.expression,
            pose=base_package.pose,
            camera_relationship=base_package.camera_relationship,
            depth_layer=self.depth_layer or base_package.depth_layer,
            interaction_target=self.interaction_target or base_package.interaction_target,
            continuity_from_previous=base_package.continuity_from_previous,
            appearance_description=self.image_prompt_clause,
            visual_identity=base_package.visual_identity,
            role_slot=_role_slot_for_anchor_function(self.anchor_function),
            shot_fit_notes=self.occlusion_relation or base_package.shot_fit_notes,
            image_text_plan=base_package.image_text_plan,
            prompt_weight=_clamped_prompt_weight(base_package.prompt_weight),
            negative_constraints=base_package.negative_constraints,
        )


def _role_slot_for_anchor_function(anchor_function: AnchorFunction) -> IPRoleSlot:
    if anchor_function is AnchorFunction.PRIMARY_CARRIER:
        return IPRoleSlot.PROTAGONIST
    if anchor_function in {
        AnchorFunction.CO_PRESENT_SUPPORT,
        AnchorFunction.EXPLAINER_POINTER,
        AnchorFunction.SCENE_BOUND_PROP,
        AnchorFunction.CONTENT_BOUND_PARTICIPANT,
        AnchorFunction.CONTENT_EXPLANATION_DIRECTOR,
    }:
        return IPRoleSlot.SUPPORTING
    if anchor_function in {
        AnchorFunction.ENVIRONMENTAL_SIGNATURE,
        AnchorFunction.EMBEDDED_MARK,
        AnchorFunction.MATERIAL_SIGNATURE,
        AnchorFunction.MICRO_CAMEO,
    }:
        return IPRoleSlot.PASSERBY
    return IPRoleSlot.ABSENT


def _clamped_prompt_weight(value: Any) -> float:
    try:
        return min(float(value or 0.0), 0.55)
    except (TypeError, ValueError):
        return 0.25


def _require_non_empty(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


__all__ = [
    "AnchorCarrierType",
    "AnchorFunction",
    "AnchorProminence",
    "AnchorStyleRelation",
    "VisualAnchorPlacementPlan",
]
