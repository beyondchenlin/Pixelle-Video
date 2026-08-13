from __future__ import annotations

import os
import stat
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import PurePosixPath

from loguru import logger

_CLI_OUTPUT_OPTION_NAMES = {
    "vcodec": "-c:v",
    "preset": "-preset",
    "crf": "-crf",
    "rc": "-rc",
    "cq": "-cq",
    "b_ref_mode": "-b_ref_mode",
    "global_quality": "-global_quality",
    "qp": "-qp",
}


@dataclass(frozen=True)
class H264RenderGraphProjection:
    """Backend-owned projection from a software filter graph to an encoder."""

    input_pixel_format: str | None = None
    requires_hardware_upload: bool = False
    output_pixel_format: str | None = "yuv420p"
    global_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class H264EncoderBackend:
    """Backend-specific H.264 encoder contract."""

    codec: str
    hardware: bool
    legacy_ffmpeg_python_compatible: bool = False
    probe_timeout_seconds: int = 15

    def output_kwargs(self) -> dict[str, object]:
        raise NotImplementedError

    def probe_command(self) -> list[str] | None:
        raise NotImplementedError

    def command_output_args(self) -> tuple[str, ...]:
        params = self.output_kwargs()
        unknown = sorted(set(params) - set(_CLI_OUTPUT_OPTION_NAMES))
        if unknown:
            raise ValueError(
                f"encoder {self.codec} has unmapped command options: {', '.join(unknown)}"
            )
        args: list[str] = []
        for key, value in params.items():
            args.extend((_CLI_OUTPUT_OPTION_NAMES[key], str(value)))
        return tuple(args)

    def render_graph_projection(self) -> H264RenderGraphProjection:
        return H264RenderGraphProjection()


@dataclass(frozen=True)
class Libx264Backend(H264EncoderBackend):
    codec: str = "libx264"
    hardware: bool = False
    legacy_ffmpeg_python_compatible: bool = True

    def output_kwargs(self) -> dict[str, object]:
        return {"vcodec": self.codec, "preset": "medium", "crf": 23}

    def probe_command(self) -> list[str]:
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=1",
            "-frames:v", "1", "-c:v", self.codec,
            "-preset", "medium", "-crf", "23", "-f", "null", "-",
        ]


@dataclass(frozen=True)
class NvencBackend(H264EncoderBackend):
    codec: str = "h264_nvenc"
    hardware: bool = True
    legacy_ffmpeg_python_compatible: bool = True

    def output_kwargs(self) -> dict[str, object]:
        return {
            "vcodec": self.codec,
            "preset": "p4",
            "rc": "vbr",
            "cq": 23,
            "b_ref_mode": "middle",
        }

    def probe_command(self) -> list[str]:
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=1",
            "-frames:v", "1", "-c:v", self.codec,
            "-preset", "p4", "-rc", "vbr", "-cq", "23",
            "-b_ref_mode", "middle", "-f", "null", "-",
        ]


@dataclass(frozen=True)
class QsvBackend(H264EncoderBackend):
    codec: str = "h264_qsv"
    hardware: bool = True

    def output_kwargs(self) -> dict[str, object]:
        return {
            "vcodec": self.codec,
            "preset": "medium",
            "global_quality": 23,
        }

    def probe_command(self) -> list[str]:
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
        ]
        device = _resolve_qsv_device()
        if device is not None:
            command.extend(("-qsv_device", device))
        command.extend(
            (
                "-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=1",
                "-frames:v", "1", "-c:v", self.codec,
                "-preset", "medium", "-global_quality", "23",
                "-f", "null", "-",
            )
        )
        return command

    def render_graph_projection(self) -> H264RenderGraphProjection:
        device = _resolve_qsv_device()
        return H264RenderGraphProjection(
            input_pixel_format="nv12",
            output_pixel_format=None,
            global_args=(
                ("-qsv_device", device)
                if device is not None
                else ()
            ),
        )


@dataclass(frozen=True)
class VaapiBackend(H264EncoderBackend):
    codec: str = "h264_vaapi"
    hardware: bool = True

    def output_kwargs(self) -> dict[str, object]:
        return {"vcodec": self.codec, "qp": 23}

    def probe_command(self) -> list[str] | None:
        device = _resolve_vaapi_device()
        if device is None:
            return None
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-vaapi_device", device,
            "-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=1",
            "-vf", "format=nv12,hwupload", "-frames:v", "1",
            "-c:v", self.codec, "-qp", "23", "-f", "null", "-",
        ]

    def render_graph_projection(self) -> H264RenderGraphProjection:
        device = _resolve_vaapi_device()
        if device is None:
            raise RuntimeError("VAAPI render graph requires an accessible device")
        return H264RenderGraphProjection(
            input_pixel_format="nv12",
            requires_hardware_upload=True,
            output_pixel_format=None,
            global_args=("-vaapi_device", device),
        )


