import json
import shutil
import wave
from pathlib import Path

import ffmpeg
import pytest
from PIL import Image

from pixelle_video.models.media_placement import MediaBox
from pixelle_video.models.render_execution_plan import RenderExecutionPlan
from pixelle_video.models.render_package import CaptionCue, RenderManifest, VisualClip
from pixelle_video.services.ffmpeg_manifest_renderer import FfmpegManifestRenderer
from pixelle_video.services.render_output_probe import RenderOutputContractError


def _layered_template_spec_payload() -> dict:
    return {
        "version": "layered_template.v1",
        "template_id": "portrait_news",
        "template_name": "Portrait News",
        "template_type": "image",
        "canvas_width": 1080,
        "canvas_height": 1920,
        "media_width": 1080,
        "media_height": 1920,
        "safe_area": {"x": 64, "y": 64, "width": 952, "height": 1792, "unit": "px"},
        "layers": [
            {
                "id": "media",
                "type": "generated_media",
                "name": "Generated media",
                "rect": {"x": 64, "y": 220, "width": 952, "height": 1180, "unit": "px"},
                "z_index": 10,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": {
                    "kind": "generated_media",
                    "ref": "generated://primary",
                    "metadata": {},
                },
                "style": {"object_fit": "contain"},
                "role": None,
            }
        ],
        "metadata": {"orientation": "portrait"},
    }


def _execution_plan() -> RenderExecutionPlan:
    return RenderExecutionPlan(
        requested_backend="ffmpeg_manifest",
        effective_backend="ffmpeg_manifest",
    )


class _RecordingVideoService:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def encode_render_graph(self, build_output, *, quiet=False):
        graph = build_output(vcodec="libx264", preset="medium", crf=23)
        command = ffmpeg.compile(graph)
        self.commands.append(command)
        output = next(
            Path(item)
            for item in command
            if item.endswith(".mp4") and ".rendering.mp4" in item
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"encoded")
        return "libx264"


class _AcceptingProbe:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def validate(self, **kwargs):
        self.calls.append(kwargs)
        assert Path(kwargs["output_path"]).is_file()
        report_path = kwargs.get("report_path")
        if report_path:
            Path(report_path).write_text('{"ok": true}', encoding="utf-8")
        return object()

    def media_duration(self, media_path, *, stream_type):
        assert stream_type == "audio"
        return float(Path(media_path).read_text(encoding="utf-8"))


def _manifest(tmp_path: Path, *, clip_count: int = 2) -> RenderManifest:
    master_audio = tmp_path / "master.wav"
    master_audio.write_text(str(float(clip_count)), encoding="utf-8")
    clips = []
    for index in range(clip_count):
        media = tmp_path / f"frame-{index}.png"
        media.write_bytes(b"png")
        clips.append(
            VisualClip(
                id=f"clip-{index}",
                frame_index=index,
                start=float(index),
                end=float(index + 1),
                media_path=str(media),
                media_type="image",
            )
        )
    return RenderManifest(
        task_id="task-1",
        title="demo",
        width=320,
        height=180,
        fps=30,
        template_id="image_default",
        master_audio_path=str(master_audio),
        master_audio_duration=float(clip_count),
        visual_clips=clips,
    )


@pytest.mark.parametrize("clip_count", [1, 2])
def test_renderer_uses_one_final_encode_for_single_and_multiple_clips(
    tmp_path,
    clip_count,
):
    video_service = _RecordingVideoService()
    probe = _AcceptingProbe()
    output_path = tmp_path / "final.mp4"

    result = FfmpegManifestRenderer(
        video_service=video_service,
        output_probe=probe,
    ).render(
        manifest=_manifest(tmp_path, clip_count=clip_count),
        execution_plan=_execution_plan(),
        output_path=str(output_path),
    )

    assert result == str(output_path.resolve())
    assert len(video_service.commands) == 1
    command = " ".join(video_service.commands[0])
    assert "segment_" not in command
    assert "pcm_s16le" not in command
    assert output_path.is_file()
    assert (tmp_path / "final.render_probe.json").is_file()
    assert len(probe.calls) == 2


