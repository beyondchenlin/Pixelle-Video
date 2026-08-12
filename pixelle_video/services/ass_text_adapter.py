from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pixelle_video.models.render_package import RenderManifest, TextCue
from pixelle_video.models.text_style import TextStyleProfile
from pixelle_video.services.ass_style_builder import AssStyleBuilder
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
            cue = item.cue
            lines.append(
                "Dialogue: "
                f"{cue.layer},{self._format_time(cue.start)},"
                f"{self._format_time(cue.end)},{item.profile.id},,0,0,0,,"
                f"{self._escape_text(cue.text)}"
            )
        return "\n".join(lines) + "\n"

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
