from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from html import escape
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from pixelle_video.models.layered_template import LayeredTemplateSpec

PresetSelection = dict[str, Any]
PresetSelectionCallback = Callable[[PresetSelection], Any]
_PENDING_SELECTION_SESSION_KEY = "_layout_preview_workbench_selection"


@dataclass(frozen=True)
class TrustedPreviewHTML:
    html: str

_TITLE = "\u5373\u65f6\u9884\u89c8\u5de5\u4f5c\u53f0"
_KICKER = "Layout Console"
_DESCRIPTION = (
    "\u5e38\u9a7b\u67e5\u770b\u5f53\u524d\u6392\u7248\u89c4\u683c\u3001"
    "\u6700\u8fd1\u6a21\u677f\u4e0e\u670d\u52a1\u7aef\u9884\u89c8\u7ed3\u679c\u3002"
)
_RECENT_TITLE = "\u6700\u8fd1\u6a21\u677f\u5feb\u6377"
_NO_RECENT = "\u6682\u65e0\u6700\u8fd1\u6a21\u677f\u3002"
_APPLY_PREFIX = "\u5957\u7528"
_APPLY_HELP = (
    "\u9009\u62e9\u6700\u8fd1\u6a21\u677f\uff0c\u4e3b\u5165\u53e3\u4f1a"
    "\u636e\u6b64\u56de\u586b\u5b8c\u6574\u89c4\u683c\u3002"
)
_CURRENT_SPEC = "\u5f53\u524d\u89c4\u683c"
_NO_SPEC = "\u6682\u65e0\u53ef\u9884\u89c8\u7684\u6392\u7248\u89c4\u683c\u3002"
_CANVAS_SIZE = "\u753b\u5e03\u5c3a\u5bf8"
_MEDIA_SIZE = "\u5a92\u4f53\u5c3a\u5bf8"
_LAYER_COUNT = "\u56fe\u5c42\u6570\u91cf"
_RENDER_SUMMARY = "\u6e32\u67d3\u6458\u8981"
_TEMPLATE_SUMMARY = "\u6a21\u677f\u6458\u8981"
_UNKNOWN_RENDER = "\u672a\u63d0\u4f9b"
_NO_PREVIEW_HTML = (
    "\u6682\u65e0\u9884\u89c8 HTML\uff0c\u5b8c\u6210\u4e00\u6b21"
    "\u670d\u52a1\u7aef\u9884\u89c8\u540e\u4f1a\u663e\u793a\u5728\u8fd9\u91cc\u3002"
)
_REFRESH_PREVIEW_FRAME = "\u5237\u65b0\u771f\u5b9e\u9884\u89c8\u5e27"
_SAVE_MY_TEMPLATE = "\u4fdd\u5b58\u4e3a\u6211\u7684\u6a21\u677f"


def render_layout_preview_workbench(
    *,
    spec_payload: LayeredTemplateSpec | Mapping[str, Any] | None,
    recent_presets: Sequence[Mapping[str, Any] | object] | None = None,
    preview_html: TrustedPreviewHTML | str | None = None,
    real_preview_frame: Mapping[str, Any] | object | None = None,
    render_summary: str | None = None,
    template_summary: str | None = None,
    on_preset_selected: PresetSelectionCallback | None = None,
    key_suffix: str = "",
    ui=st,
) -> PresetSelection | None:
    """Render the right-column layout preview workbench.

    The workbench is deliberately driven by explicit payloads. It may use
    session_state to surface a button click, but it does not treat Streamlit
    session_state, template_params, or ad-hoc HTML as layout facts.
    """

    spec = _coerce_spec(spec_payload)
    presets = _recent_presets(recent_presets)
    selected_action: PresetSelection | None = (
        _consume_action(ui=ui, key_suffix=key_suffix) if spec is not None else None
    )
    selected_preset = _consume_pending_selection(ui=ui, presets=presets)
    if selected_preset is not None and on_preset_selected is not None:
        on_preset_selected(selected_preset)

    with ui.container():
        ui.markdown(_build_workbench_header_html(), unsafe_allow_html=True)
        if spec is not None:
            rendered_action = _render_workbench_actions(ui=ui, key_suffix=key_suffix)
            if selected_action is None:
                selected_action = rendered_action
        _render_recent_presets(
            ui=ui,
            presets=presets,
            key_suffix=key_suffix,
        )
        if selected_preset is None:
            selected_preset = _consume_pending_selection(ui=ui, presets=presets)
            if selected_preset is not None and on_preset_selected is not None:
                on_preset_selected(selected_preset)

        ui.markdown(
            _build_summary_html(
                spec=spec,
                render_summary=render_summary,
                template_summary=template_summary,
            ),
            unsafe_allow_html=True,
        )
        _render_preview_container(
            ui=ui,
            spec=spec,
            preview_html=preview_html,
            real_preview_frame=real_preview_frame,
        )

    return selected_action or selected_preset


