from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pixelle_video.models.render_package import CaptionCue, VisualClip


@dataclass
class TemplateAudioRef:
    path: str
    duration: float


@dataclass
class TemplateRenderContext:
    template_id: str
    canvas_width: int
    canvas_height: int
    duration: float
    fps: int
    title: str
    author: Optional[str]
    footer: Optional[str]
    theme: Optional[str]
    style_profile: str
    template_params: Dict[str, Any] = field(default_factory=dict)
    visuals: List[VisualClip] = field(default_factory=list)
    captions: List[CaptionCue] = field(default_factory=list)
    audio: Optional[TemplateAudioRef] = None
