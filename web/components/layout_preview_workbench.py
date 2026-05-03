from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

import streamlit as st

from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    layered_template_fingerprint,
)
from pixelle_video.services.layered_template_adapters.html_preview import (
    render_layered_template_preview_html,
)
from pixelle_video.services.template_registry import TemplateRegistry
from web.components.layered_template_state import (
    load_layered_template_spec_into_editor_state,
)


def sort_recent_template_shortcuts(items: Sequence[Any], limit: int = 5) -> list[Any]:
    return sorted(
        items,
        key=lambda item: _item_value(item, "last_used_at") or "",
        reverse=True,
    )[:limit]


def render_layout_preview_workbench(
    *,
    spec: LayeredTemplateSpec | Mapping[str, Any],
    title_text: str,
    caption_text: str,
    text_rendering: Mapping[str, Any] | None,
    recent_templates: Sequence[Any],
    real_preview_state: Mapping[str, Any] | None,
    registry: TemplateRegistry | None = None,
    session_state: MutableMapping[str, Any] | None = None,
) -> None:
    normalized_spec = _normalize_spec(spec)
    registry = registry or TemplateRegistry()
    state = session_state if session_state is not None else st.session_state

    with st.container(border=True):
        st.markdown("**Instant preview workbench**")
        _render_recent_template_shortcuts(
            recent_templates=recent_templates,
            registry=registry,
            session_state=state,
        )
        st.caption(
            f"{normalized_spec.canvas_width}x{normalized_spec.canvas_height} | "
            f"{len(normalized_spec.layers)} layers"
        )
        if real_preview_state and real_preview_state.get("url"):
            st.caption(f"Real preview: {real_preview_state['url']}")
        st.markdown(
            render_layered_template_preview_html(
                spec=normalized_spec,
                title_text=title_text or "",
                caption_text=caption_text or "",
                text_rendering=text_rendering or {},
                fingerprint=layered_template_fingerprint(normalized_spec),
            ),
            unsafe_allow_html=True,
        )


def _render_recent_template_shortcuts(
    *,
    recent_templates: Sequence[Any],
    registry: TemplateRegistry,
    session_state: MutableMapping[str, Any],
) -> None:
    shortcuts = sort_recent_template_shortcuts(recent_templates, limit=5)
    if not shortcuts:
        return

    st.caption("Recent templates")
    for item in shortcuts:
        preset_id = _item_value(item, "preset_id")
        name = _item_value(item, "name") or preset_id
        spec = _item_value(item, "spec")
        if not preset_id or spec is None:
            continue
        if st.button(str(name), key=f"recent_template_{preset_id}", width="stretch"):
            registry.mark_used(str(preset_id))
            load_layered_template_spec_into_editor_state(session_state, _spec_payload(spec))


def _normalize_spec(spec: LayeredTemplateSpec | Mapping[str, Any]) -> LayeredTemplateSpec:
    if isinstance(spec, LayeredTemplateSpec):
        return spec
    return LayeredTemplateSpec.from_dict(spec)


def _spec_payload(spec: LayeredTemplateSpec | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(spec, LayeredTemplateSpec):
        return spec.to_dict()
    return dict(spec)


def _item_value(item: Any, key: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)
