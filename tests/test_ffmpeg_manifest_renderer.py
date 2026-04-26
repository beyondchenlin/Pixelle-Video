from pathlib import Path

import pytest

from pixelle_video.models.render_execution_plan import RenderExecutionPlan
from pixelle_video.models.render_package import RenderManifest, VisualClip
from pixelle_video.services.ffmpeg_manifest_renderer import FfmpegManifestRenderer


def _execution_plan() -> RenderExecutionPlan:
    return RenderExecutionPlan(
        requested_backend="ffmpeg_manifest",
        effective_backend="ffmpeg_manifest",
    )


def test_ffmpeg_manifest_renderer_uses_single_image_fast_path(tmp_path):
    calls = []

    class FakeVideoService:
        def create_video_from_image(self, image, audio, output, fps=30):
            calls.append(("image", image, audio, output, fps))
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_bytes(b"video")
            return output

    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        master_audio_path=str(tmp_path / "master.wav"),
        visual_clips=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0,
                end=2,
                media_path=str(tmp_path / "frame.png"),
                media_type="image",
            )
        ],
    )
    Path(manifest.master_audio_path).write_bytes(b"audio")
    Path(manifest.visual_clips[0].media_path).write_bytes(b"png")

    renderer = FfmpegManifestRenderer(video_service=FakeVideoService())
    output = renderer.render(
        manifest=manifest,
        execution_plan=_execution_plan(),
        output_path=str(tmp_path / "final.mp4"),
    )

    assert output == str(tmp_path / "final.mp4")
    assert calls == [
        (
            "image",
            str(tmp_path / "frame.png"),
            str(tmp_path / "master.wav"),
            str(tmp_path / "final.mp4"),
            30,
        )
    ]


def test_ffmpeg_manifest_renderer_uses_single_video_fast_path(tmp_path):
    calls = []

    class FakeVideoService:
        def merge_audio_video(self, **kwargs):
            calls.append(kwargs)
            Path(kwargs["output"]).parent.mkdir(parents=True, exist_ok=True)
            Path(kwargs["output"]).write_bytes(b"video")
            return kwargs["output"]

    master_audio = tmp_path / "master.wav"
    clip_video = tmp_path / "clip.mp4"
    master_audio.write_bytes(b"audio")
    clip_video.write_bytes(b"video")
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        master_audio_path=str(master_audio),
        visual_clips=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0,
                end=2,
                media_path=str(clip_video),
                media_type="video",
            )
        ],
    )

    renderer = FfmpegManifestRenderer(video_service=FakeVideoService())
    output = renderer.render(
        manifest=manifest,
        execution_plan=_execution_plan(),
        output_path=str(tmp_path / "final.mp4"),
    )

    assert output == str(tmp_path / "final.mp4")
    assert calls == [
        {
            "video": str(clip_video),
            "audio": str(master_audio),
            "output": str(tmp_path / "final.mp4"),
            "replace_audio": True,
            "audio_volume": 1.0,
        }
    ]


def test_ffmpeg_manifest_renderer_adds_bgm_for_single_clip(tmp_path):
    calls = []

    class FakeVideoService:
        def create_video_from_image(self, image, audio, output, fps=30):
            calls.append(("image", Path(output).name))
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_bytes(b"video")
            return output

        def _add_bgm_to_video(self, video, bgm_path, output, volume=0.2, mode="loop"):
            calls.append(("bgm", Path(video).name, bgm_path, Path(output).name, volume, mode))
            Path(output).write_bytes(b"bgm")
            return output

    master_audio = tmp_path / "master.wav"
    frame = tmp_path / "frame.png"
    master_audio.write_bytes(b"audio")
    frame.write_bytes(b"png")
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        master_audio_path=str(master_audio),
        visual_clips=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0,
                end=1,
                media_path=str(frame),
                media_type="image",
            )
        ],
    )

    output = FfmpegManifestRenderer(video_service=FakeVideoService()).render(
        manifest=manifest,
        execution_plan=_execution_plan(),
        output_path=str(tmp_path / "final.mp4"),
        bgm_path="calm.mp3",
        bgm_volume=0.4,
        bgm_mode="once",
    )

    assert output == str(tmp_path / "final.mp4")
    assert calls == [
        ("image", "final_no_bgm.mp4"),
        ("bgm", "final_no_bgm.mp4", "calm.mp3", "final.mp4", 0.4, "once"),
    ]


