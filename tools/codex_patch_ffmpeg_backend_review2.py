from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: target block not found")
    return text.replace(old, new, 1)


encoder_path = Path("pixelle_video/utils/ffmpeg_encoder.py")
text = encoder_path.read_text(encoding="utf-8")

old_helpers = '''def ffmpeg_h264_preset(vcodec: str) -> str:
    """Compatibility helper for callers that only need the family preset."""

    backend = ffmpeg_h264_backend(vcodec)
    return backend.preset or ""


def ffmpeg_h264_encode_kwargs(vcodec: str) -> dict[str, object]:
    """Compatibility helper returning family-specific non-base options."""

    backend = ffmpeg_h264_backend(vcodec)
    params = backend.output_kwargs()
    params.pop("vcodec", None)
    params.pop("preset", None)
    if backend.family == "cpu":
        params.pop("crf", None)
    return params
'''
new_helpers = '''def ffmpeg_h264_preset(vcodec: str) -> str:
    """Compatibility helper limited to simple software-frame output paths."""

    backend = ffmpeg_h264_backend(vcodec)
    if not backend.supports_simple_software_frame_output:
        raise ValueError(
            f"{vcodec} requires a hardware-frame executor and has no simple preset contract"
        )
    return backend.preset or ""


def ffmpeg_h264_encode_kwargs(vcodec: str) -> dict[str, object]:
    """Compatibility helper limited to simple software-frame output paths."""

    backend = ffmpeg_h264_backend(vcodec)
    params = ffmpeg_h264_output_kwargs(vcodec)
    params.pop("vcodec", None)
    params.pop("preset", None)
    if backend.family == "cpu":
        params.pop("crf", None)
    return params
'''
text = replace_once(text, old_helpers, new_helpers, "compatibility helpers")
encoder_path.write_text(text, encoding="utf-8")


test_path = Path("tests/test_ffmpeg_encoder.py")
tests = test_path.read_text(encoding="utf-8")
if "test_legacy_compatibility_helpers_cannot_bypass_vaapi_hardware_frame_guard" in tests:
    raise RuntimeError("review2 test already present")

tests += '''


def test_legacy_compatibility_helpers_cannot_bypass_vaapi_hardware_frame_guard() -> None:
    with pytest.raises(ValueError, match="hardware-frame executor"):
        encoder.ffmpeg_h264_preset("h264_vaapi")
    with pytest.raises(ValueError, match="hardware-frame upload"):
        encoder.ffmpeg_h264_encode_kwargs("h264_vaapi")
'''
test_path.write_text(tests, encoding="utf-8")
