import sys
import types

import pytest

from pixelle_video.models.render_package import AudioBlock, SentenceUnit
from pixelle_video.services.alignment_service import (
    AlignmentService,
    _QwenForcedAlignerClient,
)


class FakeAligner:
    def align(self, audio, text, language="Chinese"):
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

    def align(self, audio, text, language="Chinese"):
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
        ("block-0.wav", "Alpha one. Beta two.", "Chinese"),
        ("block-1.wav", "Gamma three. Delta four.", "Chinese"),
    ]
    assert [sentence.source_start for sentence in aligned if sentence.block_id == "block-0"] == [
        0.0,
        0.8,
    ]
    assert [sentence.source_start for sentence in aligned if sentence.block_id == "block-1"] == [
        5.0,
        5.7,
    ]


def test_alignment_service_can_estimate_sentence_spans_from_block_duration_metadata():
    service = AlignmentService(client=FakeAligner())
    blocks = [
        AudioBlock(
            id="block-0",
            text="Alpha one. Beta two two.",
            audio_path="block-0.wav",
            start=0.0,
            end=4.0,
            source_frame_indices=[0, 1],
        )
    ]
    sentences = [
        SentenceUnit(
            id="s1",
            text="Alpha one.",
            frame_indices=[0],
            block_id="block-0",
        ),
        SentenceUnit(
            id="s2",
            text="Beta two two.",
            frame_indices=[1],
            block_id="block-0",
        ),
    ]

    aligned = service.align_blocks_by_duration(blocks, sentences)

    assert aligned[0].source_start == pytest.approx(0.0)
    assert aligned[0].source_end == pytest.approx(1.6)
    assert aligned[1].source_start == pytest.approx(1.6)
    assert aligned[1].source_end == pytest.approx(4.0)


def _install_fake_qwen_forced_aligner(monkeypatch, fake_aligner_cls):
    fake_qwen_module = types.ModuleType("qwen_asr")
    fake_inference_module = types.ModuleType("qwen_asr.inference")
    fake_aligner_module = types.ModuleType("qwen_asr.inference.qwen3_forced_aligner")
    fake_qwen_module.__path__ = []
    fake_inference_module.__path__ = []
    fake_aligner_module.Qwen3ForcedAligner = fake_aligner_cls
    fake_inference_module.qwen3_forced_aligner = fake_aligner_module
    fake_qwen_module.inference = fake_inference_module

    monkeypatch.setitem(sys.modules, "qwen_asr", fake_qwen_module)
    monkeypatch.setitem(sys.modules, "qwen_asr.inference", fake_inference_module)
    monkeypatch.setitem(
        sys.modules,
        "qwen_asr.inference.qwen3_forced_aligner",
        fake_aligner_module,
    )


def test_alignment_service_uses_local_model_path_with_local_files_only(monkeypatch):
    captured = {}

    class FakeAligner:
        @classmethod
        def from_pretrained(cls, model_path, **load_kwargs):
            captured["model_path"] = model_path
            captured["load_kwargs"] = load_kwargs
            return cls()

        def align(self, audio, text, language="Chinese"):
            return {"words": [{"text": "Hello", "start": 1.0, "end": 2.0}]}

    _install_fake_qwen_forced_aligner(monkeypatch, FakeAligner)

    client = _QwenForcedAlignerClient(
        model_path="Qwen/Qwen3-ForcedAligner-0.6B",
        model_kwargs={"device_map": "auto", "dtype": "bfloat16"},
    )
    monkeypatch.setattr(
        client,
        "_ensure_model_local",
        lambda: (r"C:\models\Qwen3-ForcedAligner-0.6B", True),
    )

    result = client.align(audio="block.wav", text="Hello")

    assert result["words"][0]["text"] == "Hello"
    assert captured == {
        "model_path": r"C:\models\Qwen3-ForcedAligner-0.6B",
        "load_kwargs": {
            "device_map": "auto",
            "dtype": "bfloat16",
            "local_files_only": True,
        },
    }


def test_alignment_service_allows_hf_hub_fallback_when_no_local_model_is_available(
    monkeypatch,
):
    captured = {}

    class FakeAligner:
        @classmethod
        def from_pretrained(cls, model_path, **load_kwargs):
            captured["model_path"] = model_path
            captured["load_kwargs"] = load_kwargs
            return cls()

        def align(self, audio, text, language="Chinese"):
            return {"words": [{"text": "Hello", "start": 1.0, "end": 2.0}]}

    _install_fake_qwen_forced_aligner(monkeypatch, FakeAligner)

    client = _QwenForcedAlignerClient(
        model_path="Qwen/Qwen3-ForcedAligner-0.6B",
        model_kwargs={"device_map": "auto", "dtype": "bfloat16"},
    )
    monkeypatch.setattr(
        client,
        "_ensure_model_local",
        lambda: ("Qwen/Qwen3-ForcedAligner-0.6B", False),
    )

    result = client.align(audio="block.wav", text="Hello")

    assert result["words"][0]["text"] == "Hello"
    assert captured == {
        "model_path": "Qwen/Qwen3-ForcedAligner-0.6B",
        "load_kwargs": {"device_map": "auto", "dtype": "bfloat16"},
    }
