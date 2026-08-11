from __future__ import annotations

import subprocess

import pytest  # noqa: F401

from pixelle_video.utils.ffmpeg_encoder import (
    _probe_ffmpeg_encoders,
    _probe_nvidia_gpu_count,
    ffmpeg_h264_encode_kwargs,
    ffmpeg_h264_preset,
    gpu_count,
    has_gpu_encoder,
    resolve_ffmpeg_h264_encoder,
)


class TestResolveFfmpegH264Encoder:
    def test_env_override_takes_priority(self, monkeypatch):
        monkeypatch.setenv("PIXELLE_FFMPEG_H264_ENCODER", "h264_amf")
        _probe_ffmpeg_encoders.cache_clear()
        resolve_ffmpeg_h264_encoder.cache_clear()
        try:
            assert resolve_ffmpeg_h264_encoder() == "h264_amf"
        finally:
            _probe_ffmpeg_encoders.cache_clear()
            resolve_ffmpeg_h264_encoder.cache_clear()

    def test_empty_env_var_not_used_as_override(self, monkeypatch):
        monkeypatch.setenv("PIXELLE_FFMPEG_H264_ENCODER", "   ")
        _probe_ffmpeg_encoders.cache_clear()
        resolve_ffmpeg_h264_encoder.cache_clear()
        try:
            result = resolve_ffmpeg_h264_encoder()
            assert result in ("libx264", "h264_nvenc", "h264_qsv", "h264_vaapi")
        finally:
            _probe_ffmpeg_encoders.cache_clear()
            resolve_ffmpeg_h264_encoder.cache_clear()

    def test_returns_libx264_when_no_hardware_encoders(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout="V....D libx264\nV....D libx265\n",
                stderr="",
            ),
        )
        _probe_ffmpeg_encoders.cache_clear()
        resolve_ffmpeg_h264_encoder.cache_clear()
        try:
            assert resolve_ffmpeg_h264_encoder() == "libx264"
        finally:
            _probe_ffmpeg_encoders.cache_clear()
            resolve_ffmpeg_h264_encoder.cache_clear()

    def test_returns_nvenc_when_available(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout=" V....D h264_nvenc\nV....D libx264\n",
                stderr="",
            ),
        )
        _probe_ffmpeg_encoders.cache_clear()
        resolve_ffmpeg_h264_encoder.cache_clear()
        try:
            assert resolve_ffmpeg_h264_encoder() == "h264_nvenc"
        finally:
            _probe_ffmpeg_encoders.cache_clear()
            resolve_ffmpeg_h264_encoder.cache_clear()

    def test_prefers_nvenc_over_qsv(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout="V....D h264_qsv\nV....D h264_nvenc\n",
                stderr="",
            ),
        )
        _probe_ffmpeg_encoders.cache_clear()
        resolve_ffmpeg_h264_encoder.cache_clear()
        try:
            assert resolve_ffmpeg_h264_encoder() == "h264_nvenc"
        finally:
            _probe_ffmpeg_encoders.cache_clear()
            resolve_ffmpeg_h264_encoder.cache_clear()

    def test_returns_libx264_when_ffmpeg_not_found(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))
        _probe_ffmpeg_encoders.cache_clear()
        resolve_ffmpeg_h264_encoder.cache_clear()
        try:
            assert resolve_ffmpeg_h264_encoder() == "libx264"
        finally:
            _probe_ffmpeg_encoders.cache_clear()
            resolve_ffmpeg_h264_encoder.cache_clear()

    def test_returns_libx264_on_timeout(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired("ffmpeg", 15)))
        _probe_ffmpeg_encoders.cache_clear()
        resolve_ffmpeg_h264_encoder.cache_clear()
        try:
            assert resolve_ffmpeg_h264_encoder() == "libx264"
        finally:
            _probe_ffmpeg_encoders.cache_clear()
            resolve_ffmpeg_h264_encoder.cache_clear()

    def test_returns_libx264_on_nonzero_exit(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args[0],
                returncode=1,
                stdout="",
                stderr="broken ffmpeg",
            ),
        )
        _probe_ffmpeg_encoders.cache_clear()
        resolve_ffmpeg_h264_encoder.cache_clear()
        try:
            assert resolve_ffmpeg_h264_encoder() == "libx264"
        finally:
            _probe_ffmpeg_encoders.cache_clear()
            resolve_ffmpeg_h264_encoder.cache_clear()


class TestFfmpegH264Preset:
    def test_libx264_returns_medium(self):
        assert ffmpeg_h264_preset("libx264") == "medium"

    def test_nvenc_returns_p4(self):
        assert ffmpeg_h264_preset("h264_nvenc") == "p4"

    def test_qsv_returns_p4(self):
        assert ffmpeg_h264_preset("h264_qsv") == "p4"

    def test_vaapi_returns_p4(self):
        assert ffmpeg_h264_preset("h264_vaapi") == "p4"


class TestFfmpegH264EncodeKwargs:
    def test_nvenc_uses_vbr_cq_mode(self):
        params = ffmpeg_h264_encode_kwargs("h264_nvenc")
        assert params["rc"] == "vbr"
        assert params["cq"] == 23
        assert params["b_ref_mode"] == "middle"

    def test_qsv_uses_vbr_cq_mode(self):
        params = ffmpeg_h264_encode_kwargs("h264_qsv")
        assert params["rc"] == "vbr"
        assert params["cq"] == 23

    def test_libx264_adds_no_extra_params(self):
        assert ffmpeg_h264_encode_kwargs("libx264") == {}


class TestHasGpuEncoder:
    def test_true_when_nvenc_available(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout="V....D h264_nvenc\n", stderr=""
            ),
        )
        _probe_ffmpeg_encoders.cache_clear()
        resolve_ffmpeg_h264_encoder.cache_clear()
        try:
            assert has_gpu_encoder() is True
        finally:
            _probe_ffmpeg_encoders.cache_clear()
            resolve_ffmpeg_h264_encoder.cache_clear()

    def test_false_when_no_hardware_encoder(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout="V....D libx264\n", stderr=""
            ),
        )
        _probe_ffmpeg_encoders.cache_clear()
        resolve_ffmpeg_h264_encoder.cache_clear()
        try:
            assert has_gpu_encoder() is False
        finally:
            _probe_ffmpeg_encoders.cache_clear()
            resolve_ffmpeg_h264_encoder.cache_clear()


class TestGpuCount:
    def test_returns_zero_when_nvidia_smi_not_found(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))
        _probe_nvidia_gpu_count.cache_clear()
        try:
            assert gpu_count() == 0
        finally:
            _probe_nvidia_gpu_count.cache_clear()

    def test_returns_zero_on_nonzero_exit(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args[0], returncode=1, stdout="", stderr=""
            ),
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
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout="GPU 0: RTX 4090\nGPU 1: RTX 4090\n",
                stderr="",
            ),
        )
        _probe_nvidia_gpu_count.cache_clear()
        try:
            assert gpu_count() == 2
        finally:
            _probe_nvidia_gpu_count.cache_clear()
