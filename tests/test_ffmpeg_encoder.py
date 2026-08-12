from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from pixelle_video.utils import ffmpeg_encoder as encoder_module
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
    supported_hardware_h264_codecs,
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

    @pytest.mark.parametrize(
        ("codec", "expected"),
        (
            (
                "libx264",
                ("-c:v", "libx264", "-preset", "medium", "-crf", "23"),
            ),
            (
                "h264_nvenc",
                (
                    "-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr",
                    "-cq", "23", "-b_ref_mode", "middle",
                ),
            ),
            (
                "h264_qsv",
                (
                    "-c:v", "h264_qsv", "-preset", "medium",
                    "-global_quality", "23",
                ),
            ),
            ("h264_vaapi", ("-c:v", "h264_vaapi", "-qp", "23")),
        ),
    )
    def test_raw_commands_share_backend_owned_output_options(
        self,
        codec,
        expected,
    ):
        assert get_h264_backend(codec).command_output_args() == expected

    def test_unknown_encoder_override_is_rejected(self, monkeypatch):
        monkeypatch.setenv("PIXELLE_FFMPEG_H264_ENCODER", "h264_amf")
        clear_ffmpeg_encoder_probe_cache()
        try:
            with pytest.raises(ValueError, match="unsupported PIXELLE_FFMPEG_H264_ENCODER"):
                resolve_ffmpeg_h264_backend()
        finally:
            clear_ffmpeg_encoder_probe_cache()


class TestRuntimeProbeCommands:
    def test_nvenc_probe_uses_only_nvenc_runtime_options(self):
        command = get_h264_backend("h264_nvenc").probe_command()
        assert command is not None
        text = " ".join(command)
        assert "-frames:v 1" in text
        assert "-preset p4" in text
        assert "-rc vbr" in text
        assert "-cq 23" in text
        assert "-b_ref_mode middle" in text
        assert "global_quality" not in text
        assert "hwupload" not in text
        assert "s=320x180:r=30:d=1" in text

    def test_qsv_probe_uses_qsv_quality_without_nvenc_options(self):
        command = get_h264_backend("h264_qsv").probe_command()
        assert command is not None
        text = " ".join(command)
        assert "-frames:v 1" in text
        assert "-preset medium" in text
        assert "-global_quality 23" in text
        assert " -cq " not in f" {text} "
        assert "b_ref_mode" not in text
        assert "-preset p4" not in text
        assert "s=320x180:r=30:d=1" in text

    def test_qsv_probe_binds_an_explicit_drm_render_node(self, monkeypatch):
        monkeypatch.setattr(
            encoder_module,
            "_resolve_qsv_device",
            lambda: "/dev/dri/renderD129",
        )

        command = get_h264_backend("h264_qsv").probe_command()

        assert command[4:6] == [
            "-qsv_device",
            "/dev/dri/renderD129",
        ]

    def test_vaapi_probe_requires_device_and_hwupload(self, monkeypatch):
        monkeypatch.setattr(
            encoder_module,
            "_resolve_vaapi_device",
            lambda: "/dev/dri/renderD999",
        )
        command = get_h264_backend("h264_vaapi").probe_command()
        assert command is not None
        text = " ".join(command)
        assert "-vaapi_device /dev/dri/renderD999" in text
        assert "format=nv12,hwupload" in text
        assert "-frames:v 1" in text
        assert "-qp 23" in text
        assert "-preset p4" not in text
        assert "b_ref_mode" not in text

    def test_vaapi_device_override_rejects_non_device_paths(self, monkeypatch):
        monkeypatch.setenv("PIXELLE_FFMPEG_VAAPI_DEVICE", "/tmp/renderD128")

        with pytest.raises(ValueError, match="/dev/dri/renderD<number>"):
            encoder_module._resolve_vaapi_device()

    def test_vaapi_device_override_accepts_a_validated_render_node(
        self,
        monkeypatch,
    ):
        monkeypatch.setenv("PIXELLE_FFMPEG_VAAPI_DEVICE", "/dev/dri/renderD129")
        monkeypatch.setattr(
            encoder_module,
            "_is_linux_drm_render_node",
            lambda value: value == "/dev/dri/renderD129",
        )

        assert encoder_module._resolve_vaapi_device() == "/dev/dri/renderD129"

    def test_vaapi_render_graph_projection_owns_device_and_upload_contract(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            encoder_module,
            "_resolve_vaapi_device",
            lambda: "/dev/dri/renderD999",
        )

        projection = get_h264_backend("h264_vaapi").render_graph_projection()

        assert projection.input_pixel_format == "nv12"
        assert projection.requires_hardware_upload is True
        assert projection.output_pixel_format is None
        assert projection.global_args == ("-vaapi_device", "/dev/dri/renderD999")

    def test_software_and_nvenc_keep_planar_output(self):
        for codec in ("libx264", "h264_nvenc"):
            projection = get_h264_backend(codec).render_graph_projection()
            assert projection.requires_hardware_upload is False
            assert projection.output_pixel_format == "yuv420p"

    def test_qsv_render_graph_projects_system_memory_frames_to_explicit_device(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            encoder_module,
            "_resolve_qsv_device",
            lambda: "/dev/dri/renderD129",
        )
        projection = get_h264_backend("h264_qsv").render_graph_projection()
        assert projection.input_pixel_format == "nv12"
        assert projection.requires_hardware_upload is False
        assert projection.output_pixel_format is None
        assert projection.global_args == (
            "-qsv_device",
            "/dev/dri/renderD129",
        )

    def test_qsv_device_override_rejects_ambiguous_non_drm_paths(
        self,
        monkeypatch,
    ):
        monkeypatch.setenv("PIXELLE_FFMPEG_QSV_DEVICE", "/tmp/renderD128")

        with pytest.raises(ValueError, match="/dev/dri/renderD<number>"):
            encoder_module._resolve_qsv_device(platform_name="posix")

    def test_qsv_device_override_accepts_an_existing_drm_render_node(
        self,
        monkeypatch,
    ):
        monkeypatch.setenv("PIXELLE_FFMPEG_QSV_DEVICE", "/dev/dri/renderD129")
        monkeypatch.setattr(
            encoder_module,
            "_is_linux_drm_render_node",
            lambda value: value == "/dev/dri/renderD129",
        )

        assert (
            encoder_module._resolve_qsv_device(platform_name="posix")
            == "/dev/dri/renderD129"
        )

    def test_qsv_device_override_rejects_out_of_range_windows_adapter(
        self,
        monkeypatch,
    ):
        monkeypatch.setenv("PIXELLE_FFMPEG_QSV_DEVICE", "32")

        with pytest.raises(ValueError, match="between 0 and 31"):
            encoder_module._resolve_qsv_device(platform_name="nt")

    def test_qsv_device_path_must_resolve_to_a_character_device(self, monkeypatch):
        monkeypatch.setattr(
            encoder_module.os,
            "stat",
            lambda value: SimpleNamespace(st_mode=encoder_module.stat.S_IFREG),
        )
        assert encoder_module._is_linux_drm_render_node("/dev/dri/renderD128") is False

        monkeypatch.setattr(
            encoder_module.os,
            "stat",
            lambda value: SimpleNamespace(st_mode=encoder_module.stat.S_IFCHR),
        )
        assert encoder_module._is_linux_drm_render_node("/dev/dri/renderD128") is True


