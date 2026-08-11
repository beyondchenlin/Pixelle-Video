from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: target block not found")
    return text.replace(old, new, 1)


def patch_video() -> None:
    path = Path("pixelle_video/services/video.py")
    text = path.read_text(encoding="utf-8")

    old_imports = '''from pixelle_video.services.font_resolver import FontResolver
from pixelle_video.utils.ffmpeg_encoder import (
    disable_ffmpeg_h264_encoder,
    ffmpeg_h264_fallback_kwargs,
    ffmpeg_h264_output_kwargs,
    resolve_ffmpeg_h264_encoder,
)
'''
    new_imports = '''from pixelle_video.services.ffmpeg_h264_executor import FfmpegH264Executor
from pixelle_video.services.font_resolver import FontResolver
'''
    text = replace_once(text, old_imports, new_imports, "video encoder imports")

    old_init = '''    def __init__(self) -> None:
        self._ffmpeg_checked = False
        self._ffmpeg_check_lock = threading.Lock()
'''
    new_init = '''    def __init__(self) -> None:
        self._ffmpeg_checked = False
        self._ffmpeg_check_lock = threading.Lock()
        self._h264_executor = FfmpegH264Executor()
'''
    text = replace_once(text, old_init, new_init, "video executor init")

    old_encode = '''    @staticmethod
    def _h264_encode_params() -> dict[str, object]:
        return ffmpeg_h264_output_kwargs(resolve_ffmpeg_h264_encoder())

    def _encode_run(self, build_output, *, quiet=False):
        params = self._h264_encode_params()
        extra: dict[str, bool] = {"capture_stdout": True, "capture_stderr": True}
        if quiet:
            extra["quiet"] = True
        try:
            build_output(**params).run(**extra)
        except ffmpeg.Error as hardware_exc:
            vcodec = str(params.get("vcodec") or "")
            if vcodec == "libx264":
                raise

            logger.warning(
                "Hardware encoder {} failed; validating the same task with CPU libx264",
                vcodec,
            )
            try:
                build_output(**ffmpeg_h264_fallback_kwargs()).run(**extra)
            except ffmpeg.Error:
                # The task itself is not proven valid. Do not poison the process-wide
                # hardware capability cache for an input/filter/output failure.
                raise

            stderr = getattr(hardware_exc, "stderr", None)
            if isinstance(stderr, bytes):
                reason = stderr.decode("utf-8", errors="replace")
            else:
                reason = str(stderr or hardware_exc)
            reason = " ".join(reason.strip().split())[-400:]
            disable_ffmpeg_h264_encoder(
                vcodec,
                reason=reason or "hardware-specific runtime encode failure",
            )
            logger.warning(
                "CPU fallback succeeded; disabled hardware encoder {} for this process",
                vcodec,
            )
'''
    new_encode = '''    def _h264_encode_params(self) -> dict[str, object]:
        return self._h264_executor.selected_output_kwargs()

    def _encode_run(self, build_output, *, quiet=False):
        self._h264_executor.run_output(
            build_output,
            quiet=quiet,
            selected_params=self._h264_encode_params(),
        )
'''
    text = replace_once(text, old_encode, new_encode, "video encode delegation")

    old_burn = '''        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            (
                ffmpeg.input(str(input_path))
                .output(str(output_path), vf=ass_filter, acodec="copy")
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            logger.success(f"ASS subtitles burned into video: {output_path}")
            return output
        except ffmpeg.Error as e:
'''
    new_burn = '''        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            input_stream = ffmpeg.input(str(input_path))

            def _make_subtitle_output(**kw):
                return (
                    input_stream.output(
                        str(output_path),
                        vf=ass_filter,
                        acodec="copy",
                        pix_fmt="yuv420p",
                        **kw,
                    )
                    .overwrite_output()
                )

            self._encode_run(_make_subtitle_output)
            logger.success(f"ASS subtitles burned into video: {output_path}")
            return output
        except ffmpeg.Error as e:
'''
    text = replace_once(text, old_burn, new_burn, "subtitle executor routing")

    old_concat_body = '''        self._ensure_ffmpeg()
        try:
            # Build filter_complex string manually
            n = len(videos)

            # Build input stream labels: [0:v][0:a][1:v][1:a]...
            stream_spec = "".join([f"[{i}:v][{i}:a]" for i in range(n)])
            filter_complex = f"{stream_spec}concat=n={n}:v=1:a=1[v][a]"

            # Build ffmpeg command
            cmd = ["ffmpeg"]
            for video in videos:
                cmd.extend(["-i", video])
            cmd.extend(
                [
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "[v]",
                    "-map",
                    "[a]",
                    "-y",  # Overwrite output
                    output,
                ]
            )

            # Run command
            import subprocess

            subprocess.run(cmd, capture_output=True, text=True, check=True)

            logger.success(f"Videos concatenated successfully: {output}")
            return output
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            logger.error(f"FFmpeg concat filter error: {error_msg}")
            raise RuntimeError(f"Failed to concatenate videos: {error_msg}")
        except Exception as e:
            logger.error(f"Concatenation error: {e}")
            raise RuntimeError(f"Failed to concatenate videos: {e}")
'''
    new_concat_body = '''        self._ensure_ffmpeg()
        try:
            n = len(videos)
            stream_spec = "".join([f"[{i}:v][{i}:a]" for i in range(n)])
            filter_complex = f"{stream_spec}concat=n={n}:v=1:a=1[v][a]"

            def _build_concat_command(encode_args: tuple[str, ...]) -> list[str]:
                command = ["ffmpeg"]
                for video in videos:
                    command.extend(["-i", video])
                command.extend(
                    [
                        "-filter_complex",
                        filter_complex,
                        "-map",
                        "[v]",
                        "-map",
                        "[a]",
                        *encode_args,
                        "-pix_fmt",
                        "yuv420p",
                        "-y",
                        output,
                    ]
                )
                return command

            self._h264_executor.run_command(_build_concat_command)
            logger.success(f"Videos concatenated successfully: {output}")
            return output
        except Exception as e:
            logger.error(f"Concatenation error: {e}")
            raise RuntimeError(f"Failed to concatenate videos: {e}") from e
'''
    text = replace_once(text, old_concat_body, new_concat_body, "concat executor routing")

    old_overlay = '''            # Overlay the transparent image on top of the scaled video
            output_stream = ffmpeg.overlay(scaled_video, input_overlay)

            (
                ffmpeg.output(
                    output_stream,
                    output,
                    vcodec="libx264",
                    pix_fmt="yuv420p",
                    preset="medium",
                    crf=23,
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )

            logger.success(f"Image overlaid on video: {output}")
'''
    new_overlay = '''            # Overlay the transparent image on top of the scaled video
            output_stream = ffmpeg.overlay(scaled_video, input_overlay)

            def _make_overlay_output(**kw):
                return (
                    ffmpeg.output(
                        output_stream,
                        output,
                        pix_fmt="yuv420p",
                        **kw,
                    )
                    .overwrite_output()
                )

            self._encode_run(_make_overlay_output)

            logger.success(f"Image overlaid on video: {output}")
'''
    text = replace_once(text, old_overlay, new_overlay, "overlay executor routing")
    path.write_text(text, encoding="utf-8")


