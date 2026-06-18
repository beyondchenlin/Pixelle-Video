"""Structured output contract for IP role selection."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pixelle_video.models.ip_prompt_planning import IPRoleSlot


class IPRoleSelectionItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_index: int = Field(
        ge=0,
        description="Zero-based frame index matching the input frame sequence.",
    )
    role_slot: IPRoleSlot = Field(
        description="The narrative slot filled by the IP in this frame.",
    )
    role_label: str = Field(
        min_length=1,
        description="Concise human-readable label for the IP function in this frame.",
    )
    presence_level: str = Field(
        min_length=1,
        description="How visible the IP is in this frame.",
    )
    appearance_description: str = Field(
        default="",
        description=(
            "Scene-integrated description of the visible IP. Must be empty when role_slot "
            "is absent."
        ),
    )
    reason: str = Field(
        default="",
        description="Brief rationale for the selected role.",
    )

    @field_validator("role_label", "presence_level", "appearance_description", "reason", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            return str(value)
        return value.strip()

    @model_validator(mode="after")
    def _validate_absent_appearance_contract(self) -> "IPRoleSelectionItemResponse":
        if self.role_slot is IPRoleSlot.ABSENT and self.appearance_description:
            raise ValueError("appearance_description must be empty when role_slot is absent")
        return self

    def to_role_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class IPRoleSelectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_selections: list[IPRoleSelectionItemResponse] = Field(
        min_length=1,
        description="One IP role decision per input frame, preserving frame order.",
    )

    def to_role_dicts(self) -> list[dict[str, Any]]:
        return [item.to_role_dict() for item in self.role_selections]


__all__ = [
    "IPRoleSelectionItemResponse",
    "IPRoleSelectionResponse",
]
