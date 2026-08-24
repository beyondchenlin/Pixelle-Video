from __future__ import annotations

import subprocess
from pathlib import Path

import ffmpeg
import pytest

from pixelle_video.services.video_encoder_executor import (
    UnifiedVideoEncoder,
    reset_runtime_encoder_failures,
    runtime_disabled_hardware_codecs,
)
from pixelle_video.utils import ffmpeg_encoder as encoder_module
from pixelle_video.utils.ffmpeg_encoder import (
    Libx264Backend,
    NvencBackend,
    QsvBackend,
    VaapiBackend,
)


class _FakeOutput:
    def __init__(self, codec: str, attempts: list[str]) -> None:
        self.codec = codec
        self.attempts = attempts

    def run(self, **kwargs) -> None:
        self.attempts.append(self.codec)
        if self.codec == "h264_nvenc":
            raise ffmpeg.Error(
                "ffmpeg",
                b"",
                b"Cannot load libnvidia-encode.so.1",
            )


def test_real_workload_failure_disables_hardware_for_process(monkeypatch) -> None:
    monkeypatch.setattr(
        "pixelle_video.services.video_encoder_executor.available_h264_backends",
        lambda: (NvencBackend(), Libx264Backend()),
    )
    reset_runtime_encoder_failures()


def test_input_failure_falls_back_without_disabling_hardware(monkeypatch) -> None:
    class _InputFailureOutput:
        def __init__(self, codec: str, attempts: list[str]) -> None:
            self.codec = codec
            self.attempts = attempts

        def run(self, **_kwargs) -> None:
            self.attempts.append(self.codec)
            if self.codec == "h264_nvenc":
                raise ffmpeg.Error(
                    "ffmpeg",
                    b"",
                    b"input.mp4: Invalid data found when processing input",
                )

    monkeypatch.setattr(
        "pixelle_video.services.video_encoder_executor.available_h264_backends",
        lambda: (NvencBackend(), Libx264Backend()),
    )
    reset_runtime_encoder_failures()
    encoder = UnifiedVideoEncoder()

    first_attempts: list[str] = []
    selected = encoder.run_ffmpeg_python(
        lambda **params: _FakeOutput(str(params["vcodec"]), first_attempts),
        preferred_params=NvencBackend().output_kwargs(),
    )

    assert selected == "libx264"
    assert first_attempts == ["h264_nvenc", "libx264"]
    assert runtime_disabled_hardware_codecs() == ("h264_nvenc",)

    second_attempts: list[str] = []
    selected_again = encoder.run_ffmpeg_python(
        lambda **params: _FakeOutput(str(params["vcodec"]), second_attempts),
        preferred_params=NvencBackend().output_kwargs(),
    )

    assert selected_again == "libx264"
    assert second_attempts == ["libx264"]
    assert runtime_disabled_hardware_codecs() == ("h264_nvenc",)
    reset_runtime_encoder_failures()
    attempts: list[str] = []

    selected = UnifiedVideoEncoder().run_ffmpeg_python(
        lambda **params: _InputFailureOutput(str(params["vcodec"]), attempts),
        preferred_params=NvencBackend().output_kwargs(),
    )

    assert selected == "libx264"
    assert attempts == ["h264_nvenc", "libx264"]
    assert runtime_disabled_hardware_codecs() == ()


def test_png_sequence_replaces_existing_output_only_after_success(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pixelle_video.services.video_encoder_executor.available_h264_backends",
        lambda: (NvencBackend(), Libx264Backend()),
    )
    output = tmp_path / "result.mp4"
    output.write_bytes(b"existing")
    original_mode = output.stat().st_mode
    attempted_outputs: list[Path] = []

    def fake_run(command, *, check, capture_output, text):
        assert check is True
        assert capture_output is True
        assert text is True
        temporary_output = Path(command[-1])
        attempted_outputs.append(temporary_output)
        assert temporary_output != output
        temporary_output.write_bytes(b"partial")
        if "h264_nvenc" in command:
            raise subprocess.CalledProcessError(
                1,
                command,
                stderr="Cannot load libnvidia-encode.so.1",
            )
        temporary_output.write_bytes(b"complete")

    monkeypatch.setattr(
        "pixelle_video.services.video_encoder_executor.subprocess.run",
        fake_run,
    )
    reset_runtime_encoder_failures()

    result = UnifiedVideoEncoder().encode_png_sequence(
        frame_pattern=tmp_path / "frame_%06d.png",
        fps=24,
        output_path=output,
        duration=1.0,
    )

    assert result == str(output)
    assert output.read_bytes() == b"complete"
    assert output.stat().st_mode == original_mode
    assert len(attempted_outputs) == 2
    assert all(not path.exists() for path in attempted_outputs)
    assert list(tmp_path.iterdir()) == [output]
    reset_runtime_encoder_failures()


