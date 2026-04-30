from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from html import escape
from typing import Any, Mapping

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
    if any(token in value.lower() for token in ("\"", "'", "<", ">", "javascript:", "onerror")):
        return None
    return escape(value, quote=True)


def _style_css(style: Mapping[str, Any], region: Mapping[str, float]) -> str:
    font_size = int(style.get("font_size") or 42)
    color = escape(str(style.get("primary_color") or "#FFFFFF"), quote=True)
    stroke_color = escape(str(style.get("stroke_color") or "#000000"), quote=True)
    stroke_width = int(style.get("stroke_width") or 0)
    background_color = style.get("background_color")
    background_opacity = float(style.get("background_opacity") or 0.0)
    background = "transparent"
    if background_color and background_opacity > 0:
        background = escape(str(background_color), quote=True)
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
    media_box = calculate_media_box(
        canvas_width=spec.canvas_width,
        canvas_height=spec.canvas_height,
        media_source_width=spec.media_width,
        media_source_height=spec.media_height,
        placement=spec.media_placement,
    )
    canvas_width = max(float(spec.canvas_width), 1.0)
    canvas_height = max(float(spec.canvas_height), 1.0)
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
