from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pixelle_video.models.render_package import CaptionCue, TextCue, TextTrack, VisualClip

# Phase-1 field inventory maps the legacy Pixelle source templates onto the
# normalized shell contract that compiled HyperFrames templates must consume.
PHASE1_TEMPLATE_FIELD_INVENTORY: Dict[str, Dict[str, str]] = {
    "image_default": {
        "title_region": "Centered title block with ornament line accents near the top safe area.",
        "media_slot": "Single centered 900x900 image slot with corner marks and generous side padding.",
        "subtitle_safe_area": "Dedicated lower-third band below the image; rendered by captions composition, not inline shell text.",
        "author_footer_region": "Reserved footer row beneath captions for optional footer text and author attribution.",
        "decorative_background": "Light neutral background with circles, angled lines, and minimal square accents.",
        "style_profile": "image_default",
    },
    "image_life_insights_light": {
        "title_region": "Large centered header with warm textured typography in the upper section.",
        "media_slot": "Centered 600x600 illustration slot in the middle content region.",
        "subtitle_safe_area": "Wide bottom-section subtitle safe area above the author signature.",
        "author_footer_region": "Bottom-right author signature zone with optional footer copy above it.",
        "decorative_background": "Warm paper-like background with dot/grid textures and soft decorative circles.",
        "style_profile": "image_life_insights_light",
    },
}


@dataclass
class TemplateAudioRef:
    path: str
    duration: float


@dataclass
class TemplateRenderContext:
    # This dataclass is the only task-specific shell input contract for
    # compiled HyperFrames templates. Template-specific layout rules must be
    # documented via PHASE1_TEMPLATE_FIELD_INVENTORY before new shell fields
    # are introduced.
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
    text_tracks: List[TextTrack] = field(default_factory=list)
    text_cues: List[TextCue] = field(default_factory=list)
    element_animation_manifest_path: Optional[str] = None
    audio: Optional[TemplateAudioRef] = None
