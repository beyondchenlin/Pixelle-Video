from __future__ import annotations

import math
import subprocess
from pathlib import Path

from pixelle_video.models.render_execution_plan import RenderExecutionPlan
from pixelle_video.models.render_package import RenderManifest, VisualClip
from pixelle_video.render_backend import FFMPEG_MANIFEST_RENDER_BACKEND
from pixelle_video.services.video import VideoService


class FfmpegManifestRenderer:
    def __init__(self, *, video_service: VideoService | None = None):
        self.video_service = video_service or VideoService()

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

        clips = list(manifest.visual_clips)
        if not clips:
            raise ValueError("ffmpeg_manifest requires at least one visual clip")

        if len(clips) == 1:
            clip_output_path = output_path
            if bgm_path:
                output = Path(output_path)
                clip_output_path = str(
                    output.with_name(f"{output.stem}_no_bgm{output.suffix}")
                )
            rendered = self._render_single_clip(
                clips[0],
                manifest=manifest,
                output_path=clip_output_path,
            )
            if bgm_path:
                rendered = self._add_bgm_to_video(
                    video_path=rendered,
                    bgm_path=bgm_path,
                    output_path=output_path,
                    bgm_volume=bgm_volume,
                    bgm_mode=bgm_mode,
                )
        else:
            rendered = self._render_multiple_clips(
                clips,
                manifest=manifest,
                output_path=output_path,
                bgm_path=bgm_path,
                bgm_volume=bgm_volume,
                bgm_mode=bgm_mode,
            )

        if ass_path:
            burned_path = str(Path(output_path).with_name("final_text_burned.mp4"))
            return self.video_service.burn_ass_subtitles(
                rendered,
                ass_path,
                burned_path,
            )
        return rendered

    def _render_single_clip(
        self,
        clip: VisualClip,
        *,
        manifest: RenderManifest,
        output_path: str,
    ) -> str:
        if not manifest.master_audio_path:
            raise ValueError("ffmpeg_manifest single clip path requires master audio")
        if clip.media_type == "image":
            return self.video_service.create_video_from_image(
                image=clip.media_path,
                audio=manifest.master_audio_path,
                output=output_path,
                fps=manifest.fps,
            )
        return self.video_service.merge_audio_video(
            video=clip.media_path,
            audio=manifest.master_audio_path,
            output=output_path,
            replace_audio=True,
            audio_volume=1.0,
        )

    def _render_multiple_clips(
        self,
        clips: list[VisualClip],
        *,
        manifest: RenderManifest,
        output_path: str,
        bgm_path: str | None,
        bgm_volume: float,
        bgm_mode: str,
    ) -> str:
        temp_dir = Path(output_path).with_suffix("")
        temp_dir.mkdir(parents=True, exist_ok=True)
        segment_paths: list[str] = []
        for index, clip in enumerate(clips):
            segment_path = str(temp_dir / f"segment_{index:03d}.mp4")
            clip_audio_path = self._extract_clip_audio(
                manifest.master_audio_path,
                temp_dir / f"audio_{index:03d}.wav",
                start=clip.start,
                end=clip.end,
            )
            if clip.media_type == "image":
                self.video_service.create_video_from_image(
                    image=clip.media_path,
                    audio=clip_audio_path,
                    output=segment_path,
                    fps=manifest.fps,
                )
            else:
                self.video_service.merge_audio_video(
                    video=clip.media_path,
                    audio=clip_audio_path,
                    output=segment_path,
                    replace_audio=True,
                    audio_volume=1.0,
                )
            segment_paths.append(segment_path)

        return self.video_service.concat_videos(
            segment_paths,
            output_path,
            method="filter",
            bgm_path=bgm_path,
            bgm_volume=bgm_volume,
            bgm_mode=bgm_mode,
        )

    def _add_bgm_to_video(
        self,
        *,
        video_path: str,
        bgm_path: str,
        output_path: str,
        bgm_volume: float,
        bgm_mode: str,
    ) -> str:
        bgm_resolver = getattr(self.video_service, "_add_bgm_to_video", None)
        if callable(bgm_resolver):
            return bgm_resolver(
                video_path,
                bgm_path,
                output_path,
                volume=bgm_volume,
                mode=bgm_mode,
            )
        return self.video_service.add_bgm(
            video=video_path,
            bgm=bgm_path,
            output=output_path,
            bgm_volume=bgm_volume,
            loop=(bgm_mode == "loop"),
        )

    def _extract_clip_audio(
        self,
        master_audio_path: str | None,
        output_path: Path,
        *,
        start: float,
        end: float,
    ) -> str:
        if not master_audio_path:
            raise ValueError("ffmpeg_manifest multiple clip path requires master audio")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        duration = max(_finite_float(end) - _finite_float(start), 0.001)
        command = [
            "ffmpeg",
            "-y",
            "-ss",
            self._format_time(start),
            "-i",
            master_audio_path,
            "-t",
            self._format_time(duration),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"failed to extract clip audio: {result.stderr}")
        return str(output_path)

    @staticmethod
    def _format_time(value: float) -> str:
        number = max(_finite_float(value), 0.0)
        return f"{number:.3f}".rstrip("0").rstrip(".") or "0"


def _finite_float(value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return number
