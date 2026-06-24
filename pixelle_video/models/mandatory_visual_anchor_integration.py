from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

VisibleAnchorCarrierType = Literal[
    "living_character",
    "background_extra",
    "prop_object",
    "figurine",
    "embedded_mark",
    "wall_art",
    "screen_mark",
    "page_mark",
    "environment_detail",
    "partial_detail",
    "printed_mark",
    "bookplate_or_stamp",
    "embossed_mark",
    "engraved_mark",
    "surface_graphic",
    "decorative_object",
    "wearable_symbol",
    "small_supporting_prop",
    "minor_supporting_character",
]
VisibleAnchorFunction = Literal[
    "primary_carrier",
    "co_present_support",
    "explainer_pointer",
    "environmental_signature",
    "embedded_mark",
    "material_signature",
    "scene_bound_prop",
    "micro_cameo",
]
VisibleAnchorProminence = Literal[
    "embedded_mark",
    "tiny_prop",
    "micro_cameo",
    "small_side_character",
    "primary_carrier",
]
AnchorStyleRelationValue = Literal["blended", "accented", "contrasting", "independent"]


class MandatoryVisualAnchorIntegrationPlanResponse(BaseModel):
    """Flat wire contract for mandatory visual-signature integration.

    The provider-facing schema is intentionally flat. Qwen JSON mode is much more
    reliable with scalar fields than nested object definitions, and the service maps
    these fields back into the internal visual-anchor domain shape after validation.
    """

    model_config = ConfigDict(extra="forbid")

    frame_id: str
    carrier_type: VisibleAnchorCarrierType
    anchor_function: VisibleAnchorFunction
    prominence: VisibleAnchorProminence
    style_relation: AnchorStyleRelationValue = "blended"
    placement: str
    support_anchor: str
    contact_relation: str
    visual_weight_clause: str
    image_prompt_clause: str
    integrated_scene_prompt: str
    integration_strategy: str
    manifestation_form: str
    manifestation_location: str
    manifestation_visibility: str
    manifestation_relationship: str
    scene_coherence_score: int = Field(ge=1, le=10)
    disruption_risk: int = Field(ge=1, le=10)
    identity_preservation_score: int = Field(ge=1, le=10)
    reason: str
    interaction_target: str = ""
    occlusion_relation: str = ""
    ip_duty_preset: str = ""
    action_verb: str = ""
    scene_binding: str = ""
    presentation_form: str = ""
    channel_identity_removal_test: str = ""

    @field_validator(
        "frame_id",
        "placement",
        "support_anchor",
        "contact_relation",
        "visual_weight_clause",
        "image_prompt_clause",
        "integrated_scene_prompt",
        "integration_strategy",
        "manifestation_form",
        "manifestation_location",
        "manifestation_visibility",
        "manifestation_relationship",
        "reason",
        mode="before",
    )
    @classmethod
    def _require_non_empty_text(cls, value: Any) -> str:
        return _require_non_empty_text(value)

    @field_validator(
        "interaction_target",
        "occlusion_relation",
        "ip_duty_preset",
        "action_verb",
        "scene_binding",
        "presentation_form",
        "channel_identity_removal_test",
        mode="before",
    )
    @classmethod
    def _optional_text(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def to_plan_payload(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "carrier_type": self.carrier_type,
            "anchor_function": self.anchor_function,
            "prominence": self.prominence,
            "style_relation": self.style_relation,
            "placement": self.placement,
            "support_anchor": self.support_anchor,
            "contact_relation": self.contact_relation,
            "interaction_target": self.interaction_target,
            "occlusion_relation": self.occlusion_relation,
            "visual_weight_clause": self.visual_weight_clause,
            "image_prompt_clause": self.image_prompt_clause,
            "integrated_scene_prompt": self.integrated_scene_prompt,
            "integration_strategy": self.integration_strategy,
            "anchor_manifestation": {
                "form": self.manifestation_form,
                "location": self.manifestation_location,
                "visibility": self.manifestation_visibility,
                "relationship": self.manifestation_relationship,
            },
            "scene_coherence_score": self.scene_coherence_score,
            "disruption_risk": self.disruption_risk,
            "identity_preservation_score": self.identity_preservation_score,
            "reason": self.reason,
            "ip_duty_preset": self.ip_duty_preset,
            "action_verb": self.action_verb,
            "scene_binding": self.scene_binding,
            "presentation_form": self.presentation_form,
            "channel_identity_removal_test": self.channel_identity_removal_test,
        }


class MandatoryVisualAnchorIntegrationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visual_anchor_integration_plans: list[MandatoryVisualAnchorIntegrationPlanResponse] = Field(
        min_length=1
    )


def _require_non_empty_text(value: Any) -> str:
    if value is None:
        raise ValueError("field must not be empty")
    text = str(value).strip()
    if not text:
        raise ValueError("field must not be empty")
    return text


__all__ = [
    "AnchorStyleRelationValue",
    "MandatoryVisualAnchorIntegrationPlanResponse",
    "MandatoryVisualAnchorIntegrationResponse",
    "VisibleAnchorCarrierType",
    "VisibleAnchorFunction",
    "VisibleAnchorProminence",
]
