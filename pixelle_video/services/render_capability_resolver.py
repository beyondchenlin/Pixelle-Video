from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pixelle_video.render_backend import (
    FFMPEG_MANIFEST_RENDER_BACKEND,
    HYPERFRAMES_COMPILED_RENDER_BACKEND,
    LEGACY_RENDER_BACKEND,
)


@dataclass(frozen=True)
class RenderCapabilityInput:
    requested_backend: str
    template_type: str
    media_domain: str
    template_prerendered: bool
    element_motion_backend: str | None
    has_hyperframes_native_template: bool
    template_requires_browser_timeline: bool = False
    has_layered_template_spec: bool = False
    layered_template_prerender_available: bool = False


@dataclass(frozen=True)
class RenderCapabilityResult:
    effective_backend: str
    fallback_reason: str | None = None


@dataclass(frozen=True)
class HyperFramesTemplateCapabilities:
    browser_timeline_required: bool = False


def load_hyperframes_template_capabilities(
    template_dir: Path,
    *,
    template_id: str,
) -> HyperFramesTemplateCapabilities:
    capability_path = template_dir / "render_capabilities.json"
    if not capability_path.is_file():
        return HyperFramesTemplateCapabilities()

    payload = json.loads(capability_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError(f"Unsupported render capability schema: {capability_path}")
    if payload.get("template_id") != template_id:
        raise ValueError(f"Render capability template id mismatch: {capability_path}")
    browser_timeline_required = payload.get("browser_timeline_required")
    if not isinstance(browser_timeline_required, bool):
        raise ValueError(
            "browser_timeline_required must be a boolean in "
            f"{capability_path}"
        )
    return HyperFramesTemplateCapabilities(
        browser_timeline_required=browser_timeline_required
    )


class RenderCapabilityResolver:
    def resolve(self, request: RenderCapabilityInput) -> RenderCapabilityResult:
        if request.requested_backend == LEGACY_RENDER_BACKEND:
            return RenderCapabilityResult(effective_backend=LEGACY_RENDER_BACKEND)

        if request.requested_backend == HYPERFRAMES_COMPILED_RENDER_BACKEND:
            if request.has_layered_template_spec:
                return RenderCapabilityResult(
                    effective_backend=HYPERFRAMES_COMPILED_RENDER_BACKEND
                )
            if request.has_hyperframes_native_template:
                return RenderCapabilityResult(
                    effective_backend=HYPERFRAMES_COMPILED_RENDER_BACKEND
                )
            return RenderCapabilityResult(
                effective_backend=LEGACY_RENDER_BACKEND,
                fallback_reason="HyperFrames compiled backend requires a native HyperFrames template",
            )

        if request.requested_backend == FFMPEG_MANIFEST_RENDER_BACKEND:
            if request.template_requires_browser_timeline:
                if not request.has_hyperframes_native_template:
                    return RenderCapabilityResult(
                        effective_backend=LEGACY_RENDER_BACKEND,
                        fallback_reason=(
                            "ffmpeg_manifest cannot render the template browser timeline "
                            "and no native HyperFrames template is available"
                        ),
                    )
                return RenderCapabilityResult(
                    effective_backend=HYPERFRAMES_COMPILED_RENDER_BACKEND,
                    fallback_reason=(
                        "ffmpeg_manifest cannot preserve the template browser timeline"
                    ),
                )
            if request.has_layered_template_spec:
                if request.element_motion_backend == "hyperframes_canvas":
                    return RenderCapabilityResult(
                        effective_backend=HYPERFRAMES_COMPILED_RENDER_BACKEND,
                        fallback_reason=(
                            "ffmpeg_manifest cannot render hyperframes_canvas element motion"
                        ),
                    )
                if not request.layered_template_prerender_available:
                    return RenderCapabilityResult(
                        effective_backend=LEGACY_RENDER_BACKEND,
                        fallback_reason=(
                            "ffmpeg_manifest requires layered template prerendered assets"
                        ),
                    )
                return RenderCapabilityResult(
                    effective_backend=FFMPEG_MANIFEST_RENDER_BACKEND
                )
            if not request.template_prerendered:
                return RenderCapabilityResult(
                    effective_backend=LEGACY_RENDER_BACKEND,
                    fallback_reason="ffmpeg_manifest requires prerendered template assets",
                )
            if request.element_motion_backend == "hyperframes_canvas":
                if not request.has_hyperframes_native_template:
                    return RenderCapabilityResult(
                        effective_backend=LEGACY_RENDER_BACKEND,
                        fallback_reason=(
                            "ffmpeg_manifest cannot render hyperframes_canvas element "
                            "motion and no HyperFrames template is available"
                        ),
                    )
                return RenderCapabilityResult(
                    effective_backend=HYPERFRAMES_COMPILED_RENDER_BACKEND,
                    fallback_reason=(
                        "ffmpeg_manifest cannot render hyperframes_canvas element motion"
                    ),
                )
            return RenderCapabilityResult(
                effective_backend=FFMPEG_MANIFEST_RENDER_BACKEND
            )

        return RenderCapabilityResult(
            effective_backend=LEGACY_RENDER_BACKEND,
            fallback_reason=f"unsupported render backend: {request.requested_backend}",
        )