def patch_element_renderer() -> None:
    path = Path("pixelle_video/services/element_animation_renderer.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, "import subprocess\n", "", "remove element subprocess import")
    text = replace_once(
        text,
        '''from pixelle_video.services.element_animation_presets import sample_transform
from pixelle_video.utils.ffmpeg_encoder import resolve_ffmpeg_h264_encoder
''',
        '''from pixelle_video.services.element_animation_presets import sample_transform
from pixelle_video.services.ffmpeg_h264_executor import FfmpegH264Executor
''',
        "element executor import",
    )

    class_head = '''class PythonElementAnimationRenderer:
    def render_frame(
'''
    new_class_head = '''class PythonElementAnimationRenderer:
    def __init__(self, *, h264_executor: FfmpegH264Executor | None = None) -> None:
        self._h264_executor = h264_executor or FfmpegH264Executor()

    def render_frame(
'''
    text = replace_once(text, class_head, new_class_head, "element executor init")

    old_command = '''            command = [
                "ffmpeg",
                "-y",
                "-framerate",
                str(manifest.timeline.fps),
                "-i",
                str(frame_pattern),
            ]
            if manifest.audio_path and Path(manifest.audio_path).exists():
                command.extend(["-i", manifest.audio_path])

            vcodec = resolve_ffmpeg_h264_encoder()
            command.extend(["-c:v", vcodec, "-pix_fmt", "yuv420p"])
            if manifest.audio_path and Path(manifest.audio_path).exists():
                command.extend(["-c:a", "aac"])
            command.extend(["-t", str(manifest.timeline.duration)])
            command.append(str(output))

            subprocess.run(command, check=True)
'''
    new_command = '''            has_audio = bool(
                manifest.audio_path and Path(manifest.audio_path).exists()
            )

            def _build_element_command(encode_args: tuple[str, ...]) -> list[str]:
                command = [
                    "ffmpeg",
                    "-y",
                    "-framerate",
                    str(manifest.timeline.fps),
                    "-i",
                    str(frame_pattern),
                ]
                if has_audio:
                    command.extend(["-i", str(manifest.audio_path)])
                command.extend([*encode_args, "-pix_fmt", "yuv420p"])
                if has_audio:
                    command.extend(["-c:a", "aac"])
                command.extend(["-t", str(manifest.timeline.duration), str(output)])
                return command

            self._h264_executor.run_command(_build_element_command)
'''
    text = replace_once(text, old_command, new_command, "element executor routing")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_video()
    patch_element_renderer()


if __name__ == "__main__":
    main()