def test_png_sequence_cpu_failure_preserves_existing_output(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "pixelle_video.services.video_encoder_executor.available_h264_backends",
        lambda: (Libx264Backend(),),
    )
    output = tmp_path / "result.mp4"
    output.write_bytes(b"existing")
    temporary_outputs: list[Path] = []

    def fake_run(command, **_kwargs):
        temporary_output = Path(command[-1])
        temporary_outputs.append(temporary_output)
        temporary_output.write_bytes(b"partial")
        raise subprocess.CalledProcessError(1, command, stderr="disk full")

    monkeypatch.setattr(
        "pixelle_video.services.video_encoder_executor.subprocess.run",
        fake_run,
    )

    with pytest.raises(subprocess.CalledProcessError):
        UnifiedVideoEncoder().encode_png_sequence(
            frame_pattern=tmp_path / "frame_%06d.png",
            fps=24,
            output_path=output,
            duration=1.0,
        )

    assert output.read_bytes() == b"existing"
    assert len(temporary_outputs) == 1
    assert not temporary_outputs[0].exists()
    assert list(tmp_path.iterdir()) == [output]


def test_cpu_failure_is_not_silently_swallowed(monkeypatch) -> None:
    class _FailingCpuOutput:
        def run(self, **kwargs) -> None:
            raise ffmpeg.Error("ffmpeg", b"", b"cpu encode failed")

    monkeypatch.setattr(
        "pixelle_video.services.video_encoder_executor.available_h264_backends",
        lambda: (Libx264Backend(),),
    )
    reset_runtime_encoder_failures()
    encoder = UnifiedVideoEncoder()

    try:
        encoder.run_ffmpeg_python(lambda **params: _FailingCpuOutput())
    except ffmpeg.Error as exc:
        assert b"cpu encode failed" in exc.stderr
    else:
        raise AssertionError("CPU encoding failure must propagate")


def test_png_sequence_qsv_uses_backend_device_and_projection(monkeypatch, tmp_path):
    monkeypatch.setattr(
        encoder_module,
        "_resolve_qsv_device",
        lambda: "/dev/dri/renderD129",
    )

    command = UnifiedVideoEncoder()._png_sequence_command(
        backend=QsvBackend(),
        frame_pattern=tmp_path / "%08d.png",
        fps=30,
        output_path=tmp_path / "output.mp4",
        duration=1.0,
        audio_path=None,
    )

    assert command is not None
    assert command[2:4] == ["-qsv_device", "/dev/dri/renderD129"]
    assert "format=nv12" in command
    assert "-global_quality" in command
    assert "-pix_fmt" not in command


def test_png_sequence_vaapi_uses_backend_device_and_hardware_upload(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        encoder_module,
        "_resolve_vaapi_device",
        lambda: "/dev/dri/renderD129",
    )

    command = UnifiedVideoEncoder()._png_sequence_command(
        backend=VaapiBackend(),
        frame_pattern=tmp_path / "%08d.png",
        fps=30,
        output_path=tmp_path / "output.mp4",
        duration=1.0,
        audio_path=None,
    )

    assert command is not None
    assert command[2:4] == ["-vaapi_device", "/dev/dri/renderD129"]
    assert "format=nv12,hwupload" in command
    assert "-qp" in command
    assert "-pix_fmt" not in command


def test_generic_ffmpeg_graph_excludes_backends_that_require_projection(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "pixelle_video.services.video_encoder_executor.available_h264_backends",
        lambda: (QsvBackend(), VaapiBackend(), Libx264Backend()),
    )

    generic = UnifiedVideoEncoder()._ffmpeg_python_param_candidates(
        QsvBackend().output_kwargs(),
        supports_backend_projection=False,
    )
    projected = UnifiedVideoEncoder()._ffmpeg_python_param_candidates(
        None,
        supports_backend_projection=True,
    )

    assert [params["vcodec"] for params in generic] == ["libx264"]
    assert [params["vcodec"] for params in projected] == [
        "h264_qsv",
        "h264_vaapi",
        "libx264",
    ]
