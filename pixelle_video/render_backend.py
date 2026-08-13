from typing import Final, Literal, cast

RenderBackend = Literal["legacy", "hyperframes_compiled", "ffmpeg_manifest"]

LEGACY_RENDER_BACKEND: Final[RenderBackend] = "legacy"
HYPERFRAMES_COMPILED_RENDER_BACKEND: Final[RenderBackend] = "hyperframes_compiled"
FFMPEG_MANIFEST_RENDER_BACKEND: Final[RenderBackend] = "ffmpeg_manifest"
DEFAULT_RENDER_BACKEND: Final[RenderBackend] = FFMPEG_MANIFEST_RENDER_BACKEND
# Storyboards written before render_backend was persisted used the legacy path.
# Keep this compatibility fact independent from the default for newly created tasks.
HISTORICAL_MISSING_RENDER_BACKEND: Final[RenderBackend] = LEGACY_RENDER_BACKEND
SUPPORTED_RENDER_BACKENDS: Final[tuple[RenderBackend, ...]] = (
    LEGACY_RENDER_BACKEND,
    HYPERFRAMES_COMPILED_RENDER_BACKEND,
    FFMPEG_MANIFEST_RENDER_BACKEND,
)


def validate_render_backend(value: str) -> RenderBackend:
    if value not in SUPPORTED_RENDER_BACKENDS:
        supported = ", ".join(SUPPORTED_RENDER_BACKENDS)
        raise ValueError(f"render_backend must be one of: {supported}")
    return cast(RenderBackend, value)
