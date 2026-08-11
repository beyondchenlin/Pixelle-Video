from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found in {path}")


def _call_names(node: ast.AST) -> tuple[str, ...]:
    result: list[str] = []
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        result.append(ast.unparse(item.func))
    return tuple(result)


def test_video_service_encode_run_delegates_to_shared_executor() -> None:
    node = _function(ROOT / "pixelle_video/services/video.py", "_encode_run")

    assert "self._h264_executor.run_output" in _call_names(node)


def test_subtitle_overlay_and_filter_concat_use_shared_executor() -> None:
    path = ROOT / "pixelle_video/services/video.py"

    subtitle_calls = _call_names(_function(path, "burn_ass_subtitles"))
    overlay_calls = _call_names(_function(path, "overlay_image_on_video"))
    concat_calls = _call_names(_function(path, "_concat_filter"))

    assert "self._encode_run" in subtitle_calls
    assert "self._encode_run" in overlay_calls
    assert "self._h264_executor.run_command" in concat_calls


def test_video_service_no_longer_hardcodes_libx264_reencode() -> None:
    source = (ROOT / "pixelle_video/services/video.py").read_text(encoding="utf-8")

    assert 'vcodec="libx264"' not in source


def test_element_animation_uses_shared_command_executor() -> None:
    path = ROOT / "pixelle_video/services/element_animation_renderer.py"
    node = _function(path, "render_video")

    assert "self._h264_executor.run_command" in _call_names(node)
    source = path.read_text(encoding="utf-8")
    assert "resolve_ffmpeg_h264_encoder" not in source
    assert "subprocess.run" not in source
