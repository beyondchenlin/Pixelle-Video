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
        )


@dataclass
class AudioBlock:
    id: str
    text: str
    audio_path: str
    start: float
    end: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AudioBlock":
        return cls(
            id=data["id"],
            text=data["text"],
            audio_path=data["audio_path"],
            start=data["start"],
            end=data["end"],
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


@dataclass
class RenderManifest:
    task_id: str
    title: str
    width: int
    height: int
    fps: int
    template_id: str
    master_audio_path: Optional[str] = None
    audio_blocks: List[AudioBlock] = field(default_factory=list)
    sentence_units: List[SentenceUnit] = field(default_factory=list)
    visual_clips: List[VisualClip] = field(default_factory=list)
    caption_cues: List[CaptionCue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "template_id": self.template_id,
            "master_audio_path": self.master_audio_path,
            "audio_blocks": [block.to_dict() for block in self.audio_blocks],
            "sentence_units": [unit.to_dict() for unit in self.sentence_units],
            "visual_clips": [clip.to_dict() for clip in self.visual_clips],
            "caption_cues": [cue.to_dict() for cue in self.caption_cues],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RenderManifest":
        return cls(
            task_id=data["task_id"],
            title=data["title"],
            width=data["width"],
            height=data["height"],
            fps=data["fps"],
            template_id=data["template_id"],
            master_audio_path=data.get("master_audio_path"),
            audio_blocks=[AudioBlock.from_dict(item) for item in data.get("audio_blocks", [])],
            sentence_units=[SentenceUnit.from_dict(item) for item in data.get("sentence_units", [])],
            visual_clips=[VisualClip.from_dict(item) for item in data.get("visual_clips", [])],
            caption_cues=[CaptionCue.from_dict(item) for item in data.get("caption_cues", [])],
        )
