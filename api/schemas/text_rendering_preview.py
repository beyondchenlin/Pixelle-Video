from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.text_rendering import TextRenderingRequest


class TextRenderingPreviewFrameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(..., min_length=1)
    template_id: str = Field(..., min_length=1)
    title_text: str = ""
    caption_text: str = ""
    text_rendering: TextRenderingRequest = Field(default_factory=TextRenderingRequest)
    canvas_width: int = Field(..., gt=0)
    canvas_height: int = Field(..., gt=0)
    media_width: int = Field(..., gt=0)
    media_height: int = Field(..., gt=0)
    media_placement: Mapping[str, Any] = Field(default_factory=dict)
    render_backend: str | None = None
    fps: int = Field(30, gt=0)
    preview_media_storage_key: str | None = None
    preview_media_url: str | None = None


class TextRenderingPreviewFrameResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_key: str
    url: str | None = None
    fingerprint: str
