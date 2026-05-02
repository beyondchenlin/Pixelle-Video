from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
)

from pixelle_video.models.layered_template import (
    LAYERED_TEMPLATE_VERSION,
    LayerSourceSpec,
    LayeredTemplateSpec,
    RectSpec,
    TemplateLayer,
)
from pixelle_video.storage.object_store import WORKSPACE_ID_PATTERN

MAX_LAYER_COUNT = 64
MAX_TEXT_LENGTH = 2048
MAX_JSON_DEPTH = 8
MAX_JSON_KEYS = 128
MAX_JSON_LIST_ITEMS = 128
MAX_JSON_STRING_LENGTH = 4096
MAX_SOURCE_REF_LENGTH = 512


class RectSpecRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: StrictFloat | StrictInt
    y: StrictFloat | StrictInt
    width: StrictFloat | StrictInt = Field(..., gt=0)
    height: StrictFloat | StrictInt = Field(..., gt=0)
    unit: Literal["px"] = "px"

    def to_model(self) -> RectSpec:
        return RectSpec(x=self.x, y=self.y, width=self.width, height=self.height, unit=self.unit)


class LayerSourceSpecRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["color", "asset", "generated_media", "gradient"]
    ref: StrictStr = Field(..., min_length=1, max_length=MAX_SOURCE_REF_LENGTH)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_json_boundary(value)
        return value

    def to_model(self) -> LayerSourceSpec:
        return LayerSourceSpec(kind=self.kind, ref=self.ref, metadata=self.metadata)


class TemplateLayerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: StrictStr = Field(..., min_length=1, max_length=128)
    type: Literal["text", "image", "background", "generated_media"]
    name: StrictStr = Field(..., min_length=1, max_length=256)
    rect: RectSpecRequest
    z_index: StrictInt
    opacity: StrictFloat | StrictInt = Field(..., ge=0, le=1)
    rotation: StrictFloat | StrictInt = 0
    locked: StrictBool = False
    source: LayerSourceSpecRequest | None = None
    style: dict[str, Any] = Field(default_factory=dict)
    role: StrictStr | None = Field(default=None, max_length=64)

    @field_validator("style")
    @classmethod
    def validate_style(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_json_boundary(value)
        return value

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

    version: Literal[LAYERED_TEMPLATE_VERSION]
    template_id: StrictStr = Field(..., min_length=1, max_length=128)
    template_name: StrictStr = Field(..., min_length=1, max_length=256)
    template_type: Literal["static", "image", "video"]
    canvas_width: StrictInt = Field(..., gt=0, le=8192)
    canvas_height: StrictInt = Field(..., gt=0, le=8192)
    media_width: StrictInt = Field(..., gt=0, le=8192)
    media_height: StrictInt = Field(..., gt=0, le=8192)
    safe_area: RectSpecRequest
    layers: list[TemplateLayerRequest] = Field(default_factory=list, max_length=MAX_LAYER_COUNT)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_json_boundary(value)
        return value

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
    spec: LayeredTemplateSpecRequest
    title_text: str = Field(default="", max_length=MAX_TEXT_LENGTH)
    caption_text: str = Field(default="", max_length=MAX_TEXT_LENGTH)
    text_rendering: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text_rendering")
    @classmethod
    def validate_text_rendering(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_json_boundary(value)
        return value


class LayeredTemplatePreviewFrameResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["html_preview"] = "html_preview"
    html: str
    fingerprint: str


def _validate_json_boundary(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise ValueError(f"JSON payload depth must be <= {MAX_JSON_DEPTH}")
    if isinstance(value, dict):
        if len(value) > MAX_JSON_KEYS:
            raise ValueError(f"JSON object must contain <= {MAX_JSON_KEYS} keys")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            if len(key) > MAX_JSON_STRING_LENGTH:
                raise ValueError("JSON object key is too long")
            _validate_json_boundary(item, depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > MAX_JSON_LIST_ITEMS:
            raise ValueError(f"JSON array must contain <= {MAX_JSON_LIST_ITEMS} items")
        for item in value:
            _validate_json_boundary(item, depth=depth + 1)
        return
    if isinstance(value, tuple):
        if len(value) > MAX_JSON_LIST_ITEMS:
            raise ValueError(f"JSON array must contain <= {MAX_JSON_LIST_ITEMS} items")
        for item in value:
            _validate_json_boundary(item, depth=depth + 1)
        return
    if isinstance(value, str) and len(value) > MAX_JSON_STRING_LENGTH:
        raise ValueError("JSON string value is too long")
