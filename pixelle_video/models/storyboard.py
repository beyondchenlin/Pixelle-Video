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
Storyboard data models for video generation
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from pixelle_video.config.tts_defaults import DEFAULT_TTS_INFERENCE_MODE
from pixelle_video.models.layered_template import LayeredTemplateSpec
from pixelle_video.models.media_placement import MediaPlacement, resolve_media_placement
from pixelle_video.models.size_contract import (
    DEFAULT_MEDIA_ORIENTATION,
    DEFAULT_MEDIA_RESOLUTION_PRESET,
    DEFAULT_VIDEO_ORIENTATION,
    DEFAULT_VIDEO_RESOLUTION_PRESET,
)
from pixelle_video.models.storyboard_workbench import StoryboardFrameWorkbenchState
from pixelle_video.models.video_generation_contract import StoryboardControlsContract
from pixelle_video.prompt_language import (
    DEFAULT_PROMPT_LANGUAGE,
    PromptLanguage,
    normalize_prompt_language,
)
from pixelle_video.render_backend import DEFAULT_RENDER_BACKEND, validate_render_backend
from pixelle_video.tts_audio_strategy import (
    DEFAULT_TTS_AUDIO_STRATEGY,
    validate_tts_audio_strategy,
)
from pixelle_video.tts_split_strategy import DEFAULT_TTS_SPLIT_MODE, validate_tts_split_mode
from pixelle_video.utils.template_util import DEFAULT_IMAGE_TEMPLATE
from pixelle_video.utils.text_splitting import (
    DEFAULT_CAPTION_PUNCTUATION_MODE,
    DEFAULT_TTS_SENTENCE_JOINER_MODE,
    validate_caption_punctuation_mode,
    validate_tts_sentence_joiner_mode,
)

VALID_ELEMENT_ANIMATION_BACKENDS = {"hyperframes_canvas", "python_ffmpeg"}
VALID_ELEMENT_ANIMATION_INTENSITIES = {"low", "medium", "high"}
VALID_TEMPLATE_TEXT_POLICIES = {
    "caption_renderer",
    "template_body",
    "none",
    "explicit_both",
}


