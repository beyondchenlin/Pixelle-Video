from __future__ import annotations

from dataclasses import replace
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    LayerSourceSpec,
    TemplateLayer,
)
from pixelle_video.services.frame_html import HTMLDocumentFrameRenderer
from pixelle_video.services.layered_template_service import LayeredTemplateService


class LayeredTemplateHTMLFrameAdapter:
    def __init__(
        self,
        *,
        template_service: LayeredTemplateService | None = None,
        renderer: HTMLDocumentFrameRenderer | None = None,
    ) -> None:
        self.template_service = template_service or LayeredTemplateService()
        self.renderer = renderer or HTMLDocumentFrameRenderer()

    async def render_frame(
        self,
        *,
        spec: LayeredTemplateSpec | Mapping[str, Any],
        output_path: str | PathLike[str],
        title_text: str,
        caption_text: str,
        text_rendering: Mapping[str, Any] | None,
        media_path: str | None,
    ) -> Path:
        resolved_spec = _coerce_spec(spec)
        _validate_generated_media_refs(resolved_spec)
        render_spec = _map_primary_generated_media(resolved_spec, media_path=media_path)
        html = self.template_service.render_preview_html(
            spec=render_spec,
            title_text=title_text,
            caption_text=caption_text,
            text_rendering=text_rendering or {},
        )
        rendered_path = await self.renderer.render_html_document(
            html=html,
            output_path=str(output_path),
            width=render_spec.canvas_width,
            height=render_spec.canvas_height,
        )
        return Path(rendered_path)


def _coerce_spec(spec: LayeredTemplateSpec | Mapping[str, Any]) -> LayeredTemplateSpec:
    if isinstance(spec, LayeredTemplateSpec):
        return spec
    return LayeredTemplateSpec.from_dict(spec)


def _validate_generated_media_refs(spec: LayeredTemplateSpec) -> None:
    for layer in spec.layers:
        if layer.type == "generated_media" and layer.source is None:
            raise ValueError(f"generated-media layer missing source: {layer.id}")
        if layer.source is None or layer.source.kind != "generated_media":
            continue
        _validate_generated_media_layer(layer)


def _validate_generated_media_layer(layer: TemplateLayer) -> None:
    ref = str(layer.source.ref)
    if ref != "generated://primary":
        raise ValueError(f"unsupported generated-media ref: {ref}")


def _map_primary_generated_media(
    spec: LayeredTemplateSpec,
    *,
    media_path: str | None,
) -> LayeredTemplateSpec:
    has_primary_generated_media = any(
        layer.source is not None
        and layer.source.kind == "generated_media"
        and layer.source.ref == "generated://primary"
        for layer in spec.layers
    )
    if has_primary_generated_media and not media_path:
        raise ValueError("generated://primary requires media_path")
    if not media_path:
        return spec
    media_uri = Path(media_path).expanduser().resolve().as_uri()
    mapped_layers = []
    changed = False
    for layer in spec.layers:
        if (
            layer.source is not None
            and layer.source.kind == "generated_media"
            and layer.source.ref == "generated://primary"
        ):
            mapped_layers.append(
                replace(
                    layer,
                    source=LayerSourceSpec(
                        kind="asset",
                        ref=media_uri,
                        metadata=dict(layer.source.metadata),
                    ),
                )
            )
            changed = True
        else:
            mapped_layers.append(layer)
    if not changed:
        return spec
    return replace(spec, layers=tuple(mapped_layers))


__all__ = ["LayeredTemplateHTMLFrameAdapter"]
