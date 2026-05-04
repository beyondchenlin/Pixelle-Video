from __future__ import annotations

import re
from html import escape
from typing import Any, Mapping

from pixelle_video.models.layered_template import LayeredTemplateSpec, TemplateLayer
from pixelle_video.services.text_style_css_contract import (
    TextStyleRegion,
    render_text_style_css,
    text_style_lines,
)

_HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
_ARTIFACT_KEY_PATTERN = re.compile(r"^artifacts/[A-Za-z0-9_-]+/[0-9A-Za-z][0-9A-Za-z_.-]*$")
_SAFE_URL_PREFIXES = ("http://", "https://", "data:image/", "file://", "/api/files/")


def render_layered_template_preview_html(
    *,
    spec: LayeredTemplateSpec,
    title_text: str,
    caption_text: str,
    text_rendering: Mapping[str, Any],
    fingerprint: str,
) -> str:
    layers_html = "\n".join(
        _render_layer(
            spec=spec,
            layer=layer,
            title_text=title_text,
            caption_text=caption_text,
            text_rendering=text_rendering,
        )
        for layer in sorted(spec.layers, key=lambda item: (item.z_index, item.id))
        if layer.enabled
    )
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="pixelle:layered-template-fingerprint" content="{escape(fingerprint, quote=True)}">
  <style>
    html, body {{
      margin:0;
      width:{spec.canvas_width}px;
      height:{spec.canvas_height}px;
      overflow:hidden;
      background:transparent;
    }}
    .pixelle-layered-template {{
      position:relative;
      width:{spec.canvas_width}px;
      height:{spec.canvas_height}px;
      overflow:hidden;
      font-family:Arial, sans-serif;
    }}
    .pixelle-layer {{
      position:absolute;
      box-sizing:border-box;
      transform-origin:center center;
      overflow:hidden;
    }}
    .pixelle-text-layer {{
      display:flex;
      align-items:center;
      white-space:pre-wrap;
      word-break:break-word;
      line-height:1.1;
    }}
    .pixelle-layer-media {{
      width:100%;
      height:100%;
      display:block;
    }}
    .pixelle-generated-media-placeholder,
    .pixelle-missing-media-placeholder {{
      width:100%;
      height:100%;
      display:flex;
      align-items:center;
      justify-content:center;
      background:#ECEFF3;
      color:#5B6472;
      font-size:24px;
      font-family:Arial, sans-serif;
    }}
  </style>
</head>
<body>
  <div class="pixelle-layered-template" data-template-id="{escape(spec.template_id, quote=True)}">
{layers_html}
  </div>
