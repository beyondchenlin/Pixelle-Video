from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pixelle_video.models.layered_template import active_layered_template_spec
from pixelle_video.models.media_placement import MediaPlacement, resolve_media_placement
from pixelle_video.models.render_package import (
    CaptionCue,
    TextCue,
    TextTrack,
    VisualClip,
    resolve_media_layout_mode,
)
from pixelle_video.models.template_text_style_presets import (
    resolve_template_text_style_preset,
)
from pixelle_video.models.text_style import TextStyleProfile

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
    "image_landscape_full": {
        "title_region": "Centered title band across the upper safe area of a 1920x1080 full-bleed image shell.",
        "media_slot": "Single full-bleed landscape visual that occupies the whole frame behind title and subtitle overlays.",
        "subtitle_safe_area": "Raised centered subtitle band above the footer zone with no background panel.",
        "author_footer_region": "Compact lower-left info cluster consuming author, author_desc, and footer away from captions.",
        "decorative_background": "No separate paper shell; readability comes from outline and shadow over the full-bleed visual.",
        "style_profile": "image_landscape_full",
    },
    "image_landscape_minimal": {
        "title_region": "Small left-aligned title block in the upper-left safe area of a 1920x1080 white composition.",
        "media_slot": "Centered framed landscape illustration with generous whitespace around it.",
        "subtitle_safe_area": "Raised centered subtitle line below the media frame with no card or panel background.",
        "author_footer_region": "Lightweight lower-right signature cluster consuming author, author_desc, and footer.",
        "decorative_background": "White paper-like background with restrained line and circle accents.",
        "style_profile": "image_landscape_minimal",
    },
}


@dataclass
class TemplateAudioRef:
    path: str
    duration: float
    id: str = "master-audio"
    start: float = 0.0
    media_start: float = 0.0
    volume: float = 1.0
    track_index: int = 2
    role: str = "narration"

    @property
    def end(self) -> float:
        return float(self.start) + float(self.duration)


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
    media_width: Optional[int] = None
    media_height: Optional[int] = None
    sync_media_size_to_canvas: bool = False
    media_layout_mode: Optional[str] = None
    media_placement: MediaPlacement | dict[str, Any] | None = None
    layered_template_spec: Mapping[str, Any] | None = None
    template_params: Dict[str, Any] = field(default_factory=dict)
    visuals: List[VisualClip] = field(default_factory=list)
    captions: List[CaptionCue] = field(default_factory=list)
    text_style_profiles: List[TextStyleProfile] = field(default_factory=list)
    title_style_profile: TextStyleProfile | None = None
    template_title_region: Dict[str, float] = field(default_factory=dict)
    template_caption_safe_area: Dict[str, float] = field(default_factory=dict)
    text_tracks: List[TextTrack] = field(default_factory=list)
    text_cues: List[TextCue] = field(default_factory=list)
    audio_tracks: List[TemplateAudioRef] = field(default_factory=list)
    element_animation_manifest_path: Optional[str] = None
    audio: Optional[TemplateAudioRef] = None

    def __post_init__(self) -> None:
        self.sync_media_size_to_canvas = bool(self.sync_media_size_to_canvas)
        self.media_layout_mode = resolve_media_layout_mode(
            self.media_layout_mode,
            sync_media_size_to_canvas=self.sync_media_size_to_canvas,
        )
        self.media_placement = resolve_media_placement(self.media_placement)
        if self.layered_template_spec is not None:
            self.layered_template_spec = active_layered_template_spec(
                self.layered_template_spec
            )
        preset = resolve_template_text_style_preset(self.template_id)
        if not self.template_title_region:
            self.template_title_region = preset.title_region_dict()
        if not self.template_caption_safe_area:
            self.template_caption_safe_area = preset.caption_safe_area_dict()
