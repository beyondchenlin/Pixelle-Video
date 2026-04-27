from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator
from pixelle_video.utils.text_normalization import normalize_generated_source_text


class ScriptGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_text: str

    @field_validator("source_text")
    @classmethod
    def _validate_source_text(cls, value: str) -> str:
        normalized = normalize_generated_source_text(value)
        if not normalized:
            raise ValueError("source_text must not be empty")
        return normalized


__all__ = ["ScriptGenerationResponse"]
