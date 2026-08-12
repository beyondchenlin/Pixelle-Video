from __future__ import annotations

import ffmpeg

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
            raise ffmpeg.Error("ffmpeg", b"", b"nvenc workload failed")


def test_real_workload_failure_disables_hardware_for_process(monkeypatch) -> None:
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
