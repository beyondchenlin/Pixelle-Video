from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pixelle_video.models.render_package import RenderManifest, TextCue


@dataclass(frozen=True)
class AssExportOutputs:
    master: Path
    subtitle_only: Path
    overlay_only: Path


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

        master = target / "master.ass"
        subtitle_only = target / "subtitle_only.ass"
        overlay_only = target / "overlay_only.ass"
        master.write_text(self._render_ass(cues, manifest=manifest), encoding="utf-8")
        subtitle_only.write_text(
            self._render_ass(
                [cue for cue in cues if cue.role == "subtitle"],
                manifest=manifest,
            ),
            encoding="utf-8",
        )
        overlay_only.write_text(
            self._render_ass(
                [cue for cue in cues if cue.role != "subtitle"],
                manifest=manifest,
            ),
            encoding="utf-8",
        )
        return AssExportOutputs(
            master=master,
            subtitle_only=subtitle_only,
            overlay_only=overlay_only,
        )

    def _render_ass(self, cues: list[TextCue], *, manifest: RenderManifest) -> str:
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
            (
                "Style: Default,Noto Sans CJK SC,64,&H00FFFFFF,&H80000000,"
                "&H40000000,1,0,1,2,0,2,80,80,140,1"
            ),
            (
                "Style: Overlay,Noto Sans CJK SC,76,&H00FFFFFF,&H80000000,"
                "&H40000000,1,0,1,2,0,5,80,80,80,1"
            ),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        for cue in cues:
            style = "Default" if cue.role == "subtitle" else "Overlay"
            lines.append(
                "Dialogue: "
                f"{cue.layer},{self._format_time(cue.start)},"
                f"{self._format_time(cue.end)},{style},,0,0,0,,"
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
            .replace(",", "，")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\n", r"\N")
        )
