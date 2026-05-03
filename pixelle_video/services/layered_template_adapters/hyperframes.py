from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Mapping

from pixelle_video.models.layered_template import LayeredTemplateSpec, TemplateLayer
from pixelle_video.models.render_package import CaptionCue, VisualClip
from pixelle_video.models.template_render_context import TemplateRenderContext
from pixelle_video.services.text_content_sanitizer import TextContentSanitizer


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
            if layer.role != "caption"
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
            (layer for layer in spec.layers if layer.type == "text" and layer.role == "caption"),
            None,
        )
        captions_html = "\n".join(
            self._render_caption_cue(cue=cue, layer=caption_layer)
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
        text = context.title if layer.role == "title" else ""
        display_text = self.text_sanitizer.sanitize(text).display_text
        return (
            f'      <div class="pixelle-layer pixelle-layered-text" '
            f'data-layer-id="{escape(layer.id, quote=True)}" '
            f'data-layer-type="{escape(layer.type, quote=True)}" '
            f'style="{self._layer_css(layer)}{self._text_css(layer)}">'
            f"{escape(display_text)}</div>"
        )

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
    ) -> str:
        duration = max(float(cue.end) - float(cue.start), 0.001)
        css = self._layer_css(layer) + self._text_css(layer) if layer is not None else (
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
    def _layer_css(layer: TemplateLayer | None) -> str:
        if layer is None:
            return ""
        rect = layer.rect
        return (
            f"left:{rect.x:.6g}px;"
            f"top:{rect.y:.6g}px;"
            f"width:{rect.width:.6g}px;"
            f"height:{rect.height:.6g}px;"
            f"z-index:{int(layer.z_index)};"
            f"opacity:{float(layer.opacity):.6g};"
            f"transform:rotate({float(layer.rotation):.6g}deg);"
        )

    @staticmethod
    def _background_css(layer: TemplateLayer) -> str:
        background = layer.style.get("background_color")
        if background is None and layer.source is not None:
            background = layer.source.ref
        if isinstance(background, str) and background:
            return f"background:{escape(background, quote=True)};"
        return ""

    @staticmethod
    def _text_css(layer: TemplateLayer | None) -> str:
        if layer is None:
            return ""
        style: Mapping[str, Any] = layer.style
        css = []
        font_size = style.get("font_size")
        if font_size is not None:
            try:
                css.append(f"font-size:{max(1, int(font_size))}px;")
            except (TypeError, ValueError):
                pass
        color = style.get("primary_color") or style.get("color")
        if isinstance(color, str) and color:
            css.append(f"color:{escape(color, quote=True)};")
        alignment = style.get("alignment")
        if alignment in {"left", "center", "right"}:
            justify = {
                "left": "flex-start",
                "center": "center",
                "right": "flex-end",
            }[str(alignment)]
            css.append(f"text-align:{alignment};justify-content:{justify};")
        return "".join(css)

    @staticmethod
    def _object_fit(layer: TemplateLayer) -> str:
        value = layer.style.get("object_fit")
        if value in {"contain", "cover", "fill", "none", "scale-down"}:
            return str(value)
        return "cover"


__all__ = ["LayeredTemplateHyperFramesAdapter"]
