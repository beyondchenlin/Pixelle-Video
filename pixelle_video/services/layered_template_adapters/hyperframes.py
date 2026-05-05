from __future__ import annotations

import re
from html import escape
from pathlib import Path
from typing import Any, Mapping

from loguru import logger

from pixelle_video.models.layered_template import LayeredTemplateSpec, TemplateLayer
from pixelle_video.models.render_package import CaptionCue, VisualClip
from pixelle_video.models.template_render_context import TemplateRenderContext
from pixelle_video.models.text_style import TextStyleProfile
from pixelle_video.services.text_content_sanitizer import TextContentSanitizer
from pixelle_video.services.text_style_css_contract import (
    TextStyleRegion,
    render_text_style_css,
    text_style_lines,
)
from pixelle_video.services.text_style_resolver import TextStyleResolver

_HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
_UNSAFE_FONT_CHARS = {'"', "'", ";", ":", "{", "}", "(", ")", "\\", "/"}


class LayeredTemplateHyperFramesAdapter:
    def __init__(
        self,
        *,
        text_sanitizer: TextContentSanitizer | None = None,
    ) -> None:
        self.text_sanitizer = text_sanitizer or TextContentSanitizer()

    def compile(
        self,
        *,
        project_dir: Path,
        context: TemplateRenderContext,
    ) -> None:
        if context.layered_template_spec is None:
            raise ValueError("layered template HyperFrames adapter requires a spec")

        spec = LayeredTemplateSpec.from_dict(context.layered_template_spec)
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "compositions").mkdir(parents=True, exist_ok=True)
        (project_dir / "index.html").write_text(
            self._build_index_html(spec=spec, context=context),
            encoding="utf-8",
        )
        (project_dir / "compositions" / "captions.html").write_text(
            self._build_captions_html(spec=spec, context=context),
            encoding="utf-8",
        )
        (project_dir / "compositions" / "text_layer.html").write_text(
            self._build_text_layer_html(spec=spec, context=context),
            encoding="utf-8",
        )

    def _build_index_html(
        self,
        *,
        spec: LayeredTemplateSpec,
        context: TemplateRenderContext,
    ) -> str:
        layers_html = "\n".join(
            self._render_layer(layer=layer, context=context)
            for layer in sorted(spec.layers, key=lambda item: (item.z_index, item.id))
            if layer.enabled and layer.role != "caption"
        )
        audio_html = self._render_audio(context)
        duration = max(float(context.duration), 0.001)
        return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <style>
      html, body {{
        margin: 0;
        width: {spec.canvas_width}px;
        height: {spec.canvas_height}px;
        overflow: hidden;
        background: transparent;
      }}
      [data-composition-id="main-comp"] {{
        position: relative;
        width: {spec.canvas_width}px;
        height: {spec.canvas_height}px;
        overflow: hidden;
        font-family: sans-serif;
      }}
      .pixelle-layer {{
        position: absolute;
        box-sizing: border-box;
        overflow: hidden;
        transform-origin: center center;
      }}
      .pixelle-layered-text {{
        display: flex;
        align-items: center;
        white-space: pre-wrap;
        word-break: break-word;
        line-height: 1.1;
      }}
      .pixelle-layer-media {{
        width: 100%;
        height: 100%;
        display: block;
      }}
      .pixelle-generated-media-slot {{
        background: transparent;
      }}
    </style>
  </head>
  <body>
    <div
      data-composition-id="main-comp"
      data-width="{spec.canvas_width}"
      data-height="{spec.canvas_height}"
      data-duration="{duration}"
    >
{layers_html}
      <div
        id="text-layer"
        data-composition-id="text-layer"
        data-composition-src="compositions/text_layer.html"
        data-start="0"
        data-duration="{duration}"
        data-track-index="2"
      ></div>
      <div
        id="captions-layer"
        data-composition-id="captions"
        data-composition-src="compositions/captions.html"
        data-start="0"
        data-duration="{duration}"
        data-track-index="3"
      ></div>
{audio_html}
    </div>
    <script src="./runtime/vendor/gsap.min.js"></script>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      const mediaClips = Array.from(document.querySelectorAll("[data-pixelle-layered-clip]"));
      gsap.set(mediaClips, {{ autoAlpha: 0, visibility: "hidden" }});
      mediaClips.forEach((clip) => {{
        const start = Number(clip.dataset.start || 0);
        const duration = Math.max(Number(clip.dataset.duration || 0), 0.001);
        tl.set(clip, {{ autoAlpha: 1, visibility: "visible" }}, start);
        tl.set(clip, {{ autoAlpha: 0, visibility: "hidden" }}, start + duration);
      }});
      window.__timelines["main-comp"] = tl;
    </script>
  </body>
