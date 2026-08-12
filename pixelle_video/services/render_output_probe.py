from __future__ import annotations

import json
import math
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import ffmpeg


class RenderOutputContractError(RuntimeError):
    """Raised when an encoded artifact violates the final render contract."""

    ENCODER_SENSITIVE_PREFIXES = (
        "average frame rate mismatch",
        "nominal frame rate mismatch",
        "output is not constant-frame-rate",
        "codec_name mismatch",
        "pix_fmt mismatch",
        "color_range mismatch",
        "color_space mismatch",
        "color_primaries mismatch",
        "color_transfer mismatch",
    )

    def __init__(self, message: str, *, errors: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.errors = errors or (message,)

    @property
    def encoder_sensitive(self) -> bool:
        return bool(self.errors) and all(
            error.startswith(self.ENCODER_SENSITIVE_PREFIXES)
            for error in self.errors
        )


@dataclass(frozen=True)
class RenderOutputProbeResult:
    path: str
    width: int
    height: int
    fps: float
    pixel_format: str
    color_range: str
    color_space: str
    color_primaries: str
    color_transfer: str
    video_codec: str
    video_duration: float
    audio_codec: str
    audio_duration: float
    audio_sample_rate: int
    audio_channels: int
    encoder_backend: str | None = None
    lossy_encode_count: int = 1
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ok"] = self.ok
        payload["errors"] = list(self.errors)
        return payload


class RenderOutputProbe:
    DURATION_TOLERANCE_SECONDS = 0.055
    FPS_TOLERANCE = 0.001

    def media_duration(
        self,
        media_path: str | Path,
        *,
        stream_type: str,
    ) -> float:
        path = Path(media_path).resolve()
        try:
            payload = ffmpeg.probe(str(path))
        except (ffmpeg.Error, OSError) as exc:
            raw_stderr = getattr(exc, "stderr", None)
            stderr = (
                raw_stderr.decode("utf-8", errors="replace")
                if raw_stderr
                else str(exc)
            )
            raise RenderOutputContractError(
                f"render input could not be probed: {path}: {stderr}"
            ) from exc
        stream = next(
            (
                item
                for item in payload.get("streams", [])
                if item.get("codec_type") == stream_type
            ),
            None,
        )
        if stream is None:
            raise RenderOutputContractError(
                f"render input is missing its {stream_type} stream: {path}"
            )
        format_duration = _finite_float((payload.get("format") or {}).get("duration"))
        duration = _stream_duration(stream, fallback=format_duration)
        if duration <= 0:
            raise RenderOutputContractError(
                f"render input has no positive {stream_type} duration: {path}"
            )
        return duration

    def validate(
        self,
        *,
        output_path: str | Path,
        width: int,
        height: int,
        fps: int,
        duration: float,
        subtitle_end: float | None = None,
        report_path: str | Path | None = None,
        encoder_backend: str | None = None,
        lossy_encode_count: int = 1,
    ) -> RenderOutputProbeResult:
        path = Path(output_path).resolve()
        if not path.is_file() or path.stat().st_size <= 0:
            message = f"render output must be a non-empty file: {path}"
            self._write_early_failure(
                path=path,
                report_path=report_path,
                message=message,
                encoder_backend=encoder_backend,
                lossy_encode_count=lossy_encode_count,
            )
            raise RenderOutputContractError(message)

        try:
            payload = ffmpeg.probe(str(path))
        except (ffmpeg.Error, OSError) as exc:
            raw_stderr = getattr(exc, "stderr", None)
            stderr = (
                raw_stderr.decode("utf-8", errors="replace")
                if raw_stderr
                else str(exc)
            )
            message = f"render output could not be probed: {stderr}"
            self._write_early_failure(
                path=path,
                report_path=report_path,
                message=message,
                encoder_backend=encoder_backend,
                lossy_encode_count=lossy_encode_count,
            )
            raise RenderOutputContractError(message) from exc

        streams = list(payload.get("streams") or [])
        video = next(
            (stream for stream in streams if stream.get("codec_type") == "video"),
            None,
        )
        audio = next(
            (stream for stream in streams if stream.get("codec_type") == "audio"),
            None,
        )
        if video is None or audio is None:
            missing = "video" if video is None else "audio"
            message = f"render output is missing its {missing} stream"
            self._write_early_failure(
                path=path,
                report_path=report_path,
                message=message,
                encoder_backend=encoder_backend,
                lossy_encode_count=lossy_encode_count,
            )
            raise RenderOutputContractError(message)

        format_duration = _finite_float((payload.get("format") or {}).get("duration"))
        video_duration = _stream_duration(video, fallback=format_duration)
        audio_duration = _stream_duration(audio, fallback=format_duration)
        average_fps = _fraction(video.get("avg_frame_rate"))
        nominal_fps = _fraction(video.get("r_frame_rate"))
        errors: list[str] = []

        actual_width = int(video.get("width") or 0)
        actual_height = int(video.get("height") or 0)
        if (actual_width, actual_height) != (int(width), int(height)):
            errors.append(
                "canvas mismatch: "
                f"expected {width}x{height}, got {actual_width}x{actual_height}"
            )
        if not math.isclose(average_fps, float(fps), abs_tol=self.FPS_TOLERANCE):
            errors.append(f"average frame rate mismatch: expected {fps}, got {average_fps}")
        if not math.isclose(nominal_fps, float(fps), abs_tol=self.FPS_TOLERANCE):
            errors.append(f"nominal frame rate mismatch: expected {fps}, got {nominal_fps}")
        if not math.isclose(average_fps, nominal_fps, abs_tol=self.FPS_TOLERANCE):
            errors.append(
                "output is not constant-frame-rate: "
                f"average={average_fps}, nominal={nominal_fps}"
            )

        expected_video = {
            "codec_name": "h264",
            "pix_fmt": "yuv420p",
            "color_range": "tv",
            "color_space": "bt709",
            "color_primaries": "bt709",
            "color_transfer": "bt709",
        }
        for field, expected in expected_video.items():
            actual = str(video.get(field) or "")
            if actual != expected:
                errors.append(f"{field} mismatch: expected {expected}, got {actual or 'missing'}")

        expected_duration = float(duration)
        if abs(audio_duration - expected_duration) > self.DURATION_TOLERANCE_SECONDS:
            errors.append(
                "audio duration mismatch: "
                f"expected {expected_duration:.6f}, got {audio_duration:.6f}"
            )
        if abs(video_duration - expected_duration) > self.DURATION_TOLERANCE_SECONDS:
            errors.append(
                "video duration mismatch: "
                f"expected {expected_duration:.6f}, got {video_duration:.6f}"
            )
        if subtitle_end is not None:
            required_end = float(subtitle_end) + (1.0 / float(fps))
            if video_duration + self.DURATION_TOLERANCE_SECONDS < required_end:
                errors.append(
                    "video does not cover the final subtitle plus one frame: "
                    f"required {required_end:.6f}, got {video_duration:.6f}"
                )

        audio_codec = str(audio.get("codec_name") or "")
        audio_sample_rate = int(audio.get("sample_rate") or 0)
        audio_channels = int(audio.get("channels") or 0)
        if audio_codec != "aac":
            errors.append(f"audio codec mismatch: expected aac, got {audio_codec or 'missing'}")
        if audio_sample_rate != 48000:
            errors.append(
                f"audio sample rate mismatch: expected 48000, got {audio_sample_rate}"
            )
        if audio_channels != 2:
            errors.append(f"audio channel mismatch: expected 2, got {audio_channels}")

        result = RenderOutputProbeResult(
            path=str(path),
            width=actual_width,
            height=actual_height,
            fps=average_fps,
            pixel_format=str(video.get("pix_fmt") or ""),
            color_range=str(video.get("color_range") or ""),
            color_space=str(video.get("color_space") or ""),
            color_primaries=str(video.get("color_primaries") or ""),
            color_transfer=str(video.get("color_transfer") or ""),
            video_codec=str(video.get("codec_name") or ""),
            video_duration=video_duration,
            audio_codec=audio_codec,
            audio_duration=audio_duration,
            audio_sample_rate=audio_sample_rate,
            audio_channels=audio_channels,
            encoder_backend=encoder_backend,
            lossy_encode_count=int(lossy_encode_count),
            errors=tuple(errors),
        )
        if report_path is not None:
            self._write_report(report_path, result.to_dict())
        if errors:
            raise RenderOutputContractError("; ".join(errors), errors=tuple(errors))
        return result

    def _write_early_failure(
        self,
        *,
        path: Path,
        report_path: str | Path | None,
        message: str,
        encoder_backend: str | None,
        lossy_encode_count: int,
    ) -> None:
        if report_path is None:
            return
        self._write_report(
            report_path,
            {
                "path": str(path),
                "ok": False,
                "encoder_backend": encoder_backend,
                "lossy_encode_count": int(lossy_encode_count),
                "errors": [message],
            },
        )

    @staticmethod
    def _write_report(report_path: str | Path, payload: dict[str, Any]) -> None:
        target = Path(report_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_report = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary_report.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary_report, target)
        finally:
            if temporary_report.exists():
                temporary_report.unlink()


def _fraction(value: object) -> float:
    raw = str(value or "0/1")
    numerator_text, separator, denominator_text = raw.partition("/")
    try:
        numerator = float(numerator_text)
        denominator = float(denominator_text) if separator else 1.0
    except (TypeError, ValueError):
        return 0.0
    if denominator == 0:
        return 0.0
    result = numerator / denominator
    return result if math.isfinite(result) else 0.0


def _finite_float(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def _stream_duration(stream: dict[str, Any], *, fallback: float) -> float:
    duration = _finite_float(stream.get("duration"))
    if duration > 0:
        return duration
    duration_ts = _finite_float(stream.get("duration_ts"))
    time_base = _fraction(stream.get("time_base"))
    if duration_ts > 0 and time_base > 0:
        return duration_ts * time_base
    return fallback


__all__ = [
    "RenderOutputContractError",
    "RenderOutputProbe",
    "RenderOutputProbeResult",
]
