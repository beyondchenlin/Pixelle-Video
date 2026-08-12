from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont

from pixelle_video.models.render_package import RenderManifest, TextCue
from pixelle_video.models.text_style import TextStyleProfile
from pixelle_video.services.ass_style_builder import AssStyleBuilder, ass_alignment
from pixelle_video.services.font_discovery import (
    canonical_font_family_name,
    discover_font_options,
    resolve_font_file,
)
from pixelle_video.services.text_content_sanitizer import TextContentSanitizer
from pixelle_video.services.text_layout_planner import wrap_by_character_limit
from pixelle_video.services.text_style_resolver import TextStyleResolver


@dataclass(frozen=True)
class AssExportOutputs:
    master: Path
    subtitle_only: Path
    overlay_only: Path
    diagnostics: dict | None = None


@dataclass(frozen=True)
class _ResolvedAssCue:
    cue: TextCue
    profile: TextStyleProfile


class AssTextAdapter:
    """Export compiled text cues to ASS subtitle files."""

    def __init__(
        self,
        *,
        text_sanitizer: TextContentSanitizer | None = None,
    ) -> None:
        self.text_sanitizer = text_sanitizer or TextContentSanitizer()
        self._half_leading_cache: dict[tuple[object, ...], int] = {}

    def export(self, *, manifest: RenderManifest, output_dir: str | Path) -> AssExportOutputs:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)

        tracks = {
            track.id: track
            for track in manifest.text_tracks
            if track.enabled and "ass" in track.renderer_targets
        }
        cues = [cue for cue in manifest.text_cues if cue.track_id in tracks]
        resolver = TextStyleResolver(profiles=manifest.text_style_profiles)
        resolved_cues = [
            _ResolvedAssCue(
                cue=cue,
                profile=resolver.resolve_for_cue(cue=cue, track=tracks[cue.track_id]),
            )
            for cue in cues
        ]

        master = target / "master.ass"
        subtitle_only = target / "subtitle_only.ass"
        overlay_only = target / "overlay_only.ass"
        master.write_text(
            self._render_ass(resolved_cues, manifest=manifest), encoding="utf-8"
        )
        subtitle_only.write_text(
            self._render_ass(
                [item for item in resolved_cues if item.cue.role == "subtitle"],
                manifest=manifest,
            ),
            encoding="utf-8",
        )
        overlay_only.write_text(
            self._render_ass(
                [item for item in resolved_cues if item.cue.role != "subtitle"],
                manifest=manifest,
            ),
            encoding="utf-8",
        )
        return AssExportOutputs(
            master=master,
            subtitle_only=subtitle_only,
            overlay_only=overlay_only,
            diagnostics=self._copy_diagnostics(resolver.diagnostics),
        )

    def _render_ass(
        self, cues: list[_ResolvedAssCue], *, manifest: RenderManifest
    ) -> str:
        lines = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "ScaledBorderAndShadow: yes",
            f"PlayResX: {manifest.canvas_width}",
            f"PlayResY: {manifest.canvas_height}",
            "",
            "[V4+ Styles]",
            (
                "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, "
                "BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, "
                "MarginL, MarginR, MarginV, Encoding"
            ),
        ]
        builder = AssStyleBuilder()
        referenced_profiles: dict[str, TextStyleProfile] = {}
        for item in cues:
            referenced_profiles.setdefault(item.profile.id, item.profile)
        for profile_id, profile in referenced_profiles.items():
            lines.append(
                builder.build_style(
                    profile_id,
                    profile,
                    canvas_width=manifest.canvas_width,
                    canvas_height=manifest.canvas_height,
                    project_css_pixel_units=manifest.version == "render_manifest.v2",
                )
            )
        lines.extend(
            [
                "",
                "[Events]",
                (
                    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
                    "MarginV, Effect, Text"
                ),
            ]
        )

        for item in cues:
            lines.extend(self._render_dialogue_lines(item, manifest=manifest))
        return "\n".join(lines) + "\n"

    def _render_dialogue_lines(
        self,
        item: _ResolvedAssCue,
        *,
        manifest: RenderManifest,
    ) -> list[str]:
        cue = item.cue
        normalized_text = (cue.text or "").replace("\r\n", "\n").replace("\r", "\n")
        if manifest.version == "render_manifest.v2":
            normalized_text = self.text_sanitizer.sanitize(normalized_text).display_text
            if item.profile.max_chars_per_line:
                normalized_text = "\n".join(
                    wrap_by_character_limit(
                        normalized_text,
                        item.profile.max_chars_per_line,
                    )
                )
        visible_lines = normalized_text.split("\n")
        if manifest.version != "render_manifest.v2" or len(visible_lines) == 1:
            return [self._dialogue(cue, item.profile.id, self._escape_text(normalized_text))]

        scale = item.profile.scale_for_canvas(
            manifest.canvas_width,
            manifest.canvas_height,
        )
        line_step = max(
            1,
            int(round(item.profile.font_size * item.profile.line_height * scale)),
        )
        alignment = ass_alignment(item.profile)
        positions = self._line_anchor_positions(
            profile=item.profile,
            line_count=len(visible_lines),
            line_step=line_step,
            canvas_width=manifest.canvas_width,
            canvas_height=manifest.canvas_height,
            scale=scale,
        )
        return [
            self._dialogue(
                cue,
                item.profile.id,
                rf"{{\an{alignment}\pos({x},{y})}}{self._escape_text(line)}",
            )
            for line, (x, y) in zip(visible_lines, positions)
        ]

    def _dialogue(self, cue: TextCue, profile_id: str, text: str) -> str:
        return (
            "Dialogue: "
            f"{cue.layer},{self._format_time(cue.start)},"
            f"{self._format_time(cue.end)},{profile_id},,0,0,0,,{text}"
        )

    def _line_anchor_positions(
        self,
        *,
        profile: TextStyleProfile,
        line_count: int,
        line_step: int,
        canvas_width: int,
        canvas_height: int,
        scale: float,
    ) -> list[tuple[int, int]]:
        margin_x = int(round(profile.margin_x * scale))
        margin_y = int(round(profile.margin_y * scale))
        x = {
            "left": margin_x,
            "center": int(round(canvas_width / 2)),
            "right": canvas_width - margin_x,
        }[profile.alignment]

        if profile.position in {"top", "top_left", "top_right"}:
            y_values = [margin_y + index * line_step for index in range(line_count)]
        elif profile.position == "center":
            center = canvas_height / 2
            first = center - ((line_count - 1) * line_step / 2)
            y_values = [int(round(first + index * line_step)) for index in range(line_count)]
        else:
            anchor_offset = self._css_negative_half_leading(
                profile=profile,
                scale=scale,
            )
            bottom = canvas_height - margin_y + anchor_offset
            y_values = [
                bottom - (line_count - 1 - index) * line_step
                for index in range(line_count)
            ]
        return [(x, int(y)) for y in y_values]

    def _css_negative_half_leading(
        self,
        *,
        profile: TextStyleProfile,
        scale: float,
    ) -> int:
        cache_key = (
            profile.font_file,
            profile.font_family,
            profile.font_size,
            profile.line_height,
            scale,
        )
        cached = self._half_leading_cache.get(cache_key)
        if cached is not None:
            return cached
        font_path = resolve_font_file(profile.font_file)
        if font_path is None:
            expected_family = canonical_font_family_name(profile.font_family).casefold()
            font_path = next(
                (
                    option.path
                    for option in discover_font_options()
                    if canonical_font_family_name(option.family).casefold()
                    == expected_family
                ),
                None,
            )
        if font_path is None:
            self._half_leading_cache[cache_key] = 0
            return 0

        rendered_font_size = max(1, int(round(profile.font_size * scale)))
        try:
            ascent, descent = ImageFont.truetype(
                str(font_path),
                size=rendered_font_size,
            ).getmetrics()
        except (OSError, ValueError):
            self._half_leading_cache[cache_key] = 0
            return 0
        css_line_height = profile.font_size * profile.line_height * scale
        offset = max(0, int(round((ascent + descent - css_line_height) / 2)))
        self._half_leading_cache[cache_key] = offset
        return offset

    def _format_time(self, value: float) -> str:
        total_centiseconds = max(0, int(round(float(value) * 100)))
        hours, remainder = divmod(total_centiseconds, 360000)
        minutes, remainder = divmod(remainder, 6000)
        seconds, centiseconds = divmod(remainder, 100)
        return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

    def _escape_text(self, text: str) -> str:
        return (
            (text or "")
            .replace("\\", r"\\")
            .replace("{", r"\{")
            .replace("}", r"\}")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\n", r"\N")
        )

    def _copy_diagnostics(self, diagnostics: dict) -> dict:
        return {
            key: [dict(item) for item in value] if isinstance(value, list) else value
            for key, value in diagnostics.items()
        }
