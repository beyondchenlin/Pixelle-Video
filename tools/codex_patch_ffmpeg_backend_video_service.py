from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: target block not found")
    return text.replace(old, new, 1)


path = Path("pixelle_video/services/video.py")
text = path.read_text(encoding="utf-8")

text = replace_once(
    text,
    '''from pixelle_video.utils.ffmpeg_encoder import (
    ffmpeg_h264_encode_kwargs,
    ffmpeg_h264_preset,
    resolve_ffmpeg_h264_encoder,
)
''',
    '''from pixelle_video.utils.ffmpeg_encoder import (
    disable_ffmpeg_h264_encoder,
    ffmpeg_h264_fallback_kwargs,
    ffmpeg_h264_output_kwargs,
    resolve_ffmpeg_h264_encoder,
)
''',
    "encoder imports",
)

old_methods = '''    @staticmethod
    def _h264_encode_params() -> dict[str, object]:
        vcodec = resolve_ffmpeg_h264_encoder()
        params: dict[str, object] = {
            "vcodec": vcodec,
            "preset": ffmpeg_h264_preset(vcodec),
            "crf": 23,
        }
        for key, val in ffmpeg_h264_encode_kwargs(vcodec).items():
            params[key] = val
        return params

    def _encode_run(self, build_output, *, quiet=False):
        params = self._h264_encode_params()
        try:
            extra: dict[str, bool] = {"capture_stdout": True, "capture_stderr": True}
            if quiet:
                extra["quiet"] = True
            build_output(**params).run(**extra)
        except ffmpeg.Error:
            vcodec = params.get("vcodec")
            if vcodec == "libx264":
                raise
            logger.warning("GPU encoder {} failed, retrying with CPU libx264", vcodec)
            extra = {"capture_stdout": True, "capture_stderr": True}
            if quiet:
                extra["quiet"] = True
            build_output(vcodec="libx264", preset="medium", crf=23).run(**extra)
'''
new_methods = '''    @staticmethod
    def _h264_encode_params() -> dict[str, object]:
        return ffmpeg_h264_output_kwargs(resolve_ffmpeg_h264_encoder())

    def _encode_run(self, build_output, *, quiet=False):
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
text = replace_once(text, old_methods, new_methods, "video service encoder methods")
path.write_text(text, encoding="utf-8")
