from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class ScriptGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_text: str

    @field_validator("source_text")
    @classmethod
    def _validate_source_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("source_text must not be empty")
        return stripped


__all__ = ["ScriptGenerationResponse"]
