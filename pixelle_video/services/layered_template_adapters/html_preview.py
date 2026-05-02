from __future__ import annotations

from html import escape
from typing import Any, Mapping

from pixelle_video.models.layered_template import LayeredTemplateSpec, TemplateLayer


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
            layer=layer,
            title_text=title_text,
            caption_text=caption_text,
            text_rendering=text_rendering,
        )
        for layer in sorted(spec.layers, key=lambda item: (item.z_index, item.id))
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
    layer: TemplateLayer,
    title_text: str,
    caption_text: str,
    text_rendering: Mapping[str, Any],
) -> str:
    css = _layer_css(layer)
    attributes = (
        f'data-layer-id="{escape(layer.id, quote=True)}" '
        f'data-layer-type="{escape(layer.type, quote=True)}"'
    )
    if layer.type == "text":
        text = title_text if layer.role == "title" else caption_text
        return (
            f'    <div class="pixelle-layer pixelle-text-layer" {attributes} '
            f'style="{css}{_text_style_css(layer=layer, text_rendering=text_rendering)}">'
            f"{escape(text)}</div>"
        )
    return f'    <div class="pixelle-layer" {attributes} style="{css}{_source_style_css(layer)}"></div>'


def _layer_css(layer: TemplateLayer) -> str:
    rect = layer.rect
    return (
        f"left:{_px(rect.x)};"
        f"top:{_px(rect.y)};"
        f"width:{_px(rect.width)};"
        f"height:{_px(rect.height)};"
        f"z-index:{int(layer.z_index)};"
        f"opacity:{layer.opacity:.6g};"
        f"transform:rotate({layer.rotation:.6g}deg);"
    )


def _source_style_css(layer: TemplateLayer) -> str:
    background_color = layer.style.get("background_color")
    if background_color is None and layer.source and layer.source.kind == "color":
        background_color = layer.source.ref
    if background_color:
        return f"background:{escape(str(background_color), quote=True)};"
    return ""


def _text_style_css(
    *,
    layer: TemplateLayer,
    text_rendering: Mapping[str, Any],
) -> str:
    style = {}
    role_style = "title_style" if layer.role == "title" else "caption_style"
    configured_style = text_rendering.get(role_style)
    if isinstance(configured_style, Mapping):
        style.update(configured_style)
    style.update(layer.style)

    css = []
    font_size = style.get("font_size")
    if font_size:
        css.append(f"font-size:{int(font_size)}px;")
    color = style.get("primary_color") or style.get("color")
    if color:
        css.append(f"color:{escape(str(color), quote=True)};")
    alignment = style.get("alignment")
    if alignment in {"left", "center", "right"}:
        css.append(f"text-align:{alignment};justify-content:{_justify_content(str(alignment))};")
    background_color = style.get("background_color")
    if background_color:
        css.append(f"background:{escape(str(background_color), quote=True)};")
    return "".join(css)


def _justify_content(alignment: str) -> str:
    if alignment == "left":
        return "flex-start"
    if alignment == "right":
        return "flex-end"
    return "center"


def _px(value: float) -> str:
    return f"{value:.6g}px"