def _render_workbench_actions(*, ui, key_suffix: str) -> PresetSelection | None:
    refresh_clicked = ui.button(
        _REFRESH_PREVIEW_FRAME,
        key=_action_button_key("refresh_preview_frame", key_suffix=key_suffix),
    )
    save_clicked = ui.button(
        _SAVE_MY_TEMPLATE,
        key=_action_button_key("save_template", key_suffix=key_suffix),
    )
    if refresh_clicked:
        return {"action": "refresh_preview_frame"}
    if save_clicked:
        return {"action": "save_template"}
    return None


def _consume_action(*, ui, key_suffix: str) -> PresetSelection | None:
    action_keys = {
        _action_button_key("refresh_preview_frame", key_suffix=key_suffix): "refresh_preview_frame",
        _action_button_key("save_template", key_suffix=key_suffix): "save_template",
        "layout_preview_refresh_preview_frame": "refresh_preview_frame",
        "layout_preview_save_template": "save_template",
    }
    for key, action in action_keys.items():
        if ui.session_state.get(key):
            return {"action": action}
    return None


def _render_recent_presets(
    *,
    ui,
    presets: list[dict[str, Any]],
    key_suffix: str,
) -> None:
    if not presets:
        _caption(ui, _NO_RECENT)
        return

    items = "".join(
        "<li>"
        f"<span>{escape(preset['label'])}</span>"
        f"<small>{escape(preset['preset_id'])}</small>"
        "</li>"
        for preset in presets
    )
    ui.markdown(
        f"""
        <section class="layout-workbench-card">
          <div class="layout-workbench-section-title">{_RECENT_TITLE}</div>
          <ol class="layout-workbench-recent">{items}</ol>
        </section>
        """,
        unsafe_allow_html=True,
    )
    for preset in presets:
        preset_id = str(preset["preset_id"])
        if ui.button(
            f"{_APPLY_PREFIX} {preset['label']}",
            key=_recent_preset_button_key(preset_id, key_suffix=key_suffix),
            help=_APPLY_HELP,
        ):
            ui.session_state[_PENDING_SELECTION_SESSION_KEY] = preset_id


def _build_workbench_header_html() -> str:
    return f"""
    <style>
      .layout-workbench-shell {{
        border: 1px solid #d8d2c4;
        border-radius: 8px;
        padding: 10px 12px 8px;
        background: linear-gradient(135deg, #fffaf0 0%, #f6efe1 52%, #edf2e8 100%);
        box-shadow: 0 10px 24px rgba(67, 54, 32, 0.08);
      }}
      .layout-workbench-kicker {{
        color: #74624a;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: .1em;
        text-transform: uppercase;
      }}
      .layout-workbench-title {{
        color: #241d16;
        font-size: 18px;
        font-weight: 800;
        line-height: 1.2;
        margin: 2px 0 4px;
      }}
      .layout-workbench-copy {{
        color: #675b4b;
        font-size: 13px;
        line-height: 1.45;
        margin: 0 0 8px;
      }}
      .layout-workbench-card {{
        border: 1px solid rgba(80, 67, 44, .16);
        border-radius: 8px;
        margin: 8px 0;
        padding: 10px 12px;
        background: rgba(255, 255, 255, .62);
      }}
      .layout-workbench-section-title {{
        color: #352a1f;
        font-weight: 800;
        font-size: 13px;
        margin-bottom: 6px;
      }}
      .layout-workbench-recent {{
        display: grid;
        gap: 4px;
        margin: 0;
        padding-left: 20px;
      }}
      .layout-workbench-recent li span {{
        color: #251f18;
        font-weight: 700;
      }}
      .layout-workbench-recent li small {{
        color: #887b68;
        margin-left: 8px;
      }}
      .layout-workbench-grid {{
        display: grid;
        gap: 8px;
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }}
      .layout-workbench-metric {{
        border-left: 4px solid #b98242;
        border-radius: 8px;
        padding: 8px 10px;
        background: #fffdf8;
      }}
      .layout-workbench-label {{
        color: #756854;
        font-size: 11px;
        font-weight: 700;
      }}
      .layout-workbench-value {{
        color: #211a13;
        font-size: 16px;
        font-weight: 850;
      }}
      .layout-workbench-preview-card {{
        border: 1px solid rgba(80, 67, 44, .16);
        border-radius: 8px;
        margin: 8px 0 0;
        padding: 10px 12px;
        background: rgba(255, 255, 255, .68);
      }}
      .layout-workbench-preview-frame {{
        width: 100%;
        height: 320px;
        max-height: 42vh;
        border-radius: 8px;
        overflow: hidden;
        background: linear-gradient(180deg, #f6f1e6 0%, #ece4d6 100%);
        display: flex;
        align-items: center;
        justify-content: center;
      }}
      .layout-workbench-real-preview {{
        display: block;
        width: 100%;
        height: 100%;
        object-fit: contain;
        background: #f8f4ea;
      }}
      .layout-workbench-empty-preview {{
        height: 180px;
        min-height: 0;
        text-align: center;
        color: #6d624f;
        font-size: 13px;
        line-height: 1.5;
        padding: 0 20px;
      }}
      .layout-workbench-preview-meta {{
        color: #857963;
        font-size: 11px;
        margin-top: 6px;
        word-break: break-all;
      }}
      @media (max-width: 720px) {{
        .layout-workbench-grid {{ grid-template-columns: 1fr; }}
      }}
    </style>
    <section class="layout-workbench-shell">
      <div class="layout-workbench-kicker">{_KICKER}</div>
      <div class="layout-workbench-title">{_TITLE}</div>
      <p class="layout-workbench-copy">{_DESCRIPTION}</p>
    </section>
    """