</body>
</html>"""


def _render_layer(
    *,
    spec: LayeredTemplateSpec,
    layer: TemplateLayer,
    title_text: str,
    caption_text: str,
    text_rendering: Mapping[str, Any],
) -> str:
    css = _layer_css(layer, include_rect=layer.type != "text")
    attributes = (
        f'data-layer-id="{escape(layer.id, quote=True)}" '
        f'data-layer-type="{escape(layer.type, quote=True)}"'
    )
    if layer.type == "text":
        text = _resolve_text_layer_content(
            layer=layer,
            title_text=title_text,
            caption_text=caption_text,
        )
        text = "\n".join(text_style_lines(text, style=layer.style))
        return (
            f'    <div class="pixelle-layer pixelle-text-layer" {attributes} '
            f'style="{css}{_text_style_css(spec=spec, layer=layer, text_rendering=text_rendering)}">'
            f"{escape(text)}</div>"
        )
    if layer.type in {"image", "generated_media"}:
        return _render_media_layer(layer=layer, attributes=attributes, css=css)
    if layer.source and layer.source.kind == "asset":
        return _render_media_layer(
            layer=layer,
            attributes=attributes,
            css=f"{css}{_background_style_css(layer)}",
        )
    return f'    <div class="pixelle-layer" {attributes} style="{css}{_background_style_css(layer)}"></div>'


def _resolve_text_layer_content(
    *,
    layer: TemplateLayer,
    title_text: str,
    caption_text: str,
) -> str:
    text_content = layer.style.get("text_content")
    if isinstance(text_content, str) and text_content:
        return text_content
    if layer.role == "title":
        return title_text
    if layer.role == "caption":
        return caption_text
    return caption_text


def _render_media_layer(*, layer: TemplateLayer, attributes: str, css: str) -> str:
    media_url = _safe_media_url(layer)
    object_fit = _safe_object_fit(layer.style.get("object_fit"))
    media_css = f"object-fit:{object_fit};"
    if media_url:
        return (
            f'    <div class="pixelle-layer" {attributes} style="{css}">'
            f'<img class="pixelle-layer-media" src="{escape(media_url, quote=True)}" '
            f'alt="" style="{media_css}"></div>'
        )
    if layer.source and layer.source.kind == "generated_media":
        source_ref = escape(layer.source.ref, quote=True)
        return (
            f'    <div class="pixelle-layer" {attributes} style="{css}">'
            f'<div class="pixelle-generated-media-placeholder" data-source-ref="{source_ref}">'
            "Generated media</div></div>"
        )
    return (
        f'    <div class="pixelle-layer" {attributes} style="{css}">'
        '<div class="pixelle-missing-media-placeholder">Missing media</div></div>'
    )


def _safe_media_url(layer: TemplateLayer) -> str | None:
    if layer.source is None or layer.source.kind not in {"asset"}:
        return None
    ref = layer.source.ref.strip()
    if ref.startswith("assets/"):
        return f"/api/files/data/template_presets/{ref}"
    if _ARTIFACT_KEY_PATTERN.fullmatch(ref):
        return f"/api/files/{ref}"
    if ref.startswith(_SAFE_URL_PREFIXES):
        return ref
    return None


def _layer_css(layer: TemplateLayer, *, include_rect: bool = True) -> str:
    rect = layer.rect
    css = []
    if include_rect:
        css.extend(
            [
                f"left:{_px(rect.x)};",
                f"top:{_px(rect.y)};",
                f"width:{_px(rect.width)};",
                f"height:{_px(rect.height)};",
            ]
        )
    css.extend(
        [
            f"z-index:{int(layer.z_index)};",
            f"opacity:{layer.opacity:.6g};",
        ]
    )
    if include_rect:
        css.append(f"transform:rotate({layer.rotation:.6g}deg);")
    return "".join(css)


def _background_style_css(layer: TemplateLayer) -> str:
    background_color = layer.style.get("background_color")
    if background_color is None and layer.source and layer.source.kind == "color":
        background_color = layer.source.ref
    if _is_hex_color(background_color):
        return f"background:{background_color};"
    return ""


def _text_style_css(
    *,
    spec: LayeredTemplateSpec,
    layer: TemplateLayer,
    text_rendering: Mapping[str, Any],
) -> str:
    style = {}
    role_style = "title_style" if layer.role == "title" else "caption_style"
    configured_style = text_rendering.get(role_style)
    if isinstance(configured_style, Mapping):
        style.update(configured_style)
    style.update(layer.style)

    return render_text_style_css(
        style,
        canvas_width=spec.canvas_width,
        canvas_height=spec.canvas_height,
        region=TextStyleRegion(
            x=float(layer.rect.x),
            y=float(layer.rect.y),
            width=float(layer.rect.width),
            height=float(layer.rect.height),
        ),
        units="px",
        default_font_size=42,
        rotation_degrees=float(layer.rotation),
    )


def _safe_object_fit(value: Any) -> str:
    if value in {"contain", "cover", "fill", "none", "scale-down"}:
        return str(value)
    return "cover"


def _is_hex_color(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX_COLOR_PATTERN.fullmatch(value))


def _px(value: float) -> str:
    return f"{value:.6g}px"
