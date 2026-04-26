from __future__ import annotations

from os import PathLike
from typing import Any, Mapping

from pixelle_video.models.template_visual_asset import TemplateVisualAsset
from pixelle_video.services.frame_html import HTMLFrameGenerator


VALID_TEMPLATE_TEXT_POLICIES = {
    "caption_renderer",
    "template_body",
    "none",
    "explicit_both",
}
RESERVED_TEMPLATE_PARAMS = {"title", "text", "image", "index"}


def resolve_template_body_text(narration: str, text_policy: str) -> str:
    if text_policy not in VALID_TEMPLATE_TEXT_POLICIES:
        raise ValueError(f"Invalid template text policy: {text_policy}")
    if text_policy in {"template_body", "explicit_both"}:
        return narration
    return ""


def _validate_template_params(
    template_params: Mapping[str, Any] | None,
) -> dict[str, Any]:
    params = dict(template_params or {})
    reserved = sorted(str(key) for key in params if key in RESERVED_TEMPLATE_PARAMS)
    if reserved:
        joined = ", ".join(reserved)
        raise ValueError(f"reserved template parameter(s) are not allowed: {joined}")
    return params


class TemplateVisualMaterializer:
    async def materialize_frame(
        self,
        *,
        title: str,
        narration: str,
        media_path: str | None,
        frame_index: int,
        template_path: str | PathLike[str],
        template_id: str,
        output_path: str | PathLike[str],
        text_policy: str,
        template_params: Mapping[str, Any] | None = None,
    ) -> TemplateVisualAsset:
        body_text = resolve_template_body_text(narration, text_policy)
        validated_template_params = _validate_template_params(template_params)
        generator = HTMLFrameGenerator(str(template_path))
        ext = {"index": int(frame_index) + 1}
        ext.update(validated_template_params)

        generated_path = await generator.generate_frame(
            title=title,
            text=body_text,
            image=media_path or "",
            ext=ext,
            output_path=str(output_path),
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
            diagnostics={"template_params_count": len(ext) - 1},
        )
