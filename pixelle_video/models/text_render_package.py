from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from pixelle_video.models.render_package import CaptionCue, TextCue, TextTrack
from pixelle_video.models.text_layout import TextLayoutPlan
from pixelle_video.models.text_overlay import (
    FrozenJSONValue,
    freeze_json_value,
    thaw_json_value,
)
from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    TextStyleProfile,
    build_default_text_style_profiles,
)

_PUNCTUATION_MODES = {"strip_all", "strip_terminal", "preserve"}
_RENDERER_TARGETS = {"hyperframes", "html", "ass", "python"}


def _freeze_json_mapping(value: Mapping[str, Any] | None) -> Mapping[str, FrozenJSONValue]:
    frozen = freeze_json_value(dict(value or {}))
    if not isinstance(frozen, Mapping):
        raise TypeError("Expected a JSON object mapping.")
    return frozen


def _coerce_caption_settings(value: Any) -> "CaptionRenderingSettings":
    if isinstance(value, CaptionRenderingSettings):
        return value
    if value is None:
        return CaptionRenderingSettings()
    return CaptionRenderingSettings.from_dict(value)


def _coerce_layout_plan(value: Any) -> TextLayoutPlan:
    if isinstance(value, TextLayoutPlan):
        return value
    return TextLayoutPlan.from_dict(value)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    return bool(value)


def _coerce_renderer_targets(
    value: Any,
    default: tuple[str, ...] = ("hyperframes", "ass"),
) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        cleaned = value.strip()
        return (cleaned,) if cleaned else ()
    return tuple(value)


def _coerce_text_style_profile(value: Any) -> TextStyleProfile:
    if isinstance(value, TextStyleProfile):
        return value
    if isinstance(value, Mapping):
        return TextStyleProfile.from_dict(value)
    raise TypeError(f"Unsupported text style profile type: {type(value).__name__}")


def _coerce_caption_cue(value: Any) -> CaptionCue:
    if isinstance(value, CaptionCue):
        return value
    if isinstance(value, Mapping):
        return CaptionCue.from_dict(value)
    raise TypeError(f"Unsupported caption cue type: {type(value).__name__}")


def _coerce_text_track(value: Any) -> TextTrack:
    if isinstance(value, TextTrack):
        return value
    if isinstance(value, Mapping):
        return TextTrack.from_dict(value)
    raise TypeError(f"Unsupported text track type: {type(value).__name__}")


def _coerce_text_cue(value: Any) -> TextCue:
    if isinstance(value, TextCue):
        return value
    if isinstance(value, Mapping):
        return TextCue.from_dict(value)
    raise TypeError(f"Unsupported text cue type: {type(value).__name__}")


