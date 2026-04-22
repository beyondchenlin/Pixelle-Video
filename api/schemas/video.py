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

from pydantic import BaseModel, ConfigDict, Field

from pixelle_video.models.storyboard_planning import (
    ConsistencyStrength,
    ContentMode,
    FrameOverrideSource,
    RoleStrategy,
    ShotOverridePolicy,
)
from pixelle_video.render_backend import RenderBackend

StoryboardOverrideField = Literal[
    "narration_fragment",
    "knowledge_goal",
    "shot_type",
    "shot_purpose",
    "primary_subject",
    "secondary_subjects",
    "world_elements",
    "continuity_anchors",
    "focus_detail",
    "prompt_intent",
]


class StoryboardFrameOverride(BaseModel):
    """Structured per-frame storyboard override payload."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(..., min_length=1, description="Storyboard scene id")
    snapshot_identity: str = Field(..., min_length=1, description="Identity of the preview snapshot that produced this override")
    locked_fields: List[StoryboardOverrideField] = Field(
        ...,
        min_length=1,
        description="Editable frame fields that should stay locked on replay",
    )
    override_source: Optional[FrameOverrideSource] = Field(
        None,
        description="Origin of the override payload",
    )
    narration_fragment: Optional[str] = Field(None, description="Locked narration fragment override")
    knowledge_goal: Optional[str] = Field(None, description="Locked knowledge goal override")
    shot_type: Optional[str] = Field(None, description="Locked shot type override")
    shot_purpose: Optional[str] = Field(None, description="Locked shot purpose override")
    primary_subject: Optional[str] = Field(None, description="Locked primary subject override")
    secondary_subjects: Optional[List[str]] = Field(None, description="Locked secondary subject overrides")
    world_elements: Optional[List[str]] = Field(None, description="Locked world element overrides")
    continuity_anchors: Optional[List[str]] = Field(None, description="Locked continuity anchor overrides")
    focus_detail: Optional[str] = Field(None, description="Locked focus detail override")
    prompt_intent: Optional[str] = Field(None, description="Locked prompt intent override")


class VideoGenerateRequest(BaseModel):
    """Video generation request"""
    
    # === Input ===
    text: str = Field(..., description="Source text for video generation")
    
    # === Processing Mode ===
    mode: Literal["generate", "fixed"] = Field(
        "generate",
        description="Processing mode: 'generate' (AI generates narrations) or 'fixed' (use text as-is)"
    )
    
    # === Optional Title ===
    title: Optional[str] = Field(None, description="Video title (auto-generated if not provided)")
    
    # === Basic Config ===
    n_scenes: Optional[int] = Field(5, ge=1, le=20, description="Number of scenes (only used in 'generate' mode, ignored in 'fixed' mode)")
    
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
    
    # === LLM Parameters ===
    min_narration_words: int = Field(5, ge=1, le=100, description="Min narration words")
    max_narration_words: int = Field(20, ge=1, le=200, description="Max narration words")
    min_image_prompt_words: int = Field(30, ge=10, le=100, description="Min image prompt words")
    max_image_prompt_words: int = Field(60, ge=10, le=200, description="Max image prompt words")
    
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
    
    # === BGM ===
    bgm_path: Optional[str] = Field(None, description="Background music path")
    bgm_volume: float = Field(0.3, ge=0.0, le=1.0, description="BGM volume (0.0-1.0)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "text": "Atomic Habits teaches us that small changes compound over time to produce remarkable results.",
                "mode": "generate",
                "n_scenes": 5,
                "frame_template": "1080x1920/image_default.html",
                "render_backend": "legacy",
                "template_params": {
                    "accent_color": "#3498db",
                    "background": "https://example.com/custom-bg.jpg"
                },
                "title": "The Power of Atomic Habits"
            }
        }


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