</html>
"""

    def _build_captions_html(
        self,
        *,
        spec: LayeredTemplateSpec,
        context: TemplateRenderContext,
    ) -> str:
        caption_layer = next(
            (
                layer
                for layer in spec.layers
                if layer.enabled and layer.type == "text" and layer.role == "caption"
            ),
            None,
        )
        captions_html = "\n".join(
            self._render_caption_cue(
                cue=cue,
                layer=caption_layer,
                canvas_width=spec.canvas_width,
                canvas_height=spec.canvas_height,
                context=context,
            )
            for cue in context.captions
        )
        duration = max(float(context.duration), 0.001)
        return f"""<template id="captions-template">
  <div
    data-composition-id="captions"
    data-width="{spec.canvas_width}"
    data-height="{spec.canvas_height}"
    data-duration="{duration}"
  >
{captions_html}
    <style>
      [data-composition-id="captions"] {{
        position: relative;
        width: {spec.canvas_width}px;
        height: {spec.canvas_height}px;
        overflow: hidden;
        font-family: sans-serif;
      }}
      .pixelle-layered-caption {{
        position: absolute;
        box-sizing: border-box;
        display: flex;
        align-items: center;
        white-space: pre-wrap;
        word-break: break-word;
        line-height: 1.1;
      }}
    </style>
    <script src="../runtime/vendor/gsap.min.js"></script>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      const captions = Array.from(document.querySelectorAll(".pixelle-layered-caption"));
      gsap.set(captions, {{ autoAlpha: 0, visibility: "hidden" }});
      captions.forEach((caption) => {{
        const start = Number(caption.dataset.start || 0);
        const duration = Math.max(Number(caption.dataset.duration || 0), 0.001);
        tl.set(caption, {{ autoAlpha: 1, visibility: "visible" }}, start);
        tl.set(caption, {{ autoAlpha: 0, visibility: "hidden" }}, start + duration);
      }});
      window.__timelines["captions"] = tl;
    </script>
  </div>
</template>
"""

    def _build_text_layer_html(
        self,
        *,
        spec: LayeredTemplateSpec,
        context: TemplateRenderContext,
    ) -> str:
        duration = max(float(context.duration), 0.001)
        return f"""<template id="text-layer-template">
  <div
    data-composition-id="text-layer"
    data-width="{spec.canvas_width}"
    data-height="{spec.canvas_height}"
    data-duration="{duration}"
  >
    <script src="../runtime/vendor/gsap.min.js"></script>
    <script>
      window.__timelines = window.__timelines || {{}};
      window.__timelines["text-layer"] = gsap.timeline({{ paused: true }});
    </script>
  </div>
