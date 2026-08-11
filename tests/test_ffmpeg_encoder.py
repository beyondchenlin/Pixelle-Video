from __future__ import annotations

import subprocess

import pytest

from pixelle_video.utils import ffmpeg_encoder as encoder


@pytest.fixture(autouse=True)
def _reset_encoder_state(monkeypatch):
    monkeypatch.delenv("PIXELLE_FFMPEG_H264_ENCODER", raising=False)
    monkeypatch.delenv("PIXELLE_FFMPEG_VAAPI_DEVICE", raising=False)
    # Clear before each test. The monkeypatch fixture restores replaced probe
    # callables after the test, so the next test starts from real cached functions.
    encoder.clear_ffmpeg_h264_encoder_caches()


def test_backend_families_are_explicit_and_distinct() -> None:
    assert encoder.ffmpeg_h264_backend("libx264").family == "cpu"
    assert encoder.ffmpeg_h264_backend("h264_nvenc").family == "nvenc"
    assert encoder.ffmpeg_h264_backend("h264_qsv").family == "qsv"
    assert encoder.ffmpeg_h264_backend("h264_vaapi").family == "vaapi"
    assert encoder.ffmpeg_h264_backend("h264_vaapi").requires_hardware_frames is True


def test_cpu_output_kwargs_use_x264_quality_model() -> None:
    assert encoder.ffmpeg_h264_output_kwargs("libx264") == {
        "vcodec": "libx264",
        "preset": "medium",
        "crf": 23,
    }


def test_nvenc_output_kwargs_use_nvenc_quality_model_without_crf() -> None:
    params = encoder.ffmpeg_h264_output_kwargs("h264_nvenc")

    assert params == {
        "vcodec": "h264_nvenc",
        "preset": "p4",
        "cq": 23,
        "rc": "vbr",
        "b_ref_mode": "middle",
    }
    assert "crf" not in params


def test_qsv_output_kwargs_use_qsv_quality_model_without_nvenc_options() -> None:
    params = encoder.ffmpeg_h264_output_kwargs("h264_qsv")

    assert params == {
        "vcodec": "h264_qsv",
        "preset": "medium",
        "global_quality": 23,
    }
    for forbidden in ("p4", "rc", "cq", "b_ref_mode", "crf"):
        assert forbidden not in params.values()
        assert forbidden not in params


def test_vaapi_is_not_exposed_as_simple_software_frame_output() -> None:
    backend = encoder.ffmpeg_h264_backend("h264_vaapi")

    assert backend.supports_simple_software_frame_output is False
    with pytest.raises(ValueError, match="hardware-frame upload"):
        encoder.ffmpeg_h264_output_kwargs("h264_vaapi")


def test_unsupported_encoder_override_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("PIXELLE_FFMPEG_H264_ENCODER", "h264_amf")

    with pytest.raises(ValueError, match="must be one of"):
        encoder.resolve_ffmpeg_h264_encoder()


def test_vaapi_override_falls_back_until_hardware_frame_executor_exists(monkeypatch) -> None:
    monkeypatch.setenv("PIXELLE_FFMPEG_H264_ENCODER", "h264_vaapi")

    assert encoder.resolve_ffmpeg_h264_encoder() == "libx264"
    assert encoder.has_gpu_encoder() is False


def test_runtime_probe_failure_falls_through_to_next_hardware_family(monkeypatch) -> None:
    monkeypatch.setattr(
        encoder,
        "_probe_encoder_runtime",
        lambda name: name == "h264_qsv",
    )

    assert encoder.resolve_ffmpeg_h264_encoder() == "h264_qsv"
    assert encoder.has_gpu_encoder() is True


def test_all_runtime_probe_failures_fall_back_to_cpu(monkeypatch) -> None:
    monkeypatch.setattr(encoder, "_probe_encoder_runtime", lambda _name: False)

    assert encoder.resolve_ffmpeg_h264_encoder() == "libx264"
    assert encoder.has_gpu_encoder() is False


def test_runtime_failure_cache_disables_encoder_for_later_resolutions(monkeypatch) -> None:
    monkeypatch.setattr(encoder, "_probe_encoder_runtime", lambda _name: True)

    assert encoder.resolve_ffmpeg_h264_encoder() == "h264_nvenc"
    encoder.disable_ffmpeg_h264_encoder("h264_nvenc", reason="device disappeared")

    assert encoder.resolve_ffmpeg_h264_encoder() == "h264_qsv"


def test_runtime_disable_does_not_disable_cpu() -> None:
    encoder.disable_ffmpeg_h264_encoder("libx264", reason="irrelevant")

    assert encoder.ffmpeg_h264_backend("libx264").is_hardware is False


def test_nvenc_probe_command_uses_nvenc_options_and_no_crf() -> None:
    command = encoder._probe_command("h264_nvenc")

    assert command is not None
    joined = " ".join(command)
    assert "-c:v h264_nvenc" in joined
    assert "-preset p4" in joined
    assert "-rc vbr" in joined
    assert "-cq 23" in joined
    assert "-b_ref_mode middle" in joined
    assert "-crf" not in command


def test_qsv_probe_command_uses_qsv_options_and_no_nvenc_preset() -> None:
    command = encoder._probe_command("h264_qsv")

    assert command is not None
    joined = " ".join(command)
    assert "-c:v h264_qsv" in joined
    assert "-preset medium" in joined
    assert "-global_quality 23" in joined
    assert "-preset p4" not in joined
    assert "-rc" not in command
    assert "-cq" not in command
    assert "-b_ref_mode" not in command


def test_vaapi_probe_command_declares_device_and_hardware_upload(monkeypatch) -> None:
    monkeypatch.setattr(encoder, "_vaapi_device", lambda: "/dev/dri/renderD128")

    command = encoder._probe_command("h264_vaapi")

    assert command is not None
    joined = " ".join(command)
    assert "-vaapi_device /dev/dri/renderD128" in joined
    assert "-vf format=nv12,hwupload" in joined
    assert "-c:v h264_vaapi" in joined
    assert "-qp 23" in joined
    assert "-preset" not in command


def test_runtime_probe_requires_compiled_encoder_before_real_encode(monkeypatch) -> None:
    monkeypatch.setattr(encoder, "_probe_ffmpeg_encoders", lambda: set())
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert encoder._probe_encoder_runtime("h264_nvenc") is False
    assert calls == []


def test_runtime_probe_runs_real_one_frame_command(monkeypatch) -> None:
    monkeypatch.setattr(
        encoder,
        "_probe_ffmpeg_encoders",
        lambda: {"h264_nvenc"},
    )
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert encoder._probe_encoder_runtime("h264_nvenc") is True
    assert len(calls) == 1
    assert "h264_nvenc" in calls[0]
    assert "-frames:v" in calls[0]


def test_runtime_probe_failure_is_not_reported_as_gpu_capability(monkeypatch) -> None:
    monkeypatch.setattr(
        encoder,
        "_probe_ffmpeg_encoders",
        lambda: {"h264_nvenc"},
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="Cannot load libcuda",
        ),
    )

    assert encoder.resolve_ffmpeg_h264_encoder() == "libx264"
    assert encoder.has_gpu_encoder() is False


def test_gpu_count_returns_zero_when_nvidia_smi_not_found(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )

    assert encoder.gpu_count() == 0


def test_gpu_count_returns_zero_on_nonzero_exit(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="",
        ),
    )

    assert encoder.gpu_count() == 0


def test_gpu_count_returns_count_from_output(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="RTX 4090\nRTX 4090\n",
            stderr="",
        ),
    )

    assert encoder.gpu_count() == 2
