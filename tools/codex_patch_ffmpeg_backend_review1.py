from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: target block not found")
    return text.replace(old, new, 1)


path = Path("pixelle_video/services/video.py")
text = path.read_text(encoding="utf-8")
old = '''    def _encode_run(self, build_output, *, quiet=False):
        params = self._h264_encode_params()
        try:
            extra: dict[str, bool] = {"capture_stdout": True, "capture_stderr": True}
            if quiet:
                extra["quiet"] = True
            build_output(**params).run(**extra)
        except ffmpeg.Error as exc:
            vcodec = str(params.get("vcodec") or "")
            if vcodec == "libx264":
                raise
            stderr = getattr(exc, "stderr", None)
            if isinstance(stderr, bytes):
                reason = stderr.decode("utf-8", errors="replace")
            else:
                reason = str(stderr or exc)
            reason = " ".join(reason.strip().split())[-400:]
            disable_ffmpeg_h264_encoder(
                vcodec,
                reason=reason or "runtime encode failure",
            )
            logger.warning(
                "Hardware encoder {} failed and was disabled; retrying with CPU libx264",
                vcodec,
            )
            extra = {"capture_stdout": True, "capture_stderr": True}
            if quiet:
                extra["quiet"] = True
            build_output(**ffmpeg_h264_fallback_kwargs()).run(**extra)
'''
new = '''    def _encode_run(self, build_output, *, quiet=False):
        params = self._h264_encode_params()
        extra: dict[str, bool] = {"capture_stdout": True, "capture_stderr": True}
        if quiet:
            extra["quiet"] = True
        try:
            build_output(**params).run(**extra)
        except ffmpeg.Error as hardware_exc:
            vcodec = str(params.get("vcodec") or "")
            if vcodec == "libx264":
                raise

            logger.warning(
                "Hardware encoder {} failed; validating the same task with CPU libx264",
                vcodec,
            )
            try:
                build_output(**ffmpeg_h264_fallback_kwargs()).run(**extra)
            except ffmpeg.Error:
                # The task itself is not proven valid. Do not poison the process-wide
                # hardware capability cache for an input/filter/output failure.
                raise

            stderr = getattr(hardware_exc, "stderr", None)
            if isinstance(stderr, bytes):
                reason = stderr.decode("utf-8", errors="replace")
            else:
                reason = str(stderr or hardware_exc)
            reason = " ".join(reason.strip().split())[-400:]
            disable_ffmpeg_h264_encoder(
                vcodec,
                reason=reason or "hardware-specific runtime encode failure",
            )
            logger.warning(
                "CPU fallback succeeded; disabled hardware encoder {} for this process",
                vcodec,
            )
'''
path.write_text(replace_once(text, old, new, "VideoService._encode_run"), encoding="utf-8")