def test_ffmpeg_manifest_renderer_extracts_clip_audio_for_multiple_images(
    tmp_path,
    monkeypatch,
):
    calls = []
    commands = []

    class FakeVideoService:
        def create_video_from_image(self, image, audio, output, fps=30):
            calls.append(("image", Path(image).name, Path(audio).name, Path(output).name))
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_bytes(b"segment")
            return output

        def concat_videos(self, videos, output, **kwargs):
            calls.append(
                (
                    "concat",
                    [Path(item).name for item in videos],
                    Path(output).name,
                    kwargs,
                )
            )
            Path(output).write_bytes(b"final")
            return output

    def fake_run(command, capture_output=None, text=None, check=None):
        commands.append(command)
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_bytes(b"audio")
        return type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr(
        "pixelle_video.services.ffmpeg_manifest_renderer.subprocess.run",
        fake_run,
    )

    master_audio = tmp_path / "master.wav"
    master_audio.write_bytes(b"audio")
    frames = [tmp_path / "frame0.png", tmp_path / "frame1.png"]
    for frame in frames:
        frame.write_bytes(b"png")

    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        master_audio_path=str(master_audio),
        visual_clips=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0,
                end=1.5,
                media_path=str(frames[0]),
                media_type="image",
            ),
            VisualClip(
                id="clip-2",
                frame_index=1,
                start=1.5,
                end=3.0,
                media_path=str(frames[1]),
                media_type="image",
            ),
        ],
    )

    renderer = FfmpegManifestRenderer(video_service=FakeVideoService())
    renderer.render(
        manifest=manifest,
        execution_plan=_execution_plan(),
        output_path=str(tmp_path / "final.mp4"),
        bgm_path="bgm.mp3",
        bgm_volume=0.35,
        bgm_mode="once",
    )

    assert [command[command.index("-ss") + 1] for command in commands] == ["0", "1.5"]
    assert [command[command.index("-t") + 1] for command in commands] == ["1.5", "1.5"]
    assert calls[-1] == (
        "concat",
        ["segment_000.mp4", "segment_001.mp4"],
        "final.mp4",
        {
            "method": "filter",
            "bgm_path": "bgm.mp3",
            "bgm_volume": 0.35,
            "bgm_mode": "once",
        },
    )


def test_ffmpeg_manifest_renderer_burns_ass_after_render(tmp_path):
    calls = []

    class FakeVideoService:
        def create_video_from_image(self, image, audio, output, fps=30):
            calls.append(("image", output))
            Path(output).write_bytes(b"video")
            return output

        def burn_ass_subtitles(self, input_video, ass_file, output):
            calls.append(("ass", input_video, ass_file, output))
            Path(output).write_bytes(b"burned")
            return output

    master_audio = tmp_path / "master.wav"
    frame = tmp_path / "frame.png"
    ass = tmp_path / "captions.ass"
    master_audio.write_bytes(b"audio")
    frame.write_bytes(b"png")
    ass.write_text("[Script Info]\n", encoding="utf-8")
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        master_audio_path=str(master_audio),
        visual_clips=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0,
                end=1,
                media_path=str(frame),
                media_type="image",
            )
        ],
    )

    output = FfmpegManifestRenderer(video_service=FakeVideoService()).render(
        manifest=manifest,
        execution_plan=_execution_plan(),
        output_path=str(tmp_path / "final.mp4"),
        ass_path=str(ass),
    )

    assert output == str(tmp_path / "final_text_burned.mp4")
    assert calls[-1] == (
        "ass",
        str(tmp_path / "final.mp4"),
        str(ass),
        str(tmp_path / "final_text_burned.mp4"),
    )


def test_ffmpeg_manifest_renderer_requires_visual_clips(tmp_path):
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        master_audio_path=str(tmp_path / "master.wav"),
    )

    with pytest.raises(ValueError, match="at least one visual clip"):
        FfmpegManifestRenderer().render(
            manifest=manifest,
            execution_plan=_execution_plan(),
            output_path=str(tmp_path / "final.mp4"),
        )


def test_ffmpeg_manifest_renderer_requires_master_audio_for_single_clip(tmp_path):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png")
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        visual_clips=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0,
                end=1,
                media_path=str(frame),
                media_type="image",
            )
        ],
    )

    with pytest.raises(ValueError, match="requires master audio"):
        FfmpegManifestRenderer().render(
            manifest=manifest,
            execution_plan=_execution_plan(),
            output_path=str(tmp_path / "final.mp4"),
        )