_BACKENDS: dict[str, H264EncoderBackend] = {
    backend.codec: backend
    for backend in (Libx264Backend(), NvencBackend(), QsvBackend(), VaapiBackend())
}
_HARDWARE_BACKEND_ORDER = ("h264_nvenc", "h264_qsv", "h264_vaapi")
_CPU_ENCODER = "libx264"


@lru_cache(maxsize=1)
def _probe_ffmpeg_encoders() -> set[str]:
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    if result.returncode != 0:
        logger.warning(
            "ffmpeg -encoders exited with code {}; encoder discovery skipped",
            result.returncode,
        )
        return set()
    encoders: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            encoders.add(parts[1])
    return encoders


def _probe_backend_runtime(codec: str) -> bool:
    backend = get_h264_backend(codec)
    if not backend.hardware:
        return True
    command = backend.probe_command()
    if command is None:
        return False
    if codec not in _probe_ffmpeg_encoders():
        return False
    return _run_backend_probe(
        codec,
        tuple(command),
        backend.probe_timeout_seconds,
    )


@lru_cache(maxsize=None)
def _run_backend_probe(
    codec: str,
    command: tuple[str, ...],
    timeout_seconds: int,
) -> bool:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    if result.returncode != 0:
        logger.debug(
            "ffmpeg hardware encoder candidate {} is unavailable: {}",
            codec,
            _summarize_probe_error(result.stderr),
        )
        return False
    return True


def _summarize_probe_error(stderr: str | None, *, limit: int = 240) -> str:
    """Return a bounded single-line diagnostic for an optional backend probe."""

    normalized = " ".join(str(stderr or "").split())
    if not normalized:
        return "probe exited with a non-zero status and no diagnostic output"
    if len(normalized) <= limit:
        return normalized
    return f"...{normalized[-limit:]}"


@lru_cache(maxsize=None)
def _log_backend_selection_once(
    candidates: tuple[str, ...],
    override: str,
) -> None:
    """Report the effective encoder contract once per distinct selection."""

    selected = candidates[0]
    fallbacks = candidates[1:]
    if override and selected == _CPU_ENCODER and override != _CPU_ENCODER:
        logger.warning(
            "requested ffmpeg hardware encoder {} is not runnable; "
            "selected {} instead",
            override,
            selected,
        )
        return

    if selected == _CPU_ENCODER and not override:
        logger.warning(
            "no ffmpeg hardware H.264 encoder passed runtime qualification; "
            "selected {}",
            selected,
        )
        return

    logger.info(
        "ffmpeg H.264 encoder selected: {}; fallback order: {}",
        selected,
        ", ".join(fallbacks) if fallbacks else "none",
    )


def get_h264_backend(codec: str) -> H264EncoderBackend:
    normalized = str(codec or "").strip()
    if normalized not in _BACKENDS:
        raise ValueError(
            "unsupported PIXELLE_FFMPEG_H264_ENCODER; expected one of "
            f"{', '.join(sorted(_BACKENDS))}, got {normalized!r}"
        )
    return _BACKENDS[normalized]


def supported_hardware_h264_codecs() -> tuple[str, ...]:
    """Return the complete product-supported hardware qualification set."""

    return _HARDWARE_BACKEND_ORDER


def available_h264_backends() -> tuple[H264EncoderBackend, ...]:
    """Return runnable backends in execution order, always ending with CPU.

    An explicit environment override constrains hardware selection to that
    backend; if it is not runnable, the list contains only the CPU fallback.
    Automatic mode returns every runtime-probed hardware backend in priority
    order so workload failures can fall through without repeating probes.
    """

    cpu = _BACKENDS[_CPU_ENCODER]
    override = os.environ.get("PIXELLE_FFMPEG_H264_ENCODER", "").strip()
    if override:
        backend = get_h264_backend(override)
        if not backend.hardware:
            result = (backend,)
            _log_backend_selection_once(tuple(item.codec for item in result), override)
            return result
        if _probe_backend_runtime(backend.codec):
            result = (backend, cpu)
            _log_backend_selection_once(tuple(item.codec for item in result), override)
            return result
        result = (cpu,)
        _log_backend_selection_once(tuple(item.codec for item in result), override)
        return result

    result: list[H264EncoderBackend] = []
    for codec in supported_hardware_h264_codecs():
        if _probe_backend_runtime(codec):
            result.append(_BACKENDS[codec])
    result.append(cpu)
    resolved = tuple(result)
    _log_backend_selection_once(tuple(item.codec for item in resolved), override)
    return resolved