def test_large_image_timeline_uses_bounded_concat_input_command(tmp_path):
    frame = tmp_path / "shared-frame.png"
    frame.write_bytes(b"png")
    clip_count = 500
    manifest = _manifest(tmp_path, clip_count=1)
    manifest.master_audio_path = str(tmp_path / "long-master.wav")
    Path(manifest.master_audio_path).write_text(str(float(clip_count)), encoding="utf-8")
    manifest.master_audio_duration = float(clip_count)
    manifest.visual_clips = [
        VisualClip(
            id=f"clip-{index}",
            frame_index=index,
            start=float(index),
            end=float(index + 1),
            media_path=str(frame),
            media_type="image",
        )
        for index in range(clip_count)
    ]
    service = _RecordingVideoService()

    FfmpegManifestRenderer(
        video_service=service,
        output_probe=_AcceptingProbe(),
    ).render(
        manifest=manifest,
        execution_plan=_execution_plan(),
        output_path=str(tmp_path / "final.mp4"),
    )

    command = service.commands[0]
    assert command.count("-i") == 2
    assert len(" ".join(command)) < 5000


def test_renderer_composes_subtitles_and_bgm_before_the_only_encode(tmp_path):
    video_service = _RecordingVideoService()
    probe = _AcceptingProbe()
    manifest = _manifest(tmp_path)
    ass_path = tmp_path / "captions.ass"
    bgm_path = tmp_path / "music.wav"
    ass_path.write_text("[Script Info]\n", encoding="utf-8")
    bgm_path.write_bytes(b"music")

    result = FfmpegManifestRenderer(
        video_service=video_service,
        output_probe=probe,
    ).render(
        manifest=manifest,
        execution_plan=_execution_plan(),
        output_path=str(tmp_path / "final.mp4"),
        ass_path=str(ass_path),
        bgm_path=str(bgm_path),
        bgm_volume=0.35,
        bgm_mode="once",
    )

    command = " ".join(video_service.commands[0])
    assert result == str((tmp_path / "final.mp4").resolve())
    assert len(video_service.commands) == 1
    assert "ass=" in command
    assert "amix=" in command
    assert "volume=0.35" in command
    assert "final_text_burned.mp4" not in command


def test_renderer_consumes_resolved_media_box_instead_of_reinterpreting_geometry(
    tmp_path,
):
    manifest = _manifest(tmp_path, clip_count=1)
    manifest.visual_clips[0].resolved_media_box = MediaBox(
        width=160,
        height=90,
        left=24,
        top=18,
    )
    service = _RecordingVideoService()

    FfmpegManifestRenderer(
        video_service=service,
        output_probe=_AcceptingProbe(),
    ).render(
        manifest=manifest,
        execution_plan=_execution_plan(),
        output_path=str(tmp_path / "final.mp4"),
    )

    command = " ".join(service.commands[0])
    assert "overlay=eof_action=pass:shortest=1:x=24:y=18" in command
    assert "scale=160:90" in command
    assert "force_original_aspect_ratio" not in command


def test_renderer_rejects_unresolved_ass_font_before_encoding(tmp_path):
    ass_path = tmp_path / "captions.ass"
    ass_path.write_text(
        "[V4+ Styles]\n"
        "Style: Default,Definitely Missing Font,36,&H00FFFFFF\n",
        encoding="utf-8",
    )
    service = _RecordingVideoService()

    with pytest.raises(ValueError, match="must resolve"):
        FfmpegManifestRenderer(
            video_service=service,
            output_probe=_AcceptingProbe(),
        ).render(
            manifest=_manifest(tmp_path, clip_count=1),
            execution_plan=_execution_plan(),
            output_path=str(tmp_path / "final.mp4"),
            ass_path=str(ass_path),
        )

    assert service.commands == []


def test_renderer_rejects_ass_font_without_required_glyphs(tmp_path):
    ass_path = tmp_path / "captions.ass"
    ass_path.write_text(
        "[V4+ Styles]\n"
        "Style: Default,Noto Sans SC,36,&H00FFFFFF\n"
        "[Events]\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,emoji 😀\n",
        encoding="utf-8",
    )
    service = _RecordingVideoService()

    with pytest.raises(ValueError, match="missing required glyphs"):
        FfmpegManifestRenderer(
            video_service=service,
            output_probe=_AcceptingProbe(),
        ).render(
            manifest=_manifest(tmp_path, clip_count=1),
            execution_plan=_execution_plan(),
            output_path=str(tmp_path / "final.mp4"),
            ass_path=str(ass_path),
        )

    assert service.commands == []


def test_renderer_rejects_timeline_gap_before_encoding(tmp_path):
    manifest = _manifest(tmp_path)
    manifest.visual_clips[1].start = 1.2
    service = _RecordingVideoService()

    with pytest.raises(ValueError, match="continuous"):
        FfmpegManifestRenderer(
            video_service=service,
            output_probe=_AcceptingProbe(),
        ).render(
            manifest=manifest,
            execution_plan=_execution_plan(),
            output_path=str(tmp_path / "final.mp4"),
        )

    assert service.commands == []


