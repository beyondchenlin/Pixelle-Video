import json

from pixelle_video.models.render_package import SentenceUnit
from pixelle_video.services.audio_edit_service import AudioEditService, AutoEditorTimeline


class FakeAutoEditorRunner:
    def __init__(self, timeline_json: str):
        self.timeline_json = timeline_json
        self.calls: list[str] = []

    def export_timeline(self, audio_path: str) -> str:
        self.calls.append(audio_path)
        return self.timeline_json


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

    assert runner.calls == ["speech.wav"]
    assert remapped[0] is sentence
    assert sentence.remapped_start == 2.0
    assert sentence.remapped_end == 5.0
