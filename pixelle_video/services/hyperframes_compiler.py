from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha1
from html import escape
from pathlib import Path
from shutil import copy2

from pixelle_video.models.render_package import CaptionCue, TextCue
from pixelle_video.models.template_render_context import TemplateRenderContext
from pixelle_video.models.text_style import TextStyleProfile
from pixelle_video.services.font_discovery import resolve_font_file
from pixelle_video.services.text_content_sanitizer import TextContentSanitizer
from pixelle_video.services.text_style_resolver import TextStyleResolver


@dataclass(frozen=True)
class _CustomFontAsset:
    family: str
    file_name: str


class HyperFramesCompiler:
    def __init__(
        self,
        template_root: Path | None = None,
        runtime_root: Path | None = None,
        text_sanitizer: TextContentSanitizer | None = None,
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

    def compile(self, *, project_dir: Path, context: TemplateRenderContext) -> None:
        template_dir = self.template_root / context.template_id
        index_template = (template_dir / "index.template.html").read_text(encoding="utf-8")
        captions_template = (
            template_dir / "compositions" / "captions.template.html"
        ).read_text(encoding="utf-8")
        text_layer_template_path = template_dir / "compositions" / "text_layer.template.html"
        text_layer_template = (
            text_layer_template_path.read_text(encoding="utf-8")
            if text_layer_template_path.exists()
            else '<div id="text-layer">__TEXT_CUES__</div><script>__TEXT_TIMELINE__</script>'
        )

        replacements = {
            "__CANVAS_WIDTH__": str(context.canvas_width),
            "__CANVAS_HEIGHT__": str(context.canvas_height),
            "__DURATION__": str(context.duration),
            "__TITLE__": escape(context.title),
            "__AUTHOR__": escape(context.author or ""),
            "__AUTHOR_DESC__": escape(str(context.template_params.get("author_desc", ""))),
            "__FOOTER__": escape(context.footer or ""),
            "__THEME__": escape(context.theme or ""),
            "__STYLE_PROFILE__": escape(context.style_profile),
            "__VISUALS__": self._render_visuals(context),
            "__AUDIO__": self._render_audio(context),
            "__CAPTIONS__": self._render_captions(context),
            "__TEXT_CUES__": self._render_text_cues(context),
            "__TEXT_TIMELINE__": self._render_text_timeline(context),
            "__ELEMENT_ANIMATION_MANIFEST__": escape(
                context.element_animation_manifest_path or "",
                quote=True,
            ),
        }

        (project_dir / "compositions").mkdir(parents=True, exist_ok=True)
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
        (project_dir / "index.html").write_text(compiled_index, encoding="utf-8")
        (project_dir / "compositions" / "captions.html").write_text(
            compiled_captions,
            encoding="utf-8",
        )
        (project_dir / "compositions" / "text_layer.html").write_text(
            compiled_text_layer,
            encoding="utf-8",
        )

    def _render_visuals(self, context: TemplateRenderContext) -> str:
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
            rendered.append(
                (
                    f'<div id="{escape(clip.id, quote=True)}" class="clip visual-clip" '
                    f'data-start="{clip.start}" '
                    f'data-duration="{duration}" data-track-index="{track_index}"'
                    f"{element_manifest_attr}>"
                    '<div class="visual-frame">'
                    f"{media_tag}"
                    '<div class="corner-mark tl"></div>'
                    '<div class="corner-mark tr"></div>'
                    '<div class="corner-mark bl"></div>'
                    '<div class="corner-mark br"></div>'
                    '<div class="side-dots left">'
                    '<div class="side-dot"></div>'
                    '<div class="side-dot active"></div>'
                    '<div class="side-dot"></div>'
                    "</div>"
                    '<div class="side-dots right">'
                    '<div class="side-dot"></div>'
                    '<div class="side-dot active"></div>'
                    '<div class="side-dot"></div>'
                    "</div>"
                    "</div>"
                    "</div>"
                )
            )
        return "".join(rendered)

    def _build_media_tag(self, *, media_type: str, media_path: str) -> str:
        escaped_path = escape(media_path, quote=True)
        if media_type == "video":
            return (
                '<video class="visual-clip__media" '
                f'src="{escaped_path}" muted playsinline></video>'
            )
        return f'<img class="visual-clip__media" src="{escaped_path}" alt="" />'

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
            display_text = self._safe_display_text(cue.text)
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
            display_text = self._safe_display_text(cue.text)
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
    ) -> str:
        scale = profile.scale_for_canvas(context.canvas_width, context.canvas_height)
        font_size = max(1, int(round(profile.font_size * scale)))
        stroke_width = max(0, int(round(profile.stroke_width * scale)))
        margin_x = max(0, int(round(profile.margin_x * scale)))
        margin_y = max(0, int(round(profile.margin_y * scale)))
        max_width = max(1, int(round(context.canvas_width * profile.max_width_ratio)))
        background = self._rgba(profile.background_color, profile.background_opacity)
        return "; ".join(
            [
                f"--text-fill: {profile.primary_color}",
                f"--text-stroke-color: {profile.stroke_color}",
                f"--text-stroke-width: {stroke_width}px",
                f"--text-background: {background}",
                f"--text-font-family: {self._css_font_family_value(profile.font_family)}",
                f"--text-font-size: {font_size}px",
                f"--text-font-weight: {int(profile.font_weight)}",
                f"--text-line-height: {float(profile.line_height)}",
                f"--text-max-width: {max_width}px",
                f"--text-margin-x: {margin_x}px",
                f"--text-margin-y: {margin_y}px",
            ]
        ) + ";"

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
        if not self.runtime_root.exists():
            return

        for source_path in self.runtime_root.rglob("*"):
            relative_path = source_path.relative_to(self.runtime_root)
            target_path = project_dir / "runtime" / relative_path

            if source_path.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            copy2(source_path, target_path)

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

            family = str(profile.font_family).strip()
            if not family:
                continue

            source_path = source_path.resolve()
            key = (family.casefold(), str(source_path).casefold())
            if key in copied_by_key:
                continue

            target_dir.mkdir(parents=True, exist_ok=True)
            file_name = self._custom_font_file_name(source_path)
            copy2(source_path, target_dir / file_name)
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
