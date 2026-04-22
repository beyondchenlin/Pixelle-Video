import json

import pytest

from pixelle_video.models.render_package import SentenceUnit
from pixelle_video.services.audio_edit_service import (
    AudioEditService,
    AutoEditorTimeline,
    resolve_auto_editor_executable,
)


class FakeAutoEditorRunner:
    def __init__(self, timeline_json: str):
        self.timeline_json = timeline_json
        self.timeline_calls: list[tuple[str, int | None]] = []
        self.trim_calls: list[tuple[str, str, int | None]] = []

    def export_timeline(self, audio_path: str, margin_ms: int | None = None) -> str:
        self.timeline_calls.append((audio_path, margin_ms))
        return self.timeline_json

    def export_trimmed_audio(
        self,
        audio_path: str,
        output_path: str,
        margin_ms: int | None = None,
    ) -> str:
        self.trim_calls.append((audio_path, output_path, margin_ms))
        with open(output_path, "wb") as handle:
            handle.write(b"trimmed-audio")
        return output_path


def test_auto_editor_timeline_remaps_sentence_spans_across_removed_silence():
    timeline = AutoEditorTimeline(
        chunks=[[0, 30, 1.0], [30, 40, 0.0], [40, 80, 1.0]],
        timebase=10.0,
    )
    sentence = SentenceUnit(
        id="s1",
        text="Hello world.",
        source_start=2.0,
        source_end=6.0,
    )

    remapped = timeline.remap_sentence(sentence)

    assert remapped is sentence
    assert sentence.remapped_start == 2.0
    assert sentence.remapped_end == 5.0


def test_audio_edit_service_exports_timeline_and_remaps_sentence_units():
    runner = FakeAutoEditorRunner(
        json.dumps(
            {
                "version": "1",
                "source": "speech.wav",
                "timebase": 10.0,
                "chunks": [[0, 30, 1.0], [30, 40, 0.0], [40, 80, 1.0]],
            }
        )
    )
    service = AudioEditService(runner=runner)
    sentence = SentenceUnit(
        id="s1",
        text="Hello world.",
        source_start=2.0,
        source_end=6.0,
    )

    remapped = service.remap_sentence_units_from_audio("speech.wav", [sentence])

    assert runner.timeline_calls == [("speech.wav", None)]
    assert remapped[0] is sentence
    assert sentence.remapped_start == 2.0
    assert sentence.remapped_end == 5.0


def test_audio_edit_service_can_export_trimmed_audio_and_timeline_together(tmp_path):
    runner = FakeAutoEditorRunner(
        json.dumps(
            {
                "version": "1",
                "source": "speech.wav",
                "timebase": 10.0,
                "chunks": [[0, 30, 1.0], [30, 40, 0.0], [40, 80, 1.0]],
            }
        )
    )
    service = AudioEditService(runner=runner)
    output_path = tmp_path / "trimmed.wav"

    result = service.export_trimmed_audio_and_timeline("speech.wav", str(output_path))

    assert runner.timeline_calls == [("speech.wav", None)]
    assert runner.trim_calls == [("speech.wav", str(output_path), None)]
    assert result.trimmed_audio_path == str(output_path)
    assert output_path.exists()
    assert result.timeline.timebase == 10.0
    assert result.timeline.source == "speech.wav"


def test_audio_edit_service_forwards_margin_ms_to_timeline_and_trim_exports(tmp_path):
    runner = FakeAutoEditorRunner(
        json.dumps(
            {
                "version": "1",
                "source": "speech.wav",
                "timebase": 10.0,
                "chunks": [[0, 30, 1.0], [30, 40, 0.0], [40, 80, 1.0]],
            }
        )
    )
    service = AudioEditService(runner=runner)
    output_path = tmp_path / "trimmed.wav"

    service.export_trimmed_audio_and_timeline(
        "speech.wav",
        str(output_path),
        margin_ms=345,
    )

    assert runner.timeline_calls == [("speech.wav", 345)]
    assert runner.trim_calls == [("speech.wav", str(output_path), 345)]


def test_audio_edit_service_parses_mapping_chunks_and_rejects_zero_timebase():
    timeline = AutoEditorTimeline.from_mapping(
        {
            "version": "1",
            "source": "speech.wav",
            "timebase": 10.0,
            "chunks": [
                {"start": 0, "end": 30, "speed": 1.0},
                {"start": 30, "end": 40, "speed": 0.0},
                {"start": 40, "end": 80, "speed": 1.0},
            ],
        }
    )
    sentence = SentenceUnit(id="s1", text="Hello world.", source_start=2.0, source_end=6.0)

    timeline.remap_sentence(sentence)

    assert sentence.remapped_start == 2.0
    assert sentence.remapped_end == 5.0

    with pytest.raises(ValueError, match="timebase must be positive"):
        AutoEditorTimeline.from_mapping(
            {
                "version": "1",
                "source": "speech.wav",
                "timebase": 0,
                "chunks": [[0, 30, 1.0]],
            }
        )


def test_resolve_auto_editor_executable_prefers_repo_venv_binary_over_path(tmp_path):
    repo_root = tmp_path / "repo"
    path_binary = tmp_path / "path-bin" / "auto-editor.exe"
    venv_binary = repo_root / ".venv" / "Scripts" / "auto-editor.exe"

    path_binary.parent.mkdir(parents=True, exist_ok=True)
    path_binary.write_text("binary", encoding="utf-8")
    venv_binary.parent.mkdir(parents=True, exist_ok=True)
    venv_binary.write_text("binary", encoding="utf-8")

    resolved = resolve_auto_editor_executable(
        repo_root=repo_root,
        which_fn=lambda _: str(path_binary),
    )

    assert resolved == str(venv_binary)


def test_resolve_auto_editor_executable_falls_back_to_repo_venv_binary(tmp_path):
    repo_root = tmp_path / "repo"
    venv_binary = repo_root / ".venv" / "Scripts" / "auto-editor.exe"
    venv_binary.parent.mkdir(parents=True, exist_ok=True)
    venv_binary.write_text("binary", encoding="utf-8")

    resolved = resolve_auto_editor_executable(
        repo_root=repo_root,
        which_fn=lambda _: None,
    )

    assert resolved == str(venv_binary)


def test_resolve_auto_editor_executable_falls_back_to_path_when_repo_venv_is_missing(tmp_path):
    path_binary = tmp_path / "path-bin" / "auto-editor.exe"
    path_binary.parent.mkdir(parents=True, exist_ok=True)
    path_binary.write_text("binary", encoding="utf-8")

    resolved = resolve_auto_editor_executable(
        repo_root=tmp_path / "repo",
        which_fn=lambda _: str(path_binary),
    )

    assert resolved == str(path_binary)
