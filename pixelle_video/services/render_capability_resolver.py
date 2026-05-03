from __future__ import annotations

from dataclasses import dataclass

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
    has_layered_template_spec: bool = False
    layered_template_prerender_available: bool = False


@dataclass(frozen=True)
class RenderCapabilityResult:
    effective_backend: str
    fallback_reason: str | None = None


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
