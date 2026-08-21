from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

FINAL_VISUAL_PROMPT_SECTION_KEYS = (
    "main_content",
    "participation",
    "identity",
    "instance_control",
    "placement",
    "scene_fusion",
    "style",
)


class FinalVisualPromptAssemblySections(BaseModel):
    """Structured semantic sections that must compile to the final prompt."""

    model_config = ConfigDict(extra="forbid")

    main_content: str = Field(min_length=1, max_length=800)
    participation: str = Field(min_length=1, max_length=800)
    identity: str = Field(min_length=1, max_length=800)
    instance_control: str = Field(min_length=1, max_length=800)
    placement: str = Field(min_length=1, max_length=800)
    scene_fusion: str = Field(min_length=1, max_length=800)
    style: str = Field(default="", max_length=800)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_section_text(cls, value):
        if not isinstance(value, str):
            raise ValueError("prompt section fields must be strings")
        return " ".join(value.strip().split())

    def to_prompt_sections(self) -> dict[str, str]:
        payload = self.model_dump()
        return {key: payload[key] for key in FINAL_VISUAL_PROMPT_SECTION_KEYS if payload.get(key)}


class FinalVisualPromptAssemblyResponse(BaseModel):
    """Strict structured output for one final visual-prompt assembly call."""

    model_config = ConfigDict(extra="forbid")

    positive_prompt: str = Field(min_length=1, max_length=800)
    negative_prompt: str = Field(default="", max_length=800)
    prompt_sections: FinalVisualPromptAssemblySections

    @field_validator("positive_prompt", "negative_prompt", mode="before")
    @classmethod
    def normalize_prompt_text(cls, value):
        if not isinstance(value, str):
            raise ValueError("prompt fields must be strings")
        return " ".join(value.strip().split())


__all__ = [
    "FINAL_VISUAL_PROMPT_SECTION_KEYS",
    "FinalVisualPromptAssemblyResponse",
    "FinalVisualPromptAssemblySections",
]
