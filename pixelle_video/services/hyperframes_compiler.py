from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from hashlib import sha1
from html import escape
from pathlib import Path

from loguru import logger

from pixelle_video.models.layered_template import active_layered_template_spec
from pixelle_video.models.media_placement import calculate_media_box
from pixelle_video.models.render_package import CaptionCue, TextCue
from pixelle_video.models.template_render_context import TemplateRenderContext
from pixelle_video.models.template_text_style_presets import resolve_template_text_style_preset
from pixelle_video.models.text_style import DEFAULT_TITLE_STYLE_ID, TextStyleProfile
from pixelle_video.services.font_discovery import (
    canonical_font_family_name,
    font_family_from_file,
    resolve_font_file,
)
from pixelle_video.services.layered_template_adapters.hyperframes import (
    LayeredTemplateHyperFramesAdapter,
)
from pixelle_video.services.media_geometry_resolver import MediaGeometryResolver
from pixelle_video.services.text_content_sanitizer import TextContentSanitizer
from pixelle_video.services.text_layout_planner import wrap_by_character_limit
from pixelle_video.services.text_style_css_contract import (
    TextStyleRegion,
    resolve_text_style_layout,
)
from pixelle_video.services.text_style_resolver import TextStyleResolver
from pixelle_video.utils.filesystem import (
    copy_file,
    ensure_directory,
    path_exists,
    path_is_dir,
    read_text_file,
    write_text_file,
)


@dataclass(frozen=True)
class _CustomFontAsset:
    family: str
    file_name: str


@dataclass(frozen=True)
class _LayoutRegion:
    left: float
    top: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height