def _build_summary_html(
    *,
    spec: LayeredTemplateSpec | None,
    render_summary: str | None,
    template_summary: str | None,
) -> str:
    if spec is None:
        return f"""
        <section class="layout-workbench-card">
          <div class="layout-workbench-section-title">{_CURRENT_SPEC}</div>
          <p class="layout-workbench-copy">{_NO_SPEC}</p>
        </section>
        """

    resolved_render_summary = render_summary or str(
        spec.metadata.get("render_summary")
        or spec.metadata.get("render_backend")
        or _UNKNOWN_RENDER
    )
    resolved_template_summary = template_summary or (
        f"{spec.template_name} / {spec.template_type}"
    )
    return f"""
    <section class="layout-workbench-card">
      <div class="layout-workbench-section-title">{_CURRENT_SPEC}</div>
      <div class="layout-workbench-grid">
        {_metric_html(_CANVAS_SIZE, f"{spec.canvas_width} x {spec.canvas_height}")}
        {_metric_html(_MEDIA_SIZE, f"{spec.media_width} x {spec.media_height}")}
        {_metric_html(_LAYER_COUNT, str(len(spec.layers)))}
      </div>
      <p class="layout-workbench-copy"><strong>{_RENDER_SUMMARY}: </strong>{escape(resolved_render_summary)}</p>
      <p class="layout-workbench-copy"><strong>{_TEMPLATE_SUMMARY}: </strong>{escape(resolved_template_summary)}</p>
    </section>
    """


def _metric_html(label: str, value: str) -> str:
    return f"""
    <div class="layout-workbench-metric">
      <div class="layout-workbench-label">{escape(label)}</div>
      <div class="layout-workbench-value">{escape(value)}</div>
    </div>
    """


def _render_preview_container(
    *,
    ui,
    spec: LayeredTemplateSpec | None,
    preview_html: TrustedPreviewHTML | str | None,
    real_preview_frame: Mapping[str, Any] | object | None,
) -> None:
    preview_url = _real_preview_frame_url(real_preview_frame)
    preview_fingerprint = _real_preview_frame_fingerprint(real_preview_frame)
    trusted_preview_html = preview_html.html if isinstance(preview_html, TrustedPreviewHTML) else None
    if preview_url:
        ui.markdown(
            _build_real_preview_frame_html(
                preview_url=preview_url,
                preview_fingerprint=preview_fingerprint,
            ),
            unsafe_allow_html=True,
        )
        return
    if spec is not None and len(spec.layers) == 0:
        ui.markdown(_build_empty_preview_html(), unsafe_allow_html=True)
        return
    if trusted_preview_html:
        components.html(trusted_preview_html, height=320, scrolling=True)
        return
    _info(ui, _NO_PREVIEW_HTML)


