from __future__ import annotations

import math
import os
import re
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import ffmpeg

from pixelle_video.models.media_placement import MediaBox
from pixelle_video.models.render_execution_plan import RenderExecutionPlan
from pixelle_video.models.render_package import RenderManifest, VisualClip
from pixelle_video.models.size_contract import (
    MAX_GENERATION_EDGE_PX,
    MAX_GENERATION_PIXELS,
)
from pixelle_video.render_backend import FFMPEG_MANIFEST_RENDER_BACKEND
from pixelle_video.services.font_discovery import (
    canonical_font_family_name,
    discover_font_options,
    font_family_from_file,
    missing_font_characters,
    resolve_font_file,
)
from pixelle_video.services.font_resolver import FontResolver
from pixelle_video.services.layered_template_adapters.ffmpeg_manifest import (
    LayeredTemplateFfmpegAdapter,
)
from pixelle_video.services.render_output_probe import (
    RenderOutputContractError,
    RenderOutputProbe,
)
from pixelle_video.services.video import VideoService
from pixelle_video.utils.ffmpeg_encoder import get_h264_backend


class FfmpegManifestRenderer:
    """Compose a manifest on one continuous timeline and encode it once."""

    def __init__(
        self,
        *,
        video_service: VideoService | None = None,
        output_probe: RenderOutputProbe | None = None,
    ) -> None:
        self.video_service = video_service or VideoService()
        self.output_probe = output_probe or RenderOutputProbe()

    def render(
        self,
        *,
        manifest: RenderManifest,
        execution_plan: RenderExecutionPlan,
        output_path: str,
        ass_path: str | None = None,
        bgm_path: str | None = None,
        bgm_volume: float = 0.2,
        bgm_mode: str = "loop",
    ) -> str:
        if execution_plan.effective_backend != FFMPEG_MANIFEST_RENDER_BACKEND:
            raise ValueError(
                "FfmpegManifestRenderer requires effective_backend=ffmpeg_manifest"
            )

        output = Path(output_path).resolve()
        report_path = output.with_name(f"{output.stem}.render_probe.json")
        manifest = LayeredTemplateFfmpegAdapter().prepare_manifest(manifest)
        clips = list(manifest.visual_clips)
        duration = self._validate_contract(
            manifest=manifest,
            clips=clips,
            output_path=output_path,
            ass_path=ass_path,
            bgm_path=bgm_path,
            bgm_volume=bgm_volume,
            bgm_mode=bgm_mode,
            report_path=report_path,
        )
        actual_master_duration = self.output_probe.media_duration(
            manifest.master_audio_path,
            stream_type="audio",
        )
        if (
            abs(actual_master_duration - duration)
            > RenderOutputProbe.DURATION_TOLERANCE_SECONDS
        ):
            raise ValueError(
                "master audio duration does not match the canonical timeline: "
                f"audio={actual_master_duration}, timeline={duration}"
            )
        frame_counts = self._allocate_clip_frame_counts(
            clips=clips,
            duration=duration,
            fps=manifest.fps,
        )

        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_output = output.with_name(
            f".{output.stem}.{uuid.uuid4().hex}.rendering{output.suffix}"
        )
        subtitle_end = self._subtitle_end(manifest) if ass_path else None

        try:
            with self._resolved_ass_fonts_dir(
                manifest,
                output.parent,
                ass_path=Path(ass_path).resolve() if ass_path else None,
            ) as fonts_dir:
                encoder_backend = self._encode_once(
                    clips=clips,
                    frame_counts=frame_counts,
                    manifest=manifest,
                    duration=duration,
                    output_path=temporary_output,
                    ass_path=Path(ass_path).resolve() if ass_path else None,
                    fonts_dir=fonts_dir,
                    bgm_path=Path(bgm_path).resolve() if bgm_path else None,
                    bgm_volume=float(bgm_volume),
                    bgm_mode=bgm_mode,
                )
            try:
                self.output_probe.validate(
                    output_path=temporary_output,
                    width=manifest.canvas_width,
                    height=manifest.canvas_height,
                    fps=manifest.fps,
                    duration=duration,
                    subtitle_end=subtitle_end,
                    report_path=report_path,
                    encoder_backend=encoder_backend,
                    lossy_encode_count=1,
                )
            except RenderOutputContractError as exc:
                if encoder_backend == "libx264" or not exc.encoder_sensitive:
                    raise
                self.video_service.reject_render_encoder(
                    encoder_backend,
                    reason="encoded artifact failed the final output contract",
                )
                if temporary_output.exists():
                    temporary_output.unlink()
                with self._resolved_ass_fonts_dir(
                    manifest,
                    output.parent,
                    ass_path=Path(ass_path).resolve() if ass_path else None,
                ) as fonts_dir:
                    encoder_backend = self._encode_once(
                        clips=clips,
                        frame_counts=frame_counts,
                        manifest=manifest,
                        duration=duration,
                        output_path=temporary_output,
                        ass_path=Path(ass_path).resolve() if ass_path else None,
                        fonts_dir=fonts_dir,
                        bgm_path=Path(bgm_path).resolve() if bgm_path else None,
                        bgm_volume=float(bgm_volume),
                        bgm_mode=bgm_mode,
                    )
                self.output_probe.validate(
                    output_path=temporary_output,
                    width=manifest.canvas_width,
                    height=manifest.canvas_height,
                    fps=manifest.fps,
                    duration=duration,
                    subtitle_end=subtitle_end,
                    report_path=report_path,
                    encoder_backend=encoder_backend,
                    lossy_encode_count=1,
                )
            os.replace(temporary_output, output)
            self.output_probe.validate(
                output_path=output,
                width=manifest.canvas_width,
                height=manifest.canvas_height,
                fps=manifest.fps,
                duration=duration,
                subtitle_end=subtitle_end,
                report_path=report_path,
                encoder_backend=encoder_backend,
                lossy_encode_count=1,
            )
            return str(output)
        finally:
            if temporary_output.exists():
                temporary_output.unlink()

    def _encode_once(
        self,
        *,
        clips: list[VisualClip],
        frame_counts: list[int],
        manifest: RenderManifest,
        duration: float,
        output_path: Path,
        ass_path: Path | None,
        fonts_dir: Path | None,
        bgm_path: Path | None,
        bgm_volume: float,
        bgm_mode: str,
    ) -> str:
        with self._visual_timeline_stream(
            clips=clips,
            frame_counts=frame_counts,
            width=manifest.canvas_width,
            height=manifest.canvas_height,
            fps=manifest.fps,
            working_dir=output_path.parent,
        ) as video_stream:
            if ass_path is not None:
                ass_options: dict[str, str] = {"filename": str(ass_path)}
                if fonts_dir is not None:
                    ass_options["fontsdir"] = str(fonts_dir)
                video_stream = video_stream.filter("ass", **ass_options)

            audio_stream = self._master_audio_stream(
                Path(manifest.master_audio_path).resolve(),
                duration=duration,
            )
            if bgm_path is not None:
                bgm_stream = self._bgm_stream(
                    bgm_path,
                    duration=duration,
                    volume=bgm_volume,
                    mode=bgm_mode,
                )
                audio_stream = ffmpeg.filter(
                    [audio_stream, bgm_stream],
                    "amix",
                    inputs=2,
                    duration="first",
                    dropout_transition=0,
                    normalize=0,
                )

            def _build_output(**encoder_kwargs):
                codec = str(encoder_kwargs.get("vcodec") or "")
                projection = get_h264_backend(codec).render_graph_projection()
                projected_video = video_stream
                if projection.input_pixel_format is not None:
                    projected_video = projected_video.filter(
                        "format",
                        projection.input_pixel_format,
                    )
                if projection.requires_hardware_upload:
                    projected_video = projected_video.filter("hwupload")
                output_options: dict[str, object] = {
                    "acodec": "aac",
                    "audio_bitrate": "192k",
                    "ar": 48000,
                    "ac": 2,
                    "r": manifest.fps,
                    "vsync": "cfr",
                    "t": _format_time(duration),
                    "movflags": "+faststart",
                    "color_range": "tv",
                    "colorspace": "bt709",
                    "color_primaries": "bt709",
                    "color_trc": "bt709",
                    **encoder_kwargs,
                }
                if projection.output_pixel_format is not None:
                    output_options["pix_fmt"] = projection.output_pixel_format
                return ffmpeg.output(
                    projected_video,
                    audio_stream,
                    str(output_path),
                    **output_options,
                ).global_args(
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    *projection.global_args,
                ).overwrite_output()

            return self.video_service.encode_render_graph(_build_output)

    @contextmanager
    def _visual_timeline_stream(
        self,
        *,
        clips: list[VisualClip],
        frame_counts: list[int],
        width: int,
        height: int,
        fps: int,
        working_dir: Path,
    ):
        has_shared_box, shared_box = self._shared_media_box(clips)
        if (
            len(clips) > 1
            and all(clip.media_type == "image" for clip in clips)
            and has_shared_box
        ):
            concat_path = working_dir / f".pixelle-{uuid.uuid4().hex}.ffconcat"
            lines = ["ffconcat version 1.0"]
            for clip, frame_count in zip(clips, frame_counts):
                lines.append(f"file '{_escape_ffconcat_path(clip.media_path)}'")
                lines.append(f"duration {_format_time(frame_count / fps)}")
            lines.append(f"file '{_escape_ffconcat_path(clips[-1].media_path)}'")
            concat_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            try:
                source = ffmpeg.input(
                    str(concat_path),
                    format="concat",
                    safe=0,
                ).video
                yield self._normalize_visual_stream(
                    source,
                    frame_count=sum(frame_counts),
                    width=width,
                    height=height,
                    fps=fps,
                    media_box=shared_box,
                )
            finally:
                if concat_path.exists():
                    concat_path.unlink()
            return

        streams = [
            self._visual_stream(
                clip,
                frame_count=frame_count,
                width=width,
                height=height,
                fps=fps,
            )
            for clip, frame_count in zip(clips, frame_counts)
        ]
        yield streams[0] if len(streams) == 1 else ffmpeg.concat(*streams, v=1, a=0).node[0]

    @staticmethod
    def _shared_media_box(
        clips: list[VisualClip],
    ) -> tuple[bool, MediaBox | None]:
        first = clips[0].resolved_media_box
        if all(clip.resolved_media_box == first for clip in clips[1:]):
            return True, first
        return False, None

    @staticmethod
    def _visual_stream(
        clip: VisualClip,
        *,
        frame_count: int,
        width: int,
        height: int,
        fps: int,
    ):
        if clip.media_type == "image":
            source = ffmpeg.input(clip.media_path, loop=1, framerate=fps).video
        else:
            source = ffmpeg.input(clip.media_path, stream_loop=-1).video
        return FfmpegManifestRenderer._normalize_visual_stream(
            source,
            frame_count=frame_count,
            width=width,
            height=height,
            fps=fps,
            media_box=clip.resolved_media_box,
        )

    @staticmethod
    def _normalize_visual_stream(
        source,
        *,
        frame_count: int,
        width: int,
        height: int,
        fps: int,
        media_box: MediaBox | None,
    ):
        box = media_box or MediaBox(
            width=width,
            height=height,
            left=0,
            top=0,
        )
        box_width = max(1, int(round(box.width)))
        box_height = max(1, int(round(box.height)))
        normalized = (
            source.filter("fps", fps=fps, round="near")
            .filter("trim", end_frame=frame_count)
            .filter("setpts", "PTS-STARTPTS")
        )
        scale_options: dict[str, object] = {
            "flags": "lanczos",
            "out_color_matrix": "bt709",
            "out_range": "tv",
        }
        if media_box is None:
            scale_options["force_original_aspect_ratio"] = "decrease"
        normalized = normalized.filter(
            "scale",
            box_width,
            box_height,
            **scale_options,
        )
        if media_box is None:
            normalized = normalized.filter(
                "pad",
                box_width,
                box_height,
                "(ow-iw)/2",
                "(oh-ih)/2",
                color="black",
            )
        normalized = normalized.filter("setsar", 1).filter("format", "yuv420p")
        if (
            box_width != width
            or box_height != height
            or round(box.left) != 0
            or round(box.top) != 0
        ):
            background = ffmpeg.input(
                f"color=c=black:s={width}x{height}:r={fps}",
                f="lavfi",
                t=_format_time(frame_count / fps),
            ).video
            normalized = ffmpeg.overlay(
                background,
                normalized,
                x=int(round(box.left)),
                y=int(round(box.top)),
                eof_action="pass",
                shortest=1,
            ).filter("setpts", "PTS-STARTPTS")
        return (
            normalized.filter("setsar", 1)
            .filter("format", "yuv420p")
            .filter(
                "setparams",
                range="tv",
                color_primaries="bt709",
                color_trc="bt709",
                colorspace="bt709",
            )
        )

    @staticmethod
    def _master_audio_stream(path: Path, *, duration: float):
        return (
            ffmpeg.input(str(path)).audio
            .filter("aresample", 48000)
            .filter("aformat", sample_fmts="fltp", channel_layouts="stereo")
            .filter("apad", whole_dur=_format_time(duration))
            .filter("atrim", duration=_format_time(duration))
            .filter("asetpts", "PTS-STARTPTS")
        )

    @staticmethod
    def _bgm_stream(
        path: Path,
        *,
        duration: float,
        volume: float,
        mode: str,
    ):
        input_kwargs = {"stream_loop": -1} if mode == "loop" else {}
        stream = (
            ffmpeg.input(str(path), **input_kwargs).audio
            .filter("aresample", 48000)
            .filter("aformat", sample_fmts="fltp", channel_layouts="stereo")
            .filter("volume", volume)
        )
        if mode == "once":
            stream = stream.filter("apad", whole_dur=_format_time(duration))
        return (
            stream.filter("atrim", duration=_format_time(duration))
            .filter("asetpts", "PTS-STARTPTS")
        )

    @staticmethod
    def _allocate_clip_frame_counts(
        *,
        clips: list[VisualClip],
        duration: float,
        fps: int,
    ) -> list[int]:
        total_frames = max(len(clips), int(math.ceil(duration * fps)))
        boundaries = [0]
        for index, clip in enumerate(clips[:-1], start=1):
            candidate = int(round(float(clip.end) * fps))
            lower = boundaries[-1] + 1
            upper = total_frames - (len(clips) - index)
            boundaries.append(min(max(candidate, lower), upper))
        boundaries.append(total_frames)
        return [right - left for left, right in zip(boundaries, boundaries[1:])]

    @staticmethod
    def _subtitle_end(manifest: RenderManifest) -> float | None:
        values = [float(cue.end) for cue in manifest.caption_cues]
        values.extend(float(cue.end) for cue in manifest.text_cues)
        return max(values) if values else None

    @contextmanager
    def _resolved_ass_fonts_dir(
        self,
        manifest: RenderManifest,
        output_dir: Path,
        *,
        ass_path: Path | None,
    ) -> Iterator[Path | None]:
        if ass_path is None:
            yield None
            return

        required_families = self._ass_font_requirements(ass_path)
        referenced: list[Path] = []
        for profile in manifest.text_style_profiles:
            expected_family = canonical_font_family_name(profile.font_family)
            if not profile.font_file or expected_family.casefold() not in required_families:
                continue
            font_path = resolve_font_file(profile.font_file)
            if font_path is None:
                raise ValueError(
                    f"font_file must resolve to an existing application asset: {profile.font_file}"
                )
            actual_family = font_family_from_file(font_path)
            if actual_family.casefold() != expected_family.casefold():
                raise ValueError(
                    "font family does not match font_file: "
                    f"expected {expected_family!r}, got {actual_family!r} from {font_path}"
                )
            referenced.append(font_path)

        resolved_families = {
            font_family_from_file(path).casefold()
            for path in referenced
        }
        resolver = FontResolver()
        options_by_family: dict[str, Path] = {}
        for candidate_dir in resolver.candidate_dirs:
            for option in discover_font_options([candidate_dir]):
                options_by_family.setdefault(
                    canonical_font_family_name(option.family).casefold(),
                    option.path.resolve(),
                )
        for family_key in sorted(required_families.keys() - resolved_families):
            font_path = options_by_family.get(family_key)
            if font_path is None:
                raise ValueError(
                    "ASS font family must resolve to a task or application font asset: "
                    f"{required_families[family_key]!r}"
                )
            referenced.append(font_path)

        paths_by_family: dict[str, Path] = {}
        for path in referenced:
            family_key = canonical_font_family_name(
                font_family_from_file(path)
            ).casefold()
            existing = paths_by_family.get(family_key)
            if existing is not None and existing != path:
                raise ValueError(
                    "ASS font family resolves to multiple font files: "
                    f"family={family_key!r}, files={[str(existing), str(path)]}"
                )
            paths_by_family[family_key] = path
        for family_key, requirement in required_families.items():
            missing = missing_font_characters(
                paths_by_family[family_key],
                requirement["text"],
            )
            if missing:
                raise ValueError(
                    "ASS font asset is missing required glyphs: "
                    f"family={requirement['family']!r}, characters={''.join(missing)!r}"
                )

        unique_fonts = list(dict.fromkeys(path.resolve() for path in referenced))
        if not unique_fonts:
            yield resolver.resolve_fontsdir()
            return
        parent_dirs = {path.parent for path in unique_fonts}
        if len(parent_dirs) == 1:
            yield next(iter(parent_dirs))
            return

        with tempfile.TemporaryDirectory(prefix="pixelle-render-fonts-", dir=output_dir) as raw_dir:
            font_dir = Path(raw_dir)
            for index, font_path in enumerate(unique_fonts):
                shutil.copy2(font_path, font_dir / f"{index:03d}-{font_path.name}")
            yield font_dir

    @staticmethod
    def _ass_font_requirements(ass_path: Path) -> dict[str, dict[str, str]]:
        styles: dict[str, str] = {}
        requirements: dict[str, dict[str, str]] = {}
        content = ass_path.read_text(encoding="utf-8-sig")
        for line in content.splitlines():
            if line.startswith("Style:"):
                fields = line.removeprefix("Style:").split(",")
                if len(fields) >= 2:
                    family = canonical_font_family_name(fields[1].strip())
                    if family:
                        styles[fields[0].strip()] = family
                        requirements.setdefault(
                            family.casefold(),
                            {"family": family, "text": ""},
                        )
            if not line.startswith("Dialogue:"):
                continue
            fields = line.removeprefix("Dialogue:").split(",", 9)
            if len(fields) < 10:
                continue
            style_name = fields[3].strip()
            if re.search(r"\\fn", fields[9]):
                raise ValueError(
                    "ASS inline font overrides are forbidden; use a resolved text style profile"
                )
            cue_text = re.sub(r"\{[^}]*\}", "", fields[9]).replace(r"\N", "\n")
            family = styles.get(style_name)
            if family:
                requirements[family.casefold()]["text"] += cue_text
        return requirements

    @staticmethod
    def _validate_contract(
        *,
        manifest: RenderManifest,
        clips: list[VisualClip],
        output_path: str,
        ass_path: str | None,
        bgm_path: str | None,
        bgm_volume: float,
        bgm_mode: str,
        report_path: Path,
    ) -> float:
        if manifest.canvas_width <= 0 or manifest.canvas_height <= 0:
            raise ValueError("ffmpeg_manifest requires positive canvas dimensions")
        if manifest.canvas_width % 2 or manifest.canvas_height % 2:
            raise ValueError("ffmpeg_manifest requires even canvas dimensions")
        if (
            manifest.canvas_width > MAX_GENERATION_EDGE_PX
            or manifest.canvas_height > MAX_GENERATION_EDGE_PX
            or manifest.canvas_width * manifest.canvas_height > MAX_GENERATION_PIXELS
        ):
            raise ValueError("ffmpeg_manifest canvas exceeds the render resource budget")
        if manifest.fps <= 0:
            raise ValueError("ffmpeg_manifest requires a positive frame rate")
        if not clips:
            raise ValueError("ffmpeg_manifest requires at least one visual clip")
        if manifest.version == "render_manifest.v2" and any(
            clip.resolved_media_box is None for clip in clips
        ):
            raise ValueError(
                "render_manifest.v2 requires a resolved_media_box for every visual clip"
            )
        if not manifest.master_audio_path:
            raise ValueError("ffmpeg_manifest requires master audio")

        master_audio = Path(manifest.master_audio_path).resolve()
        if not master_audio.is_file():
            raise ValueError(f"master audio must be an existing file: {master_audio}")
        inputs = {master_audio}
        previous_end = 0.0
        for index, clip in enumerate(clips):
            if clip.media_type not in {"image", "video"}:
                raise ValueError(
                    f"visual clip {clip.id!r} has unsupported media_type={clip.media_type!r}"
                )
            media_path = Path(clip.media_path).resolve()
            if not media_path.is_file():
                raise ValueError(f"visual clip media must be an existing file: {media_path}")
            inputs.add(media_path)
            start = _finite_float(clip.start)
            end = _finite_float(clip.end)
            if end <= start:
                raise ValueError(f"visual clip {clip.id!r} must have a positive duration")
            if index == 0 and abs(start) > 0.001:
                raise ValueError("visual timeline must start at zero")
            if index > 0 and abs(start - previous_end) > 0.001:
                raise ValueError(
                    "visual timeline must be continuous: "
                    f"clip {clip.id!r} starts at {start}, previous clip ends at {previous_end}"
                )
            previous_end = end

        duration = _finite_float(manifest.master_audio_duration)
        if duration <= 0:
            duration = previous_end
        if duration <= 0:
            raise ValueError("ffmpeg_manifest requires a positive master duration")
        if abs(previous_end - duration) > RenderOutputProbe.DURATION_TOLERANCE_SECONDS:
            raise ValueError(
                "visual timeline must end at the master duration: "
                f"visual={previous_end}, master={duration}"
            )

        output = Path(output_path).resolve()
        for label, value in (("ass_path", ass_path), ("bgm_path", bgm_path)):
            if value is None:
                continue
            path = Path(value).resolve()
            if not path.is_file():
                raise ValueError(f"{label} must be an existing file: {path}")
            if output == path:
                raise ValueError(f"output_path cannot overwrite {label}")
            inputs.add(path)
        if output in inputs:
            raise ValueError("output_path cannot overwrite a render input")
        if report_path.resolve() in inputs:
            raise ValueError("render probe report cannot overwrite a render input")
        if bgm_path is not None:
            if bgm_mode not in {"once", "loop"}:
                raise ValueError("bgm_mode must be 'once' or 'loop'")
            volume = _finite_float(bgm_volume)
            if not 0.0 <= volume <= 1.0:
                raise ValueError("bgm_volume must be between 0 and 1")
        return duration


def _finite_float(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return number


def _format_time(value: float) -> str:
    return f"{max(_finite_float(value), 0.0):.6f}".rstrip("0").rstrip(".") or "0"


def _escape_ffconcat_path(value: str) -> str:
    normalized = str(Path(value).resolve()).replace("\\", "/")
    return normalized.replace("'", "'\\''")


__all__ = ["FfmpegManifestRenderer"]
