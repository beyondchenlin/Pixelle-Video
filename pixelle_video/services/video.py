# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Public video service with one H.264 re-encode execution boundary.

The stable media operations live in ``video_operations``. This facade preserves
all existing import paths while routing every inherited re-encode through
``UnifiedVideoEncoder`` and overriding the few historical entry points that
previously bypassed the encoder policy entirely.
"""

import shutil
from pathlib import Path
from typing import List, Literal, Optional

import ffmpeg
from loguru import logger

from pixelle_video.services.video_encoder_executor import UnifiedVideoEncoder
from pixelle_video.services.video_operations import (
    VideoService as _VideoOperations,
)
from pixelle_video.services.video_operations import (
    _ffmpeg_duration,
    check_ffmpeg,
)
from pixelle_video.utils.ffmpeg_encoder import (
    get_h264_backend,
    resolve_ffmpeg_h264_backend,
)


class VideoService(_VideoOperations):
    """Encoder-policy-aware facade for all video operations."""

    def __init__(self) -> None:
        super().__init__()
        self._video_encoder = UnifiedVideoEncoder()

    def _h264_encode_params(
        self,
        *,
        supports_hardware_frames: bool = False,
    ) -> dict[str, object]:
        backend = resolve_ffmpeg_h264_backend()
        # VAAPI needs a device and hwupload filter owned by raw execution paths.
        # Generic ffmpeg-python graphs therefore begin from CPU unless their
        # caller explicitly projects software frames into the backend contract.
        if backend.codec == "h264_vaapi" and not supports_hardware_frames:
            backend = get_h264_backend("libx264")
        return dict(backend.output_kwargs())

    def _encode_run(
        self,
        build_output,
        *,
        quiet=False,
        supports_hardware_frames: bool = False,
    ):
        return self._video_encoder.run_ffmpeg_python(
            build_output,
            quiet=quiet,
            preferred_params=self._h264_encode_params(
                supports_hardware_frames=supports_hardware_frames
            ),
        )

    def encode_render_graph(self, build_output, *, quiet: bool = False) -> str:
        """Encode one fully composed render graph through the shared H.264 policy."""

        self._ensure_ffmpeg()
        return self._encode_run(
            build_output,
            quiet=quiet,
            supports_hardware_frames=True,
        )

    def reject_render_encoder(self, codec: str, *, reason: str) -> None:
        """Disable a hardware encoder whose artifact failed the output contract."""

        self._video_encoder.disable_hardware_backend(codec, reason=reason)

    def concat_videos(
        self,
        videos: List[str],
        output: str,
        method: Literal["demuxer", "filter"] = "demuxer",
        bgm_path: Optional[str] = None,
        bgm_volume: float = 0.2,
        bgm_mode: Literal["once", "loop"] = "loop",
    ) -> str:
        if not videos:
            raise ValueError("Videos list cannot be empty")
        if len(videos) == 1:
            if bgm_path:
                self._ensure_ffmpeg()
                logger.info("Single video provided with BGM; applying BGM instead of bypassing it")
                return self._add_bgm_to_video(
                    video=videos[0],
                    bgm_path=bgm_path,
                    output=output,
                    volume=bgm_volume,
                    mode=bgm_mode,
                )
            logger.info(f"Only one video provided, copying to {output}")
            shutil.copy(videos[0], output)
            return output
        return super().concat_videos(
            videos,
            output,
            method=method,
            bgm_path=bgm_path,
            bgm_volume=bgm_volume,
            bgm_mode=bgm_mode,
        )

    def burn_ass_subtitles(
        self,
        input_video: str,
        ass_file: str,
        output: str,
        fonts_dir: str | Path | None = None,
        font_file: str | Path | None = None,
    ) -> str:
        input_path = Path(input_video).resolve()
        ass_path = Path(ass_file).resolve()
        output_path = Path(output).resolve()
        if input_path == output_path:
            raise ValueError("input_video and output cannot be the same path")
        if not input_path.is_file():
            raise ValueError(f"input_video must be an existing file: {input_video}")
        if not ass_path.is_file():
            raise ValueError(f"ass_file must be an existing file: {ass_file}")

        resolved_fonts_dir = self._resolve_ass_fonts_dir(fonts_dir, font_file)
        self._ensure_ffmpeg()
        ass_filter = self._build_ass_filter(ass_path, fonts_dir=resolved_fonts_dir)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        def _make_output(**kw):
            return (
                ffmpeg.input(str(input_path))
                .output(str(output_path), vf=ass_filter, acodec="copy", **kw)
                .overwrite_output()
            )

        try:
            self._encode_run(_make_output)
            logger.success(f"ASS subtitles burned into video: {output_path}")
            return output
        except ffmpeg.Error as exc:
            error_msg = (
                exc.stderr.decode("utf-8", errors="replace")
                if exc.stderr
                else str(exc)
            )
            logger.error(f"FFmpeg ASS burn-in error: {error_msg}")
            raise RuntimeError(f"Failed to burn ASS subtitles: {error_msg}") from exc

    def _concat_filter(self, videos: List[str], output: str) -> str:
        """Filter-concatenate while normalizing missing audio to silence."""

        self._ensure_ffmpeg()
        streams = []
        for video in videos:
            input_video = ffmpeg.input(video)
            streams.append(input_video.video)
            if self.has_audio_stream(video):
                audio = (
                    input_video.audio
                    .filter("aresample", 48000)
                    .filter(
                        "aformat",
                        sample_fmts="fltp",
                        channel_layouts="stereo",
                    )
                )
            else:
                duration = max(self._get_video_duration(video), 0.001)
                audio = ffmpeg.input(
                    "anullsrc=channel_layout=stereo:sample_rate=48000",
                    f="lavfi",
                    t=_ffmpeg_duration(duration),
                ).audio
            streams.append(audio)

        try:
            joined = ffmpeg.concat(*streams, v=1, a=1).node
            video_stream = joined[0]
            audio_stream = joined[1]

            def _make_output(**kw):
                return (
                    ffmpeg.output(
                        video_stream,
                        audio_stream,
                        output,
                        acodec="aac",
                        audio_bitrate="192k",
                        **kw,
                    )
                    .overwrite_output()
                )

            self._encode_run(_make_output)
            logger.success(f"Videos concatenated successfully: {output}")
            return output
        except ffmpeg.Error as exc:
            error_msg = exc.stderr.decode() if exc.stderr else str(exc)
            logger.error(f"FFmpeg concat filter error: {error_msg}")
            raise RuntimeError(f"Failed to concatenate videos: {error_msg}") from exc

    def overlay_image_on_video(
        self,
        video: str,
        overlay_image: str,
        output: str,
        scale_mode: str = "contain",
    ) -> str:
        self._ensure_ffmpeg()
        if scale_mode not in {"contain", "cover", "stretch"}:
            raise ValueError("scale_mode must be contain, cover, or stretch")
        logger.info(f"Overlaying image on video (scale_mode={scale_mode})")

        try:
            overlay_probe = ffmpeg.probe(overlay_image)
            overlay_stream = next(
                stream
                for stream in overlay_probe["streams"]
                if stream["codec_type"] == "video"
            )
            overlay_width = int(overlay_stream["width"])
            overlay_height = int(overlay_stream["height"])

            input_video = ffmpeg.input(video)
            input_overlay = ffmpeg.input(overlay_image)
            if scale_mode == "contain":
                scaled_video = input_video.filter(
                    "scale",
                    overlay_width,
                    overlay_height,
                    force_original_aspect_ratio="decrease",
                ).filter(
                    "pad",
                    overlay_width,
                    overlay_height,
                    "(ow-iw)/2",
                    "(oh-ih)/2",
                    color="black",
                )
            elif scale_mode == "cover":
                scaled_video = input_video.filter(
                    "scale",
                    overlay_width,
                    overlay_height,
                    force_original_aspect_ratio="increase",
                ).filter("crop", overlay_width, overlay_height)
            else:
                scaled_video = input_video.filter(
                    "scale",
                    overlay_width,
                    overlay_height,
                )

            output_stream = ffmpeg.overlay(scaled_video, input_overlay)
            has_audio = self.has_audio_stream(video)

            def _make_output(**kw):
                if has_audio:
                    return (
                        ffmpeg.output(
                            output_stream,
                            input_video.audio,
                            output,
                            pix_fmt="yuv420p",
                            acodec="copy",
                            **kw,
                        )
                        .overwrite_output()
                    )
                return (
                    ffmpeg.output(
                        output_stream,
                        output,
                        pix_fmt="yuv420p",
                        **kw,
                    )
                    .overwrite_output()
                )

            self._encode_run(_make_output)
            logger.success(f"Image overlaid on video: {output}")
            return output
        except ffmpeg.Error as exc:
            error_msg = exc.stderr.decode() if exc.stderr else str(exc)
            logger.error(f"FFmpeg overlay error: {error_msg}")
            raise RuntimeError(f"Failed to overlay image on video: {error_msg}") from exc


__all__ = ["VideoService", "check_ffmpeg"]