def _build_real_preview_frame_html(
    *,
    preview_url: str,
    preview_fingerprint: str | None,
) -> str:
    meta = ""
    if preview_fingerprint:
        meta = (
            '<div class="layout-workbench-preview-meta">'
            f"{escape(preview_fingerprint)}"
            "</div>"
        )
    return f"""
    <section class="layout-workbench-preview-card">
      <div class="layout-workbench-section-title">真实预览帧</div>
      <div class="layout-workbench-preview-frame">
        <img
          class="layout-workbench-real-preview"
          src="{escape(preview_url, quote=True)}"
          alt="真实预览帧"
          loading="lazy"
        />
      </div>
      {meta}
    </section>
    """


def _build_empty_preview_html() -> str:
    return """
    <section class="layout-workbench-preview-card">
      <div class="layout-workbench-section-title">即时预览</div>
      <div class="layout-workbench-preview-frame layout-workbench-empty-preview">
        <div>当前模板还没有图层</div>
      </div>
    </section>
    """


def _real_preview_frame_url(frame: Mapping[str, Any] | object | None) -> str | None:
    if frame is None:
        return None
    url = _read_field(frame, "url")
    if url is None:
        return None
    candidate = str(url).strip()
    return candidate or None


def _real_preview_frame_fingerprint(frame: Mapping[str, Any] | object | None) -> str | None:
    if frame is None:
        return None
    fingerprint = _read_field(frame, "fingerprint")
    if fingerprint is None:
        return None
    candidate = str(fingerprint).strip()
    return candidate or None


def _coerce_spec(
    spec_payload: LayeredTemplateSpec | Mapping[str, Any] | None,
) -> LayeredTemplateSpec | None:
    if spec_payload is None:
        return None
    if isinstance(spec_payload, LayeredTemplateSpec):
        return spec_payload
    try:
        return LayeredTemplateSpec.from_dict(spec_payload)
    except (KeyError, TypeError, ValueError):
        return None


def _recent_presets(
    recent_presets: Sequence[Mapping[str, Any] | object] | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in list(recent_presets or []):
        preset_id = _read_field(item, "preset_id") or _read_field(item, "id")
        if not preset_id:
            continue
        spec = _coerce_spec(_read_field(item, "spec") or _read_field(item, "spec_payload"))
        if spec is None:
            continue
        label = (
            _read_field(item, "template_name")
            or _read_field(item, "name")
            or _read_field(item, "label")
            or preset_id
        )
        normalized.append(
            {
                "preset_id": str(preset_id),
                "label": str(label),
                "last_used_at": _read_field(item, "last_used_at"),
                "spec_payload": spec.to_dict(),
            }
        )
    normalized.sort(key=_recent_sort_key, reverse=True)
    return normalized[:5]


def _consume_pending_selection(*, ui, presets: list[dict[str, Any]]) -> PresetSelection | None:
    selected_preset_id = ui.session_state.get(_PENDING_SELECTION_SESSION_KEY)
    if not selected_preset_id:
        return None
    ui.session_state.pop(_PENDING_SELECTION_SESSION_KEY, None)
    for preset in presets:
        if preset["preset_id"] == selected_preset_id:
            return {
                "preset_id": preset["preset_id"],
                "spec_payload": preset["spec_payload"],
            }
    return None


def _recent_sort_key(preset: Mapping[str, Any]) -> float:
    value = preset.get("last_used_at")
    normalized = _normalize_recent_timestamp(value)
    return normalized.timestamp() if normalized is not None else float("-inf")


def _normalize_recent_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _recent_preset_button_key(preset_id: str, *, key_suffix: str) -> str:
    digest = hashlib.sha1(str(preset_id).encode("utf-8")).hexdigest()[:12]
    return f"layout_preview_recent_preset_{digest}{key_suffix}"


def _action_button_key(action: str, *, key_suffix: str) -> str:
    return f"layout_preview_{action}{key_suffix}"


def trust_preview_html(value: str | None) -> TrustedPreviewHTML | None:
    if value is None:
        return None
    return TrustedPreviewHTML(html=str(value))


def _caption(ui, value: str) -> None:
    caption = getattr(ui, "caption", None)
    if callable(caption):
        caption(value)
        return
    ui.markdown(value)


def _info(ui, value: str) -> None:
    ui.markdown(value)


def _read_field(item: Mapping[str, Any] | object, field: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(field)
    return getattr(item, field, None)


__all__ = [
    "render_layout_preview_workbench",
    "trust_preview_html",
]
