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

from api.schemas.layered_template_preview import LayeredTemplateSpecRequest
from api.schemas.reference_image import ReferenceImageInputRequest
from api.schemas.storyboard_contract import (
    StoryboardFrameOverride,
    StoryboardPromptLanguage,
)
from api.schemas.text_rendering import TextRenderingRequest
from pixelle_video.models.article_concretization import (
    CognitiveAnchorKind,
    DiagramAspectRatio,
    DiagramRenderStyle,
    ExplanationDiagramGrammar,
    SeriesVisualSignatureRole,
)
from pixelle_video.models.article_understanding import ArticleUnderstandingMode
from pixelle_video.models.media_placement import MediaPlacement
from pixelle_video.models.script_generation_limits import SCRIPT_TARGET_WORDS_MAX
from pixelle_video.models.series_visual_signature_request import (
    SeriesVisualSignatureControlsContract,
)
from pixelle_video.models.series_visual_signature_strategy import SeriesVisualSignatureStrategy
from pixelle_video.models.size_contract import (
    MAX_GENERATION_EDGE_PX,
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
from pixelle_video.models.visual_planning_mode import VisibleTextPolicy, VisualPlanningMode
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
ArticleUnderstandingModeRequest = ArticleUnderstandingMode
VisualPlanningModeRequest = VisualPlanningMode
SeriesVisualSignatureStrategyRequest = SeriesVisualSignatureStrategy
CognitiveAnchorKindRequest = CognitiveAnchorKind
ExplanationDiagramGrammarRequest = ExplanationDiagramGrammar
SeriesVisualSignatureRoleRequest = SeriesVisualSignatureRole
DiagramRenderStyleRequest = DiagramRenderStyle
DiagramAspectRatioRequest = DiagramAspectRatio
VisibleTextPolicyRequest = VisibleTextPolicy
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
    fit: Literal["contain", "cover", "stretch", "original_size"] = Field(
        "contain",
        description=(
            "Media fitting policy: contain preserves the full source, cover fills and crops, "
            "stretch fills without preserving aspect ratio, and original_size uses source pixels."
        ),
    )
    scale_percent: StrictInt = Field(
        100,
        ge=10,
        le=100,
        description="Display size as percent of the selected fitting policy's base rectangle.",
    )
    offset_x: StrictInt = Field(
        0,
        description="Horizontal offset in final-canvas pixels from the centered media box.",
    )
    offset_y: StrictInt = Field(
        0,
        description="Vertical offset in final-canvas pixels from the centered media box.",
    )

    def to_model(self) -> MediaPlacement:
        return MediaPlacement.from_dict(self.model_dump())

    def to_dict(self) -> dict[str, Any]:
        return self.to_model().to_dict()


class TemplateDisplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    show_title: bool = False
    show_signature: bool = False


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

    # === Business Context ===
    workspace_id: Optional[str] = Field(
        None,
        description="Workspace context for generated assets, traces, prompt plans, and IP resources.",
    )
    project_id: Optional[str] = Field(
        None,
        description="Project context for Asset Bible / IP prompt-chain resources.",
    )

    # === Storyboard Generation ===
    storyboard_mode: Literal["information", "smart", "punctuation", "sentence"] = Field(
        "information",
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
    tts_inference_mode: Optional[Literal["local", "comfyui"]] = Field(
        None,
        description=(
            "TTS inference mode override for this request. Use 'local' to avoid "
            "ComfyUI reference-audio requirements."
        ),
    )
    voice_id: Optional[str] = Field(None, description="Public voice resource ID resolved server-side")
    style_id: Optional[str] = Field(None, description="Public visual style resource ID resolved server-side")
    template_id: Optional[str] = Field(None, description="Public frame template resource ID resolved server-side")
    bgm_id: Optional[str] = Field(None, description="Public background music resource ID resolved server-side")
    workflow_preset_id: Optional[str] = Field(None, description="Public media workflow preset resource ID resolved server-side")
    tts_workflow_preset_id: Optional[str] = Field(None, description="Public TTS workflow preset resource ID resolved server-side")
    reference_image: Optional[ReferenceImageInputRequest] = Field(
        None,
        description=(
            "Gray reference-image selector. Only upload_id/artifact_id are accepted; "
            "server paths, URLs, and base64 are forbidden."
        ),
    )
    identity_reference_required: bool = Field(False, description="Require a connected reference image for identity delivery; never fall back to text-only.")
    series_visual_signature_enabled: bool = Field(False, description="Enable IP prompt chain for image prompt generation.")
    series_visual_signature_asset_bible_id: Optional[str] = Field(None, description="Public asset bible resource ID resolved server-side for IP prompt chain.")
    series_visual_signature_profile_id: Optional[str] = Field(None, description="IP profile ID inside the selected asset bible.")
    series_visual_signature_expression_mode: Optional[Literal["auto"]] = Field(
        None,
        description="Enabled two-stage fusion decides the visual expression automatically.",
    )
    series_visual_signature_structure_mode: Optional[Literal["auto"]] = Field(
        None,
        description="Enabled two-stage fusion decides the scene structure automatically.",
    )
    series_visual_signature_participation_mode: Optional[Literal["auto"]] = Field(
        None,
        description="Enabled two-stage fusion decides the scene participation automatically.",
    )
    series_visual_signature_mode: Optional[Literal["auto"]] = Field(
        None,
        description="Enabled two-stage fusion chooses one scene-specific fusion mode.",
    )
    series_visual_signature_consistency_mode: Optional[Literal["off"]] = Field(
        None,
        description="Legacy fixed consistency modes are disabled for two-stage fusion.",
    )
    series_visual_signature_presentation_mode: Optional[Literal["auto"]] = Field(
        None,
        description=(
            "Enabled visual-anchor two-stage fusion accepts only 'auto' so the "
            "fusion model chooses one scene-specific presentation."
        ),
    )
    series_visual_signature_enforcement: Optional[Literal["strict"]] = Field(None, description="Two-stage fusion always fails closed before image generation.")
    series_visual_signature_fallback_enabled: Optional[Literal[False]] = Field(None, description="Two-stage fusion never silently falls back to a legacy prompt path.")
    series_visual_signature_fallback_mode: Optional[Literal["disabled"]] = Field(None, description="Legacy prompt fallback is disabled for two-stage fusion.")
    series_visual_signature_min_visibility: Optional[Literal["clear"]] = Field(None, description="The single identity instance must remain recognizable without a fixed size or position.")
    series_visual_signature_llm_prompt_assembly_enabled: bool = Field(
        False,
        description=(
            "Legacy one-stage prompt assembly must remain disabled when two-stage "
            "visual-anchor fusion is enabled."
        ),
    )
    article_understanding_mode: ArticleUnderstandingModeRequest = Field(ArticleUnderstandingMode.AUTO, description="V4.4 article understanding mode.")
    visual_planning_mode: VisualPlanningModeRequest = Field(VisualPlanningMode.AUTO, description="V4.4 visual planning mode.")
    series_visual_signature_strategy: SeriesVisualSignatureStrategyRequest = Field(SeriesVisualSignatureStrategy.AUTO, description="V4.4 series visual signature strategy.")
    user_intent_hint: Optional[str] = Field(None, description="Optional user intent hint for V4.4 article visual planning.")
    allow_mixed_lenses: bool = Field(True, description="Allow V4.4 article understanding to use mixed lenses across frames.")
    strict_user_mode: bool = Field(False, description="Reject planner fallback when user-selected V4.4 controls conflict.")
    force_v44_planning: bool = Field(False, description="Force V4.4 planning path for eligible generation.")
    article_concretization_enabled: bool = Field(False, description="Enable article concretization request metadata for V4.4 planning.")
    cognitive_anchor_kind: CognitiveAnchorKindRequest = Field(CognitiveAnchorKind.AUTO, description="Requested cognitive anchor kind for article concretization.")
    explanation_diagram_grammar: ExplanationDiagramGrammarRequest = Field(ExplanationDiagramGrammar.AUTO, description="Requested explanation diagram grammar for article concretization.")
    series_visual_signature_role: SeriesVisualSignatureRoleRequest = Field(SeriesVisualSignatureRole.NONE, description="Requested series visual signature role for article concretization.")
    diagram_render_style: DiagramRenderStyleRequest = Field(DiagramRenderStyle.AUTO, description="Requested diagram render style for article concretization.")
    diagram_aspect_ratio: DiagramAspectRatioRequest = Field(DiagramAspectRatio.AUTO, description="Requested diagram aspect ratio for article concretization.")
    diagram_visible_text_policy: VisibleTextPolicyRequest = Field(VisibleTextPolicy.NO_VISIBLE_TEXT, description="Requested visible text policy for article concretization diagrams.")
    diagram_approved_labels: List[str] = Field(default_factory=list, description="Approved visible diagram labels for article concretization.")
    diagram_user_intent_hint: Optional[str] = Field(None, max_length=500, description="Optional user intent hint for article concretization diagrams.")
    tts_audio_strategy: Optional[StandardTtsAudioStrategy] = Field(None, description="Standard video TTS audio strategy. Per-frame audio is not supported.")
    tts_duration: Optional[float] = Field(None, ge=0.5, le=60.0, description="Target duration in seconds for TTS workflows that expose a duration parameter.")
    tts_split_mode: Optional[TtsSplitMode] = Field(None, description="IndexTTS2 text split mode: internal_only or external_only")
    max_chars_per_tts_segment: Optional[int] = Field(None, ge=1, description="Maximum characters per external TTS segment")
    tts_split_overflow_policy: Optional[str] = Field(None, description="External TTS split overflow policy")
    tts_boundary_search_radius: Optional[int] = Field(None, ge=0, description="Search radius for external TTS punctuation boundaries")
    tts_soft_overflow_chars: Optional[int] = Field(None, ge=0, description="Allowed soft overflow characters for external TTS splitting")
    tts_audio_boundary_fade_ms: Optional[int] = Field(None, ge=0, description="Fade duration in milliseconds when joining external TTS audio segments")
    tts_sentence_joiner_mode: Optional[Literal["direct", "space"]] = Field(None, description="How normalized TTS sentence units are joined inside an audio block")
    caption_punctuation_mode: Optional[Literal["strip_all", "strip_terminal", "preserve"]] = Field(None, description="How punctuation is formatted for displayed captions")
    preserve_natural_punctuation: Optional[bool] = Field(None, description="Ask complete script generation to preserve natural punctuation for downstream speech and captions")

    # === LLM Parameters ===
    min_image_prompt_words: int = Field(30, ge=10, le=100, description="Min image prompt words")
    max_image_prompt_words: int = Field(60, ge=10, le=200, description="Max image prompt words")
    llm_prompt_batch_size: Optional[int] = Field(None, ge=PROMPT_BATCH_SIZE_MIN, le=PROMPT_BATCH_SIZE_MAX, description="Request-scoped LLM prompt batch size override")
    llm_prompt_batch_concurrent_limit: Optional[int] = Field(None, ge=PROMPT_BATCH_CONCURRENT_LIMIT_MIN, le=PROMPT_BATCH_CONCURRENT_LIMIT_MAX, description="Request-scoped LLM prompt batch concurrency override")
    media_seed: Optional[int] = Field(
        None,
        ge=1,
        le=2**64 - 1,
        description=(
            "Registered random seed used by every visual-anchor frame in this "
            "request for reproducible generation and acceptance evidence."
        ),
    )

    # === Size Parameters ===
    canvas_width: Optional[int] = Field(None, ge=1, le=MAX_GENERATION_EDGE_PX, multiple_of=2, description="Final video canvas width. Defaults to the selected video preset.")
    canvas_height: Optional[int] = Field(None, ge=1, le=MAX_GENERATION_EDGE_PX, multiple_of=2, description="Final video canvas height. Defaults to the selected video preset.")
    media_width: Optional[int] = Field(None, ge=1, le=MAX_GENERATION_EDGE_PX, description="Generated image/media width. Defaults to the selected media preset.")
    media_height: Optional[int] = Field(None, ge=1, le=MAX_GENERATION_EDGE_PX, description="Generated image/media height. Defaults to the selected media preset.")
    video_orientation: Optional[VideoOrientation] = Field(None, description="Final video orientation preset group.")
    video_resolution_preset: Optional[VideoResolutionPreset] = Field(None, description="Final video resolution preset.")
    media_orientation: Optional[VideoOrientation] = Field(None, description="Generated image/media orientation preset group.")
    media_resolution_preset: Optional[MediaResolutionPreset] = Field(None, description="Generated image/media resolution preset.")
    sync_media_size_to_canvas: bool = Field(False, description="When true, generated image/media dimensions follow the final video canvas.")
    media_placement: MediaPlacementRequest = Field(default_factory=MediaPlacementRequest, description="Generated image/video display size and position inside the final video canvas.")

    # === Video Parameters ===
    video_fps: int = Field(30, ge=15, le=60, description="Video FPS")

    # === Template Custom Parameters ===
    template_params: Optional[Dict[str, Any]] = Field(None, description="Custom template parameters. Available parameters depend on the template.")
    template_display: TemplateDisplayRequest = Field(default_factory=TemplateDisplayRequest, description="Template shell display controls. Title and signature/watermark are hidden by default.")

    # === Render Backend ===
    render_backend: Optional[RenderBackend] = Field(
        None,
        description=(
            "Render backend: 'legacy', 'hyperframes_compiled', or 'ffmpeg_manifest'"
        ),
    )

    # === Storyboard Planning ===
    world_preset_id: Optional[str] = Field(None, description="Storyboard world preset id")
    generation_world_hint: Optional[str] = Field(None, max_length=4000, description="Per-generation world hint for the current source text. Display name remains 世界观提示.")
    shot_preset_id: Optional[str] = Field(None, description="Storyboard shot preset id")
    storyboard_prompt_language: StoryboardPromptLanguage = Field("zh_CN", description="Language used for storyboard planning fields and generated image prompts")
    consistency_strength: Optional[ConsistencyStrength] = Field(None, description="Storyboard consistency strength")
    content_mode: Optional[ContentMode] = Field(None, description="Storyboard content mode override")
    role_strategy: Optional[RoleStrategy] = Field(None, description="Storyboard role strategy override")
    role_locking_strength: Optional[ConsistencyStrength] = Field(None, description="Storyboard role locking strength override")
    shot_strategy: Optional[ShotOverridePolicy] = Field(None, description="Storyboard shot strategy override")
    frame_overrides: Optional[List[StoryboardFrameOverride]] = Field(None, description="Per-frame storyboard overrides collected from preview")
    text_rendering: Optional[TextRenderingRequest] = Field(None, description="Unified text rendering and generated-image text policy")
    layered_template_spec: Optional[LayeredTemplateSpecRequest] = Field(None, description="Normalized layered template snapshot for generation")
    selected_template_preset_id: Optional[str] = Field(None, description="Selected layered template preset id")

    # === BGM ===
    bgm_volume: float = Field(0.3, ge=0.0, le=1.0, description="BGM volume (0.0-1.0)")

    @field_validator(
        "workspace_id",
        "project_id",
        "voice_id",
        "style_id",
        "template_id",
        "bgm_id",
        "workflow_preset_id",
        "tts_workflow_preset_id",
        "series_visual_signature_asset_bible_id",
        "series_visual_signature_profile_id",
    )
    @classmethod
    def validate_public_resource_ids(cls, value: str | None, info) -> str | None:
        return validate_public_resource_id(info.field_name, value)

    @field_validator("generation_world_hint")
    @classmethod
    def normalize_generation_world_hint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_storyboard_generation_contract(self) -> "VideoGenerateRequest":
        if self.video_orientation is None:
            self.video_orientation = _infer_video_orientation_from_standard_preset(
                self.video_resolution_preset
            )

        if self.storyboard_mode in {"smart", "information"}:
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
                raise ValueError("storyboard_max_scene_count is only valid for deterministic storyboard modes")
        else:
            if self.storyboard_count_mode != "auto":
                raise ValueError("deterministic storyboard modes require auto count mode")
            if self.storyboard_scene_count is not None:
                raise ValueError("storyboard_scene_count is not valid for deterministic storyboard modes")
            limits = current_storyboard_generation_limits()
            if self.storyboard_max_scene_count is None:
                self.storyboard_max_scene_count = limits.default_deterministic_max_scene_count
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

        if self.identity_reference_required and not self.series_visual_signature_enabled:
            raise ValueError("必须启用系列身份后才能要求参考图身份约束")
        if self.series_visual_signature_enabled:
            if self.series_visual_signature_asset_bible_id is None:
                raise ValueError("series_visual_signature_asset_bible_id is required when series_visual_signature_enabled=True")
            if self.series_visual_signature_profile_id is None:
                raise ValueError("series_visual_signature_profile_id is required when series_visual_signature_enabled=True")

        SeriesVisualSignatureControlsContract.from_mapping(
            {
                "series_visual_signature_mode": self.series_visual_signature_mode,
                "series_visual_signature_consistency_mode": self.series_visual_signature_consistency_mode,
                "series_visual_signature_presentation_mode": self.series_visual_signature_presentation_mode,
                "series_visual_signature_enforcement": self.series_visual_signature_enforcement,
                "series_visual_signature_fallback_enabled": self.series_visual_signature_fallback_enabled,
                "series_visual_signature_fallback_mode": self.series_visual_signature_fallback_mode,
                "series_visual_signature_min_visibility": self.series_visual_signature_min_visibility,
            }
        )

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
    if frame_template and video_orientation is None and not has_canvas_size_intent(size_params):
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
