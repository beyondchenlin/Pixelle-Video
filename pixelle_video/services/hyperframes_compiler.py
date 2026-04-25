from __future__ import annotations

from html import escape
from pathlib import Path
from shutil import copy2

from pixelle_video.models.template_render_context import TemplateRenderContext


class HyperFramesCompiler:
    def __init__(
        self,
        template_root: Path | None = None,
        runtime_root: Path | None = None,
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
            "__ELEMENT_ANIMATION_MANIFEST__": context.element_animation_manifest_path or "",
        }

        compiled_index = self._replace_placeholders(index_template, replacements)
        compiled_captions = self._replace_placeholders(captions_template, replacements)
        compiled_text_layer = self._replace_placeholders(text_layer_template, replacements)

        (project_dir / "compositions").mkdir(parents=True, exist_ok=True)
        self._copy_runtime_assets(project_dir)
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
            rendered.append(
                (
                    f'<div id="{escape(clip.id, quote=True)}" class="clip visual-clip" '
                    f'data-start="{clip.start}" '
                    f'data-duration="{duration}" data-track-index="{track_index}">'
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
        rendered: list[str] = []
        for cue in context.captions:
            duration = max(float(cue.end) - float(cue.start), 0.1)
            rendered.append(
                (
                    f'<div id="{escape(cue.id, quote=True)}" class="clip caption-group" '
                    f'data-start="{cue.start}" '
                    f'data-duration="{duration}" '
                    'data-track-index="1">'
                    f'<div class="caption-text">{escape(cue.text)}</div>'
                    "</div>"
                )
            )
        return "".join(rendered)

    def _render_text_cues(self, context: TemplateRenderContext) -> str:
        tracks = {track.id: track for track in context.text_tracks if track.enabled}
        rendered: list[str] = []
        for cue in context.text_cues:
            track = tracks.get(cue.track_id)
            if track is None or "hyperframes" not in track.renderer_targets:
                continue

            duration = max(float(cue.end) - float(cue.start), 0.1)
            rendered.append(
                (
                    f'<div id="{escape(cue.id, quote=True)}" '
                    f'class="clip text-cue text-cue--{escape(cue.role, quote=True)}" '
                    f'data-start="{cue.start}" data-duration="{duration}" '
                    f'data-track-id="{escape(cue.track_id, quote=True)}" '
                    f'data-role="{escape(cue.role, quote=True)}" '
                    f'data-slot="{escape(cue.slot or "center", quote=True)}" '
                    f'data-layer="{cue.layer}">'
                    f'<span class="text-cue__content">{escape(cue.text)}</span>'
                    "</div>"
                )
            )
        return "".join(rendered)

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

    @staticmethod
    def _replace_placeholders(template: str, replacements: dict[str, str]) -> str:
        compiled = template
        for placeholder, value in replacements.items():
            compiled = compiled.replace(placeholder, value)
        return compiled
