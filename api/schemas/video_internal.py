from __future__ import annotations

from typing import Optional

from pydantic import Field, model_validator

from api.schemas.video import VideoGenerateRequest, validate_raw_frame_template_orientation


class VideoGenerateInternalRequest(VideoGenerateRequest):
    """Internal/debug video request that may carry raw executable controls."""

    tts_workflow: Optional[str] = Field(
        None,
        description="Internal TTS workflow key or path resolved by trusted tooling",
    )
    ref_audio: Optional[str] = Field(
        None,
        description="Internal reference audio path or object key",
    )
    media_workflow: Optional[str] = Field(
        None,
        description="Internal media workflow key or path resolved by trusted tooling",
    )
    frame_template: Optional[str] = Field(
        None,
        description="Internal frame template path or key resolved by trusted tooling",
    )
    prompt_prefix: Optional[str] = Field(
        None,
        description="Internal raw image prompt prefix",
    )
    bgm_path: Optional[str] = Field(
        None,
        description="Internal background music path or object key",
    )

    @model_validator(mode="after")
    def validate_internal_raw_generation_contract(self) -> "VideoGenerateInternalRequest":
        size_params = {
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "media_width": self.media_width,
            "media_height": self.media_height,
            "video_orientation": self.video_orientation,
            "video_resolution_preset": self.video_resolution_preset,
            "media_orientation": self.media_orientation,
            "media_resolution_preset": self.media_resolution_preset,
            "sync_media_size_to_canvas": self.sync_media_size_to_canvas,
        }
        self.video_orientation = validate_raw_frame_template_orientation(
            frame_template=self.frame_template,
            video_orientation=self.video_orientation,
            size_params=size_params,
        )
        return self


__all__ = ["VideoGenerateInternalRequest"]
