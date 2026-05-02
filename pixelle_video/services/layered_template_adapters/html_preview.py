from __future__ import annotations

import html
import re
from pathlib import PurePosixPath
from typing import Any, Mapping
from urllib.parse import unquote

from pixelle_video.models.layered_template import LayeredTemplateSpec, TemplateLayer
from pixelle_video.services.text_style_preview_css import (
    TextPreviewRegion,
    render_text_style_preview_css,
    text_preview_lines,
)

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?$")


def render_layered_template_preview_html(
    *,
    spec: LayeredTemplateSpec,
    title_text: str = "",
    caption_text: str = "",
    text_rendering: Mapping[str, Any] | None = None,
) -> str:
    """Render a safe HTML preview from LayeredTemplateSpec only."""
    resolved_text_rendering = text_rendering or {}
    layers = "\n".join(
        _render_layer(
            layer,
            title_text=title_text,
            caption_text=caption_text,
            text_rendering=resolved_text_rendering,
            canvas_width=spec.canvas_width,
            canvas_height=spec.canvas_height,
        )
        for _, layer in sorted(enumerate(spec.layers), key=lambda item: (item[1].z_index, item[0]))
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        "<style>"
        "html,body{margin:0;padding:0;background:#111;}"
        ".layered-template-preview{position:relative;overflow:hidden;margin:0 auto;"
        "font-family:Arial,sans-serif;}"
        ".layer{position:absolute;box-sizing:border-box;overflow:hidden;}"
        ".text-layer{display:flex;white-space:pre-wrap;line-height:1.18;}"
        ".media-layer{display:flex;align-items:center;justify-content:center;background:#222;color:#aaa;}"
        ".media-layer img{width:100%;height:100%;object-fit:cover;display:block;}"
        "</style></head><body>"
        f'<div class="layered-template-preview" style="width:{spec.canvas_width}px;'
        f"height:{spec.canvas_height}px;aspect-ratio:{spec.canvas_width} / {spec.canvas_height};"
        '">'
        f"{layers}</div></body></html>"
    )


def _render_layer(
    layer: TemplateLayer,
    *,
    title_text: str,
    caption_text: str,
    text_rendering: Mapping[str, Any],
    canvas_width: int,
    canvas_height: int,
) -> str:
    attrs = (
        f'data-layer-id="{_escape_attr(layer.id)}" '
        f'data-layer-type="{_escape_attr(layer.type)}" '
        f'data-role="{_escape_attr(layer.role or "")}"'
    )
    style = _base_style(layer)
    if layer.type == "background":
        return f'<div class="layer background-layer" {attrs} style="{style}{_background_style(layer)}"></div>'
    if layer.type in {"image", "generated_media"}:
        return _render_media_layer(layer, attrs=attrs, style=style)
    if layer.type == "text":
        return _render_text_layer(
            layer,
            attrs=attrs,
            style=style,
            title_text=title_text,
            caption_text=caption_text,
            text_rendering=text_rendering,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )
    return f'<div class="layer" {attrs} style="{style}"></div>'


def _base_style(layer: TemplateLayer) -> str:
    rect = layer.rect
    return (
        f"left:{_px(rect.x)};top:{_px(rect.y)};width:{_px(rect.width)};height:{_px(rect.height)};"
        f"z-index:{layer.z_index};opacity:{_number(layer.opacity)};"
        f"transform:rotate({_number(layer.rotation)}deg);"
    )


def _background_style(layer: TemplateLayer) -> str:
    color = "#000000"
    if layer.source and layer.source.kind == "color":
        color = _safe_color(layer.source.ref, "#000000")
    elif layer.source and layer.source.kind == "gradient":
        color = _safe_gradient(layer.source.ref)
    return f"background:{color};"


def _render_media_layer(layer: TemplateLayer, *, attrs: str, style: str) -> str:
    if layer.type == "image" and layer.source and layer.source.kind == "asset":
        ref = _safe_asset_ref(layer.source.ref)
        if ref:
            return (
                f'<div class="layer media-layer" {attrs} style="{style}">'
                f'<img alt="" src="{_escape_attr(ref)}"></div>'
            )
    label = "generated media" if layer.type == "generated_media" else "image"
    return f'<div class="layer media-layer" {attrs} style="{style}">{html.escape(label)}</div>'


def _render_text_layer(
    layer: TemplateLayer,
    *,
    attrs: str,
    style: str,
    title_text: str,
    caption_text: str,
    text_rendering: Mapping[str, Any],
    canvas_width: int,
    canvas_height: int,
) -> str:
    text = _text_for_layer(layer, title_text=title_text, caption_text=caption_text)
    text_style = _resolve_text_style(layer, text_rendering)
    rendered_text = "<br/>".join(
        html.escape(line, quote=True)
        for line in text_preview_lines(text, text_style)
    )
    layer_style = _text_style(
        layer,
        text_style,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
    )
    return (
        f'<div class="layer text-layer" {attrs} style="{style}{layer_style}">'
        f"{rendered_text}</div>"
    )


def _text_style(
    layer: TemplateLayer,
    style: Mapping[str, Any],
    *,
    canvas_width: int,
    canvas_height: int,
) -> str:
    return render_text_style_preview_css(
        style,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        region=TextPreviewRegion(
            x=layer.rect.x,
            y=layer.rect.y,
            width=layer.rect.width,
            height=layer.rect.height,
        ),
        units="px",
        default_font_size=48,
        rotation_degrees=layer.rotation,
    )


def _resolve_text_style(
    layer: TemplateLayer,
    text_rendering: Mapping[str, Any],
) -> Mapping[str, Any]:
    if layer.role == "title":
        title_style = text_rendering.get("title_style")
        if isinstance(title_style, Mapping):
            return title_style
        return {}
    if layer.role == "caption":
        caption_style = text_rendering.get("caption_style")
        if isinstance(caption_style, Mapping):
            return caption_style
        return {}
    return layer.style


def _text_for_layer(layer: TemplateLayer, *, title_text: str, caption_text: str) -> str:
    if layer.role == "title":
        return title_text
    if layer.role == "caption":
        return caption_text
    for source in (layer.style, layer.source.metadata if layer.source else {}, layer.source.to_dict() if layer.source else {}):
        for key in ("text", "content", "value", "label"):
            value = source.get(key)
            if value is not None:
                return str(value)
    return ""


def _px(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value)}px"
    return f"{value:.3f}px"


def _number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return min(max(parsed, minimum), maximum)


def _safe_color(value: str, default: str) -> str:
    return value if _HEX_COLOR_RE.fullmatch(value) else default


def _safe_gradient(value: str) -> str:
    if "url(" in value.lower() or "expression(" in value.lower() or "javascript:" in value.lower():
        return "#000000"
    parts = [part.strip() for part in value.split(",")]
    if len(parts) >= 2 and all(part and part == _safe_color(part, "") for part in parts):
        return f"linear-gradient(180deg,{','.join(parts)})"
    return "#000000"


def _safe_asset_ref(value: str) -> str:
    lowered = value.lower().strip()
    if "://" in lowered or lowered.startswith(("javascript:", "data:", "vbscript:", "//")):
        return ""
    if "\\" in value:
        return ""
    decoded = unquote(value)
    if decoded != value:
        return _safe_asset_ref(decoded)
    path = PurePosixPath(value)
    if path.is_absolute():
        return ""
    if any(part in {"", ".", ".."} for part in path.parts):
        return ""
    if not path.parts or path.parts[0] != "assets":
        return ""
    return value


def _escape_attr(value: str) -> str:
    return html.escape(value, quote=True)
