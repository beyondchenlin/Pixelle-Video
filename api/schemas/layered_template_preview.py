from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.text_rendering import TextRenderingRequest
from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    LayerSourceSpec,
    RectSpec,
    TemplateLayer,
)
from pixelle_video.storage.object_store import WORKSPACE_ID_PATTERN


class RectSpecRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    unit: Literal["px"] = "px"

    def to_model(self) -> RectSpec:
        return RectSpec(
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            unit=self.unit,
        )


class LayerSourceSpecRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["color", "asset", "generated_media", "gradient"]
    ref: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_model(self) -> LayerSourceSpec:
        return LayerSourceSpec(kind=self.kind, ref=self.ref, metadata=self.metadata)


class TemplateLayerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    type: Literal["text", "image", "background", "generated_media"]
    name: str = Field(min_length=1)
    rect: RectSpecRequest
    z_index: int
    opacity: float = Field(ge=0.0, le=1.0)
    rotation: float = 0.0
    locked: bool = False
    source: LayerSourceSpecRequest | None = None
    style: dict[str, Any] = Field(default_factory=dict)
    role: str | None = None

    def to_model(self) -> TemplateLayer:
        return TemplateLayer(
            id=self.id,
            type=self.type,
            name=self.name,
            rect=self.rect.to_model(),
            z_index=self.z_index,
            opacity=self.opacity,
            rotation=self.rotation,
            locked=self.locked,
            source=self.source.to_model() if self.source else None,
            style=self.style,
            role=self.role,
        )


class LayeredTemplateSpecRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["layered_template.v1"]
    template_id: str = Field(min_length=1)
    template_name: str = Field(min_length=1)
    template_type: str = Field(min_length=1)
    canvas_width: int = Field(gt=0, le=8192)
    canvas_height: int = Field(gt=0, le=8192)
    media_width: int = Field(gt=0, le=8192)
    media_height: int = Field(gt=0, le=8192)
    safe_area: RectSpecRequest
    layers: list[TemplateLayerRequest] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_model(self) -> LayeredTemplateSpec:
        return LayeredTemplateSpec(
            version=self.version,
            template_id=self.template_id,
            template_name=self.template_name,
            template_type=self.template_type,
            canvas_width=self.canvas_width,
            canvas_height=self.canvas_height,
            media_width=self.media_width,
            media_height=self.media_height,
            safe_area=self.safe_area.to_model(),
            layers=tuple(layer.to_model() for layer in self.layers),
            metadata=self.metadata,
        )


class LayeredTemplatePreviewFrameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=WORKSPACE_ID_PATTERN.pattern,
    )
    title_text: str = ""
    caption_text: str = ""
    text_rendering: TextRenderingRequest = Field(default_factory=TextRenderingRequest)
    spec: LayeredTemplateSpecRequest

    def to_service_request(self):
        from pixelle_video.services.layered_template_service import (
            LayeredTemplatePreviewFrameRequest as ServiceRequest,
        )

        return ServiceRequest(
            workspace_id=self.workspace_id,
            spec=self.spec.to_model(),
            title_text=self.title_text,
            caption_text=self.caption_text,
            text_rendering=self.text_rendering.model_dump(exclude_none=True),
        )

    def normalized_spec(self) -> dict[str, Any]:
        return self.spec.to_model().to_dict()


class LayeredTemplatePreviewFrameResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_key: str
    url: str | None = None
