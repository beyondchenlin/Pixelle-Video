from __future__ import annotations

import subprocess

import pytest

from pixelle_video.utils.ffmpeg_encoder import (
    _probe_nvidia_gpu_count,
    clear_ffmpeg_encoder_probe_cache,
    ffmpeg_h264_encode_kwargs,
    ffmpeg_h264_output_kwargs,
    ffmpeg_h264_preset,
    get_h264_backend,
    gpu_count,
    has_gpu_encoder,
    resolve_ffmpeg_h264_backend,
    resolve_ffmpeg_h264_encoder,
)


def _completed(args, *, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=args,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _runtime_probe_runner(*, encoders: tuple[str, ...], failing: tuple[str, ...] = ()):
    def _run(args, **kwargs):
        if "-encoders" in args:
            stdout = "\n".join(f"V....D {codec}" for codec in encoders)
            return _completed(args, stdout=stdout)
        codec = ""
        if "-c:v" in args:
            codec = args[args.index("-c:v") + 1]
        if codec in failing:
            return _completed(args, returncode=1, stderr=f"{codec} runtime unavailable")
        return _completed(args)

    return _run


class TestBackendContracts:
    def test_libx264_owns_software_quality_parameters(self):
        params = ffmpeg_h264_output_kwargs("libx264")
        assert params == {
            "vcodec": "libx264",
            "preset": "medium",
            "crf": 23,
        }

    def test_nvenc_owns_nvenc_parameters_only(self):
        params = ffmpeg_h264_output_kwargs("h264_nvenc")
        assert params["preset"] == "p4"
        assert params["rc"] == "vbr"
        assert params["cq"] == 23
        assert params["b_ref_mode"] == "middle"
        assert "crf" not in params
        assert "global_quality" not in params

    def test_qsv_uses_qsv_preset_and_global_quality(self):
        params = ffmpeg_h264_output_kwargs("h264_qsv")
        assert params == {
            "vcodec": "h264_qsv",
            "preset": "medium",
            "global_quality": 23,
        }
        assert "rc" not in params
        assert "cq" not in params
        assert "b_ref_mode" not in params

    def test_vaapi_does_not_invent_nvenc_preset(self):
        params = ffmpeg_h264_output_kwargs("h264_vaapi")
        assert params == {"vcodec": "h264_vaapi", "qp": 23}
        with pytest.raises(ValueError, match="does not define a preset"):
            ffmpeg_h264_preset("h264_vaapi")

    def test_compatibility_extras_never_cross_encoder_families(self):
        assert ffmpeg_h264_encode_kwargs("libx264") == {}
        assert ffmpeg_h264_encode_kwargs("h264_qsv") == {"global_quality": 23}
        assert ffmpeg_h264_encode_kwargs("h264_vaapi") == {"qp": 23}

    def test_unknown_encoder_override_is_rejected(self, monkeypatch):
        monkeypatch.setenv("PIXELLE_FFMPEG_H264_ENCODER", "h264_amf")
        clear_ffmpeg_encoder_probe_cache()
        try:
            with pytest.raises(ValueError, match="unsupported PIXELLE_FFMPEG_H264_ENCODER"):
                resolve_ffmpeg_h264_backend()
        finally:
            clear_ffmpeg_encoder_probe_cache()


class TestRuntimeProbeSelection:
    def test_compiled_encoder_that_cannot_encode_is_not_selected(self, monkeypatch):
        monkeypatch.delenv("PIXELLE_FFMPEG_H264_ENCODER", raising=False)
        monkeypatch.setattr(
            subprocess,
            "run",
            _runtime_probe_runner(
                encoders=("h264_nvenc", "libx264"),
                failing=("h264_nvenc",),
            ),
        )
        clear_ffmpeg_encoder_probe_cache()
        try:
            assert resolve_ffmpeg_h264_backend().codec == "libx264"
            assert has_gpu_encoder() is False
        finally:
            clear_ffmpeg_encoder_probe_cache()

    def test_nvenc_is_selected_only_after_real_probe_succeeds(self, monkeypatch):
        monkeypatch.delenv("PIXELLE_FFMPEG_H264_ENCODER", raising=False)
        monkeypatch.setattr(
            subprocess,
            "run",
            _runtime_probe_runner(encoders=("h264_nvenc", "libx264")),
        )
        clear_ffmpeg_encoder_probe_cache()
        try:
            backend = resolve_ffmpeg_h264_backend()
            assert backend.codec == "h264_nvenc"
            assert backend.hardware is True
            assert resolve_ffmpeg_h264_encoder() == "h264_nvenc"
        finally:
            clear_ffmpeg_encoder_probe_cache()

    def test_qsv_can_be_runtime_selected_without_receiving_nvenc_parameters(self, monkeypatch):
        monkeypatch.delenv("PIXELLE_FFMPEG_H264_ENCODER", raising=False)
        monkeypatch.setattr(
            subprocess,
            "run",
            _runtime_probe_runner(encoders=("h264_qsv", "libx264")),
        )
        clear_ffmpeg_encoder_probe_cache()
        try:
            backend = resolve_ffmpeg_h264_backend()
            assert backend.codec == "h264_qsv"
            assert backend.output_kwargs()["preset"] == "medium"
            assert "cq" not in backend.output_kwargs()
            assert has_gpu_encoder() is True
            # Legacy ffmpeg-python call sites cannot yet express the complete
            # QSV execution contract; they stay on CPU until the unified executor.
            assert resolve_ffmpeg_h264_encoder() == "libx264"
        finally:
            clear_ffmpeg_encoder_probe_cache()

    def test_hardware_override_falls_back_when_runtime_probe_fails(self, monkeypatch):
        monkeypatch.setenv("PIXELLE_FFMPEG_H264_ENCODER", "h264_qsv")
        monkeypatch.setattr(
            subprocess,
            "run",
            _runtime_probe_runner(
                encoders=("h264_qsv", "libx264"),
                failing=("h264_qsv",),
            ),
        )
        clear_ffmpeg_encoder_probe_cache()
        try:
            assert resolve_ffmpeg_h264_backend().codec == "libx264"
        finally:
            clear_ffmpeg_encoder_probe_cache()

    def test_nvenc_keeps_priority_when_multiple_runtime_probes_succeed(self, monkeypatch):
        monkeypatch.delenv("PIXELLE_FFMPEG_H264_ENCODER", raising=False)
        monkeypatch.setattr(
            subprocess,
            "run",
            _runtime_probe_runner(
                encoders=("h264_nvenc", "h264_qsv", "libx264"),
            ),
        )
        clear_ffmpeg_encoder_probe_cache()
        try:
            assert resolve_ffmpeg_h264_backend().codec == "h264_nvenc"
        finally:
            clear_ffmpeg_encoder_probe_cache()


class TestBackendMetadata:
    def test_backend_registry_reports_hardware_truthfully(self):
        assert get_h264_backend("libx264").hardware is False
        assert get_h264_backend("h264_nvenc").hardware is True
        assert get_h264_backend("h264_qsv").hardware is True
        assert get_h264_backend("h264_vaapi").hardware is True


class TestGpuCount:
    def test_returns_zero_when_nvidia_smi_not_found(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()),
        )
        _probe_nvidia_gpu_count.cache_clear()
        try:
            assert gpu_count() == 0
        finally:
            _probe_nvidia_gpu_count.cache_clear()

    def test_returns_zero_on_nonzero_exit(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: _completed(args[0], returncode=1),
        )
        _probe_nvidia_gpu_count.cache_clear()
        try:
            assert gpu_count() == 0
        finally:
            _probe_nvidia_gpu_count.cache_clear()

    def test_returns_count_from_output(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: _completed(
                args[0],
                stdout="GPU 0: RTX 4090\nGPU 1: RTX 4090\n",
            ),
        )
        _probe_nvidia_gpu_count.cache_clear()
        try:
            assert gpu_count() == 2
        finally:
            _probe_nvidia_gpu_count.cache_clear()
