from pixelle_video.models.render_package import AudioBlock, SentenceUnit
from pixelle_video.services.alignment_service import AlignmentService


class FakeAligner:
    def align(self, audio, text, language="zh"):
        return {
            "words": [
                {"text": "Sentence", "start": 0.10, "end": 0.80},
                {"text": "1", "start": 0.80, "end": 1.10},
                {"text": "Sentence", "start": 2.20, "end": 2.90},
                {"text": "2", "start": 2.90, "end": 3.20},
            ]
        }


class BlockAwareFakeAligner:
    def __init__(self):
        self.calls = []

    def align(self, audio, text, language="zh"):
        self.calls.append((audio, text, language))
        if audio == "block-0.wav":
            return {
                "words": [
                    {"text": "Alpha", "start": 0.0, "end": 0.4},
                    {"text": "one", "start": 0.4, "end": 0.8},
                    {"text": "Beta", "start": 0.8, "end": 1.2},
                    {"text": "two", "start": 1.2, "end": 1.6},
                ]
            }

        return {
            "words": [
                {"text": "Gamma", "start": 5.0, "end": 5.3},
                {"text": "three", "start": 5.3, "end": 5.7},
                {"text": "Delta", "start": 5.7, "end": 6.0},
                {"text": "four", "start": 6.0, "end": 6.4},
            ]
        }


def test_alignment_service_maps_known_text_back_to_sentence_spans():
    service = AlignmentService(client=FakeAligner())
    block = AudioBlock(
        id="block-0",
        text="Sentence 1. Sentence 2.",
        audio_path="block.wav",
        start=0.0,
        end=4.0,
        source_frame_indices=[0, 1],
    )
    sentences = [
        SentenceUnit(
            id="s1",
            text="Sentence 1.",
            frame_indices=[0],
            block_id="block-0",
            source_start=0.0,
            source_end=0.0,
        ),
        SentenceUnit(
            id="s2",
            text="Sentence 2.",
            frame_indices=[1],
            block_id="block-0",
            source_start=0.0,
            source_end=0.0,
        ),
    ]

    aligned = service.align_block(block, sentences)

    assert aligned[0].source_start == 0.10
    assert aligned[0].source_end == 1.10
    assert aligned[1].source_start == 2.20
    assert aligned[1].source_end == 3.20


def test_alignment_service_groups_sentences_by_block_id_when_aligning_multiple_blocks():
    client = BlockAwareFakeAligner()
    service = AlignmentService(client=client)
    blocks = [
        AudioBlock(
            id="block-0",
            text="Alpha one. Beta two.",
            audio_path="block-0.wav",
            start=0.0,
            end=2.0,
            source_frame_indices=[0, 1],
        ),
        AudioBlock(
            id="block-1",
            text="Gamma three. Delta four.",
            audio_path="block-1.wav",
            start=2.0,
            end=4.0,
            source_frame_indices=[2, 3],
        ),
    ]
    sentences = [
        SentenceUnit(
            id="s1",
            text="Alpha one.",
            frame_indices=[0],
            block_id="block-0",
            source_start=None,
            source_end=None,
        ),
        SentenceUnit(
            id="s2",
            text="Beta two.",
            frame_indices=[1],
            block_id="block-0",
            source_start=None,
            source_end=None,
        ),
        SentenceUnit(
            id="s3",
            text="Gamma three.",
            frame_indices=[2],
            block_id="block-1",
            source_start=None,
            source_end=None,
        ),
        SentenceUnit(
            id="s4",
            text="Delta four.",
            frame_indices=[3],
            block_id="block-1",
            source_start=None,
            source_end=None,
        ),
    ]

    aligned = service.align_blocks(blocks, sentences)

    assert client.calls == [
        ("block-0.wav", "Alpha one. Beta two.", "zh"),
        ("block-1.wav", "Gamma three. Delta four.", "zh"),
    ]
    assert [sentence.source_start for sentence in aligned if sentence.block_id == "block-0"] == [
        0.0,
        0.8,
    ]
    assert [sentence.source_start for sentence in aligned if sentence.block_id == "block-1"] == [
        5.0,
        5.7,
    ]
