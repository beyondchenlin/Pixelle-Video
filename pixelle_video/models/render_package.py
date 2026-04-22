# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Render package models for the render contract.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SentenceUnit:
    id: str
    text: str
    frame_indices: List[int] = field(default_factory=list)
    block_id: Optional[str] = None
    source_start: Optional[float] = None
    source_end: Optional[float] = None
    remapped_start: Optional[float] = None
    remapped_end: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SentenceUnit":
        return cls(
            id=data["id"],
            text=data["text"],
            frame_indices=list(data.get("frame_indices", [])),
            block_id=data.get("block_id"),
            source_start=data.get("source_start"),
            source_end=data.get("source_end"),
            remapped_start=data.get("remapped_start"),
            remapped_end=data.get("remapped_end"),
        )


@dataclass
class AudioBlock:
    id: str
    text: str
    audio_path: Optional[str] = None
    start: float = 0.0
    end: float = 0.0
    source_frame_indices: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AudioBlock":
        return cls(
            id=data["id"],
            text=data["text"],
            audio_path=data.get("audio_path"),
            start=data.get("start", 0.0),
            end=data.get("end", 0.0),
            source_frame_indices=list(data.get("source_frame_indices", [])),
        )


@dataclass
class VisualClip:
    id: str
    frame_index: int
    start: float
    end: float
    media_path: str
    media_type: str
    track_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisualClip":
        return cls(
            id=data["id"],
            frame_index=data["frame_index"],
            start=data["start"],
            end=data["end"],
            media_path=data["media_path"],
            media_type=data["media_type"],
            track_index=data.get("track_index", 0),
        )


@dataclass
class CaptionCue:
    id: str
    text: str
    start: float
    end: float
    frame_indices: List[int] = field(default_factory=list)
    style_profile: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CaptionCue":
        return cls(
            id=data["id"],
            text=data["text"],
            start=data["start"],
            end=data["end"],
            frame_indices=list(data.get("frame_indices", [])),
            style_profile=data.get("style_profile"),
        )


def resolve_render_window(unit: SentenceUnit) -> tuple[float, float]:
    if unit.remapped_start is not None and unit.remapped_end is not None:
        return unit.remapped_start, unit.remapped_end
    if unit.source_start is None or unit.source_end is None:
        raise ValueError(f"SentenceUnit {unit.id} is missing source timing.")
    return unit.source_start, unit.source_end


@dataclass(init=False)
class RenderManifest:
    task_id: str
    title: str
    canvas_width: int
    canvas_height: int
    media_width: Optional[int]
    media_height: Optional[int]
    fps: int
    template_id: str
    master_audio_path: Optional[str] = None
    master_audio_duration: Optional[float] = None
    audio_blocks: List[AudioBlock] = field(default_factory=list)
    sentence_units: List[SentenceUnit] = field(default_factory=list)
    visual_clips: List[VisualClip] = field(default_factory=list)
    caption_cues: List[CaptionCue] = field(default_factory=list)
    canonical_timeline: str = "source"

    def __init__(
        self,
        *,
        task_id: str,
        title: str,
        fps: int,
        template_id: str,
        canvas_width: Optional[int] = None,
        canvas_height: Optional[int] = None,
        media_width: Optional[int] = None,
        media_height: Optional[int] = None,
        master_audio_path: Optional[str] = None,
        master_audio_duration: Optional[float] = None,
        audio_blocks: Optional[List[AudioBlock]] = None,
        sentence_units: Optional[List[SentenceUnit]] = None,
        visual_clips: Optional[List[VisualClip]] = None,
        caption_cues: Optional[List[CaptionCue]] = None,
        canonical_timeline: str = "source",
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> None:
        effective_canvas_width = canvas_width if canvas_width is not None else width
        effective_canvas_height = canvas_height if canvas_height is not None else height
        if effective_canvas_width is None or effective_canvas_height is None:
            raise ValueError("RenderManifest requires canvas_width/canvas_height or width/height.")

        self.task_id = task_id
        self.title = title
        self.canvas_width = int(effective_canvas_width)
        self.canvas_height = int(effective_canvas_height)
        self.media_width = (
            int(media_width) if media_width is not None else self.canvas_width
        )
        self.media_height = (
            int(media_height) if media_height is not None else self.canvas_height
        )
        self.fps = int(fps)
        self.template_id = template_id
        self.master_audio_path = master_audio_path
        self.master_audio_duration = (
            float(master_audio_duration) if master_audio_duration is not None else None
        )
        self.audio_blocks = list(audio_blocks or [])
        self.sentence_units = list(sentence_units or [])
        self.visual_clips = list(visual_clips or [])
        self.caption_cues = list(caption_cues or [])
        self.canonical_timeline = canonical_timeline

    @property
    def width(self) -> int:
        return self.canvas_width

    @property
    def height(self) -> int:
        return self.canvas_height

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "media_width": self.media_width,
            "media_height": self.media_height,
            # Compatibility fields for the current runtime-manifest templates.
            "width": self.canvas_width,
            "height": self.canvas_height,
            "fps": self.fps,
            "template_id": self.template_id,
            "master_audio_path": self.master_audio_path,
            "master_audio_duration": self.master_audio_duration,
            "audio_blocks": [block.to_dict() for block in self.audio_blocks],
            "sentence_units": [unit.to_dict() for unit in self.sentence_units],
            "visual_clips": [clip.to_dict() for clip in self.visual_clips],
            "caption_cues": [cue.to_dict() for cue in self.caption_cues],
            "canonical_timeline": self.canonical_timeline,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RenderManifest":
        return cls(
            task_id=data["task_id"],
            title=data["title"],
            canvas_width=data.get("canvas_width", data.get("width")),
            canvas_height=data.get("canvas_height", data.get("height")),
            media_width=data.get("media_width"),
            media_height=data.get("media_height"),
            fps=data["fps"],
            template_id=data["template_id"],
            master_audio_path=data.get("master_audio_path"),
            master_audio_duration=data.get("master_audio_duration"),
            audio_blocks=[AudioBlock.from_dict(item) for item in data.get("audio_blocks", [])],
            sentence_units=[SentenceUnit.from_dict(item) for item in data.get("sentence_units", [])],
            visual_clips=[VisualClip.from_dict(item) for item in data.get("visual_clips", [])],
            caption_cues=[CaptionCue.from_dict(item) for item in data.get("caption_cues", [])],
            canonical_timeline=data.get("canonical_timeline", "source"),
        )