@dataclass(frozen=True)
class CaptionRenderingSettings:
    version: str = "caption_rendering_settings.v1"
    enabled: bool = False
    source: str = "narration_timing"
    style_profile: str = DEFAULT_CAPTION_STYLE_ID
    punctuation_mode: str = "strip_all"
    renderer_targets: tuple[str, ...] = ("hyperframes", "ass")

    def __post_init__(self) -> None:
        if not str(self.source).strip():
            raise ValueError("CaptionRenderingSettings source cannot be empty")
        if not str(self.style_profile).strip():
            raise ValueError("CaptionRenderingSettings style_profile cannot be empty")
        if self.punctuation_mode not in _PUNCTUATION_MODES:
            raise ValueError(f"Unsupported punctuation_mode: {self.punctuation_mode}")
        targets = tuple(
            str(target).strip()
            for target in _coerce_renderer_targets(self.renderer_targets)
        )
        unknown_targets = set(targets) - _RENDERER_TARGETS
        if unknown_targets:
            raise ValueError(f"Unsupported renderer targets: {sorted(unknown_targets)}")
        object.__setattr__(self, "enabled", _coerce_bool(self.enabled, False))
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "style_profile", str(self.style_profile))
        object.__setattr__(self, "renderer_targets", targets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "enabled": self.enabled,
            "source": self.source,
            "style_profile": self.style_profile,
            "punctuation_mode": self.punctuation_mode,
            "renderer_targets": list(self.renderer_targets),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "CaptionRenderingSettings":
        payload = dict(data or {})
        return cls(
            version=str(payload.get("version", "caption_rendering_settings.v1")),
            enabled=_coerce_bool(payload.get("enabled"), False),
            source=str(payload.get("source", "narration_timing")),
            style_profile=str(payload.get("style_profile", DEFAULT_CAPTION_STYLE_ID)),
            punctuation_mode=str(payload.get("punctuation_mode", "strip_all")),
            renderer_targets=_coerce_renderer_targets(payload.get("renderer_targets")),
        )


@dataclass(frozen=True)
class TextRenderPackage:
    task_id: str
    version: str = "text_render_package.v1"
    caption_settings: CaptionRenderingSettings = field(
        default_factory=CaptionRenderingSettings
    )
    text_style_profiles: tuple[TextStyleProfile, ...] = field(default_factory=tuple)
    caption_cues: tuple[CaptionCue, ...] = field(default_factory=tuple)
    text_tracks: tuple[TextTrack, ...] = field(default_factory=tuple)
    text_cues: tuple[TextCue, ...] = field(default_factory=tuple)
    layout_plan: TextLayoutPlan = field(default_factory=TextLayoutPlan)
    diagnostics: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.task_id).strip():
            raise ValueError("TextRenderPackage task_id cannot be empty")
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(
            self, "caption_settings", _coerce_caption_settings(self.caption_settings)
        )
        object.__setattr__(
            self,
            "text_style_profiles",
            tuple(
                _coerce_text_style_profile(profile)
                for profile in self.text_style_profiles
            ),
        )
        object.__setattr__(
            self,
            "caption_cues",
            tuple(_coerce_caption_cue(cue) for cue in self.caption_cues),
        )
        object.__setattr__(
            self,
            "text_tracks",
            tuple(_coerce_text_track(track) for track in self.text_tracks),
        )
        object.__setattr__(
            self,
            "text_cues",
            tuple(_coerce_text_cue(cue) for cue in self.text_cues),
        )
        object.__setattr__(self, "layout_plan", _coerce_layout_plan(self.layout_plan))
        object.__setattr__(self, "diagnostics", _freeze_json_mapping(self.diagnostics))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "task_id": self.task_id,
            "caption_settings": self.caption_settings.to_dict(),
            "text_style_profiles": [
                profile.to_dict() for profile in self.text_style_profiles
            ],
            "caption_cues": [cue.to_dict() for cue in self.caption_cues],
            "text_tracks": [track.to_dict() for track in self.text_tracks],
            "text_cues": [cue.to_dict() for cue in self.text_cues],
            "layout_plan": self.layout_plan.to_dict(),
            "diagnostics": thaw_json_value(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TextRenderPackage":
        payload = dict(data)
        missing_fields = [
            field_name
            for field_name in (
                "version",
                "caption_settings",
                "text_style_profiles",
                "caption_cues",
                "text_tracks",
                "text_cues",
                "layout_plan",
                "diagnostics",
            )
            if field_name not in payload
        ]
        diagnostics = dict(payload.get("diagnostics") or {})
        if missing_fields:
            existing_compatibility = diagnostics.get("compatibility")
            if isinstance(existing_compatibility, Mapping):
                compatibility = dict(existing_compatibility)
            else:
                compatibility = {}
                if existing_compatibility is not None:
                    compatibility["legacy_value"] = existing_compatibility
            compatibility["applied_defaults"] = missing_fields
            diagnostics["compatibility"] = compatibility

        return cls(
            version=str(payload.get("version", "text_render_package.v1")),
            task_id=str(payload["task_id"]),
            caption_settings=CaptionRenderingSettings.from_dict(
                payload.get("caption_settings")
            ),
            text_style_profiles=tuple(
                TextStyleProfile.from_dict(item)
                for item in payload.get(
                    "text_style_profiles",
                    [
                        profile.to_dict()
                        for profile in build_default_text_style_profiles()
                    ],
                )
            ),
            caption_cues=tuple(
                CaptionCue.from_dict(item) for item in payload.get("caption_cues", ())
            ),
            text_tracks=tuple(
                TextTrack.from_dict(item) for item in payload.get("text_tracks", ())
            ),
            text_cues=tuple(
                TextCue.from_dict(item) for item in payload.get("text_cues", ())
            ),
            layout_plan=TextLayoutPlan.from_dict(payload.get("layout_plan")),
            diagnostics=diagnostics,
        )
