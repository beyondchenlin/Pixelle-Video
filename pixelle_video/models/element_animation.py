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
Element animation manifest models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AnimationIntensity = Literal["low", "medium", "high"]
AnimationPreset = Literal["float", "pulse", "drift", "pop", "parallax"]
BackgroundMode = Literal["inpainted", "source_image_low_motion"]
ElementRenderBackend = Literal["hyperframes_canvas", "python_ffmpeg"]


@dataclass
class ElementMotionBounds:
    translate_px: float = 12.0
    rotate_deg: float = 1.5
    scale_delta: float = 0.03

    def to_dict(self) -> dict[str, float]:
        return {
            "translate_px": self.translate_px,
            "rotate_deg": self.rotate_deg,
            "scale_delta": self.scale_delta,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ElementMotionBounds":
        data = data or {}
        return cls(
            translate_px=float(data.get("translate_px", 12.0)),
            rotate_deg=float(data.get("rotate_deg", 1.5)),
            scale_delta=float(data.get("scale_delta", 0.03)),
        )


@dataclass
class ElementAnimationCanvas:
    width: int
    height: int

    def to_dict(self) -> dict[str, int]:
        return {
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ElementAnimationCanvas":
        return cls(
            width=int(data["width"]),
            height=int(data["height"]),
        )


@dataclass
class ElementAnimationTimeline:
    duration: float
    fps: int

    def to_dict(self) -> dict[str, float | int]:
        return {
            "duration": self.duration,
            "fps": self.fps,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ElementAnimationTimeline":
        return cls(
            duration=float(data["duration"]),
            fps=int(data["fps"]),
        )


@dataclass
class ElementAnimationBackground:
    mode: BackgroundMode
    image_path: str
    motion_bounds: ElementMotionBounds = field(default_factory=ElementMotionBounds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "image_path": self.image_path,
            "motion_bounds": self.motion_bounds.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ElementAnimationBackground":
        return cls(
            mode=data["mode"],
            image_path=str(data["image_path"]),
            motion_bounds=ElementMotionBounds.from_dict(data.get("motion_bounds")),
        )


@dataclass
class ElementAnimationSegmentation:
    provider: str
    workflow: str
    prompt: str | None
    candidate_limit: int
    selected_count: int

    def __post_init__(self) -> None:
        if self.candidate_limit < 1:
            raise ValueError("candidate_limit must be at least 1")
        if self.selected_count < 1:
            raise ValueError("selected_count must be at least 1")
        if self.selected_count > self.candidate_limit:
            raise ValueError("selected_count cannot exceed candidate_limit")

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "workflow": self.workflow,
            "prompt": self.prompt,
            "candidate_limit": self.candidate_limit,
            "selected_count": self.selected_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ElementAnimationSegmentation":
        return cls(
            provider=str(data["provider"]),
            workflow=str(data["workflow"]),
            prompt=data.get("prompt"),
            candidate_limit=int(data["candidate_limit"]),
            selected_count=int(data["selected_count"]),
        )


@dataclass
class ElementAnimation:
    preset: AnimationPreset
    intensity: AnimationIntensity
    seed: int
    motion_bounds: ElementMotionBounds = field(default_factory=ElementMotionBounds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset": self.preset,
            "intensity": self.intensity,
            "seed": self.seed,
            "motion_bounds": self.motion_bounds.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ElementAnimation":
        return cls(
            preset=data["preset"],
            intensity=data["intensity"],
            seed=int(data["seed"]),
            motion_bounds=ElementMotionBounds.from_dict(data.get("motion_bounds")),
        )


@dataclass
class SegmentedElement:
    id: str
    label: str
    image_path: str
    mask_path: str
    bbox: list[int]
    score: float
    selected: bool
    z_index: int
    animation: ElementAnimation

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "image_path": self.image_path,
            "mask_path": self.mask_path,
            "bbox": list(self.bbox),
            "score": self.score,
            "selected": self.selected,
            "z_index": self.z_index,
            "animation": self.animation.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SegmentedElement":
        return cls(
            id=str(data["id"]),
            label=str(data["label"]),
            image_path=str(data["image_path"]),
            mask_path=str(data["mask_path"]),
            bbox=[int(value) for value in data["bbox"]],
            score=float(data["score"]),
            selected=bool(data["selected"]),
            z_index=int(data["z_index"]),
            animation=ElementAnimation.from_dict(data["animation"]),
        )


@dataclass
class ElementAnimationRender:
    backend: ElementRenderBackend

    def to_dict(self) -> dict[str, str]:
        return {
            "backend": self.backend,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ElementAnimationRender":
        return cls(
            backend=data["backend"],
        )


@dataclass
class ElementAnimationManifest:
    source_image_path: str
    canvas: ElementAnimationCanvas
    timeline: ElementAnimationTimeline
    background: ElementAnimationBackground
    segmentation: ElementAnimationSegmentation
    elements: list[SegmentedElement]
    render: ElementAnimationRender
    audio_path: str | None = None

    def selected_elements(self) -> list[SegmentedElement]:
        return sorted(
            [element for element in self.elements if element.selected],
            key=lambda element: element.z_index,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_image_path": self.source_image_path,
            "canvas": self.canvas.to_dict(),
            "timeline": self.timeline.to_dict(),
            "background": self.background.to_dict(),
            "segmentation": self.segmentation.to_dict(),
            "elements": [element.to_dict() for element in self.elements],
            "render": self.render.to_dict(),
            "audio_path": self.audio_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ElementAnimationManifest":
        return cls(
            source_image_path=str(data["source_image_path"]),
            canvas=ElementAnimationCanvas.from_dict(data["canvas"]),
            timeline=ElementAnimationTimeline.from_dict(data["timeline"]),
            background=ElementAnimationBackground.from_dict(data["background"]),
            segmentation=ElementAnimationSegmentation.from_dict(data["segmentation"]),
            elements=[
                SegmentedElement.from_dict(element)
                for element in data.get("elements", [])
            ],
            render=ElementAnimationRender.from_dict(data["render"]),
            audio_path=data.get("audio_path"),
        )
