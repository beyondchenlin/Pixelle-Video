from pixelle_video.services.render_capability_resolver import (
    RenderCapabilityInput,
    RenderCapabilityResolver,
)


def test_resolver_allows_ffmpeg_manifest_for_prerendered_image_template():
    result = RenderCapabilityResolver().resolve(
        RenderCapabilityInput(
            requested_backend="ffmpeg_manifest",
            template_type="image",
            media_domain="image",
            template_prerendered=True,
            element_motion_backend="python_ffmpeg",
            has_hyperframes_native_template=False,
        )
    )

    assert result.effective_backend == "ffmpeg_manifest"
    assert result.fallback_reason is None


def test_resolver_falls_back_when_ffmpeg_manifest_needs_browser_template():
    result = RenderCapabilityResolver().resolve(
        RenderCapabilityInput(
            requested_backend="ffmpeg_manifest",
            template_type="image",
            media_domain="image",
            template_prerendered=False,
            element_motion_backend="hyperframes_canvas",
            has_hyperframes_native_template=False,
        )
    )

    assert result.effective_backend == "legacy"
    assert "requires prerendered template" in result.fallback_reason


def test_resolver_routes_hyperframes_canvas_motion_to_hyperframes():
    result = RenderCapabilityResolver().resolve(
        RenderCapabilityInput(
            requested_backend="ffmpeg_manifest",
            template_type="image",
            media_domain="image",
            template_prerendered=True,
            element_motion_backend="hyperframes_canvas",
            has_hyperframes_native_template=True,
        )
    )

    assert result.effective_backend == "hyperframes_compiled"
    assert "hyperframes_canvas" in result.fallback_reason


def test_resolver_falls_back_unknown_backend_to_legacy():
    result = RenderCapabilityResolver().resolve(
        RenderCapabilityInput(
            requested_backend="unknown",
            template_type="image",
            media_domain="image",
            template_prerendered=True,
            element_motion_backend=None,
            has_hyperframes_native_template=False,
        )
    )

    assert result.effective_backend == "legacy"
    assert "unsupported render backend" in result.fallback_reason
