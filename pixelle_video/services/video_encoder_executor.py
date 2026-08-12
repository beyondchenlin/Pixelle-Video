from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import ffmpeg
from loguru import logger

from pixelle_video.utils.ffmpeg_encoder import (
    H264EncoderBackend,
    available_h264_backends,
    ffmpeg_h264_fallback_kwargs,
    get_h264_backend,
)

_DISABLED_HARDWARE_CODECS: set[str] = set()
_DISABLED_HARDWARE_CODECS_LOCK = threading.Lock()


class UnifiedVideoEncoder:
    """One execution boundary for every H.264 re-encode.

    Hardware discovery is handled by ``ffmpeg_encoder``. This executor adds a
    second, workload-level safety layer: when a backend passes the tiny probe but
    fails a real encode, it is disabled for the rest of the process and the
    current operation immediately falls through to the next runnable backend.
    """

    def run_ffmpeg_python(
        self,
        build_output: Callable[..., Any],
        *,
        quiet: bool = False,
        preferred_params: Mapping[str, object] | None = None,
        supports_backend_projection: bool = False,
    ) -> str:
        last_error: ffmpeg.Error | None = None
        for params in self._ffmpeg_python_param_candidates(
            preferred_params,
            supports_backend_projection=supports_backend_projection,
        ):
            codec = str(params.get("vcodec") or "")
            try:
                extra: dict[str, bool] = {
                    "capture_stdout": True,
                    "capture_stderr": True,
                }
                if quiet:
                    extra["quiet"] = True
                build_output(**dict(params)).run(**extra)
                return codec
            except ffmpeg.Error as exc:
                last_error = exc
                backend = _known_backend(codec)
                if backend is None or not backend.hardware:
                    raise
                self.disable_hardware_backend(
                    codec,
                    reason="real ffmpeg-python workload failed",
                )
                logger.warning(
                    "hardware encoder {} failed real workload; trying next backend",
                    codec,
                )
        if last_error is not None:
            raise last_error
        raise RuntimeError("no H.264 encoder candidate was available")

    def encode_png_sequence(
        self,
        *,
        frame_pattern: str | Path,
        fps: int,
        output_path: str | Path,
        duration: float,
        audio_path: str | Path | None = None,
    ) -> str:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        last_error: subprocess.CalledProcessError | None = None
        for backend in self.runtime_backend_candidates():
            command = self._png_sequence_command(
                backend=backend,
                frame_pattern=Path(frame_pattern),
                fps=fps,
                output_path=output,
                duration=duration,
                audio_path=Path(audio_path) if audio_path else None,
            )
            if command is None:
                continue
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return str(output)
            except subprocess.CalledProcessError as exc:
                last_error = exc
                if not backend.hardware:
                    raise
                self.disable_hardware_backend(
                    backend.codec,
                    reason="real PNG-sequence workload failed",
                )
                if output.exists():
                    output.unlink()
                logger.warning(
                    "hardware encoder {} failed PNG sequence workload; trying next backend",
                    backend.codec,
                )
        if last_error is not None:
            raise last_error
        raise RuntimeError("no H.264 encoder candidate could encode the PNG sequence")

    def runtime_backend_candidates(self) -> tuple[H264EncoderBackend, ...]:
        result: list[H264EncoderBackend] = []
        for backend in available_h264_backends():
            if backend.hardware and self.is_hardware_backend_disabled(backend.codec):
                continue
            result.append(backend)
        if not result or result[-1].codec != "libx264":
            result.append(get_h264_backend("libx264"))
        return tuple(_dedupe_backends(result))

    @staticmethod
    def disable_hardware_backend(codec: str, *, reason: str) -> None:
        backend = _known_backend(codec)
        if backend is None or not backend.hardware:
            return
        with _DISABLED_HARDWARE_CODECS_LOCK:
            already_disabled = codec in _DISABLED_HARDWARE_CODECS
            _DISABLED_HARDWARE_CODECS.add(codec)
        if not already_disabled:
            logger.warning(
                "disabling hardware encoder {} for current process: {}",
                codec,
                reason,
            )

    @staticmethod
    def is_hardware_backend_disabled(codec: str) -> bool:
        with _DISABLED_HARDWARE_CODECS_LOCK:
            return codec in _DISABLED_HARDWARE_CODECS

    def _ffmpeg_python_param_candidates(
        self,
        preferred_params: Mapping[str, object] | None,
        *,
        supports_backend_projection: bool,
    ) -> tuple[dict[str, object], ...]:
        candidates: list[dict[str, object]] = []
        preferred = dict(preferred_params or {})
        preferred_codec = str(preferred.get("vcodec") or "")
        preferred_backend = _known_backend(preferred_codec)
        preferred_supports_graph = (
            preferred_backend is None
            or preferred_backend.legacy_ffmpeg_python_compatible
            or supports_backend_projection
        )
        if (
            preferred
            and preferred_supports_graph
            and not self.is_hardware_backend_disabled(preferred_codec)
        ):
            candidates.append(preferred)

        for backend in self.runtime_backend_candidates():
            # Generic ffmpeg-python graphs cannot apply backend-owned device,
            # format, or upload projections. Only explicitly compatible backends
            # may enter those paths; render graphs opt in to the full contract.
            if (
                not supports_backend_projection
                and not backend.legacy_ffmpeg_python_compatible
            ):
                continue
            candidates.append(dict(backend.output_kwargs()))

        candidates.append(dict(ffmpeg_h264_fallback_kwargs()))
        return tuple(_dedupe_param_sets(candidates))

    def _png_sequence_command(
        self,
        *,
        backend: H264EncoderBackend,
        frame_pattern: Path,
        fps: int,
        output_path: Path,
        duration: float,
        audio_path: Path | None,
    ) -> list[str] | None:
        try:
            projection = backend.render_graph_projection()
        except RuntimeError:
            return None
        command = ["ffmpeg", "-y", *projection.global_args]

        command.extend(
            (
                "-framerate",
                str(fps),
                "-i",
                str(frame_pattern),
            )
        )
        if audio_path is not None and audio_path.exists():
            command.extend(("-i", str(audio_path)))

        filters: list[str] = []
        if projection.input_pixel_format is not None:
            filters.append(f"format={projection.input_pixel_format}")
        if projection.requires_hardware_upload:
            filters.append("hwupload")
        if filters:
            command.extend(("-vf", ",".join(filters)))

        command.extend(backend.command_output_args())
        if projection.output_pixel_format is not None:
            command.extend(("-pix_fmt", projection.output_pixel_format))

        if audio_path is not None and audio_path.exists():
            command.extend(("-c:a", "aac"))
        command.extend(("-t", str(duration), str(output_path)))
        return command


def reset_runtime_encoder_failures() -> None:
    """Test/process-maintenance hook; discovery probe caches remain untouched."""

    with _DISABLED_HARDWARE_CODECS_LOCK:
        _DISABLED_HARDWARE_CODECS.clear()


def runtime_disabled_hardware_codecs() -> tuple[str, ...]:
    with _DISABLED_HARDWARE_CODECS_LOCK:
        return tuple(sorted(_DISABLED_HARDWARE_CODECS))


def _known_backend(codec: str) -> H264EncoderBackend | None:
    try:
        return get_h264_backend(codec)
    except ValueError:
        return None


def _dedupe_backends(
    values: list[H264EncoderBackend],
) -> list[H264EncoderBackend]:
    result: list[H264EncoderBackend] = []
    seen: set[str] = set()
    for backend in values:
        if backend.codec in seen:
            continue
        seen.add(backend.codec)
        result.append(backend)
    return result


def _dedupe_param_sets(
    values: list[dict[str, object]],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for params in values:
        key = tuple(sorted((str(k), repr(v)) for k, v in params.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(params)
    return result


__all__ = [
    "UnifiedVideoEncoder",
    "reset_runtime_encoder_failures",
    "runtime_disabled_hardware_codecs",
]
