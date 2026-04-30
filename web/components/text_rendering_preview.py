from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from html import escape
from math import isfinite
from typing import Any, Mapping

import httpx
import streamlit as st

from pixelle_video.models.media_placement import calculate_media_box
from pixelle_video.models.template_text_style_presets import (
    resolve_template_text_style_preset,
)
from web.i18n import tr

PREVIEW_STYLE_IGNORED_KEYS = {
    "preview_title_text",
    "preview_caption_text",
    "preview_media_ref",
}
SAFE_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
SAFE_MEDIA_REF_RE = re.compile(
    r"^(?:https?://[^\s\"'<>]+|/[A-Za-z0-9._/-]*|artifacts/[A-Za-z0-9._/-]+|[A-Za-z0-9._/-]+)$"
)


@dataclass(frozen=True)
class TextRenderingPreviewSpec:
    template_id: str
    render_backend: str | None
    canvas_width: int
    canvas_height: int
    media_width: int
    media_height: int
    media_placement: dict[str, Any]
    preview_media_ref: str | None
    placeholder_media: bool
    title_text: str
    caption_text: str
    title_style: dict[str, Any]
    caption_style: dict[str, Any]
    template_title_region: dict[str, float]
    template_caption_safe_area: dict[str, float]
    fingerprint: str = field(default="")


def _clean_style(style: Mapping[str, Any] | None) -> dict[str, Any]:
    if not style:
        return {}
    return {
        str(key): value
        for key, value in style.items()
        if key not in PREVIEW_STYLE_IGNORED_KEYS and value is not None
    }


def preview_spec_fingerprint(spec: TextRenderingPreviewSpec | Mapping[str, Any]) -> str:
    payload = spec.__dict__ if isinstance(spec, TextRenderingPreviewSpec) else dict(spec)
    payload = {key: value for key, value in payload.items() if key != "fingerprint"}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def build_text_rendering_preview_spec(
    *,
    template_id: str,
    render_backend: str | None,
    canvas_width: int,
    canvas_height: int,
    media_width: int,
    media_height: int,
    media_placement: Mapping[str, Any] | None = None,
    preview_media_ref: str | None = None,
    title_text: str | None = None,
    caption_text: str | None = None,
    title_style: Mapping[str, Any] | None = None,
    caption_style: Mapping[str, Any] | None = None,
    **_ignored: Any,
) -> TextRenderingPreviewSpec:
    preset = resolve_template_text_style_preset(template_id)
    normalized_preview_media_ref = str(preview_media_ref).strip() if preview_media_ref else None
    spec = TextRenderingPreviewSpec(
        template_id=str(template_id),
        render_backend=str(render_backend) if render_backend is not None else None,
        canvas_width=int(canvas_width),
        canvas_height=int(canvas_height),
        media_width=int(media_width),
        media_height=int(media_height),
        media_placement=dict(media_placement or {}),
        preview_media_ref=normalized_preview_media_ref,
        placeholder_media=normalized_preview_media_ref is None,
        title_text=str(title_text or ""),
        caption_text=str(caption_text or ""),
        title_style=_clean_style(title_style),
        caption_style=_clean_style(caption_style),
        template_title_region=preset.title_region_dict(),
        template_caption_safe_area=preset.caption_safe_area_dict(),
    )
    return TextRenderingPreviewSpec(**{**spec.__dict__, "fingerprint": preview_spec_fingerprint(spec)})


