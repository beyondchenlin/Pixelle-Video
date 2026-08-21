from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FinalVisualPromptAssemblyResponse(BaseModel):
    """Strict structured output for one final visual-prompt assembly call."""

    model_config = ConfigDict(extra="forbid")

    positive_prompt: str = Field(min_length=1, max_length=1200)
    negative_prompt: str = Field(default="", max_length=800)

    @field_validator("positive_prompt", "negative_prompt", mode="before")
    @classmethod
    def normalize_prompt_text(cls, value):
        if not isinstance(value, str):
            raise ValueError("prompt fields must be strings")
        return " ".join(value.strip().split())


__all__ = ["FinalVisualPromptAssemblyResponse"]
