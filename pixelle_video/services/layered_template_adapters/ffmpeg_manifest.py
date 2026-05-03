from __future__ import annotations

from dataclasses import replace

from pixelle_video.models.render_package import RenderManifest, VisualClip


class LayeredTemplateFfmpegAdapter:
    """Validate the ffmpeg path consumes prerendered layered-template frames."""

    def prepare_manifest(self, manifest: RenderManifest) -> RenderManifest:
        if manifest.layered_template_spec is None:
            return manifest

        invalid_clips = [
            clip
            for clip in manifest.visual_clips
            if clip.source_kind != "template_frame"
        ]
        if invalid_clips:
            raise ValueError(
                "ffmpeg_manifest layered template requires prerendered "
                "template_frame assets"
            )

        return replace(
            manifest,
            visual_clips=[
                replace(clip, media_role="final_frame")
                if isinstance(clip, VisualClip)
                else clip
                for clip in manifest.visual_clips
            ],
        )


__all__ = ["LayeredTemplateFfmpegAdapter"]