class HyperFramesCompiler:
    def __init__(
        self,
        template_root: Path | None = None,
        runtime_root: Path | None = None,
        text_sanitizer: TextContentSanitizer | None = None,
        media_geometry_resolver: MediaGeometryResolver | None = None,
    ):
        self.template_root = (
            Path(template_root)
            if template_root is not None
            else Path("resources/hyperframes/templates")
        )
        self.runtime_root = (
            Path(runtime_root)
            if runtime_root is not None
            else Path("resources/hyperframes/runtime")
        )
        self.text_sanitizer = text_sanitizer or TextContentSanitizer()
        self.media_geometry_resolver = media_geometry_resolver or MediaGeometryResolver()

    def compile(self, *, project_dir: Path, context: TemplateRenderContext) -> None:
        layered_template_spec = active_layered_template_spec(
            context.layered_template_spec
        )
        if layered_template_spec is not None:
            ensure_directory(project_dir / "compositions")
            self._copy_runtime_assets(project_dir)
            self._copy_custom_font_assets(
                project_dir,
                context.text_style_profiles,
            )
            LayeredTemplateHyperFramesAdapter(
                text_sanitizer=self.text_sanitizer,
            ).compile(
                project_dir=project_dir,
                context=replace(context, layered_template_spec=layered_template_spec),
            )
            return

        template_dir = self.template_root / context.template_id
        index_template = read_text_file(template_dir / "index.template.html")
        captions_template = read_text_file(
            template_dir / "compositions" / "captions.template.html"
        )
        text_layer_template_path = template_dir / "compositions" / "text_layer.template.html"
        text_layer_template = (
            read_text_file(text_layer_template_path)
            if path_exists(text_layer_template_path)
            else '<div id="text-layer">__TEXT_CUES__</div><script>__TEXT_TIMELINE__</script>'
        )

        replacements = {
            "__CANVAS_WIDTH__": str(context.canvas_width),
            "__CANVAS_HEIGHT__": str(context.canvas_height),
            "__DURATION__": str(context.duration),
            "__TITLE__": self._render_title(context),
            "__TITLE_STYLE_CSS__": self._render_title_style_css(context),
            "__AUTHOR__": escape(context.author or ""),
            "__AUTHOR_DESC__": escape(str(context.template_params.get("author_desc", ""))),
            "__FOOTER__": escape(context.footer or ""),
            "__THEME__": escape(context.theme or ""),
            "__STYLE_PROFILE__": escape(context.style_profile),
            "__MEDIA_LAYOUT_MODE__": escape(context.media_layout_mode, quote=True),
            "__MEDIA_PLACEMENT_CSS__": self._render_media_placement_css(context),
            "__VISUALS__": self._render_visuals(context, base_dir=project_dir),
            "__AUDIO__": self._render_audio(context),
            "__CAPTIONS__": self._render_captions(context),
            "__TEXT_CUES__": self._render_text_cues(context),
            "__TEXT_TIMELINE__": self._render_text_timeline(context),
            "__ELEMENT_ANIMATION_MANIFEST__": escape(
                context.element_animation_manifest_path or "",
                quote=True,
            ),
        }

        ensure_directory(project_dir / "compositions")
        self._copy_runtime_assets(project_dir)
        custom_fonts = self._copy_custom_font_assets(
            project_dir,
            context.text_style_profiles,
        )

        compiled_index = self._inject_custom_font_faces(
            self._replace_placeholders(index_template, replacements),
            custom_fonts,
            font_url_prefix="./runtime/custom_fonts",
        )
        compiled_captions = self._inject_custom_font_faces(
            self._replace_placeholders(captions_template, replacements),
            custom_fonts,
            font_url_prefix="../runtime/custom_fonts",
        )
        compiled_text_layer = self._inject_custom_font_faces(
            self._replace_placeholders(text_layer_template, replacements),
            custom_fonts,
            font_url_prefix="../runtime/custom_fonts",
        )
        write_text_file(project_dir / "index.html", compiled_index)
        write_text_file(
            project_dir / "compositions" / "captions.html",
            compiled_captions,
        )
        write_text_file(
            project_dir / "compositions" / "text_layer.html",
            compiled_text_layer,
        )

    def _render_visuals(
        self,
        context: TemplateRenderContext,
        *,
        base_dir: Path | None = None,
    ) -> str:
        rendered: list[str] = []
        for clip in context.visuals:
            duration = max(float(clip.end) - float(clip.start), 0.1)
            track_index = clip.track_index if clip.track_index is not None else 1
            media_tag = self._build_media_tag(
                media_type=clip.media_type,
                media_path=clip.media_path,
            )
            element_manifest_attr = ""
            if clip.element_animation_manifest_path:
                element_manifest_attr = (
                    ' data-element-animation-manifest="'
                    f'{escape(clip.element_animation_manifest_path, quote=True)}"'
                )
            box = clip.resolved_media_box or self.media_geometry_resolver.resolve_box(
                media_path=clip.media_path,
                media_type=clip.media_type,
                canvas_width=context.canvas_width,
                canvas_height=context.canvas_height,
                fallback_width=context.media_width,
                fallback_height=context.media_height,
                placement=context.media_placement,
                base_dir=base_dir,
            )
            geometry_style = (
                f"--pixelle-media-display-width:{box.width:.6f}px;"
                f"--pixelle-media-display-height:{box.height:.6f}px;"
                f"--pixelle-media-left:{box.left:.6f}px;"
                f"--pixelle-media-top:{box.top:.6f}px"
            )
            rendered.append(
                (
                    f'<div id="{escape(clip.id, quote=True)}" class="clip pixelle-media-clip" '
                    f'data-start="{clip.start}" '
                    f'data-duration="{duration}" data-track-index="{track_index}" '
                    f'style="{geometry_style}"'
                    f"{element_manifest_attr}>"
                    f"{media_tag}"
                    "</div>"
                )
            )
        return "".join(rendered)

    def _build_media_tag(self, *, media_type: str, media_path: str) -> str:
        escaped_path = escape(media_path, quote=True)
        if media_type == "video":
            return (
                '<video class="pixelle-media" '
                f'src="{escaped_path}" muted playsinline></video>'
            )
        return f'<img class="pixelle-media" src="{escaped_path}" alt="" />'

    def _render_media_placement_css(self, context: TemplateRenderContext) -> str:
        source_width = int(context.media_width or context.canvas_width)
        source_height = int(context.media_height or context.canvas_height)
        box = calculate_media_box(
            canvas_width=context.canvas_width,
            canvas_height=context.canvas_height,
            media_source_width=source_width,
            media_source_height=source_height,
            placement=context.media_placement,
        )
        return (
            "<style data-pixelle-media-placement>"
            ":root{"
            f"--pixelle-media-display-width: {round(box.width)}px;"
            f"--pixelle-media-display-height: {round(box.height)}px;"
            f"--pixelle-media-left: {round(box.left)}px;"
            f"--pixelle-media-top: {round(box.top)}px;"
            "}"
            "#main-comp .pixelle-media-layer{position:absolute!important;"
            "inset:0!important;pointer-events:none!important;}"
            "#main-comp .pixelle-media-layer>.pixelle-media-clip{position:absolute!important;"
            "left:var(--pixelle-media-left)!important;"
            "top:var(--pixelle-media-top)!important;"
            "width:var(--pixelle-media-display-width)!important;"
            "height:var(--pixelle-media-display-height)!important;"
            "max-width:none!important;max-height:none!important;}"
            "#main-comp .pixelle-media-layer>.pixelle-media-clip>.pixelle-media{"
            "width:100%!important;height:100%!important;max-width:none!important;"
            "max-height:none!important;object-fit:fill!important;display:block!important;}"
            "</style>"
        )

    def _render_audio(self, context: TemplateRenderContext) -> str:
        audio_tracks = list(context.audio_tracks)
        if not audio_tracks and context.audio is not None:
            audio_tracks = [context.audio]
        if not audio_tracks:
            return ""

        rendered: list[str] = []
        for track in audio_tracks:
            start = float(track.start)
            duration = max(float(track.duration), 0.0)
            end = start + duration
            rendered.append(
                (
                    f'<audio id="{escape(track.id, quote=True)}" '
                    f'src="{escape(track.path, quote=True)}" '
                    f'data-start="{start}" '
                    f'data-end="{end}" '
                    f'data-duration="{duration}" '
                    f'data-media-start="{float(track.media_start)}" '
                    f'data-volume="{float(track.volume)}" '
                    f'data-track-index="{int(track.track_index)}" '
                    f'data-role="{escape(track.role, quote=True)}"></audio>'
                )
            )
        return "".join(rendered)

    def _render_captions(self, context: TemplateRenderContext) -> str:
        resolver = TextStyleResolver(profiles=context.text_style_profiles)
        rendered: list[str] = []
        for cue in context.captions:
            duration = max(float(cue.end) - float(cue.start), 0.1)
            profile = resolver.resolve_for_cue(cue=self._caption_as_text_cue(cue))
            css_variables = self._style_profile_css_variables(profile, context)
            text_style = self._text_content_inline_style()
            display_text = self._wrapped_cue_text(
                cue.text,
                profile,
                render_manifest_version=context.render_manifest_version,
            )
            rendered.append(
                (
                    f'<div id="{escape(cue.id, quote=True)}" class="clip caption-group" '
                    f'data-start="{cue.start}" '
                    f'data-duration="{duration}" '
                    'data-track-index="1" '
                    f'data-style-profile="{escape(profile.id, quote=True)}" '
                    f'style="{escape(css_variables, quote=True)}">'
                    f'<div class="caption-text" style="{escape(text_style, quote=True)}">'
                    f"{escape(display_text)}</div>"
                    "</div>"
                )
            )
        return "".join(rendered)

    def _render_text_cues(self, context: TemplateRenderContext) -> str:
        tracks = {track.id: track for track in context.text_tracks if track.enabled}
        resolver = TextStyleResolver(profiles=context.text_style_profiles)
        rendered: list[str] = []
        for cue in context.text_cues:
            track = tracks.get(cue.track_id)
            if track is None or "hyperframes" not in track.renderer_targets:
                continue

            duration = max(float(cue.end) - float(cue.start), 0.1)
            profile = resolver.resolve_for_cue(cue=cue, track=track)
            css_variables = self._style_profile_css_variables(profile, context)
            cue_style = (
                f"{css_variables} max-width: var(--text-max-width);"
            )
            text_style = self._text_content_inline_style()
            display_text = self._wrapped_cue_text(
                cue.text,
                profile,
                render_manifest_version=context.render_manifest_version,
            )
            rendered.append(
                (
                    f'<div id="{escape(cue.id, quote=True)}" '
                    f'class="clip text-cue text-cue--{escape(cue.role, quote=True)}" '
                    f'data-start="{cue.start}" data-duration="{duration}" '
                    f'data-track-id="{escape(cue.track_id, quote=True)}" '
                    f'data-role="{escape(cue.role, quote=True)}" '
                    f'data-slot="{escape(cue.slot or "center", quote=True)}" '
                    f'data-layer="{cue.layer}" '
                    f'data-style-profile="{escape(profile.id, quote=True)}" '
                    f'style="{escape(cue_style, quote=True)}">'
                    f'<span class="text-cue__content" '
                    f'style="{escape(text_style, quote=True)}">'
                    f"{escape(display_text)}</span>"
                    "</div>"
                )
            )
        return "".join(rendered)

    def _safe_display_text(self, text: object) -> str:
        return self.text_sanitizer.sanitize(text).display_text

    def _wrapped_cue_text(
        self,
        text: object,
        profile: TextStyleProfile,
        *,
        render_manifest_version: str,
    ) -> str:
        display_text = self._safe_display_text(text)
        if (
            render_manifest_version != "render_manifest.v2"
            or not profile.max_chars_per_line
        ):
            return display_text
        return "\n".join(
            wrap_by_character_limit(display_text, profile.max_chars_per_line)
        )

    def _render_title(self, context: TemplateRenderContext) -> str:
        display_text = self._safe_display_text(context.title)
        profile = self._effective_title_style_profile(context)
        if not profile.max_chars_per_line:
            return escape(display_text)

        max_chars = max(1, int(profile.max_chars_per_line))
        lines = [
            display_text[index : index + max_chars]
            for index in range(0, len(display_text), max_chars)
        ]
        return "<br/>".join(escape(line) for line in lines)

    def _render_title_style_css(self, context: TemplateRenderContext) -> str:
        return self._style_profile_css_variables(
            self._effective_title_style_profile(context),
            context,
            prefix="title",
        )

    def _effective_title_style_profile(
        self,
        context: TemplateRenderContext,
    ) -> TextStyleProfile:
        if context.title_style_profile is not None:
            logger.info(
                "[TEXT_STYLE_DIAG] Compiler: using context.title_style_profile "
                "id={} font_size={} color={}",
                context.title_style_profile.id,
                context.title_style_profile.font_size,
                context.title_style_profile.primary_color,
            )
            return context.title_style_profile

        title_payload = resolve_template_text_style_preset(
            context.template_id
        ).title_style_dict()
        title_payload["id"] = DEFAULT_TITLE_STYLE_ID
        return TextStyleProfile.from_dict(title_payload)

    def _caption_as_text_cue(self, cue: CaptionCue) -> TextCue:
        return TextCue(
            id=cue.id,
            track_id="captions",
            text=cue.text,
            start=float(cue.start),
            end=float(cue.end),
            role="caption",
            frame_indices=tuple(cue.frame_indices),
            style_profile=cue.style_profile,
        )

    def _style_profile_css_variables(
        self,
        profile: TextStyleProfile,
        context: TemplateRenderContext,
        *,
        prefix: str = "text",
    ) -> str:
        scale = profile.scale_for_canvas(context.canvas_width, context.canvas_height)
        font_size = max(1, int(round(profile.font_size * scale)))
        stroke_width = max(0, int(round(profile.stroke_width * scale)))
        margin_x = max(0, int(round(profile.margin_x * scale)))
        margin_y = max(0, int(round(profile.margin_y * scale)))
        layout_region = (
            self._title_layout_region(context) if prefix == "title" else None
        )
        position_declarations, available_width = (
            self._style_profile_position_css_variables(
                profile=profile,
                canvas_width=context.canvas_width,
                canvas_height=context.canvas_height,
                margin_x=margin_x,
                margin_y=margin_y,
                prefix=prefix,
                region=layout_region,
            )
        )
        max_width = max(1, int(round(context.canvas_width * profile.max_width_ratio)))
        if available_width is not None:
            max_width = min(max_width, max(1, int(round(available_width))))
        background = self._rgba(profile.background_color, profile.background_opacity)
        declarations = [
            f"--{prefix}-fill: {profile.primary_color}",
            f"--{prefix}-stroke-color: {profile.stroke_color}",
            f"--{prefix}-stroke-width: {stroke_width}px",
            f"--{prefix}-background: {background}",
            "--"
            f"{prefix}-font-family: "
            f"{self._css_font_family_value(canonical_font_family_name(profile.font_family))}",
            f"--{prefix}-font-size: {font_size}px",
            f"--{prefix}-font-weight: {int(profile.font_weight)}",
            f"--{prefix}-line-height: {float(profile.line_height)}",
            f"--{prefix}-max-width: {max_width}px",
            f"--{prefix}-box-width: {max_width}px",
            f"--{prefix}-margin-x: {margin_x}px",
            f"--{prefix}-margin-y: {margin_y}px",
            f"--{prefix}-text-align: {profile.alignment}",
            f"--{prefix}-justify-content: {self._justify_content(profile.alignment)}",
            f"--{prefix}-align-items: {self._align_items(profile.position)}",
        ]
        declarations.extend(position_declarations)
        return "; ".join(declarations) + ";"

    @staticmethod
    def _style_profile_position_css_variables(
        *,
        profile: TextStyleProfile,
        canvas_width: int,
        canvas_height: int,
        margin_x: int,
        margin_y: int,
        prefix: str,
        region: _LayoutRegion | None = None,
    ) -> tuple[list[str], float | None]:
        preview_region = (
            TextStyleRegion(
                x=region.left,
                y=region.top,
                width=region.width,
                height=region.height,
            )
            if region is not None
            else TextStyleRegion(
                x=0,
                y=0,
                width=float(canvas_width),
                height=float(canvas_height),
            )
        )
        layout = resolve_text_style_layout(
            position=profile.position,
            canvas_width=float(canvas_width),
            canvas_height=float(canvas_height),
            region=preview_region,
            margin_x=float(margin_x),
            margin_y=float(margin_y),
            max_width_ratio=float(profile.max_width_ratio),
        )

        return [
            f"--{prefix}-left: {HyperFramesCompiler._css_px_or_auto(layout.left)}",
            f"--{prefix}-right: {HyperFramesCompiler._css_px_or_auto(layout.right)}",
            f"--{prefix}-top: {HyperFramesCompiler._css_px_or_auto(layout.top)}",
            f"--{prefix}-bottom: {HyperFramesCompiler._css_px_or_auto(layout.bottom)}",
            f"--{prefix}-transform: {layout.transform}",
        ], layout.width

    @staticmethod
    def _css_px_or_auto(value: float | None) -> str:
        if value is None:
            return "auto"
        return f"{round(value)}px"

    @classmethod
    def _title_layout_region(cls, context: TemplateRenderContext) -> _LayoutRegion:
        region = context.template_title_region or {}
        x = cls._region_fraction(region.get("x"), 0.0)
        y = cls._region_fraction(region.get("y"), 0.0)
        width = cls._region_fraction(region.get("width"), 1.0)
        height = cls._region_fraction(region.get("height"), 1.0)
        width = min(width, max(0.0, 1.0 - x))
        height = min(height, max(0.0, 1.0 - y))
        return _LayoutRegion(
            left=float(context.canvas_width) * x,
            top=float(context.canvas_height) * y,
            width=max(1.0, float(context.canvas_width) * width),
            height=max(1.0, float(context.canvas_height) * height),
        )

    @staticmethod
    def _region_fraction(value: object, default: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            numeric = default
        return max(0.0, min(numeric, 1.0))

    @staticmethod
    def _justify_content(alignment: str) -> str:
        return {
            "left": "flex-start",
            "right": "flex-end",
        }.get(alignment, "center")

    @staticmethod
    def _align_items(position: str) -> str:
        if position in {"top", "top_left", "top_right"}:
            return "flex-start"
        if position in {"bottom", "lower_third", "bottom_left", "bottom_right"}:
            return "flex-end"
        return "center"

    @staticmethod
    def _text_content_inline_style() -> str:
        return (
            "color: var(--text-fill); "
            "font-family: var(--text-font-family); "
            "font-size: var(--text-font-size); "
            "font-weight: var(--text-font-weight); "
            "line-height: var(--text-line-height); "
            "-webkit-text-stroke: var(--text-stroke-width) "
            "var(--text-stroke-color);"
        )

    @staticmethod
    def _rgba(color: str | None, opacity: float) -> str:
        if not color:
            return "rgba(0, 0, 0, 0)"
        red = int(color[1:3], 16)
        green = int(color[3:5], 16)
        blue = int(color[5:7], 16)
        alpha = max(0.0, min(float(opacity), 1.0))
        return f"rgba({red}, {green}, {blue}, {alpha:g})"

    @staticmethod
    def _css_font_family_value(value: object) -> str:
        raw_value = str(value).replace("\r", " ").replace("\n", " ")
        unsafe_chars = ("\"", "'", "`", ";", "{", "}", "\\", "/", "*", ":", "(", ")")
        if any(char in raw_value for char in unsafe_chars):
            return "sans-serif"

        cleaned_chars = []
        for char in raw_value:
            if char.isalnum() or char.isspace() or char in {"-", "_", ",", "."}:
                cleaned_chars.append(char)
        cleaned = " ".join("".join(cleaned_chars).split())
        families = [
            family.strip()
            for family in cleaned.split(",")
            if family.strip()
        ]
        return ", ".join(families) or "sans-serif"

    def _render_text_timeline(self, context: TemplateRenderContext) -> str:
        return (
            'const textCues = Array.from(document.querySelectorAll(".text-cue"));\n'
            'const tl = gsap.timeline({ paused: true });\n'
            "gsap.set(textCues, { autoAlpha: 0, visibility: \"hidden\" });\n"
            "textCues.forEach((cue) => {\n"
            "  const start = Number(cue.dataset.start || 0);\n"
            "  const duration = Math.max(Number(cue.dataset.duration || 0), 0.1);\n"
            "  tl.set(cue, { autoAlpha: 1, visibility: \"visible\" }, start);\n"
            "  tl.set(cue, { autoAlpha: 0, visibility: \"hidden\" }, start + duration);\n"
            "});\n"
            f"padTimelineToDuration(tl, {float(context.duration)});\n"
            "window.__timelines = window.__timelines || {};\n"
            'window.__timelines["text-layer"] = tl;'
        )

    def _copy_runtime_assets(self, project_dir: Path) -> None:
        if not path_exists(self.runtime_root):
            return

        for source_path in self.runtime_root.rglob("*"):
            relative_path = source_path.relative_to(self.runtime_root)
            target_path = project_dir / "runtime" / relative_path

            if path_is_dir(source_path):
                ensure_directory(target_path)
                continue

            copy_file(source_path, target_path)

    def _copy_custom_font_assets(
        self,
        project_dir: Path,
        profiles: Iterable[TextStyleProfile],
    ) -> list[_CustomFontAsset]:
        copied_by_key: dict[tuple[str, str], _CustomFontAsset] = {}
        target_dir = project_dir / "runtime" / "custom_fonts"
        for profile in profiles:
            if not profile.font_file:
                continue

            source_path = resolve_font_file(profile.font_file)
            if source_path is None:
                raise ValueError(f"font_file must be an existing file: {profile.font_file}")

            family = canonical_font_family_name(profile.font_family)
            if not family:
                continue

            actual_family = font_family_from_file(source_path)
            if actual_family.casefold() != family.casefold():
                raise ValueError(
                    "font family does not match font_file: "
                    f"expected {family!r}, got {actual_family!r} from {source_path}"
                )

            source_path = source_path.resolve()
            key = (family.casefold(), str(source_path).casefold())
            if key in copied_by_key:
                continue

            file_name = self._custom_font_file_name(source_path)
            copy_file(source_path, target_dir / file_name)
            copied_by_key[key] = _CustomFontAsset(
                family=family,
                file_name=file_name,
            )

        return list(copied_by_key.values())

    def _inject_custom_font_faces(
        self,
        html: str,
        custom_fonts: list[_CustomFontAsset],
        *,
        font_url_prefix: str,
    ) -> str:
        if not custom_fonts:
            return html

        css = "\n".join(
            self._custom_font_face_css(asset, font_url_prefix=font_url_prefix)
            for asset in custom_fonts
        )
        style_end = "</style>"
        if style_end in html:
            return html.replace(style_end, f"{css}\n{style_end}", 1)

        style_block = f"<style>\n{css}\n</style>"
        head_end = "</head>"
        if head_end in html:
            return html.replace(head_end, f"{style_block}\n{head_end}", 1)
        return f"{style_block}\n{html}"

    @staticmethod
    def _custom_font_file_name(source_path: Path) -> str:
        digest = sha1(str(source_path).encode("utf-8")).hexdigest()[:10]
        stem = "".join(
            char if char.isalnum() or char in {"-", "_"} else "-"
            for char in source_path.stem
        ).strip("-") or "font"
        suffix = source_path.suffix.lower()
        return f"{stem}-{digest}{suffix}"

    def _custom_font_face_css(
        self,
        asset: _CustomFontAsset,
        *,
        font_url_prefix: str,
    ) -> str:
        family = self._css_string_literal(asset.family)
        url = f"{font_url_prefix}/{asset.file_name}"
        return (
            f"@font-face {{ font-family: {family}; "
            f"src: url(\"{url}\"); font-display: swap; }}"
        )

    @staticmethod
    def _css_string_literal(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
        return f"\"{escaped}\""

    @staticmethod
    def _replace_placeholders(template: str, replacements: dict[str, str]) -> str:
        compiled = template
        for placeholder, value in replacements.items():
            compiled = compiled.replace(placeholder, value)
        return compiled