@dataclass
class StoryboardConfig:
    """Storyboard configuration parameters"""
    
    # Required parameters (must come first in dataclass)
    media_width: int                           # Media width (image or video, required)
    media_height: int                          # Media height (image or video, required)
    canvas_width: Optional[int] = None         # Final video canvas width
    canvas_height: Optional[int] = None        # Final video canvas height
    
    # Task isolation
    task_id: Optional[str] = None              # Task ID for file isolation (auto-generated if None)
    
    n_storyboard: int = 5                      # Number of storyboard frames
    min_narration_words: int = 5               # Min narration word count
    max_narration_words: int = 20              # Max narration word count
    min_image_prompt_words: int = 30           # Min image prompt word count
    max_image_prompt_words: int = 60           # Max image prompt word count
    
    # Video parameters (fps only, size is determined by frame template)
    video_fps: int = 30                        # Frame rate
    video_orientation: str = DEFAULT_VIDEO_ORIENTATION
    video_resolution_preset: str = DEFAULT_VIDEO_RESOLUTION_PRESET
    media_orientation: str = DEFAULT_MEDIA_ORIENTATION
    media_resolution_preset: str = DEFAULT_MEDIA_RESOLUTION_PRESET
    sync_media_size_to_canvas: bool = False
    media_placement: MediaPlacement | dict[str, Any] | None = None
    
    # Audio parameters
    tts_inference_mode: str = DEFAULT_TTS_INFERENCE_MODE  # TTS inference mode: "local" or "comfyui"
    voice_id: Optional[str] = None             # Voice ID (for local: Edge TTS voice ID; for comfyui: workflow-specific)
    tts_workflow: Optional[str] = None         # TTS workflow filename (for ComfyUI mode, None = use default)
    tts_speed: Optional[float] = None          # TTS speed multiplier (0.5-2.0, 1.0 = normal)
    ref_audio: Optional[str] = None            # Reference audio for voice cloning (ComfyUI mode only)
    ref_audio_text: Optional[str] = None       # Transcript for the reference audio (ComfyUI voice cloning)

    # Render contract
    tts_batching_mode: str = "paragraph"       # TTS batching mode
    tts_audio_strategy: str = DEFAULT_TTS_AUDIO_STRATEGY  # TTS audio organization strategy
    tts_split_mode: str = DEFAULT_TTS_SPLIT_MODE  # TTS text segmentation strategy
    tts_sentence_joiner_mode: str = DEFAULT_TTS_SENTENCE_JOINER_MODE  # TTS sentence joiner strategy
    caption_punctuation_mode: str = DEFAULT_CAPTION_PUNCTUATION_MODE  # Caption punctuation display mode
    preserve_natural_punctuation: bool = True     # Ask LLM narration generation to keep natural punctuation
    tts_batch_max_sentences: int = 8           # Maximum sentences per TTS batch
    tts_batch_max_chars: int = 220             # Maximum characters per TTS batch
    max_chars_per_tts_segment: int = 90        # Maximum characters per external TTS segment
    tts_split_overflow_policy: str = "hard_limit"  # TTS split overflow policy
    tts_boundary_search_radius: int = 20       # External TTS splitter search radius
    tts_soft_overflow_chars: int = 0           # External TTS splitter soft overflow
    tts_audio_boundary_fade_ms: int = 8        # Boundary fade for assembled TTS audio
    subtitle_alignment_engine: str = "qwen_forced_aligner"  # Subtitle alignment engine
    silence_trim_tool: Optional[str] = None    # Silence trim tool name
    silence_trim_margin_ms: int = 120          # Silence trim margin in milliseconds
    render_backend: str = DEFAULT_RENDER_BACKEND  # Render backend
    element_animation_enabled: bool = False
    element_animation_backend: str = "hyperframes_canvas"
    element_animation_subject_count: int = 3
    element_animation_candidate_limit: int = 3
    element_animation_prompt: Optional[str] = None
    element_animation_intensity: str = "medium"
    element_animation_workflow: str = "image_sam31_segment.json"
    
    # Media workflow
    media_workflow: Optional[str] = None       # Media workflow filename (image or video, None = use default)
    media_negative_prompt: Optional[str] = None  # Optional negative prompt for media workflows
    
    # Frame template (includes template design-coordinate information in path)
    frame_template: str = DEFAULT_IMAGE_TEMPLATE
    template_params: Optional[Dict[str, Any]] = None  # Custom template parameters (e.g., {"accent_color": "#ff0000"})
    layered_template_spec: Optional[Dict[str, Any]] = None
    selected_template_preset_id: Optional[str] = None
    template_text_policy: str = "caption_renderer"
    world_preset_id: Optional[str] = None
    shot_preset_id: Optional[str] = None
    storyboard_prompt_language: Optional[PromptLanguage] = None
    content_mode: Optional[str] = None
    consistency_strength: Optional[str] = None
    role_strategy: Optional[str] = None
    role_locking_strength: Optional[str] = None
    shot_strategy: Optional[str] = None

    def __post_init__(self):
        self.media_width = int(self.media_width)
        self.media_height = int(self.media_height)
        if self.canvas_width is None:
            self.canvas_width = self.media_width
        if self.canvas_height is None:
            self.canvas_height = self.media_height
        self.canvas_width = int(self.canvas_width)
        self.canvas_height = int(self.canvas_height)
        if self.media_width <= 0 or self.media_height <= 0:
            raise ValueError("media dimensions must be positive")
        if self.canvas_width <= 0 or self.canvas_height <= 0:
            raise ValueError("canvas dimensions must be positive")
        self.sync_media_size_to_canvas = bool(self.sync_media_size_to_canvas)
        self.media_placement = resolve_media_placement(self.media_placement)

        self.render_backend = validate_render_backend(self.render_backend)
        self.tts_audio_strategy = validate_tts_audio_strategy(self.tts_audio_strategy)
        self.tts_split_mode = validate_tts_split_mode(self.tts_split_mode)
        self.tts_sentence_joiner_mode = validate_tts_sentence_joiner_mode(
            self.tts_sentence_joiner_mode
        )
        self.caption_punctuation_mode = validate_caption_punctuation_mode(
            self.caption_punctuation_mode
        )
        self.preserve_natural_punctuation = bool(self.preserve_natural_punctuation)
        self.max_chars_per_tts_segment = max(1, int(self.max_chars_per_tts_segment))
        self.tts_boundary_search_radius = max(0, int(self.tts_boundary_search_radius))
        self.tts_soft_overflow_chars = max(0, int(self.tts_soft_overflow_chars))
        self.tts_audio_boundary_fade_ms = max(0, int(self.tts_audio_boundary_fade_ms))
        self.element_animation_subject_count = int(self.element_animation_subject_count)
        self.element_animation_candidate_limit = int(self.element_animation_candidate_limit)
        if self.element_animation_subject_count < 1:
            raise ValueError("element_animation_subject_count must be >= 1")
        if self.element_animation_candidate_limit < self.element_animation_subject_count:
            raise ValueError("element_animation_candidate_limit must be >= element_animation_subject_count")
        if self.element_animation_backend not in VALID_ELEMENT_ANIMATION_BACKENDS:
            raise ValueError(
                "element_animation_backend must be one of "
                f"{sorted(VALID_ELEMENT_ANIMATION_BACKENDS)}"
            )
        if self.element_animation_intensity not in VALID_ELEMENT_ANIMATION_INTENSITIES:
            raise ValueError(
                "element_animation_intensity must be one of "
                f"{sorted(VALID_ELEMENT_ANIMATION_INTENSITIES)}"
            )
        if self.template_text_policy not in VALID_TEMPLATE_TEXT_POLICIES:
            raise ValueError(
                "template_text_policy must be one of "
                f"{sorted(VALID_TEMPLATE_TEXT_POLICIES)}"
            )
        if self.layered_template_spec is not None:
            self.layered_template_spec = LayeredTemplateSpec.from_dict(
                self.layered_template_spec
            ).to_dict()

    @property
    def media_layout_mode(self) -> str:
        return "canvas" if self.sync_media_size_to_canvas else "template"


