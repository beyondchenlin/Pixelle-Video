from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from pixelle_video.services.video import VideoService


ROOT = Path(__file__).resolve().parents[2]


def test_single_video_with_bgm_applies_bgm_instead_of_copying(monkeypatch) -> None:
    service = VideoService()
    calls: list[dict[str, object]] = []

    def fake_add_bgm(**kwargs):
        calls.append(kwargs)
        return str(kwargs["output"])

    monkeypatch.setattr(service, "_add_bgm_to_video", fake_add_bgm)

    result = service.concat_videos(
        ["single.mp4"],
        "final.mp4",
        bgm_path="music.mp3",
        bgm_volume=0.35,
        bgm_mode="loop",
    )

    assert result == "final.mp4"
    assert calls == [
        {
            "video": "single.mp4",
            "bgm_path": "music.mp3",
            "output": "final.mp4",
            "volume": 0.35,
            "mode": "loop",
        }
    ]


def test_silent_concat_input_gets_audio_without_video_reencode(monkeypatch, tmp_path) -> None:
    service = VideoService()
    monkeypatch.setattr(service, "has_audio_stream", lambda _video: False)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    normalized = service._ensure_concat_audio_track(
        "silent.mp4",
        temp_dir=str(tmp_path),
        index=2,
    )

    assert normalized.endswith("concat_audio_0002.mp4")
    assert len(commands) == 1
    command = commands[0]
    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in command
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "aac"
    assert "-shortest" in command


def test_concat_input_with_audio_is_left_untouched(monkeypatch, tmp_path) -> None:
    service = VideoService()
    monkeypatch.setattr(service, "has_audio_stream", lambda _video: True)

    assert (
        service._ensure_concat_audio_track(
            "already_has_audio.mp4",
            temp_dir=str(tmp_path),
            index=0,
        )
        == "already_has_audio.mp4"
    )


def _function(path: Path, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found")


def test_overlay_preserves_source_audio_when_present() -> None:
    node = _function(
        ROOT / "pixelle_video/services/video.py",
        "overlay_image_on_video",
    )
    source = ast.unparse(node)

    assert "video_has_audio = self.has_audio_stream(video)" in source
    assert "streams.append(input_video.audio)" in source
    assert "output_kwargs['acodec'] = 'copy'" in source


def test_standard_pipeline_no_longer_forces_hyperframes_gpu_true() -> None:
    node = _function(
        ROOT / "pixelle_video/pipelines/standard.py",
        "_post_production_hyperframes",
    )

    render_calls = [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "render_async"
    ]
    assert len(render_calls) == 1
    keywords = {item.arg for item in render_calls[0].keywords if item.arg}
    assert "use_gpu" not in keywords
