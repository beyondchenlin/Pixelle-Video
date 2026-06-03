from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pixelle_video.models.visual_anchor_planning import (
    AnchorCarrierType,
    AnchorFunction,
    AnchorProminence,
    AnchorStyleRelation,
)


class MandatoryVisualAnchorIntegrationManifestationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    form: str
    location: str
    visibility: str
    relationship: str

    @field_validator("form", "location", "visibility", "relationship", mode="before")
    @classmethod
    def _require_non_empty_text(cls, value: Any) -> str:
        return _require_non_empty_text(value)


class MandatoryVisualAnchorIntegrationPlanResponse(BaseModel):
    """Single selected placement plan for mandatory visual-signature integration.

    This is intentionally not a candidate-list schema. The runtime consumes exactly one
    visible plan per frame, so the LLM contract mirrors that shape directly.
    """

    model_config = ConfigDict(extra="forbid")

    frame_id: str
    carrier_type: AnchorCarrierType
    anchor_function: AnchorFunction
    prominence: AnchorProminence
    style_relation: AnchorStyleRelation = AnchorStyleRelation.BLENDED
    placement: str
    support_anchor: str
    contact_relation: str
    visual_weight_clause: str
    image_prompt_clause: str
    integrated_scene_prompt: str
    integration_strategy: str
    anchor_manifestation: MandatoryVisualAnchorIntegrationManifestationResponse
    scene_coherence_score: int = Field(ge=1, le=10)
    disruption_risk: int = Field(ge=1, le=10)
    identity_preservation_score: int = Field(ge=1, le=10)
    reason: str
    interaction_target: str = ""
    occlusion_relation: str = ""

    @field_validator(
        "frame_id",
        "placement",
        "support_anchor",
        "contact_relation",
        "visual_weight_clause",
        "image_prompt_clause",
        "integrated_scene_prompt",
        "integration_strategy",
        "reason",
        mode="before",
    )
    @classmethod
    def _require_non_empty_text(cls, value: Any) -> str:
        return _require_non_empty_text(value)

    @field_validator("interaction_target", "occlusion_relation", mode="before")
    @classmethod
    def _optional_text(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

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
    "MandatoryVisualAnchorIntegrationManifestationResponse",
    "MandatoryVisualAnchorIntegrationPlanResponse",
    "MandatoryVisualAnchorIntegrationResponse",
]
