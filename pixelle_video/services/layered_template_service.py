from __future__ import annotations

import re
from typing import Any, Mapping

from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    layered_template_fingerprint,
)
from pixelle_video.services.layered_template_adapters.html_preview import (
    render_layered_template_preview_html,
)

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?$")


class LayeredTemplateService:
    def normalize_spec(self, spec: LayeredTemplateSpec | Mapping[str, Any]) -> LayeredTemplateSpec:
        if isinstance(spec, LayeredTemplateSpec):
            return LayeredTemplateSpec.from_dict(spec.to_dict())
        return LayeredTemplateSpec.from_dict(spec)

    def validate_spec(self, spec: LayeredTemplateSpec | Mapping[str, Any]) -> LayeredTemplateSpec:
        normalized = self.normalize_spec(spec)
        layer_ids: set[str] = set()
        for layer in normalized.layers:
            if layer.id in layer_ids:
                raise ValueError(f"duplicate layer id: {layer.id}")
            layer_ids.add(layer.id)
            if layer.source and layer.source.kind == "color" and not _HEX_COLOR_RE.fullmatch(
                layer.source.ref
            ):
                raise ValueError(
                    f"layer {layer.id} color source must be a hex color"
                )
        return normalized

    def fingerprint(self, spec: LayeredTemplateSpec | Mapping[str, Any]) -> str:
        return layered_template_fingerprint(self.normalize_spec(spec))

    def render_preview_html(
        self,
        *,
        spec: LayeredTemplateSpec | Mapping[str, Any],
        title_text: str = "",
        caption_text: str = "",
        text_rendering: Mapping[str, Any] | None = None,
    ) -> str:
        normalized = self.validate_spec(spec)
        return render_layered_template_preview_html(
            spec=normalized,
            title_text=title_text,
            caption_text=caption_text,
            text_rendering=text_rendering or {},
        )
