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
Video generation API schemas
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.schemas.text_rendering import TextRenderingRequest
from pixelle_video.models.storyboard_limits import current_storyboard_generation_limits
from pixelle_video.models.storyboard_planning import (
    ConsistencyStrength,
    ContentMode,
    FrameOverrideSource,
    RoleStrategy,
    ShotOverridePolicy,
)
from pixelle_video.render_backend import RenderBackend
from pixelle_video.tts_split_strategy import TtsSplitMode
from pixelle_video.utils.prompt_generation_performance import (
    PROMPT_BATCH_CONCURRENT_LIMIT_MAX,
    PROMPT_BATCH_CONCURRENT_LIMIT_MIN,
    PROMPT_BATCH_SIZE_MAX,
    PROMPT_BATCH_SIZE_MIN,
)

StoryboardOverrideField = Literal[
    "source_text",
    "visual_goal",
    "prompt_intent",
    "shot_type",
    "shot_purpose",
    "primary_subject",
    "secondary_subjects",
    "world_elements",
    "continuity_anchors",
    "focus_detail",
]


class StoryboardFrameOverride(BaseModel):
    """Structured per-frame storyboard override payload bound to StoryboardPlan identity."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(..., min_length=1, description="Storyboard plan id")
    plan_revision: int = Field(..., ge=1, description="Storyboard plan revision")
    frame_id: str = Field(..., min_length=1, description="Storyboard plan frame id")
    source_digest: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
        description="SHA-256 digest of the plan source text",
    )
    locked_fields: List[StoryboardOverrideField] = Field(
        ...,
        min_length=1,
        description="Editable frame fields that should stay locked on replay",
    )
    override_source: Optional[FrameOverrideSource] = Field(
        None,
        description="Origin of the override payload",
    )
    source_text: Optional[str] = Field(None, description="Locked source text override")
    visual_goal: Optional[str] = Field(None, description="Locked visual goal override")
    prompt_intent: Optional[str] = Field(None, description="Locked prompt intent override")
    shot_type: Optional[str] = Field(None, description="Locked shot type override")
    shot_purpose: Optional[str] = Field(None, description="Locked shot purpose override")
    primary_subject: Optional[str] = Field(None, description="Locked primary subject override")
    secondary_subjects: Optional[List[str]] = Field(None, description="Locked secondary subject overrides")
    world_elements: Optional[List[str]] = Field(None, description="Locked world element overrides")
    continuity_anchors: Optional[List[str]] = Field(None, description="Locked continuity anchor overrides")
    focus_detail: Optional[str] = Field(None, description="Locked focus detail override")

    @model_validator(mode="after")
    def validate_locked_field_values(self) -> "StoryboardFrameOverride":
        provided_fields = [
            field_name
            for field_name in StoryboardOverrideField.__args__
            if getattr(self, field_name) is not None
        ]
        for field_name in provided_fields:
            if field_name not in self.locked_fields:
                raise ValueError(f"{field_name} must be listed in locked_fields")
        return self


class VideoGenerateRequest(BaseModel):
    """Video generation request"""
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "text": "Atomic Habits teaches us that small changes compound over time to produce remarkable results.",
                "mode": "generate",
                "storyboard_mode": "smart",
                "storyboard_count_mode": "auto",
                "script_length_mode": "auto",
                "frame_template": "1080x1920/image_default.html",
                "render_backend": "legacy",
                "template_params": {
                    "accent_color": "#3498db",
                    "background": "https://example.com/custom-bg.jpg",
                },
                "title": "The Power of Atomic Habits",
            }
        }
    )
    
    # === Input ===
    text: str = Field(..., description="Source text for video generation")
    
    # === Processing Mode ===
    mode: Literal["generate", "fixed"] = Field(
        "generate",
        description="Processing mode: 'generate' (AI generates narrations) or 'fixed' (use text as-is)"
    )
    
    # === Optional Title ===
    title: Optional[str] = Field(None, description="Video title (auto-generated if not provided)")
    
    # === Storyboard Generation ===
    storyboard_mode: Literal["smart", "punctuation", "sentence"] = Field(
        "smart",
        description="Storyboard generation mode",
    )
    storyboard_count_mode: Literal["auto", "manual"] = Field(
        "auto",
        description="Storyboard count mode. Manual is only valid with smart storyboard mode.",
    )
    storyboard_scene_count: Optional[int] = Field(
        None,
        ge=1,
        description="Manual storyboard scene count. Only valid with smart + manual.",
    )
    script_length_mode: Literal["auto", "short", "medium", "long", "custom"] = Field(
        "auto",
        description="Complete script length mode for generate mode",
    )
    script_target_words: Optional[int] = Field(
        None,
        ge=1,
        description="Custom target word count. Only valid with generate + custom script length mode.",
    )
    
    # === TTS Parameters ===
    tts_workflow: Optional[str] = Field(
        None, 
        description="TTS workflow key (e.g., 'runninghub/tts_edge.json'). If not specified, uses default workflow from config."
    )
    ref_audio: Optional[str] = Field(
        None, 
        description="Reference audio path for voice cloning (optional)"
    )
    voice_id: Optional[str] = Field(
        None, 
        description="(Deprecated) TTS voice ID for legacy compatibility"
    )
    tts_split_mode: Optional[TtsSplitMode] = Field(
        None,
        description="IndexTTS2 text split mode: internal_only or external_only",
    )
    max_chars_per_tts_segment: Optional[int] = Field(
        None,
        ge=1,
        description="Maximum characters per external TTS segment",
    )
    tts_split_overflow_policy: Optional[str] = Field(
        None,
        description="External TTS split overflow policy",
    )
    tts_boundary_search_radius: Optional[int] = Field(
        None,
        ge=0,
        description="Search radius for external TTS punctuation boundaries",
    )
    tts_soft_overflow_chars: Optional[int] = Field(
        None,
        ge=0,
        description="Allowed soft overflow characters for external TTS splitting",
    )
    tts_audio_boundary_fade_ms: Optional[int] = Field(
        None,
        ge=0,
        description="Fade duration in milliseconds when joining external TTS audio segments",
    )
    tts_sentence_joiner_mode: Optional[Literal["direct", "space"]] = Field(
        None,
        description="How normalized TTS sentence units are joined inside an audio block",
    )
    caption_punctuation_mode: Optional[Literal["strip_all", "strip_terminal", "preserve"]] = Field(
        None,
        description="How punctuation is formatted for displayed captions",
    )
    preserve_natural_punctuation: Optional[bool] = Field(
        None,
        description="Ask LLM narration generation to preserve natural punctuation",
    )
    
    # === LLM Parameters ===
    min_image_prompt_words: int = Field(30, ge=10, le=100, description="Min image prompt words")
    max_image_prompt_words: int = Field(60, ge=10, le=200, description="Max image prompt words")
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
    
    # === Media Parameters ===
    # Note: media_width and media_height are auto-determined from template meta tags
    media_workflow: Optional[str] = Field(None, description="Custom media workflow (image or video)")
    
    # === Video Parameters ===
    video_fps: int = Field(30, ge=15, le=60, description="Video FPS")
    
    # === Frame Template (determines video size) ===
    frame_template: Optional[str] = Field(
        None, 
        description="HTML template path with size (e.g., '1080x1920/default.html'). Video size is auto-determined from template."
    )
    
    # === Template Custom Parameters ===
    template_params: Optional[Dict[str, Any]] = Field(
        None,
        description="Custom template parameters (e.g., {'accent_color': '#ff0000', 'background': 'url'}). "
                    "Available parameters depend on the template. Use GET /api/templates/{template_path}/params to discover them."
    )

    # === Render Backend ===
    render_backend: Optional[RenderBackend] = Field(
        None,
        description="Render backend: 'legacy' or 'hyperframes_compiled'",
    )
    
    # === Image Style ===
    prompt_prefix: Optional[str] = Field(None, description="Image style prefix")

    # === Storyboard Planning ===
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
    
    # === BGM ===
    bgm_path: Optional[str] = Field(None, description="Background music path")
    bgm_volume: float = Field(0.3, ge=0.0, le=1.0, description="BGM volume (0.0-1.0)")

    @model_validator(mode="after")
    def validate_storyboard_generation_contract(self) -> "VideoGenerateRequest":
        if self.storyboard_mode == "smart":
            if self.storyboard_count_mode == "manual":
                if self.storyboard_scene_count is None:
                    raise ValueError("storyboard_scene_count is required with smart manual mode")
                limits = current_storyboard_generation_limits()
                if not limits.min_scene_count <= self.storyboard_scene_count <= limits.max_scene_count:
                    raise ValueError(
                        "storyboard_scene_count must be between "
                        f"{limits.min_scene_count} and {limits.max_scene_count}"
                    )
            elif self.storyboard_scene_count is not None:
                raise ValueError("storyboard_scene_count is valid only with smart manual mode")
        else:
            if self.storyboard_count_mode != "auto":
                raise ValueError("deterministic storyboard modes require auto count mode")
            if self.storyboard_scene_count is not None:
                raise ValueError("storyboard_scene_count is not valid for deterministic storyboard modes")

        if self.mode == "fixed":
            if self.script_length_mode != "auto":
                raise ValueError("script_length_mode is only configurable in generate mode")
            if self.script_target_words is not None:
                raise ValueError("script_target_words is only valid in generate mode")
        elif self.script_length_mode == "custom":
            if self.script_target_words is None:
                raise ValueError("script_target_words is required with custom script length mode")
        elif self.script_target_words is not None:
            raise ValueError("script_target_words is only valid with custom script length mode")

        return self


class VideoGenerateResponse(BaseModel):
    """Video generation response (synchronous)"""
    success: bool = True
    message: str = "Success"
    video_url: str = Field(..., description="URL to access generated video")
    duration: float = Field(..., description="Video duration in seconds")
    file_size: int = Field(..., description="File size in bytes")


class VideoGenerateAsyncResponse(BaseModel):
    """Video generation async response"""
    success: bool = True
    message: str = "Task created successfully"
    task_id: str = Field(..., description="Task ID for tracking progress")
