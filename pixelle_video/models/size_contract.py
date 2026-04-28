from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

VALID_ORIENTATIONS = ("landscape", "portrait", "square")
VALID_VIDEO_RESOLUTION_PRESETS = ("1k", "2k", "4k")
VALID_MEDIA_RESOLUTION_PRESETS = ("768", "1k", "2k", "4k")

DEFAULT_VIDEO_ORIENTATION = "landscape"
DEFAULT_VIDEO_RESOLUTION_PRESET = "1k"
DEFAULT_MEDIA_ORIENTATION = "square"
DEFAULT_MEDIA_RESOLUTION_PRESET = "768"


@dataclass(frozen=True)
class SizeSpec:
    width: int
    height: int

    def __post_init__(self) -> None:
        if int(self.width) <= 0 or int(self.height) <= 0:
            raise ValueError("size dimensions must be positive")

    def as_tuple(self) -> tuple[int, int]:
        return int(self.width), int(self.height)


DEFAULT_MEDIA_SIZE = SizeSpec(768, 768)

VIDEO_SIZE_PRESETS: dict[str, dict[str, SizeSpec]] = {
    "landscape": {
        "1k": SizeSpec(1280, 720),
        "2k": SizeSpec(1920, 1080),
        "4k": SizeSpec(3840, 2160),
    },
    "portrait": {
        "1k": SizeSpec(720, 1280),
        "2k": SizeSpec(1080, 1920),
        "4k": SizeSpec(2160, 3840),
    },
    "square": {
        "1k": SizeSpec(1024, 1024),
        "2k": SizeSpec(2048, 2048),
        "4k": SizeSpec(4096, 4096),
    },
}

MEDIA_SIZE_PRESETS: dict[str, dict[str, SizeSpec]] = {
    "landscape": VIDEO_SIZE_PRESETS["landscape"],
    "portrait": VIDEO_SIZE_PRESETS["portrait"],
    "square": {
        DEFAULT_MEDIA_RESOLUTION_PRESET: DEFAULT_MEDIA_SIZE,
        **VIDEO_SIZE_PRESETS["square"],
    },
}

_VIDEO_PRESET_ALIASES = {
    "1280x720": "1k",
    "720x1280": "1k",
    "1024x1024": "1k",
    "1920x1080": "2k",
    "1080x1920": "2k",
    "2048x2048": "2k",
    "3840x2160": "4k",
    "2160x3840": "4k",
    "4096x4096": "4k",
}

_MEDIA_PRESET_ALIASES = {
    "768x768": "768",
    **_VIDEO_PRESET_ALIASES,
}


def _normalize_optional_string(value: Any, default: str) -> str:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    return normalized or default


def normalize_orientation(
    value: Any = None,
    *,
    default: str = DEFAULT_VIDEO_ORIENTATION,
    field_name: str = "orientation",
) -> str:
    orientation = _normalize_optional_string(value, default)
    if orientation not in VALID_ORIENTATIONS:
        raise ValueError(f"unsupported {field_name}: {orientation}")
    return orientation


def normalize_video_orientation(value: Any = None) -> str:
    return normalize_orientation(
        value,
        default=DEFAULT_VIDEO_ORIENTATION,
        field_name="video orientation",
    )


def normalize_media_orientation(value: Any = None) -> str:
    return normalize_orientation(
        value,
        default=DEFAULT_MEDIA_ORIENTATION,
        field_name="media orientation",
    )


def normalize_video_resolution_preset(value: Any = None) -> str:
    preset = _normalize_optional_string(value, DEFAULT_VIDEO_RESOLUTION_PRESET)
    preset = _VIDEO_PRESET_ALIASES.get(preset, preset)
    if preset not in VALID_VIDEO_RESOLUTION_PRESETS:
        raise ValueError(f"unsupported video resolution preset: {preset}")
    return preset


def normalize_media_resolution_preset(
    value: Any = None,
    *,
    orientation: str | None = None,
) -> str:
    normalized_orientation = normalize_media_orientation(orientation)
    default = (
        DEFAULT_MEDIA_RESOLUTION_PRESET
        if normalized_orientation == DEFAULT_MEDIA_ORIENTATION
        else DEFAULT_VIDEO_RESOLUTION_PRESET
    )
    preset = _normalize_optional_string(value, default)
    preset = _MEDIA_PRESET_ALIASES.get(preset, preset)
    if preset not in VALID_MEDIA_RESOLUTION_PRESETS:
        raise ValueError(f"unsupported media resolution preset: {preset}")
    if preset not in MEDIA_SIZE_PRESETS[normalized_orientation]:
        raise ValueError(
            "unsupported media resolution preset "
            f"{preset!r} for {normalized_orientation!r}"
        )
    return preset