def _safe_media_ref(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not SAFE_MEDIA_REF_RE.match(cleaned):
        return None
    if ".." in cleaned.split("/"):
        return None
    return escape(cleaned, quote=True)


def _safe_color(value: Any, default: str | None) -> str | None:
    cleaned = str(value or "").strip()
    if SAFE_COLOR_RE.fullmatch(cleaned):
        return cleaned
    return default


def _safe_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        float_value = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not isfinite(float_value):
        return default
    numeric_value = int(float_value)
    return min(max(numeric_value, minimum), maximum)


def _safe_float(value: Any, default: float, *, minimum: float, maximum: float) -> float:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not isfinite(numeric_value):
        return default
    return min(max(numeric_value, minimum), maximum)


def _style_css(style: Mapping[str, Any], region: Mapping[str, float]) -> str:
    font_size = _safe_int(style.get("font_size"), 42, minimum=8, maximum=240)
    color = _safe_color(style.get("primary_color"), "#FFFFFF")
    stroke_color = _safe_color(style.get("stroke_color"), "#000000")
    stroke_width = _safe_int(style.get("stroke_width"), 0, minimum=0, maximum=16)
    background_color = _safe_color(style.get("background_color"), None)
    background_opacity = _safe_float(
        style.get("background_opacity"),
        0.0,
        minimum=0.0,
        maximum=1.0,
    )
    background = "transparent"
    if background_color and background_opacity > 0:
        background = background_color
    return (
        f"left:{float(region.get('x', 0.0)) * 100:.3f}%;"
        f"top:{float(region.get('y', 0.0)) * 100:.3f}%;"
        f"width:{float(region.get('width', 1.0)) * 100:.3f}%;"
        f"height:{float(region.get('height', 0.16)) * 100:.3f}%;"
        f"font-size:{font_size}px;"
        f"color:{color};"
        f"background:{background};"
        f"opacity:{background_opacity if background != 'transparent' else 1.0};"
        f"-webkit-text-stroke:{stroke_width}px {stroke_color};"
    )


def _media_box_css(spec: TextRenderingPreviewSpec) -> str:
    try:
        media_box = calculate_media_box(
            canvas_width=spec.canvas_width,
            canvas_height=spec.canvas_height,
            media_source_width=spec.media_width,
            media_source_height=spec.media_height,
            placement=spec.media_placement,
        )
        canvas_width = float(spec.canvas_width)
        canvas_height = float(spec.canvas_height)
    except (TypeError, ValueError):
        return "left:0.000%;top:0.000%;width:100.000%;height:100.000%;"
    return (
        f"left:{media_box.left / canvas_width * 100:.3f}%;"
        f"top:{media_box.top / canvas_height * 100:.3f}%;"
        f"width:{media_box.width / canvas_width * 100:.3f}%;"
        f"height:{media_box.height / canvas_height * 100:.3f}%;"
    )


def render_preview_html(spec: TextRenderingPreviewSpec) -> str:
    media_ref = _safe_media_ref(spec.preview_media_ref)
    media_layer = (
        f'<img src="{media_ref}" alt="" />'
        if media_ref
        else '<div class="text-rendering-preview__media-placeholder"></div>'
    )
    aspect_ratio = max(spec.canvas_width, 1) / max(spec.canvas_height, 1)
    return f"""
<div class="text-rendering-preview" data-fingerprint="{escape(spec.fingerprint, quote=True)}"
     style="aspect-ratio:{aspect_ratio:.6f};">
  <div class="text-rendering-preview__layer text-rendering-preview__media" data-layer="media"
       style="{_media_box_css(spec)}">
    {media_layer}
  </div>
  <div class="text-rendering-preview__layer text-rendering-preview__title" data-layer="title"
       style="{_style_css(spec.title_style, spec.template_title_region)}">
    {escape(spec.title_text)}
  </div>
  <div class="text-rendering-preview__layer text-rendering-preview__caption" data-layer="caption"
       style="{_style_css(spec.caption_style, spec.template_caption_safe_area)}">
    {escape(spec.caption_text)}
  </div>
</div>
<style>
.text-rendering-preview {{
  position: relative;
  width: 100%;
  overflow: hidden;
  border-radius: 12px;
  background: #111827;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.12);
}}
.text-rendering-preview__layer {{
  position: absolute;
  box-sizing: border-box;
}}
.text-rendering-preview__media {{
  display: grid;
  place-items: center;
}}
.text-rendering-preview__media img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
}}
.text-rendering-preview__media-placeholder {{
  width: 100%;
  height: 100%;
  background:
    linear-gradient(135deg, rgba(255,255,255,.16), rgba(255,255,255,.02)),
    repeating-linear-gradient(45deg, rgba(255,255,255,.06) 0 10px, transparent 10px 20px);
}}
.text-rendering-preview__title,
.text-rendering-preview__caption {{
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.2%;
  text-align: center;
  line-height: 1.16;
  word-break: break-word;
}}
</style>
"""


def render_text_rendering_preview(
    spec: TextRenderingPreviewSpec,
    *,
    ui: Any | None = None,
    translate=None,
) -> None:
    ui = ui or st
    translate = translate or tr
    ui.markdown(f"**{translate('text_rendering_preview.title')}**")
    caption = getattr(ui, "caption", None)
    if caption is not None:
        caption(translate("text_rendering_preview.instant_notice"))
    ui.markdown(render_preview_html(spec), unsafe_allow_html=True)


def build_real_preview_state(
    storage_key: str | None,
    url: str | None,
    fingerprint: str | None,
    error: str | None,
    frame_fingerprint: str | None = None,
) -> dict[str, Any]:
    state = {
        "storage_key": storage_key,
        "url": url,
        "fingerprint": fingerprint,
        "error": error,
    }
    if frame_fingerprint is not None:
        state["frame_fingerprint"] = frame_fingerprint
    return state


def is_real_preview_stale(
    state: Mapping[str, Any] | None,
    fingerprint: str,
) -> bool:
    if not state:
        return True
    return state.get("fingerprint") != fingerprint


def render_real_preview_status(
    spec: TextRenderingPreviewSpec,
    state: Mapping[str, Any] | None,
    ui: Any,
    translate,
) -> None:
    if state and state.get("url") and not is_real_preview_stale(state, spec.fingerprint):
        image = getattr(ui, "image", None)
        if image is not None:
            image(state["url"], caption=translate("text_rendering_preview.real_current"))
        return
    if state and state.get("url"):
        caption = getattr(ui, "caption", None)
        if caption is not None:
            caption(translate("text_rendering_preview.real_stale"))
    if state and state.get("error"):
        error = getattr(ui, "error", None)
        if error is not None:
            error(translate("text_rendering_preview.real_failed", error=state["error"]))


def _http_status_error_message(exc: httpx.HTTPStatusError) -> str:
    response = exc.response
    try:
        detail = response.json().get("detail")
    except Exception:
        detail = None
    if detail:
        return str(detail)
    if response.text:
        return response.text
    return str(exc)


def request_real_preview_frame(
    spec: TextRenderingPreviewSpec,
    text_rendering_payload: Mapping[str, Any],
    api_base_url: str,
    workspace_id: str,
) -> dict[str, Any]:
    endpoint = f"{api_base_url.rstrip('/')}/text-rendering/preview-frame"
    payload: dict[str, Any] = {
        "workspace_id": workspace_id,
        "template_id": spec.template_id,
        "render_backend": spec.render_backend,
        "canvas_width": spec.canvas_width,
        "canvas_height": spec.canvas_height,
        "media_width": spec.media_width,
        "media_height": spec.media_height,
        "media_placement": spec.media_placement,
        "title_text": spec.title_text,
        "caption_text": spec.caption_text,
        "text_rendering": dict(text_rendering_payload),
    }
    preview_media_ref = str(spec.preview_media_ref or "").strip()
    if preview_media_ref.startswith("artifacts/"):
        payload["preview_media_storage_key"] = preview_media_ref

    try:
        response = httpx.post(endpoint, json=payload, timeout=60.0)
        response.raise_for_status()
        data = response.json()
        return build_real_preview_state(
            storage_key=data.get("storage_key"),
            url=data.get("url"),
            fingerprint=spec.fingerprint,
            error=None,
            frame_fingerprint=data.get("fingerprint"),
        )
    except httpx.HTTPStatusError as exc:
        return build_real_preview_state(
            storage_key=None,
            url=None,
            fingerprint=spec.fingerprint,
            error=_http_status_error_message(exc),
        )
    except Exception as exc:
        return build_real_preview_state(
            storage_key=None,
            url=None,
            fingerprint=spec.fingerprint,
            error=str(exc),
        )
