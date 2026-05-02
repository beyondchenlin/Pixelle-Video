from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    LayerSourceSpec,
    RectSpec,
    TemplateLayer,
)

LAYERED_TEMPLATE_EDITOR_STATE_KEY = "layered_template_editor_state"
SessionState = MutableMapping[str, Any]


@dataclass(frozen=True)
class LayeredTemplateEditorState:
    canvas_width: int
    canvas_height: int
    media_width: int
    media_height: int
    layers: tuple[TemplateLayer, ...] = ()
    selected_layer_id: str | None = None

    @classmethod
    def empty(
        cls,
        *,
        canvas_width: int,
        canvas_height: int,
        media_width: int,
        media_height: int,
    ) -> LayeredTemplateEditorState:
        return cls(
            canvas_width=int(canvas_width),
            canvas_height=int(canvas_height),
            media_width=int(media_width),
            media_height=int(media_height),
        )

    def append_text_layer(self, name: str) -> LayeredTemplateEditorState:
        layer = TemplateLayer(
            id=_new_layer_id(),
            type="text",
            name=name,
            rect=RectSpec(
                x=96,
                y=120,
                width=max(1, self.canvas_width - 192),
                height=180,
            ),
            z_index=_next_z_index(self.layers),
            opacity=1.0,
            rotation=0.0,
            locked=False,
            source=None,
            style={},
        )
        return self._append_layer(layer)

    def append_image_layer(self, name: str) -> LayeredTemplateEditorState:
        side = max(1, min(self.media_width, self.media_height, self.canvas_width, self.canvas_height))
        layer = TemplateLayer(
            id=_new_layer_id(),
            type="image",
            name=name,
            rect=RectSpec(
                x=(self.canvas_width - side) / 2,
                y=(self.canvas_height - side) / 2,
                width=side,
                height=side,
            ),
            z_index=_next_z_index(self.layers),
            opacity=1.0,
            rotation=0.0,
            locked=False,
            source=None,
            style={},
        )
        return self._append_layer(layer)

    def append_background_layer(self, name: str) -> LayeredTemplateEditorState:
        layer = TemplateLayer(
            id=_new_layer_id(),
            type="background",
            name=name,
            rect=RectSpec(
                x=0,
                y=0,
                width=self.canvas_width,
                height=self.canvas_height,
            ),
            z_index=_next_z_index(self.layers, default=0),
            opacity=1.0,
            rotation=0.0,
            locked=False,
            source=None,
            style={},
        )
        return self._append_layer(layer)

    def update_layer_source(
        self,
        layer_id: str,
        source: LayerSourceSpec,
    ) -> LayeredTemplateEditorState:
        return self._update_layer(layer_id, source=source)

    def update_layer_name(
        self,
        layer_id: str,
        name: str,
    ) -> LayeredTemplateEditorState:
        return self._update_layer(layer_id, name=str(name))

    def update_layer_rect(
        self,
        layer_id: str,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> LayeredTemplateEditorState:
        return self._update_layer(
            layer_id,
            rect=RectSpec(x=x, y=y, width=width, height=height),
        )

    def update_layer_z_index(
        self,
        layer_id: str,
        z_index: int,
    ) -> LayeredTemplateEditorState:
        return self._update_layer(layer_id, z_index=int(z_index))

    def update_layer_opacity(
        self,
        layer_id: str,
        opacity: float,
    ) -> LayeredTemplateEditorState:
        return self._update_layer(layer_id, opacity=float(opacity))

    def update_layer_rotation(
        self,
        layer_id: str,
        rotation: float,
    ) -> LayeredTemplateEditorState:
        return self._update_layer(layer_id, rotation=float(rotation))

    def update_layer_locked(
        self,
        layer_id: str,
        locked: bool,
    ) -> LayeredTemplateEditorState:
        return self._update_layer(layer_id, locked=bool(locked))

    def update_layer_role(
        self,
        layer_id: str,
        role: str | None,
    ) -> LayeredTemplateEditorState:
        normalized_role = str(role).strip() if role is not None else None
        return self._update_layer(layer_id, role=normalized_role or None)

    def update_layer_style(
        self,
        layer_id: str,
        style: dict[str, Any],
    ) -> LayeredTemplateEditorState:
        return self._update_layer(layer_id, style=dict(style))

    def _update_layer(
        self,
        layer_id: str,
        **changes: Any,
    ) -> LayeredTemplateEditorState:
        if not any(layer.id == layer_id for layer in self.layers):
            return self
        layers = tuple(
            replace(layer, **changes) if layer.id == layer_id else layer
            for layer in self.layers
        )
        return replace(self, layers=layers)

    def build_spec(
        self,
        *,
        template_id: str,
        template_name: str,
        template_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> LayeredTemplateSpec:
        return LayeredTemplateSpecBuilder.from_editor_state(self).build(
            template_id=template_id,
            template_name=template_name,
            template_type=template_type,
            metadata=metadata,
        )

    def _append_layer(self, layer: TemplateLayer) -> LayeredTemplateEditorState:
        return replace(self, layers=(*self.layers, layer), selected_layer_id=layer.id)


@dataclass(frozen=True)
class LayeredTemplateSpecBuilder:
    canvas_width: int
    canvas_height: int
    media_width: int
    media_height: int
    layers: tuple[TemplateLayer, ...] = ()

    @classmethod
    def from_editor_state(
        cls,
        state: LayeredTemplateEditorState,
    ) -> LayeredTemplateSpecBuilder:
        return cls(
            canvas_width=state.canvas_width,
            canvas_height=state.canvas_height,
            media_width=state.media_width,
            media_height=state.media_height,
            layers=state.layers,
        )

    def build(
        self,
        *,
        template_id: str,
        template_name: str,
        template_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> LayeredTemplateSpec:
        return LayeredTemplateSpec(
            version="layered_template.v1",
            template_id=template_id,
            template_name=template_name,
            template_type=template_type,
            canvas_width=self.canvas_width,
            canvas_height=self.canvas_height,
            media_width=self.media_width,
            media_height=self.media_height,
            safe_area=RectSpec(
                x=0,
                y=0,
                width=self.canvas_width,
                height=self.canvas_height,
            ),
            layers=self.layers,
            metadata=metadata or {},
        )


def ensure_layered_template_editor_state(
    *,
    session_state: SessionState,
    canvas_width: int,
    canvas_height: int,
    media_width: int,
    media_height: int,
) -> LayeredTemplateEditorState:
    existing = session_state.get(LAYERED_TEMPLATE_EDITOR_STATE_KEY)
    if isinstance(existing, LayeredTemplateEditorState) and (
        existing.canvas_width,
        existing.canvas_height,
        existing.media_width,
        existing.media_height,
    ) == (
        int(canvas_width),
        int(canvas_height),
        int(media_width),
        int(media_height),
    ):
        return existing

    state = LayeredTemplateEditorState.empty(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        media_width=media_width,
        media_height=media_height,
    )
    session_state[LAYERED_TEMPLATE_EDITOR_STATE_KEY] = state
    return state


def load_layered_template_spec_into_editor_state(
    session_state: SessionState,
    spec_payload: dict[str, Any],
) -> LayeredTemplateEditorState:
    spec = LayeredTemplateSpec.from_dict(spec_payload)
    state = LayeredTemplateEditorState(
        canvas_width=spec.canvas_width,
        canvas_height=spec.canvas_height,
        media_width=spec.media_width,
        media_height=spec.media_height,
        layers=spec.layers,
        selected_layer_id=spec.layers[0].id if spec.layers else None,
    )
    session_state[LAYERED_TEMPLATE_EDITOR_STATE_KEY] = state
    return state


def _new_layer_id() -> str:
    return f"layer_{uuid4().hex[:8]}"


def _next_z_index(layers: tuple[TemplateLayer, ...], *, default: int = 10) -> int:
    if not layers:
        return default
    return max(layer.z_index for layer in layers) + 10

