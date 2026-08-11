from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: target block not found")
    return text.replace(old, new, 1)


def patch_video() -> None:
    path = Path("pixelle_video/services/video.py")
    text = path.read_text(encoding="utf-8")

    old_single = '''        if len(videos) == 1:
            logger.info(f"Only one video provided, copying to {output}")
            shutil.copy(videos[0], output)
            return output

        self._ensure_ffmpeg()
'''
    new_single = '''        if len(videos) == 1:
            if bgm_path:
                logger.info(
                    "Only one video provided; applying requested BGM without concat"
                )
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

        self._ensure_ffmpeg()
'''
    text = replace_once(text, old_single, new_single, "single-video BGM routing")

    old_concat = '''        self._ensure_ffmpeg()
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
    new_concat = '''        self._ensure_ffmpeg()
        try:
            with tempfile.TemporaryDirectory(dir=get_temp_path()) as temp_dir:
                normalized_videos = [
                    self._ensure_concat_audio_track(
                        video,
                        temp_dir=temp_dir,
                        index=index,
                    )
                    for index, video in enumerate(videos)
                ]
                n = len(normalized_videos)
                stream_spec = "".join([f"[{i}:v][{i}:a]" for i in range(n)])
                filter_complex = f"{stream_spec}concat=n={n}:v=1:a=1[v][a]"

                def _build_concat_command(encode_args: tuple[str, ...]) -> list[str]:
                    command = ["ffmpeg"]
                    for normalized_video in normalized_videos:
                        command.extend(["-i", normalized_video])
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

    def _ensure_concat_audio_track(
        self,
        video: str,
        *,
        temp_dir: str,
        index: int,
    ) -> str:
        """Return an input with an audio stream without re-encoding video frames."""

        if self.has_audio_stream(video):
            return video

        import subprocess

        normalized = str(Path(temp_dir) / f"concat_audio_{index:04d}.mp4")
        command = [
            "ffmpeg",
            "-y",
            "-i",
            video,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            normalized,
        ]
        try:
            subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            reason = exc.stderr or str(exc)
            raise RuntimeError(
                f"Failed to synthesize silent concat audio track: {reason}"
            ) from exc
        return normalized
'''
    text = replace_once(text, old_concat, new_concat, "silent concat normalization")

    old_overlay_head = '''            input_video = ffmpeg.input(video)
            input_overlay = ffmpeg.input(overlay_image)
'''
    new_overlay_head = '''            video_has_audio = self.has_audio_stream(video)
            input_video = ffmpeg.input(video)
            input_overlay = ffmpeg.input(overlay_image)
'''
    text = replace_once(text, old_overlay_head, new_overlay_head, "overlay audio probe")

    old_overlay_output = '''            def _make_overlay_output(**kw):
                return (
                    ffmpeg.output(
                        output_stream,
                        output,
                        pix_fmt="yuv420p",
                        **kw,
                    )
                    .overwrite_output()
                )
'''
    new_overlay_output = '''            def _make_overlay_output(**kw):
                streams = [output_stream]
                output_kwargs: dict[str, object] = {
                    "pix_fmt": "yuv420p",
                    **kw,
                }
                if video_has_audio:
                    streams.append(input_video.audio)
                    output_kwargs["acodec"] = "copy"
                return (
                    ffmpeg.output(
                        *streams,
                        output,
                        **output_kwargs,
                    )
                    .overwrite_output()
                )
'''
    text = replace_once(text, old_overlay_output, new_overlay_output, "overlay audio preservation")
    path.write_text(text, encoding="utf-8")


def patch_standard_pipeline() -> None:
    path = Path("pixelle_video/pipelines/standard.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''            expected_duration=master_audio_duration,
            expect_audio=bool(master_audio_path),
            use_gpu=True,
        )
''',
        '''            expected_duration=master_audio_duration,
            expect_audio=bool(master_audio_path),
        )
''',
        "HyperFrames GPU override",
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_video()
    patch_standard_pipeline()


if __name__ == "__main__":
    main()
