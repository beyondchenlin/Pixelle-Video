"""Structured response models for narration and prompt generation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class _StringListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @staticmethod
    def _normalize_strings(values: list[str], field_name: str) -> list[str]:
        normalized: list[str] = []
        for value in values:
            if not isinstance(value, str):
                raise ValueError(f"{field_name} must contain strings only")
            stripped = value.strip()
            if not stripped:
                raise ValueError(f"{field_name} must not contain empty strings")
            normalized.append(stripped)
        return normalized


class NarrationBatchResponse(_StringListResponse):
    narrations: list[str]

    @field_validator("narrations")
    @classmethod
    def _validate_narrations(cls, values: list[str]) -> list[str]:
        return cls._normalize_strings(values, "narrations")


class ImagePromptBatchResponse(_StringListResponse):
    image_prompts: list[str]

    @field_validator("image_prompts")
    @classmethod
    def _validate_image_prompts(cls, values: list[str]) -> list[str]:
        return cls._normalize_strings(values, "image_prompts")


class VideoPromptBatchResponse(_StringListResponse):
    video_prompts: list[str]

    @field_validator("video_prompts")
    @classmethod
    def _validate_video_prompts(cls, values: list[str]) -> list[str]:
        return cls._normalize_strings(values, "video_prompts")


__all__ = [
    "NarrationBatchResponse",
    "ImagePromptBatchResponse",
    "VideoPromptBatchResponse",
]
