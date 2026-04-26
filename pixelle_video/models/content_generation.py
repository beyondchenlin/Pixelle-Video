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
    # New field: sentence indices covered by this frame (alternative to source_start/source_end)
    # Accepts int (single sentence) or list[int] (multiple sentences) for better LLM compatibility
    sentence_indices: Optional[list[int] | int] = None
    # Source span indices are used when an exact manual frame count requires splitting
    # inside long sentences. Spans are deterministic server-provided source ranges.
    source_span_indices: Optional[list[int] | int] = None

    @field_validator("source_text", "visual_goal", "prompt_intent")
    @classmethod
    def _validate_text_fields(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("smart storyboard text fields must not be empty")
        return stripped

    @field_validator("sentence_indices", mode="before")
    @classmethod
    def _normalize_sentence_indices(cls, value):
        """Convert various formats to list[int] for uniform processing.
        
        Handles:
        - None -> None
        - int -> [int]
        - list[int] -> list[int]
        - str like "[0, 1]" -> [0, 1] (LLM sometimes returns JSON string)
        """
        if value is None:
            return None
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            # Handle JSON string format from LLM
            try:
                import json
                parsed = json.loads(value)
                if isinstance(parsed, int):
                    return [parsed]
                if isinstance(parsed, list):
                    return [int(x) for x in parsed]
            except (json.JSONDecodeError, ValueError):
                pass
            raise ValueError(f"Cannot parse sentence_indices string: {value}")
        return value

    @field_validator("source_span_indices", mode="before")
    @classmethod
    def _normalize_source_span_indices(cls, value):
        if value is None:
            return None
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            try:
                import json
                parsed = json.loads(value)
                if isinstance(parsed, int):
                    return [parsed]
                if isinstance(parsed, list):
                    return [int(x) for x in parsed]
            except (json.JSONDecodeError, ValueError):
                pass
            raise ValueError(f"Cannot parse source_span_indices string: {value}")
        return value

    @model_validator(mode="after")
    def _validate_source_range_pair(self):
        # Validate that if char range is provided, both are set
        if (self.source_start is not None) != (self.source_end is not None):
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