@dataclass
class StoryboardFrame:
    """Single storyboard frame"""
    index: int                                 # Frame index (0-based)
    narration: str                             # Narration text
    image_prompt: str                          # Image generation prompt (can be None for text-only or video)
    
    # Generated resource paths
    audio_path: Optional[str] = None           # Audio file path (narration)
    media_type: Optional[str] = None           # Media type: "image" or "video" (None if no media)
    image_path: Optional[str] = None           # Original image path (for image type)
    video_path: Optional[str] = None           # Original video path (for video type, before composition)
    composed_image_path: Optional[str] = None  # Composed image path (with subtitles, for image type)
    template_visual_path: Optional[str] = None
    element_animation_manifest_path: Optional[str] = None
    element_motion_video_path: Optional[str] = None
    video_segment_path: Optional[str] = None   # Final video segment path
    
    # Metadata
    duration: float = 0.0                      # Frame duration (seconds, from audio or video)
    created_at: Optional[datetime] = None
    shot_type: Optional[str] = None
    shot_purpose: Optional[str] = None
    frame_source: Optional[str] = None
    workbench_state: Optional[StoryboardFrameWorkbenchState] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if isinstance(self.workbench_state, Mapping):
            self.workbench_state = StoryboardFrameWorkbenchState.from_dict(self.workbench_state)
        elif self.workbench_state is not None and not isinstance(
            self.workbench_state,
            StoryboardFrameWorkbenchState,
        ):
            raise ValueError("workbench_state must be StoryboardFrameWorkbenchState")


@dataclass
class ContentMetadata:
    """Content metadata for visual display and narration generation"""
    title: str                                 # Content title
    author: Optional[str] = None               # Author/creator
    subtitle: Optional[str] = None             # Subtitle
    genre: Optional[str] = None                # Genre/category
    summary: Optional[str] = None              # Content summary
    publication_year: Optional[str] = None     # Publication year
    cover_url: Optional[str] = None            # Cover/thumbnail image URL


