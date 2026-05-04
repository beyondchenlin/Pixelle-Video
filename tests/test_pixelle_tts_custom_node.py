import importlib.util
import sys
import types
from pathlib import Path

import pytest

PLUGIN_PATH = Path("tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS/pixelle_edge_tts.py")


def _load_plugin_module():
    spec = importlib.util.spec_from_file_location("pixelle_edge_tts_plugin", PLUGIN_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_speed_multiplier_to_rate_formats_positive_and_negative_values():
    module = _load_plugin_module()

    assert module.speed_multiplier_to_rate(1.0) == "+0%"
    assert module.speed_multiplier_to_rate(1.2) == "+20%"
    assert module.speed_multiplier_to_rate(0.85) == "-15%"


def test_normalize_voice_id_accepts_real_edge_voice_ids():
    module = _load_plugin_module()

    assert module.normalize_voice_id("zh-CN-YunjianNeural") == "zh-CN-YunjianNeural"


def test_normalize_voice_id_rejects_display_labels():
    module = _load_plugin_module()

    with pytest.raises(ValueError, match="real Edge voice ID"):
        module.normalize_voice_id("[Chinese] zh-CN Yunjian")


def test_pixelle_float_input_returns_float_value():
    module = _load_plugin_module()
    node = module.PixelleFloatInput()

    assert node.get_value(1.25) == (1.25,)


def test_pixelle_omnivoice_transcribe_uses_preloaded_whisper_pipeline(monkeypatch):
    module = _load_plugin_module()
    node = module.PixelleOmniVoiceTranscribe()
    calls = []

    monkeypatch.setattr(
        module,
        "comfy_audio_to_mono_numpy",
        lambda audio: ("audio-array", 16000),
    )
    monkeypatch.setattr(
        module,
        "transcribe_audio_with_pipeline",
        lambda pipe, audio_np, sample_rate: calls.append((pipe, audio_np, sample_rate))
        or "transcribed text",
    )

    result = node.transcribe(
        {"waveform": object(), "sample_rate": 16000},
        {"pipeline": "whisper-pipeline"},
    )

    assert result == ("transcribed text",)
    assert calls == [("whisper-pipeline", "audio-array", 16000)]


def test_comfy_audio_to_mono_numpy_mixes_channels(monkeypatch):
    module = _load_plugin_module()

    class FakeWaveform:
        def detach(self):
            return self

        def cpu(self):
            return self

        def float(self):
            return self

        def numpy(self):
            return [
                [
                    [1.0, 3.0, 5.0],
                    [3.0, 5.0, 7.0],
                ]
            ]

    audio_np, sample_rate = module.comfy_audio_to_mono_numpy(
        {"waveform": FakeWaveform(), "sample_rate": 44100}
    )

    assert sample_rate == 44100
    assert audio_np.tolist() == [2.0, 4.0, 6.0]


def test_pixelle_omnivoice_transcribe_requires_whisper_pipeline():
    module = _load_plugin_module()
    node = module.PixelleOmniVoiceTranscribe()

    with pytest.raises(ValueError, match="valid OmniVoice whisper_model"):
        node.transcribe({"waveform": object(), "sample_rate": 16000}, {})


def test_decode_pcm_bytes_to_audio_rejects_silent_waveform(monkeypatch):
    module = _load_plugin_module()

    class FakeTensor:
        def clone(self):
            return self

        def numel(self):
            return 4

        def abs(self):
            return self

        def max(self):
            return 0.0

    fake_torch = types.ModuleType("torch")
    fake_torch.float32 = object()
    fake_torch.frombuffer = lambda _buffer, dtype: FakeTensor()
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    with pytest.raises(RuntimeError, match="decoded waveform is silent"):
        module.decode_pcm_bytes_to_audio(b"\x00" * 16, sample_rate=24000)