def resolve_canvas_size(orientation: Any = None, preset: Any = None) -> SizeSpec:
    normalized_orientation = normalize_video_orientation(orientation)
    normalized_preset = normalize_video_resolution_preset(preset)
    return VIDEO_SIZE_PRESETS[normalized_orientation][normalized_preset]


def resolve_media_size(orientation: Any = None, preset: Any = None) -> SizeSpec:
    normalized_orientation = normalize_media_orientation(orientation)
    normalized_preset = normalize_media_resolution_preset(
        preset,
        orientation=normalized_orientation,
    )
    return MEDIA_SIZE_PRESETS[normalized_orientation][normalized_preset]


def _optional_int_pair(
    params: Mapping[str, Any],
    width_key: str,
    height_key: str,
) -> SizeSpec | None:
    width = params.get(width_key)
    height = params.get(height_key)
    if width is None and height is None:
        return None
    if width is None or height is None:
        raise ValueError(f"{width_key} and {height_key} must be provided together")
    return SizeSpec(int(width), int(height))


def _has_new_canvas_intent(params: Mapping[str, Any]) -> bool:
    return any(
        key in params and params.get(key) is not None
        for key in (
            "canvas_width",
            "canvas_height",
            "video_orientation",
            "video_resolution_preset",
            "sync_media_size_to_canvas",
        )
    )


@dataclass(frozen=True)
class GenerationSizeContract:
    canvas_width: int
    canvas_height: int
    media_width: int
    media_height: int
    video_orientation: str = DEFAULT_VIDEO_ORIENTATION
    video_resolution_preset: str = DEFAULT_VIDEO_RESOLUTION_PRESET
    media_orientation: str = DEFAULT_MEDIA_ORIENTATION
    media_resolution_preset: str = DEFAULT_MEDIA_RESOLUTION_PRESET
    sync_media_size_to_canvas: bool = False

    @classmethod
    def default(cls) -> GenerationSizeContract:
        return cls.from_params({})

    @classmethod
    def from_params(cls, params: Mapping[str, Any] | None) -> GenerationSizeContract:
        source = dict(params or {})
        video_orientation = normalize_video_orientation(
            source.get("video_orientation")
        )
        video_preset = normalize_video_resolution_preset(
            source.get("video_resolution_preset")
        )
        media_orientation = normalize_media_orientation(
            source.get("media_orientation")
        )
        media_preset = normalize_media_resolution_preset(
            source.get("media_resolution_preset"),
            orientation=media_orientation,
        )
        sync = bool(source.get("sync_media_size_to_canvas", False))

        explicit_canvas = _optional_int_pair(source, "canvas_width", "canvas_height")
        explicit_media = _optional_int_pair(source, "media_width", "media_height")

        if explicit_canvas is not None:
            canvas = explicit_canvas
        elif explicit_media is not None and not _has_new_canvas_intent(source):
            canvas = explicit_media
        else:
            canvas = resolve_canvas_size(video_orientation, video_preset)

        if sync:
            media = canvas
        elif explicit_media is not None:
            media = explicit_media
        else:
            media = resolve_media_size(media_orientation, media_preset)

        return cls(
            canvas_width=canvas.width,
            canvas_height=canvas.height,
            media_width=media.width,
            media_height=media.height,
            video_orientation=video_orientation,
            video_resolution_preset=video_preset,
            media_orientation=media_orientation,
            media_resolution_preset=media_preset,
            sync_media_size_to_canvas=sync,
        )

    def to_params(self) -> dict[str, Any]:
        return {
            "canvas_width": int(self.canvas_width),
            "canvas_height": int(self.canvas_height),
            "media_width": int(self.media_width),
            "media_height": int(self.media_height),
            "video_orientation": self.video_orientation,
            "video_resolution_preset": self.video_resolution_preset,
            "media_orientation": self.media_orientation,
            "media_resolution_preset": self.media_resolution_preset,
            "sync_media_size_to_canvas": bool(self.sync_media_size_to_canvas),
        }