def test_renderer_rejects_unresolved_geometry_in_v2_manifest(tmp_path):
    manifest = _manifest(tmp_path, clip_count=1)
    manifest.version = "render_manifest.v2"

    with pytest.raises(ValueError, match="resolved_media_box"):
        FfmpegManifestRenderer(output_probe=_AcceptingProbe()).render(
            manifest=manifest,
            execution_plan=_execution_plan(),
            output_path=str(tmp_path / "final.mp4"),
        )


def test_renderer_rejects_output_that_would_overwrite_an_input(tmp_path):
    manifest = _manifest(tmp_path, clip_count=1)

    with pytest.raises(ValueError, match="cannot overwrite"):
        FfmpegManifestRenderer().render(
            manifest=manifest,
            execution_plan=_execution_plan(),
            output_path=manifest.visual_clips[0].media_path,
        )


def test_renderer_rejects_probe_report_that_would_overwrite_an_input(tmp_path):
    manifest = _manifest(tmp_path, clip_count=1)
    report_input = tmp_path / "final.render_probe.json"
    report_input.write_bytes(b"image")
    manifest.visual_clips[0].media_path = str(report_input)

    with pytest.raises(ValueError, match="probe report cannot overwrite"):
        FfmpegManifestRenderer(output_probe=_AcceptingProbe()).render(
            manifest=manifest,
            execution_plan=_execution_plan(),
            output_path=str(tmp_path / "final.mp4"),
        )


def test_renderer_rejects_master_audio_duration_drift_before_encoding(tmp_path):
    manifest = _manifest(tmp_path, clip_count=1)
    manifest.master_audio_path = str(tmp_path / "wrong-duration.wav")
    Path(manifest.master_audio_path).write_text("1.5", encoding="utf-8")
    service = _RecordingVideoService()

    with pytest.raises(ValueError, match="master audio duration"):
        FfmpegManifestRenderer(
            video_service=service,
            output_probe=_AcceptingProbe(),
        ).render(
            manifest=manifest,
            execution_plan=_execution_plan(),
            output_path=str(tmp_path / "final.mp4"),
        )

    assert service.commands == []