</template>
"""

    def _render_layer(
        self,
        *,
        layer: TemplateLayer,
        context: TemplateRenderContext,
    ) -> str:
        if layer.type == "background":
            return self._render_background_layer(layer)
        if layer.type == "text":
            return self._render_text_layer(layer=layer, context=context)
        if layer.type in {"image", "generated_media"}:
            return self._render_media_layer(layer=layer, context=context)
        raise ValueError(f"unsupported layered template layer type: {layer.type} ({layer.id})")

    def _render_background_layer(self, layer: TemplateLayer) -> str:
        source_url = self._asset_source_url(layer)
        if source_url:
            object_fit = self._object_fit(layer)
            return (
                f'      <div class="pixelle-layer" data-layer-id="{escape(layer.id, quote=True)}" '
                f'data-layer-type="{escape(layer.type, quote=True)}" '
                f'style="{self._layer_css(layer)}{self._background_css(layer)}">'
                f'<img class="pixelle-layer-media" src="{escape(source_url, quote=True)}" '
                f'alt="" style="object-fit:{object_fit};" /></div>'
            )
        return (
            f'      <div class="pixelle-layer" data-layer-id="{escape(layer.id, quote=True)}" '
            f'data-layer-type="{escape(layer.type, quote=True)}" '
            f'style="{self._layer_css(layer)}{self._background_css(layer)}"></div>'
        )

    def _render_text_layer(
        self,
        *,
        layer: TemplateLayer,
        context: TemplateRenderContext,
    ) -> str:
        text = self._resolve_text_layer_content(layer=layer, context=context)
        effective_style = self._resolve_effective_title_style(
            layer=layer,
            context=context,
        )
        normalized = "\n".join(text_style_lines(text, style=effective_style))
        display_text = self.text_sanitizer.sanitize(normalized).display_text
        return (
            f'      <div class="pixelle-layer pixelle-layered-text" '
            f'data-layer-id="{escape(layer.id, quote=True)}" '
            f'data-layer-type="{escape(layer.type, quote=True)}" '
            f'style="{self._layer_css(layer, include_rect=False)}{self._text_css_from_style(style=effective_style, layer=layer, canvas_width=context.canvas_width, canvas_height=context.canvas_height)}">'
            f"{escape(display_text)}</div>"
        )

    @staticmethod
    def _resolve_text_layer_content(
        *,
        layer: TemplateLayer,
        context: TemplateRenderContext,
    ) -> str:
        text_content = layer.style.get("text_content")
        if isinstance(text_content, str) and text_content:
            return text_content
        if layer.role == "title":
            return context.title
        if layer.role == "caption":
            return ""
        return ""

    def _render_media_layer(
        self,
        *,
        layer: TemplateLayer,
        context: TemplateRenderContext,
    ) -> str:
        if layer.source is not None and layer.source.kind == "generated_media":
            if layer.source.ref != "generated://primary":
                raise ValueError(f"unsupported generated-media ref: {layer.source.ref}")
            return self._render_generated_media_slot(layer=layer, visuals=context.visuals)

        source_url = self._asset_source_url(layer)
        if not source_url:
            return (
                f'      <div class="pixelle-layer" data-layer-id="{escape(layer.id, quote=True)}" '
                f'data-layer-type="{escape(layer.type, quote=True)}" '
                f'style="{self._layer_css(layer)}"></div>'
            )
        object_fit = self._object_fit(layer)
        return (
            f'      <div class="pixelle-layer" data-layer-id="{escape(layer.id, quote=True)}" '
            f'data-layer-type="{escape(layer.type, quote=True)}" '
            f'style="{self._layer_css(layer)}">'
            f'<img class="pixelle-layer-media" src="{escape(source_url, quote=True)}" '
            f'alt="" style="object-fit:{object_fit};" /></div>'
        )

    def _render_generated_media_slot(
        self,
        *,
        layer: TemplateLayer,
        visuals: list[VisualClip],
    ) -> str:
        object_fit = self._object_fit(layer)
        media_items = "\n".join(
            self._render_visual_clip(clip=clip, object_fit=object_fit)
            for clip in visuals
        )
        return (
            f'      <div class="pixelle-layer pixelle-generated-media-slot" '
            f'data-layer-id="{escape(layer.id, quote=True)}" '
            f'data-layer-type="{escape(layer.type, quote=True)}" '
            f'style="{self._layer_css(layer)}">\n'
            f"{media_items}\n"
            "      </div>"
        )

    def _render_visual_clip(self, *, clip: VisualClip, object_fit: str) -> str:
        duration = max(float(clip.end) - float(clip.start), 0.001)
        escaped_path = escape(clip.media_path, quote=True)
        attrs = (
            f'data-pixelle-layered-clip="true" data-start="{float(clip.start)}" '
            f'data-duration="{duration}" data-track-index="{int(clip.track_index)}"'
        )
        if clip.media_type == "video":
            return (
                f'        <video class="pixelle-layer-media" {attrs} '
                f'src="{escaped_path}" muted playsinline '
                f'style="object-fit:{object_fit};"></video>'
            )
        return (
            f'        <img class="pixelle-layer-media" {attrs} '
            f'src="{escaped_path}" alt="" style="object-fit:{object_fit};" />'
        )

    def _render_caption_cue(
        self,
        *,
        cue: CaptionCue,
        layer: TemplateLayer | None,
        canvas_width: int,
        canvas_height: int,
        context: TemplateRenderContext,
    ) -> str:
        duration = max(float(cue.end) - float(cue.start), 0.001)
        effective_style = self._resolve_effective_caption_style(
            cue=cue,
            layer=layer,
            context=context,
        )
        css = self._layer_css(layer, include_rect=False) + self._text_css_from_style(
            style=effective_style,
            layer=layer,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        ) if layer is not None else (
            "left:0;top:0;width:100%;height:100%;z-index:0;opacity:1;"
            "transform:rotate(0deg);font-size:32px;color:#ffffff;"
            "justify-content:center;text-align:center;"
        )
        text = self.text_sanitizer.sanitize(cue.text).display_text
        return (
            f'      <div id="{escape(cue.id, quote=True)}" '
            f'class="pixelle-layered-caption" data-start="{float(cue.start)}" '
            f'data-duration="{duration}" data-track-index="1" '
            f'style="{css}">{escape(text)}</div>'
        )

    def _render_audio(self, context: TemplateRenderContext) -> str:
        audio_tracks = list(context.audio_tracks)
        if not audio_tracks and context.audio is not None:
            audio_tracks = [context.audio]
        rendered = []
        for track in audio_tracks:
            duration = max(float(track.duration), 0.0)
            rendered.append(
                (
                    f'      <audio id="{escape(track.id, quote=True)}" '
                    f'src="{escape(track.path, quote=True)}" data-start="{float(track.start)}" '
                    f'data-duration="{duration}" data-track-index="{int(track.track_index)}" '
                    f'data-media-start="{float(track.media_start)}" '
                    f'data-volume="{float(track.volume)}" '
                    f'data-role="{escape(track.role, quote=True)}"></audio>'
                )
            )
        return "\n".join(rendered)

    @staticmethod
    def _asset_source_url(layer: TemplateLayer) -> str | None:
        if layer.source is None or layer.source.kind != "asset":
            return None
        return str(layer.source.ref)

    @staticmethod
    def _layer_css(layer: TemplateLayer | None, *, include_rect: bool = True) -> str:
        if layer is None:
            return ""
        rect = layer.rect
        css = []
        if include_rect:
            css.extend(
                [
                    f"left:{rect.x:.6g}px;",
                    f"top:{rect.y:.6g}px;",
                    f"width:{rect.width:.6g}px;",
                    f"height:{rect.height:.6g}px;",
                ]
            )
        css.extend(
            [
                f"z-index:{int(layer.z_index)};",
                f"opacity:{float(layer.opacity):.6g};",
            ]
        )
        if include_rect:
            css.append(f"transform:rotate({float(layer.rotation):.6g}deg);")
        return "".join(css)

    @staticmethod
    def _background_css(layer: TemplateLayer) -> str:
        background = layer.style.get("background_color")
        if background is None and layer.source is not None:
            background = layer.source.ref
        if _is_hex_color(background):
            return f"background:{escape(background, quote=True)};"
        return ""

    @staticmethod
    def _text_css_from_style(
        style: Mapping[str, Any],
        layer: TemplateLayer | None,
        *,
        canvas_width: int,
        canvas_height: int,
    ) -> str:
        if layer is None:
            return ""
        return render_text_style_css(
            style,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
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

    @staticmethod
    def _object_fit(layer: TemplateLayer) -> str:
        value = layer.style.get("object_fit")
        if value in {"contain", "cover", "fill", "none", "scale-down"}:
            return str(value)
        return "cover"

    def _resolve_effective_title_style(
        self,
        *,
        layer: TemplateLayer,
        context: TemplateRenderContext,
    ) -> Mapping[str, Any]:
        if context.title_style_profile is None:
            logger.debug(
                "[TEXT_STYLE_DIAG] LayeredAdapter: no title_style_profile in context, "
                "using layer.style defaults for title layer '{}'",
                layer.id,
            )
            return dict(layer.style)

        base_style = dict(layer.style)
        user_style = context.title_style_profile.to_dict()
        user_style_clean = {k: v for k, v in user_style.items() if v is not None}

        effective = {**base_style, **user_style_clean}
        logger.info(
            "[TEXT_STYLE_DIAG] LayeredAdapter: title layer '{}' using user style: "
            "font_size={} primary_color={} (layer defaults overridden)",
            layer.id,
            effective.get("font_size"),
            effective.get("primary_color"),
        )
        return effective

    def _resolve_effective_caption_style(
        self,
        *,
        cue: CaptionCue,
        layer: TemplateLayer | None,
        context: TemplateRenderContext,
    ) -> Mapping[str, Any]:
        base_style = dict(layer.style) if layer is not None else {}

        if not context.text_style_profiles:
            logger.debug(
                "[TEXT_STYLE_DIAG] LayeredAdapter: no text_style_profiles in context, "
                "using layer.style defaults for caption cue '{}'",
                cue.id,
            )
            return base_style

        resolver = TextStyleResolver(profiles=context.text_style_profiles)
        caption_profile = resolver.resolve_for_cue(cue=cue)

        user_style_clean = {k: v for k, v in caption_profile.to_dict().items() if v is not None}
        effective = {**base_style, **user_style_clean}
        logger.info(
            "[TEXT_STYLE_DIAG] LayeredAdapter: caption cue '{}' resolved profile '{}': "
            "font_size={} primary_color={} (layer defaults overridden by user style)",
            cue.id,
            caption_profile.id,
            effective.get("font_size"),
            effective.get("primary_color"),
        )
        return effective


__all__ = ["LayeredTemplateHyperFramesAdapter"]


def _is_hex_color(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX_COLOR_PATTERN.fullmatch(value))


def _safe_font_family(value: Any) -> str | None:
    raw_value = str(value or "").replace("\r", " ").replace("\n", " ")
    if not raw_value.strip() or any(char in raw_value for char in _UNSAFE_FONT_CHARS):
        return None
    cleaned_chars = []
    for char in raw_value:
        if char.isalnum() or char.isspace() or char in {"-", "_", ",", "."}:
            cleaned_chars.append(char)
    cleaned = " ".join("".join(cleaned_chars).split())
    families = [family.strip() for family in cleaned.split(",") if family.strip()]
    return ", ".join(families) or None