@dataclass
class Storyboard:
    """Complete storyboard"""
    title: str                                 # Video title
    config: StoryboardConfig                   # Configuration
    frames: List[StoryboardFrame] = field(default_factory=list)
    
    # Content metadata (optional)
    content_metadata: Optional[ContentMetadata] = None
    
    # Final output
    final_video_path: Optional[str] = None
    total_duration: float = 0.0
    planning_snapshot: Optional[Dict[str, Any]] = None
    
    # Metadata
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    @property
    def is_completed(self) -> bool:
        """Check if all frames are processed"""
        return all(
            frame.video_segment_path is not None
            for frame in self.frames
        )
    
    @property
    def progress(self) -> float:
        """Return processing progress (0.0-1.0)"""
        if not self.frames:
            return 0.0
        completed = sum(
            1 for frame in self.frames
            if frame.video_segment_path is not None
        )
        return completed / len(self.frames)


@dataclass
class VideoGenerationResult:
    """Video generation result"""
    video_path: str                            # Final video path
    storyboard: Storyboard                     # Complete storyboard
    duration: float                            # Total duration
    file_size: int                             # File size (bytes)
    created_at: datetime = field(default_factory=datetime.now)


def _first_non_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _read_mapping_value(data: Any, key: str) -> Any:
    if isinstance(data, dict):
        return data.get(key)
    return getattr(data, key, None)


def build_storyboard_config_planning_kwargs(
    planning_snapshot: Optional[Dict[str, Any]],
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    snapshot = planning_snapshot or {}
    storyboard_contract = StoryboardControlsContract.from_mapping(
        params or {},
        default_prompt_language=DEFAULT_PROMPT_LANGUAGE,
    )

    return {
        "world_preset_id": _first_non_none(
            snapshot.get("world_preset_id"),
            storyboard_contract.world_preset_id,
        ),
        "shot_preset_id": _first_non_none(
            snapshot.get("shot_preset_id"),
            snapshot.get("effective_final_shot_preset"),
            storyboard_contract.shot_preset_id,
        ),
        "storyboard_prompt_language": normalize_prompt_language(
            _first_non_none(
                snapshot.get("storyboard_prompt_language"),
                storyboard_contract.storyboard_prompt_language,
            ),
            default=DEFAULT_PROMPT_LANGUAGE,
        ),
        "content_mode": _first_non_none(
            snapshot.get("content_mode"),
            snapshot.get("resolved_content_mode"),
            storyboard_contract.content_mode,
        ),
        "consistency_strength": _first_non_none(
            snapshot.get("consistency_strength"),
            snapshot.get("selected_consistency_strength"),
            storyboard_contract.consistency_strength,
        ),
        "role_strategy": _first_non_none(
            snapshot.get("role_strategy"),
            snapshot.get("resolved_role_strategy"),
            storyboard_contract.role_strategy,
        ),
        "role_locking_strength": _first_non_none(
            snapshot.get("role_locking_strength"),
            snapshot.get("selected_role_locking_strength"),
            storyboard_contract.role_locking_strength,
        ),
        "shot_strategy": _first_non_none(
            snapshot.get("shot_strategy"),
            snapshot.get("selected_shot_strategy"),
            storyboard_contract.shot_strategy,
        ),
    }


def build_storyboard_frame_planning_kwargs(
    planning_snapshot: Optional[Dict[str, Any]],
    frame_index: int,
) -> Dict[str, Any]:
    snapshot = planning_snapshot or {}
    frames = snapshot.get("frames")
    if not isinstance(frames, list) or frame_index >= len(frames):
        return {}

    frame_data = frames[frame_index]
    return {
        "shot_type": _read_mapping_value(frame_data, "shot_type"),
        "shot_purpose": _read_mapping_value(frame_data, "shot_purpose"),
        "frame_source": _read_mapping_value(frame_data, "frame_source"),
    }