def resolve_ffmpeg_h264_backend() -> H264EncoderBackend:
    return available_h264_backends()[0]


def resolve_ffmpeg_h264_encoder() -> str:
    """Compatibility resolver for legacy ffmpeg-python call sites."""

    backend = resolve_ffmpeg_h264_backend()
    if backend.legacy_ffmpeg_python_compatible:
        return backend.codec
    logger.info(
        "encoder {} requires unified executor; using libx264 for legacy call site",
        backend.codec,
    )
    return _CPU_ENCODER


def ffmpeg_h264_output_kwargs(vcodec: str) -> dict[str, object]:
    return dict(get_h264_backend(vcodec).output_kwargs())


def ffmpeg_h264_preset(vcodec: str) -> str:
    params = ffmpeg_h264_output_kwargs(vcodec)
    preset = params.get("preset")
    if not isinstance(preset, str) or not preset:
        raise ValueError(f"encoder {vcodec} does not define a preset option")
    return preset


def ffmpeg_h264_encode_kwargs(vcodec: str) -> dict[str, object]:
    params = ffmpeg_h264_output_kwargs(vcodec)
    for key in ("vcodec", "preset", "crf"):
        params.pop(key, None)
    return params


def has_gpu_encoder() -> bool:
    return resolve_ffmpeg_h264_backend().hardware


@lru_cache(maxsize=1)
def _probe_nvidia_gpu_count() -> int:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 0
    if result.returncode != 0:
        return 0
    return len([line for line in result.stdout.strip().splitlines() if line.strip()])


def gpu_count() -> int:
    return _probe_nvidia_gpu_count()


def ffmpeg_h264_fallback_kwargs() -> dict[str, object]:
    return ffmpeg_h264_output_kwargs(_CPU_ENCODER)


def clear_ffmpeg_encoder_probe_cache() -> None:
    _probe_ffmpeg_encoders.cache_clear()
    _run_backend_probe.cache_clear()
    _log_backend_selection_once.cache_clear()


def _resolve_vaapi_device() -> str | None:
    override = os.environ.get("PIXELLE_FFMPEG_VAAPI_DEVICE", "").strip()
    if override:
        if not _is_linux_drm_render_node(override):
            raise ValueError(
                "PIXELLE_FFMPEG_VAAPI_DEVICE must be a /dev/dri/renderD<number> node"
            )
        return override
    default = "/dev/dri/renderD128"
    return default if _is_linux_drm_render_node(default) else None


def _resolve_qsv_device(*, platform_name: str | None = None) -> str | None:
    current_platform = os.name if platform_name is None else platform_name
    override = os.environ.get("PIXELLE_FFMPEG_QSV_DEVICE", "").strip()
    if override:
        if current_platform == "nt":
            if not override.isdecimal() or not 0 <= int(override) <= 31:
                raise ValueError(
                    "PIXELLE_FFMPEG_QSV_DEVICE must be a DirectX adapter index "
                    "between 0 and 31 on Windows"
                )
            return override
        if not _is_linux_drm_render_node(override):
            raise ValueError(
                "PIXELLE_FFMPEG_QSV_DEVICE must be a /dev/dri/renderD<number> node"
            )
        return override
    if current_platform == "nt":
        return None
    default = "/dev/dri/renderD128"
    return default if _is_linux_drm_render_node(default) else None


def _is_linux_drm_render_node(value: str) -> bool:
    path = PurePosixPath(value)
    if (
        path.parent != PurePosixPath("/dev/dri")
        or not path.name.startswith("renderD")
        or not path.name.removeprefix("renderD").isdecimal()
    ):
        return False
    try:
        return stat.S_ISCHR(os.stat(value).st_mode)
    except OSError:
        return False


__all__ = [
    "H264EncoderBackend",
    "H264RenderGraphProjection",
    "Libx264Backend",
    "NvencBackend",
    "QsvBackend",
    "VaapiBackend",
    "available_h264_backends",
    "clear_ffmpeg_encoder_probe_cache",
    "ffmpeg_h264_encode_kwargs",
    "ffmpeg_h264_fallback_kwargs",
    "ffmpeg_h264_output_kwargs",
    "ffmpeg_h264_preset",
    "get_h264_backend",
    "gpu_count",
    "has_gpu_encoder",
    "resolve_ffmpeg_h264_backend",
    "resolve_ffmpeg_h264_encoder",
    "supported_hardware_h264_codecs",
]