def test_renderer_retries_with_software_when_hardware_artifact_breaks_contract(
    tmp_path,
):
    class FallbackVideoService(_RecordingVideoService):
        def __init__(self):
            super().__init__()
            self.codecs = ["h264_nvenc", "libx264"]
            self.rejected = []

        def encode_render_graph(self, build_output, *, quiet=False):
            codec = self.codecs[len(self.commands)]
            graph = build_output(vcodec=codec)
            command = ffmpeg.compile(graph)
            self.commands.append(command)
            output = next(
                Path(item)
                for item in command
                if item.endswith(".mp4") and ".rendering.mp4" in item
            )
            output.write_bytes(b"encoded")
            return codec

        def reject_render_encoder(self, codec, *, reason):
            self.rejected.append((codec, reason))

    class RejectFirstProbe(_AcceptingProbe):
        def validate(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise RenderOutputContractError(
                    "color_space mismatch: expected bt709, got missing",
                    errors=("color_space mismatch: expected bt709, got missing",),
                )
            report_path = kwargs.get("report_path")
            if report_path:
                Path(report_path).write_text('{"ok": true}', encoding="utf-8")
            return object()

    service = FallbackVideoService()
    probe = RejectFirstProbe()

    FfmpegManifestRenderer(video_service=service, output_probe=probe).render(
        manifest=_manifest(tmp_path, clip_count=1),
        execution_plan=_execution_plan(),
        output_path=str(tmp_path / "final.mp4"),
    )

    assert len(service.commands) == 2
    assert service.rejected == [
        ("h264_nvenc", "encoded artifact failed the final output contract")
    ]
    assert probe.calls[-1]["encoder_backend"] == "libx264"


def test_renderer_does_not_blame_hardware_for_timeline_contract_failures(tmp_path):
    class HardwareVideoService(_RecordingVideoService):
        def encode_render_graph(self, build_output, *, quiet=False):
            graph = build_output(vcodec="h264_nvenc")
            command = ffmpeg.compile(graph)
            self.commands.append(command)
            output = next(
                Path(item)
                for item in command
                if item.endswith(".mp4") and ".rendering.mp4" in item
            )
            output.write_bytes(b"encoded")
            return "h264_nvenc"

        def reject_render_encoder(self, codec, *, reason):
            raise AssertionError("timeline failures must not disable hardware")

    class TimelineFailureProbe(_AcceptingProbe):
        def validate(self, **kwargs):
            raise RenderOutputContractError(
                "audio duration mismatch: expected 1.0, got 0.5",
                errors=("audio duration mismatch: expected 1.0, got 0.5",),
            )

    service = HardwareVideoService()
    with pytest.raises(RenderOutputContractError, match="audio duration mismatch"):
        FfmpegManifestRenderer(
            video_service=service,
            output_probe=TimelineFailureProbe(),
        ).render(
            manifest=_manifest(tmp_path, clip_count=1),
            execution_plan=_execution_plan(),
            output_path=str(tmp_path / "final.mp4"),
        )

    assert len(service.commands) == 1


def test_renderer_rejects_unprerendered_layered_template_visuals(tmp_path):
    manifest = _manifest(tmp_path, clip_count=1)
    manifest.layered_template_spec = _layered_template_spec_payload()

    with pytest.raises(ValueError, match="prerendered template_frame assets"):
        FfmpegManifestRenderer().render(
            manifest=manifest,
            execution_plan=_execution_plan(),
            output_path=str(tmp_path / "final.mp4"),
        )


def test_renderer_accepts_prerendered_layered_template_visuals(tmp_path):
    manifest = _manifest(tmp_path, clip_count=1)
    manifest.layered_template_spec = _layered_template_spec_payload()
    manifest.visual_clips[0].source_kind = "template_frame"
    service = _RecordingVideoService()

    result = FfmpegManifestRenderer(
        video_service=service,
        output_probe=_AcceptingProbe(),
    ).render(
        manifest=manifest,
        execution_plan=_execution_plan(),
        output_path=str(tmp_path / "final.mp4"),
    )

    assert result == str((tmp_path / "final.mp4").resolve())
    assert len(service.commands) == 1


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg runtime is required",
)
def test_real_renderer_meets_timeline_encoding_color_and_subtitle_contract(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("PIXELLE_FFMPEG_H264_ENCODER", "libx264")
    red = tmp_path / "第一帧.png"
    blue = tmp_path / "第二帧.png"
    Image.new("RGB", (320, 180), (255, 0, 0)).save(red)
    Image.new("RGB", (320, 180), (0, 0, 255)).save(blue)

    master_audio = tmp_path / "主音轨.wav"
    with wave.open(str(master_audio), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(b"\0\0\0\0" * int(2.4 * 48000))

    ass_dir = tmp_path / "字幕 空格"
    ass_dir.mkdir()
    ass_path = ass_dir / "主字幕.ass"
    ass_path.write_text(
        "\n".join(
            [
                "[Script Info]",
                "ScriptType: v4.00+",
                "PlayResX: 320",
                "PlayResY: 180",
                "",
                "[V4+ Styles]",
                "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
                "Style: Default,Noto Sans SC,36,&H00FFFFFF,&H00000000,&H00000000,0,0,1,1,0,2,10,10,10,1",
                "",
                "[Events]",
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
                "Dialogue: 0,0:00:00.40,0:00:02.20,Default,,0,0,0,,字幕,comma",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = RenderManifest(
        task_id="real-contract",
        title="demo",
        width=320,
        height=180,
        fps=30,
        template_id="image_default",
        master_audio_path=str(master_audio),
        master_audio_duration=2.4,
        caption_cues=[
            CaptionCue(id="caption", text="字幕,comma", start=0.4, end=2.2)
        ],
        visual_clips=[
            VisualClip(
                id="red",
                frame_index=0,
                start=0.0,
                end=1.2,
                media_path=str(red),
                media_type="image",
            ),
            VisualClip(
                id="blue",
                frame_index=1,
                start=1.2,
                end=2.4,
                media_path=str(blue),
                media_type="image",
            ),
        ],
    )
    output = tmp_path / "final.mp4"

    result = FfmpegManifestRenderer().render(
        manifest=manifest,
        execution_plan=_execution_plan(),
        output_path=str(output),
        ass_path=str(ass_path),
    )

    report = json.loads((tmp_path / "final.render_probe.json").read_text(encoding="utf-8"))
    assert result == str(output.resolve())
    assert report["ok"] is True
    assert (report["width"], report["height"]) == (320, 180)
    assert report["fps"] == pytest.approx(30.0)
    assert report["pixel_format"] == "yuv420p"
    assert report["color_space"] == "bt709"
    assert report["audio_duration"] == pytest.approx(2.4, abs=0.055)
    assert list(tmp_path.glob("*.mp4")) == [output]
