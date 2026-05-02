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
Progress event models for video generation

Provides structured progress events for UI layer to consume and translate.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, Union

from loguru import logger


class ProgressEventType(StrEnum):
    GENERATING_SOURCE_TEXT = "generating_source_text"
    PREPARING_SOURCE_TEXT = "preparing_source_text"
    GENERATING_STORYBOARD_PLAN = "generating_storyboard_plan"
    GENERATING_TITLE = "generating_title"
    GENERATING_NARRATIONS = "generating_narrations"
    SPLITTING_SCRIPT = "splitting_script"
    GENERATING_IMAGE_PROMPTS = "generating_image_prompts"
    GENERATING_VIDEO_PROMPTS = "generating_video_prompts"
    PREPARING_FRAMES = "preparing_frames"
    FRAME_STEP = "frame_step"
    PROCESSING_FRAME = "processing_frame"
    CONCATENATING = "concatenating"
    SYNTHESIZING_AUDIO = "synthesizing_audio"
    PREPARING_RENDER_MANIFEST = "preparing_render_manifest"
    RENDERING_FFMPEG_MANIFEST = "rendering_ffmpeg_manifest"
    RENDERING_HYPERFRAMES = "rendering_hyperframes"
    GENERATION = "generation"
    FINALIZING = "finalizing"
    COMPLETED = "completed"


class ProgressFrameAction(StrEnum):
    AUDIO = "audio"
    IMAGE = "image"
    MEDIA = "media"
    COMPOSE = "compose"
    VIDEO = "video"


PROGRESS_EVENT_I18N_KEYS: Mapping[str, str] = MappingProxyType(
    {
        ProgressEventType.GENERATING_SOURCE_TEXT.value: "progress.generating_source_text",
        ProgressEventType.PREPARING_SOURCE_TEXT.value: "progress.preparing_source_text",
        ProgressEventType.GENERATING_STORYBOARD_PLAN.value: "progress.generating_storyboard_plan",
        ProgressEventType.GENERATING_TITLE.value: "progress.generating_title",
        ProgressEventType.GENERATING_NARRATIONS.value: "progress.generating_narrations",
        ProgressEventType.SPLITTING_SCRIPT.value: "progress.splitting_script",
        ProgressEventType.GENERATING_IMAGE_PROMPTS.value: "progress.generating_image_prompts",
        ProgressEventType.GENERATING_VIDEO_PROMPTS.value: "progress.generating_video_prompts",
        ProgressEventType.PREPARING_FRAMES.value: "progress.preparing_frames",
        ProgressEventType.FRAME_STEP.value: "progress.frame_step",
        ProgressEventType.PROCESSING_FRAME.value: "progress.frame",
        ProgressEventType.CONCATENATING.value: "progress.concatenating",
        ProgressEventType.SYNTHESIZING_AUDIO.value: "progress.synthesizing_audio",
        ProgressEventType.PREPARING_RENDER_MANIFEST.value: "progress.preparing_render_manifest",
        ProgressEventType.RENDERING_FFMPEG_MANIFEST.value: "progress.rendering_ffmpeg_manifest",
        ProgressEventType.RENDERING_HYPERFRAMES.value: "progress.rendering_hyperframes",
        ProgressEventType.GENERATION.value: "progress.generation",
        ProgressEventType.FINALIZING.value: "progress.finalizing",
        ProgressEventType.COMPLETED.value: "progress.completed",
    }
)

PROGRESS_FRAME_ACTION_I18N_KEYS: Mapping[str, str] = MappingProxyType(
    {
        ProgressFrameAction.AUDIO.value: "progress.step_audio",
        ProgressFrameAction.IMAGE.value: "progress.step_image",
        ProgressFrameAction.MEDIA.value: "progress.step_media",
        ProgressFrameAction.COMPOSE.value: "progress.step_compose",
        ProgressFrameAction.VIDEO.value: "progress.step_video",
    }
)


def normalize_progress_event_type(event_type: str | ProgressEventType) -> str:
    return event_type.value if isinstance(event_type, ProgressEventType) else str(event_type)


def normalize_progress_frame_action(action: str | ProgressFrameAction) -> str:
    return action.value if isinstance(action, ProgressFrameAction) else str(action)


def progress_event_i18n_key(event_type: str | ProgressEventType) -> Optional[str]:
    return PROGRESS_EVENT_I18N_KEYS.get(normalize_progress_event_type(event_type))


def progress_frame_action_i18n_key(action: str | ProgressFrameAction | None) -> Optional[str]:
    if action is None:
        return None
    return PROGRESS_FRAME_ACTION_I18N_KEYS.get(normalize_progress_frame_action(action))


@dataclass(frozen=True)
class ProgressI18nMessage:
    """Localized message token carried by progress callbacks.

    Attributes:
        key: i18n translation key to resolve in the UI layer.
        params: Named interpolation values for that key.
        fallback: Optional fallback plain text when key is not available.
    """

    key: str
    params: Mapping[str, Any] = field(default_factory=dict)
    fallback: Optional[str] = None


ProgressExtraInfo = Union[str, ProgressI18nMessage]


@dataclass
class ProgressEvent:
    """
    Structured progress event for video generation
    
    Attributes:
        event_type: Type of event (e.g., "generating_narrations", "frame_step", "concatenating")
        progress: Progress value from 0.0 to 1.0
        frame_current: Current frame number (1-based, optional)
        frame_total: Total number of frames (optional)
        step: Current step within frame (1-4, optional)
        action: Action being performed (e.g., "audio", "image", "compose", "video", optional)
    
    Examples:
        # Simple progress event
        ProgressEvent(event_type="generating_narrations", progress=0.05)
        
        # Frame step event
        ProgressEvent(
            event_type="frame_step",
            progress=0.23,
            frame_current=1,
            frame_total=5,
            step=1,
            action="audio"
        )
    """
    event_type: str | ProgressEventType
    progress: float
    
    # Optional frame-related fields
    frame_current: Optional[int] = None
    frame_total: Optional[int] = None
    step: Optional[int] = None  # 1-4 for frame processing steps
    action: Optional[str | ProgressFrameAction] = None  # "audio", "image", "compose", "video"
    extra_info: Optional[ProgressExtraInfo] = None
    
    def __post_init__(self):
        """Validate progress value"""
        self.event_type = normalize_progress_event_type(self.event_type)
        if self.action is not None:
            self.action = normalize_progress_frame_action(self.action)
        if not 0.0 <= self.progress <= 1.0:
            raise ValueError(f"Progress must be between 0.0 and 1.0, got {self.progress}")


class ProgressSink(Protocol):
    """Receives structured progress events."""

    def emit(self, event: ProgressEvent) -> None:
        ...


class CallbackProgressSink:
    """Adapts the legacy progress callback shape to the sink contract."""

    def __init__(self, callback: Callable[[ProgressEvent], None]) -> None:
        self._callback = callback

    def emit(self, event: ProgressEvent) -> None:
        self._callback(event)


class ProgressDispatcher:
    """Fan out one progress event to every registered sink."""

    def __init__(self, sinks: Sequence[ProgressSink] | None = None) -> None:
        self._sinks = list(sinks or [])

    def emit(self, event: ProgressEvent) -> None:
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception as exc:
                logger.warning(f"Progress sink failed: {exc}")

    @property
    def sinks(self) -> tuple[ProgressSink, ...]:
        return tuple(self._sinks)
