from __future__ import annotations

from os import PathLike
from typing import Any, Mapping

from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    layered_template_fingerprint,
)
from pixelle_video.models.media_placement import resolve_media_placement
from pixelle_video.models.render_package import resolve_media_layout_mode
from pixelle_video.models.template_display import (
    TemplateDisplaySettings,
    resolve_template_params_and_display,
)
from pixelle_video.models.template_parameters import validate_template_params
from pixelle_video.models.template_visual_asset import TemplateVisualAsset
from pixelle_video.services.frame_html import HTMLFrameGenerator
from pixelle_video.services.layered_template_adapters.html_frame import (
    LayeredTemplateHTMLFrameAdapter,
)

VALID_TEMPLATE_TEXT_POLICIES = {
    "caption_renderer",
    "template_body",
    "none",
    "explicit_both",
}
def resolve_template_body_text(template_body_text: str, text_policy: str) -> str:
    if text_policy not in VALID_TEMPLATE_TEXT_POLICIES:
        raise ValueError(f"Invalid template text policy: {text_policy}")
    if text_policy in {"template_body", "explicit_both"}:
        return template_body_text
    return ""


class TemplateVisualMaterializer:
    async def materialize_frame(
        self,
        *,
        title: str,
        template_body_text: str,
        media_path: str | None,
        frame_index: int,
        template_path: str | PathLike[str],
        template_id: str,
        output_path: str | PathLike[str],
        text_policy: str,
        caption_text: str | None = None,
        template_params: Mapping[str, Any] | None = None,
        canvas_width: int | None = None,
        canvas_height: int | None = None,
        media_layout_mode: str | None = None,
        media_type: str = "image",
        media_width: int | None = None,
        media_height: int | None = None,
        media_placement: Any = None,
        text_rendering: Mapping[str, Any] | None = None,
        template_display: TemplateDisplaySettings | Mapping[str, Any] | None = None,
        layered_template_spec: LayeredTemplateSpec | Mapping[str, Any] | None = None,
    ) -> TemplateVisualAsset:
        body_text = resolve_template_body_text(template_body_text, text_policy)
        raw_template_params, display_settings = resolve_template_params_and_display(
            template_params,
            template_display,
        )
        validated_template_params = validate_template_params(raw_template_params)
        render_title = display_settings.render_title(title)
        render_template_params = display_settings.render_template_params(
            validated_template_params
        )
        spec = _coerce_layered_template_spec(layered_template_spec)
        if spec is not None:
            adapter = LayeredTemplateHTMLFrameAdapter()
            generated_path = await adapter.render_frame(
                spec=spec,
                output_path=output_path,
                title_text=render_title,
                caption_text=caption_text if caption_text is not None else body_text,
                text_rendering=text_rendering or {},
                media_path=media_path,
            )
            return TemplateVisualAsset(
                path=str(generated_path),
                frame_index=int(frame_index),
                template_id=spec.template_id,
                template_path=f"layered_template:{spec.template_id}",
                width=spec.canvas_width,
                height=spec.canvas_height,
                media_path=media_path,
                text_policy=text_policy,
                diagnostics={
                    "layered_template_id": spec.template_id,
                    "layered_template_fingerprint": layered_template_fingerprint(spec),
                    "layered_template_canvas": f"{spec.canvas_width}x{spec.canvas_height}",
                    "template_params_count": len(validated_template_params),
                    "template_display": display_settings.to_dict(),
                },
            )
        resolved_media_layout_mode = resolve_media_layout_mode(media_layout_mode)
        generator = HTMLFrameGenerator(
            str(template_path),
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )
        ext = {
            "index": int(frame_index) + 1,
            "media_layout_mode": resolved_media_layout_mode,
        }
        ext.update(render_template_params)

        generated_path = await generator.generate_frame(
            title=render_title,
            text=body_text,
            image=media_path or "",
            ext=ext,
            output_path=str(output_path),
            media_placement=resolve_media_placement(media_placement),
            media_type=media_type,
            media_width=media_width,
            media_height=media_height,
        )

        return TemplateVisualAsset(
            path=str(generated_path),
            frame_index=int(frame_index),
            template_id=template_id,
            template_path=str(template_path),
            width=int(generator.width),
            height=int(generator.height),
            media_path=media_path,
            text_policy=text_policy,
            diagnostics={
                "template_params_count": len(validated_template_params),
                "template_display": display_settings.to_dict(),
            },
        )


def _coerce_layered_template_spec(
    value: LayeredTemplateSpec | Mapping[str, Any] | None,
) -> LayeredTemplateSpec | None:
    if value is None:
        return None
    if isinstance(value, LayeredTemplateSpec):
        return value
    return LayeredTemplateSpec.from_dict(value)
