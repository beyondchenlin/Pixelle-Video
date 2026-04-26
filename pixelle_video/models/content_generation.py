"""Structured response models for narration and prompt generation."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


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


class SmartStoryboardFrameResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_text: str
    visual_goal: str
    prompt_intent: str
    source_start: Optional[int] = None
    source_end: Optional[int] = None

    @field_validator("source_text", "visual_goal", "prompt_intent")
    @classmethod
    def _validate_text_fields(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("smart storyboard text fields must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_source_range_pair(self):
        if (self.source_start is None) != (self.source_end is None):
            raise ValueError("source_start and source_end must be set together")
        return self


class SmartStoryboardPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    frames: list[SmartStoryboardFrameResponse]

    @field_validator("frames")
    @classmethod
    def _validate_frames(cls, values: list[SmartStoryboardFrameResponse]) -> list[SmartStoryboardFrameResponse]:
        if not values:
            raise ValueError("frames must not be empty")
        return values


__all__ = [
    "NarrationBatchResponse",
    "ImagePromptBatchResponse",
    "VideoPromptBatchResponse",
    "SmartStoryboardFrameResponse",
    "SmartStoryboardPlanResponse",
]