class TestRuntimeProbeSelection:
    def test_runtime_probe_cache_is_scoped_to_the_resolved_device(self, monkeypatch):
        device = {"value": "/dev/dri/renderD128"}
        commands: list[tuple[str, ...]] = []
        monkeypatch.setattr(
            encoder_module,
            "_resolve_qsv_device",
            lambda: device["value"],
        )
        def _run(command, **kwargs):
            if "-encoders" in command:
                return _completed(command, stdout="V....D h264_qsv")
            commands.append(tuple(command))
            return _completed(command)

        monkeypatch.setattr(subprocess, "run", _run)
        clear_ffmpeg_encoder_probe_cache()
        try:
            assert encoder_module._probe_backend_runtime("h264_qsv") is True
            assert encoder_module._probe_backend_runtime("h264_qsv") is True
            device["value"] = "/dev/dri/renderD129"
            assert encoder_module._probe_backend_runtime("h264_qsv") is True
        finally:
            clear_ffmpeg_encoder_probe_cache()

        assert len(commands) == 2
        assert commands[0][5] == "/dev/dri/renderD128"
        assert commands[1][5] == "/dev/dri/renderD129"

    def test_encoder_selection_tracks_environment_changes_without_stale_cache(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            subprocess,
            "run",
            _runtime_probe_runner(
                encoders=("h264_nvenc", "h264_qsv", "libx264"),
            ),
        )
        clear_ffmpeg_encoder_probe_cache()
        try:
            monkeypatch.setenv("PIXELLE_FFMPEG_H264_ENCODER", "h264_nvenc")
            assert resolve_ffmpeg_h264_backend().codec == "h264_nvenc"

            monkeypatch.setenv("PIXELLE_FFMPEG_H264_ENCODER", "h264_qsv")
            assert resolve_ffmpeg_h264_backend().codec == "h264_qsv"
        finally:
            clear_ffmpeg_encoder_probe_cache()

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
    def test_supported_hardware_registry_is_the_complete_product_contract(self):
        assert supported_hardware_h264_codecs() == (
            "h264_nvenc",
            "h264_qsv",
            "h264_vaapi",
        )

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
