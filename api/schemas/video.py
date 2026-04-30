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

from typing import Any, Dict, List, Literal, Optional, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from api.schemas.storyboard_contract import (
    StoryboardFrameOverride,
    StoryboardPromptLanguage,
)
from api.schemas.text_rendering import TextRenderingRequest
from pixelle_video.models.media_placement import MediaPlacement
from pixelle_video.models.script_generation_limits import SCRIPT_TARGET_WORDS_MAX
from pixelle_video.models.size_contract import (
    STANDARD_VIDEO_SIZE_PRESETS,
    GenerationSizeContract,
    has_canvas_size_intent,
    orientation_from_dimensions,
)
from pixelle_video.models.storyboard_limits import (
    DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MAX,
    DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MIN,
    current_storyboard_generation_limits,
)
from pixelle_video.models.storyboard_planning import (
    ConsistencyStrength,
    ContentMode,
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
from pixelle_video.utils.template_util import (
    get_template_orientation,
    resolve_template_path,
    validate_template_canvas_orientation,
)

StandardTtsAudioStrategy = Literal["auto", "master_track"]
VideoOrientation = Literal["landscape", "portrait", "square"]
VideoResolutionPreset = Literal[
    "landscape_hd",
    "landscape_full_hd",
    "landscape_4k",
    "portrait_hd",
    "portrait_full_hd",
    "portrait_4k",
    "square_standard",
    "1k",
    "2k",
    "4k",
]
MediaResolutionPreset = Literal["768", "1k", "2k", "4k"]


def validate_public_resource_id(field_name: str, value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if value != value.strip():
        raise ValueError(f"{field_name} must be a resource ID, not raw provider or path syntax")
    if not value:
        raise ValueError(f"{field_name} must be a resource ID, not raw provider or path syntax")
    if not value[0].isalnum() or any(
        char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
        for char in value
    ):
        raise ValueError(f"{field_name} must be a resource ID, not raw provider or path syntax")
    return value


class MediaPlacementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basis: Literal["canvas"] = Field(
        "canvas",
        description="Placement basis. First version supports final canvas only.",
    )
    fit: Literal["contain"] = Field(
        "contain",
        description="Preserve aspect ratio and do not crop.",
    )
    scale_percent: StrictInt = Field(
        100,
        ge=10,
        le=100,
        description="Display size as percent of final video canvas contain-fit size.",
    )
    anchor: Literal[
        "top_left",
        "top",
        "top_right",
        "left",
        "center",
        "right",
        "bottom_left",
        "bottom",
        "bottom_right",
    ] = Field("center", description="9-grid anchor for the displayed media.")

    def to_model(self) -> MediaPlacement:
        return MediaPlacement.from_dict(self.model_dump())

    def to_dict(self) -> dict[str, Any]:
        return self.to_model().to_dict()


def _infer_video_orientation_from_standard_preset(
    preset: VideoResolutionPreset | None,
) -> VideoOrientation | None:
    if preset is None:
        return None
    for orientation, presets in STANDARD_VIDEO_SIZE_PRESETS.items():
        if preset in presets:
            return cast(VideoOrientation, orientation)
    return None


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
                "template_id": "portrait_default",
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
        description=(
            "Processing mode: 'generate' creates a complete source_text script; "
            "'fixed' uses text as the complete source_text."
        ),
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
    storyboard_max_scene_count: Optional[int] = Field(
        None,
        ge=DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MIN,
        le=DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MAX,
        description=(
            "Maximum storyboard frame count for punctuation or sentence storyboard modes."
        ),
    )
    script_length_mode: Literal["auto", "short", "medium", "long", "custom"] = Field(
        "auto",
        description="Complete script length mode for generate mode",
    )
    script_target_words: Optional[int] = Field(
        None,
        ge=1,
        le=SCRIPT_TARGET_WORDS_MAX,
        description="Custom target word count. Only valid with generate + custom script length mode.",
    )
    
    # === TTS Parameters ===
    voice_id: Optional[str] = Field(
        None,
        description="Public voice resource ID resolved server-side",
    )
    style_id: Optional[str] = Field(
        None,
        description="Public visual style resource ID resolved server-side",
    )
    template_id: Optional[str] = Field(
        None,
        description="Public frame template resource ID resolved server-side",
    )
    bgm_id: Optional[str] = Field(
        None,
        description="Public background music resource ID resolved server-side",
    )
    workflow_preset_id: Optional[str] = Field(
        None,
        description="Public media workflow preset resource ID resolved server-side",
    )
    tts_audio_strategy: Optional[StandardTtsAudioStrategy] = Field(
        None,
        description="Standard video TTS audio strategy. Per-frame audio is not supported.",
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
        description=(
            "Ask complete script generation to preserve natural punctuation "
            "for downstream speech and captions"
        ),
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
    
    # === Size Parameters ===
    canvas_width: Optional[int] = Field(
        None,
        ge=1,
        description="Final video canvas width. Defaults to the selected video preset.",
    )
    canvas_height: Optional[int] = Field(
        None,
        ge=1,
        description="Final video canvas height. Defaults to the selected video preset.",
    )
    media_width: Optional[int] = Field(
        None,
        ge=1,
        description="Generated image/media width. Defaults to the selected media preset.",
    )
    media_height: Optional[int] = Field(
        None,
        ge=1,
        description="Generated image/media height. Defaults to the selected media preset.",
    )
    video_orientation: Optional[VideoOrientation] = Field(
        None,
        description="Final video orientation preset group.",
    )
    video_resolution_preset: Optional[VideoResolutionPreset] = Field(
        None,
        description="Final video resolution preset.",
    )
    media_orientation: Optional[VideoOrientation] = Field(
        None,
        description="Generated image/media orientation preset group.",
    )
    media_resolution_preset: Optional[MediaResolutionPreset] = Field(
        None,
        description="Generated image/media resolution preset.",
    )
    sync_media_size_to_canvas: bool = Field(
        False,
        description="When true, generated image/media dimensions follow the final video canvas.",
    )
    media_placement: MediaPlacementRequest = Field(
        default_factory=MediaPlacementRequest,
        description="Generated image/video display size and position inside the final video canvas.",
    )

    # === Video Parameters ===
    video_fps: int = Field(30, ge=15, le=60, description="Video FPS")
    
    # === Frame Template ===
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
    
    # === Storyboard Planning ===
    world_preset_id: Optional[str] = Field(None, description="Storyboard world preset id")
    shot_preset_id: Optional[str] = Field(None, description="Storyboard shot preset id")
    storyboard_prompt_language: StoryboardPromptLanguage = Field(
        "zh_CN",
        description="Language used for storyboard planning fields and generated image prompts",
    )
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
    bgm_volume: float = Field(0.3, ge=0.0, le=1.0, description="BGM volume (0.0-1.0)")

    @field_validator(
        "voice_id",
        "style_id",
        "template_id",
        "bgm_id",
        "workflow_preset_id",
    )
    @classmethod
    def validate_public_resource_ids(cls, value: str | None, info) -> str | None:
        return validate_public_resource_id(info.field_name, value)

    @model_validator(mode="after")
    def validate_storyboard_generation_contract(self) -> "VideoGenerateRequest":
        if self.video_orientation is None:
            self.video_orientation = _infer_video_orientation_from_standard_preset(
                self.video_resolution_preset
            )

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
            if self.storyboard_max_scene_count is not None:
                raise ValueError(
                    "storyboard_max_scene_count is only valid for deterministic storyboard modes"
                )
        else:
            if self.storyboard_count_mode != "auto":
                raise ValueError("deterministic storyboard modes require auto count mode")
            if self.storyboard_scene_count is not None:
                raise ValueError("storyboard_scene_count is not valid for deterministic storyboard modes")
            limits = current_storyboard_generation_limits()
            if self.storyboard_max_scene_count is None:
                self.storyboard_max_scene_count = (
                    limits.default_deterministic_max_scene_count
                )
            elif self.storyboard_max_scene_count > limits.deterministic_max_scene_count_limit:
                raise ValueError(
                    "storyboard_max_scene_count must be between "
                    f"{DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MIN} and "
                    f"{limits.deterministic_max_scene_count_limit}"
                )

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

        size_params = {
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "media_width": self.media_width,
            "media_height": self.media_height,
            "video_orientation": self.video_orientation,
            "video_resolution_preset": self.video_resolution_preset,
            "media_orientation": self.media_orientation,
            "media_resolution_preset": self.media_resolution_preset,
            "sync_media_size_to_canvas": self.sync_media_size_to_canvas,
        }
        GenerationSizeContract.from_params(size_params)

        return self


def validate_raw_frame_template_orientation(
    *,
    frame_template: str | None,
    video_orientation: VideoOrientation | None,
    size_params: dict[str, Any],
) -> VideoOrientation | None:
    if (
        frame_template
        and video_orientation is None
        and not has_canvas_size_intent(size_params)
    ):
        video_orientation = get_template_orientation(resolve_template_path(frame_template))
        size_params["video_orientation"] = video_orientation

    size_contract = GenerationSizeContract.from_params(size_params)
    if frame_template:
        canvas_orientation = orientation_from_dimensions(
            size_contract.canvas_width,
            size_contract.canvas_height,
        )
        validate_template_canvas_orientation(
            resolve_template_path(frame_template),
            canvas_orientation,
        )
    return video_orientation


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
