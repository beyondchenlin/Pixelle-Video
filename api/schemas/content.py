# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Content generation API schemas
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.schemas.storyboard_contract import (
    StoryboardFrameOverride,
    StoryboardPlanPayload,
    StoryboardPromptLanguage,
)
from api.schemas.text_rendering import TextRenderingRequest
from pixelle_video.models.storyboard_planning import (
    ConsistencyStrength,
    ContentMode,
    RoleStrategy,
    ShotOverridePolicy,
)
from pixelle_video.utils.prompt_generation_performance import (
    PROMPT_BATCH_CONCURRENT_LIMIT_MAX,
    PROMPT_BATCH_CONCURRENT_LIMIT_MIN,
    PROMPT_BATCH_SIZE_MAX,
    PROMPT_BATCH_SIZE_MIN,
)

# ============================================================================
# Narration Generation
# ============================================================================

class NarrationGenerateRequest(BaseModel):
    """Narration generation request"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "Atomic Habits is about making small changes that lead to remarkable results.",
                "n_scenes": 5,
                "min_words": 5,
                "max_words": 20,
            }
        }
    )

    text: str = Field(..., description="Source text to generate narrations from")
    n_scenes: int = Field(5, ge=1, le=20, description="Number of scenes")
    min_words: int = Field(5, ge=1, le=100, description="Minimum words per narration")
    max_words: int = Field(20, ge=1, le=200, description="Maximum words per narration")


class NarrationGenerateResponse(BaseModel):
    """Narration generation response"""
    success: bool = True
    message: str = "Success"
    narrations: List[str] = Field(..., description="Generated narrations")


# ============================================================================
# Image Prompt Generation
# ============================================================================

class ImagePromptGenerateRequest(BaseModel):
    """Image prompt generation request"""
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "narrations": [
                    "Small habits compound over time",
                    "Focus on systems, not goals",
                ],
                "min_words": 30,
                "max_words": 60,
                "prompt_prefix": "angry birds world",
                "workflow": "selfhost/image_z_image_turbo_gguf.json",
            }
        }
    )

    narrations: List[str] = Field(..., description="List of narrations")
    min_words: int = Field(30, ge=10, le=100, description="Minimum words per prompt")
    max_words: int = Field(60, ge=10, le=200, description="Maximum words per prompt")
    llm_prompt_batch_size: Optional[int] = Field(
        None,
        ge=PROMPT_BATCH_SIZE_MIN,
        le=PROMPT_BATCH_SIZE_MAX,
        description="Request-scoped LLM prompt batch size override",
    )
    llm_prompt_batch_concurrent_limit: Optional[int] = Field(
        None,
        ge=PROMPT_BATCH_CONCURRENT_LIMIT_MIN,
        le=PROMPT_BATCH_CONCURRENT_LIMIT_MAX,
        description="Request-scoped LLM prompt batch concurrency override",
    )
    prompt_prefix: Optional[str] = Field(
        None,
        description="Request-scoped image style prefix override",
    )
    workflow: Optional[str] = Field(
        None,
        description="Workflow key used for capability-gated optional fields",
    )
    storyboard_prompt_language: StoryboardPromptLanguage = Field(
        "en_US",
        description="Language used for storyboard planning fields and generated image prompts",
    )
    storyboard_generation: Optional[StoryboardPlanPayload] = Field(
        None,
        description="Replayable storyboard plan contract used to validate plan-aware prompt overrides",
    )
    world_preset_id: Optional[str] = Field(None, description="Storyboard world preset id")
    shot_preset_id: Optional[str] = Field(None, description="Storyboard shot preset id")
    consistency_strength: Optional[ConsistencyStrength] = Field(
        None,
        description="Storyboard consistency strength",
    )
    content_mode: Optional[ContentMode] = Field(None, description="Storyboard content mode override")
    role_strategy: Optional[RoleStrategy] = Field(None, description="Storyboard role strategy override")
    role_locking_strength: Optional[ConsistencyStrength] = Field(
        None,
        description="Storyboard role locking strength override",
    )
    shot_strategy: Optional[ShotOverridePolicy] = Field(None, description="Storyboard shot strategy override")
    frame_overrides: Optional[List[StoryboardFrameOverride]] = Field(
        None,
        description="Per-frame storyboard overrides collected from preview",
    )
    text_rendering: Optional[TextRenderingRequest] = Field(
        None,
        description="Unified text rendering and generated-image text policy",
    )

    @model_validator(mode="after")
    def validate_storyboard_contract(self) -> "ImagePromptGenerateRequest":
        if self.frame_overrides and self.storyboard_generation is None:
            raise ValueError("storyboard_generation is required when frame_overrides are provided")
        if self.storyboard_generation is not None:
            original_source_texts = self.storyboard_generation.source_texts()
            effective_source_texts = self._compute_effective_source_texts()
            if self.narrations != effective_source_texts:
                raise ValueError(
                    "narrations must match storyboard_generation frame source_text order "
                    "(after applying source_text overrides if any)"
                )
        return self

    def _compute_effective_source_texts(self) -> list[str]:
        """Compute effective source texts after applying source_text overrides."""
        if self.storyboard_generation is None:
            return list(self.narrations)

        original_texts = self.storyboard_generation.source_texts()
        if not self.frame_overrides:
            return original_texts

        # Build override lookup by frame_id
        overrides_by_frame_id: dict[str, str] = {}
        for override in self.frame_overrides:
            if override.source_text is not None and "source_text" in override.locked_fields:
                overrides_by_frame_id[override.frame_id] = override.source_text

        # Apply overrides to compute effective texts
        effective_texts: list[str] = []
        for i, frame in enumerate(self.storyboard_generation.frames):
            frame_id = frame.get("frame_id", "")
            if frame_id in overrides_by_frame_id:
                effective_texts.append(overrides_by_frame_id[frame_id])
            else:
                effective_texts.append(original_texts[i])

        return effective_texts


class ImagePromptGenerateResponse(BaseModel):
    """Image prompt generation response"""
    success: bool = True
    message: str = "Success"
    image_prompts: List[str] = Field(..., description="Generated image prompts")


# ============================================================================
# Title Generation
# ============================================================================

class TitleGenerateRequest(BaseModel):
    """Title generation request"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "Atomic Habits is about making small changes that lead to remarkable results.",
                "style": "engaging",
            }
        }
    )

    text: str = Field(..., description="Source text")
    style: Optional[str] = Field(None, description="Title style (e.g., 'engaging', 'formal')")


class TitleGenerateResponse(BaseModel):
    """Title generation response"""
    success: bool = True
    message: str = "Success"
    title: str = Field(..., description="Generated title")
