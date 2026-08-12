from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from api.schemas.text_rendering import TextRenderingRequest
from pixelle_video.storage.object_store import WORKSPACE_ID_PATTERN


class TextRenderingPreviewMediaPlacementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basis: Literal["canvas"] = Field("canvas")
    fit: Literal["contain", "cover", "stretch", "original_size"] = Field("contain")
    scale_percent: StrictInt = Field(100, ge=10, le=100)
    anchor: Literal[
        "top_left",
        "top",
        "top_right",
        "left",
        "center",
        "right",
        "bottom_left",
        "bottom",
        "bottom_right",
    ] = Field("center")


class TextRenderingPreviewFrameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=WORKSPACE_ID_PATTERN.pattern,
    )
    template_id: str = Field(..., min_length=1)
    title_text: str = ""
    caption_text: str = ""
    text_rendering: TextRenderingRequest = Field(default_factory=TextRenderingRequest)
    canvas_width: int = Field(..., gt=0, le=8192)
    canvas_height: int = Field(..., gt=0, le=8192)
    media_width: int = Field(..., gt=0, le=8192)
    media_height: int = Field(..., gt=0, le=8192)
    media_placement: TextRenderingPreviewMediaPlacementRequest = Field(
        default_factory=TextRenderingPreviewMediaPlacementRequest
    )
    render_backend: str | None = None
    fps: int = Field(30, gt=0, le=120)
    preview_media_storage_key: str | None = None


class TextRenderingPreviewFrameResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_key: str
    url: str | None = None
