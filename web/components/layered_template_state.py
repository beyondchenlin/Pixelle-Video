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
from pixelle_video.models.size_contract import GenerationSizeContract

LAYERED_TEMPLATE_EDITOR_STATE_KEY = "layered_template_editor_state"
LAYERED_TEMPLATE_SELECTED_SPEC_IDENTITY_KEY = "layered_template_selected_spec_identity"
LAYERED_TEMPLATE_SELECTED_SIZE_PARAMS_KEY = "layered_template_selected_size_params"
LAYERED_TEMPLATE_PENDING_WIDGET_STATE_KEY = "layered_template_pending_widget_state"
SessionState = MutableMapping[str, Any]


@dataclass(frozen=True)
class LayeredTemplateEditorState:
    canvas_width: int
    canvas_height: int
    media_width: int
    media_height: int
    safe_area: RectSpec
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
        safe_area: RectSpec | None = None,
    ) -> LayeredTemplateEditorState:
        normalized_canvas_width = int(canvas_width)
        normalized_canvas_height = int(canvas_height)
        return cls(
            canvas_width=normalized_canvas_width,
            canvas_height=normalized_canvas_height,
            media_width=int(media_width),
            media_height=int(media_height),
            safe_area=safe_area
            or RectSpec(
                x=0,
                y=0,
                width=normalized_canvas_width,
                height=normalized_canvas_height,
            ),
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

    def update_layer_enabled(
        self,
        layer_id: str,
        enabled: bool,
    ) -> LayeredTemplateEditorState:
        return self._update_layer(layer_id, enabled=bool(enabled))

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

    def delete_layer(self, layer_id: str) -> LayeredTemplateEditorState:
        if not any(layer.id == layer_id for layer in self.layers):
            return self
        layers = tuple(layer for layer in self.layers if layer.id != layer_id)
        selected_layer_id = self.selected_layer_id
        if selected_layer_id == layer_id:
            selected_layer_id = layers[-1].id if layers else None
        return replace(self, layers=layers, selected_layer_id=selected_layer_id)

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
    safe_area: RectSpec
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
            safe_area=state.safe_area,
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
            safe_area=self.safe_area,
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
        safe_area=spec.safe_area,
        layers=spec.layers,
        selected_layer_id=spec.layers[0].id if spec.layers else None,
    )
    session_state[LAYERED_TEMPLATE_EDITOR_STATE_KEY] = state
    session_state[LAYERED_TEMPLATE_SELECTED_SPEC_IDENTITY_KEY] = {
        "template_id": spec.template_id,
        "template_name": spec.template_name,
        "template_type": spec.template_type,
        "metadata": dict(spec.metadata),
    }
    size_params = _size_params_from_spec(spec)
    session_state[LAYERED_TEMPLATE_SELECTED_SIZE_PARAMS_KEY] = size_params
    _queue_template_widget_state(session_state, spec, size_params)
    return state


def resolve_layered_template_spec_identity(
    session_state: SessionState,
    *,
    fallback_template_id: str,
    fallback_template_name: str,
    fallback_template_type: str,
    fallback_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity = session_state.get(LAYERED_TEMPLATE_SELECTED_SPEC_IDENTITY_KEY)
    if _is_valid_spec_identity(identity):
        return {
            "template_id": str(identity["template_id"]),
            "template_name": str(identity["template_name"]),
            "template_type": str(identity["template_type"]),
            "metadata": dict(identity.get("metadata") or {}),
        }
    return {
        "template_id": str(fallback_template_id),
        "template_name": str(fallback_template_name),
        "template_type": str(fallback_template_type),
        "metadata": dict(fallback_metadata or {}),
    }


def clear_layered_template_spec_identity(session_state: SessionState) -> None:
    session_state.pop(LAYERED_TEMPLATE_SELECTED_SPEC_IDENTITY_KEY, None)
    session_state.pop(LAYERED_TEMPLATE_SELECTED_SIZE_PARAMS_KEY, None)
    session_state.pop(LAYERED_TEMPLATE_PENDING_WIDGET_STATE_KEY, None)


def apply_pending_layered_template_widget_state(
    session_state: SessionState,
) -> None:
    pending = session_state.pop(LAYERED_TEMPLATE_PENDING_WIDGET_STATE_KEY, None)
    if not isinstance(pending, dict):
        return
    for key, value in pending.items():
        if value is None:
            session_state.pop(key, None)
        else:
            session_state[key] = value


def resolve_layered_template_selected_size_params(
    session_state: SessionState,
) -> dict[str, Any] | None:
    value = session_state.get(LAYERED_TEMPLATE_SELECTED_SIZE_PARAMS_KEY)
    if not isinstance(value, dict):
        return None
    required = (
        "canvas_width",
        "canvas_height",
        "media_width",
        "media_height",
        "video_orientation",
        "video_resolution_preset",
        "media_orientation",
        "media_resolution_preset",
        "sync_media_size_to_canvas",
    )
    if any(key not in value for key in required):
        return None
    return dict(value)


def has_layered_template_spec_identity(session_state: SessionState) -> bool:
    return _is_valid_spec_identity(
        session_state.get(LAYERED_TEMPLATE_SELECTED_SPEC_IDENTITY_KEY)
    )


def _is_valid_spec_identity(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("template_id"), str)
        and bool(value["template_id"])
        and isinstance(value.get("template_name"), str)
        and bool(value["template_name"])
        and isinstance(value.get("template_type"), str)
        and bool(value["template_type"])
        and (
            value.get("metadata") is None
            or isinstance(value.get("metadata"), dict)
        )
    )


def _size_params_from_spec(spec: LayeredTemplateSpec) -> dict[str, Any]:
    return GenerationSizeContract.from_params(
        {
            "canvas_width": spec.canvas_width,
            "canvas_height": spec.canvas_height,
            "media_width": spec.media_width,
            "media_height": spec.media_height,
        }
    ).to_params()


def _queue_template_widget_state(
    session_state: SessionState,
    spec: LayeredTemplateSpec,
    size_params: dict[str, Any],
) -> None:
    pending = {
        "video_orientation": size_params["video_orientation"],
        "video_resolution_preset": size_params["video_resolution_preset"],
        "media_orientation": size_params["media_orientation"],
        "media_resolution_preset": size_params["media_resolution_preset"],
        "sync_media_size_to_canvas": size_params["sync_media_size_to_canvas"],
        "template_type_selector": spec.template_type,
        "last_template_type": spec.template_type,
    }
    legacy_template_path = spec.metadata.get("legacy_template_path")
    if isinstance(legacy_template_path, str) and legacy_template_path.strip():
        pending["selected_template"] = legacy_template_path.strip()
    else:
        pending["selected_template"] = None
    session_state[LAYERED_TEMPLATE_PENDING_WIDGET_STATE_KEY] = pending


def _new_layer_id() -> str:
    return f"layer_{uuid4().hex[:8]}"


def _next_z_index(layers: tuple[TemplateLayer, ...], *, default: int = 10) -> int:
    if not layers:
        return default
    return max(layer.z_index for layer in layers) + 10

