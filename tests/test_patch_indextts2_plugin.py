import importlib

import pytest

UTILS_SAMPLE = """import os
import tempfile
import numpy as np
import soundfile as sf
from typing import Tuple


def save_temp_wav(wave_sr: Tuple[np.ndarray, int]) -> str:
    wave, sr = wave_sr
    tmpdir = tempfile.gettempdir()
    path = os.path.join(tmpdir, "indextts2_cached.wav")
    if os.path.exists(path):
        return path
    sf.write(path, wave, int(sr))
    return path
"""


INFER_V2_SAMPLE = """import os
import torch


class IndexTTS2:
    def __init__(self):
        self.model_dir = "models"
        self.cfg = type("Cfg", (), {"qwen_emo_path": "qwen0.6bemo4-merge "})()
        self.qwen_emo = QwenEmotion(os.path.join(self.model_dir, self.cfg.qwen_emo_path))

    @torch.no_grad()
    def get_emb(self, input_features, attention_mask):
        return input_features

    def infer(self, text, use_emo_text=False, emo_text=None, **generation_kwargs):
        if use_emo_text:
            if emo_text is None:
                emo_text = text
            emo_dict, content = self.qwen_emo.inference(emo_text)
            emo_vector = list(emo_dict.values())

        do_sample = generation_kwargs.pop("do_sample", True)
        top_p = generation_kwargs.pop("top_p", 0.8)

        codes, speech_conditioning_latent = self.gpt.inference_speech(
            text,
            do_sample=True,
            top_p=top_p,
        )
        return codes, speech_conditioning_latent


class QwenEmotion:
    def __init__(self, model_dir):
        self.model_dir = model_dir
"""


CURRENT_UPSTREAM_INFER_V2_SAMPLE = """import os
import torch


class IndexTTS2:
    def __init__(self):
        self.model_dir = "models"
        self.cfg = type("Cfg", (), {"qwen_emo_path": "qwen0.6bemo4-merge "})()
        qwen_subdir = str(self.cfg.qwen_emo_path).strip()
        self.qwen_emo = QwenEmotion(os.path.join(self.model_dir, qwen_subdir))

    @torch.no_grad()
    def get_emb(self, input_features, attention_mask):
        return input_features

    def infer(self, text, use_emo_text=False, emo_text=None, **generation_kwargs):
        if use_emo_text:
            if emo_text is None:
                emo_text = text
            emo_dict, content = self.qwen_emo.inference(emo_text)
            emo_vector = list(emo_dict.values())

        do_sample = generation_kwargs.pop("do_sample", True)
        top_p = generation_kwargs.pop("top_p", 0.8)

        codes, speech_conditioning_latent = self.gpt.inference_speech(
            text,
            do_sample=True,
            top_p=top_p,
        )
        return codes, speech_conditioning_latent


class QwenEmotion:
    def __init__(self, model_dir):
        self.model_dir = model_dir
"""


INFER_V2_SAMPLE_WITH_UNRELATED_DO_SAMPLE = """import os
import torch


class IndexTTS2:
    def __init__(self):
        self.model_dir = "models"
        self.cfg = type("Cfg", (), {"qwen_emo_path": "qwen0.6bemo4-merge "})()
        qwen_subdir = str(self.cfg.qwen_emo_path).strip()
        self.qwen_emo_path = os.path.join(self.model_dir, qwen_subdir)
        self.qwen_emo = None

    def _get_qwen_emo(self):
        if self.qwen_emo is None:
            self.qwen_emo = QwenEmotion(self.qwen_emo_path)
        return self.qwen_emo

    @torch.no_grad()
    def get_emb(self, input_features, attention_mask):
        return input_features

    def infer(self, text, use_emo_text=False, emo_text=None, **generation_kwargs):
        fallback_result = self.audit_generation_defaults(do_sample=True)
        if use_emo_text:
            if emo_text is None:
                emo_text = text
            emo_dict, content = self._get_qwen_emo().inference(emo_text)
            emo_vector = list(emo_dict.values())

        do_sample = generation_kwargs.pop("do_sample", True)
        top_p = generation_kwargs.pop("top_p", 0.8)

        codes, speech_conditioning_latent = self.gpt.inference_speech(
            text,
            do_sample=True,
            top_p=top_p,
        )
        return codes, speech_conditioning_latent


class QwenEmotion:
    def __init__(self, model_dir):
        self.model_dir = model_dir
"""


def load_module():
    return importlib.import_module("tools.patch_indextts2_plugin")


def create_minimal_plugin(tmp_path):
    plugin_dir = tmp_path / "ComfyUI-Index-TTS"
    utils_path = plugin_dir / "indextts2" / "utils.py"
    infer_path = plugin_dir / "indextts2" / "vendor" / "indextts" / "infer_v2.py"
    utils_path.parent.mkdir(parents=True)
    infer_path.parent.mkdir(parents=True)
    utils_path.write_text(UTILS_SAMPLE, encoding="utf-8")
    infer_path.write_text(INFER_V2_SAMPLE, encoding="utf-8")
    return plugin_dir, utils_path, infer_path


def create_minimal_plugin_with_infer(tmp_path, infer_text):
    plugin_dir, utils_path, infer_path = create_minimal_plugin(tmp_path)
    infer_path.write_text(infer_text, encoding="utf-8")
    return plugin_dir, utils_path, infer_path


def test_patch_plugin_updates_minimal_samples_idempotently(tmp_path):
    patch_module = load_module()
    plugin_dir, utils_path, infer_path = create_minimal_plugin(tmp_path)

    first_result = patch_module.patch_plugin(plugin_dir)
    first_utils = utils_path.read_text(encoding="utf-8")
    first_infer = infer_path.read_text(encoding="utf-8")
    second_result = patch_module.patch_plugin(plugin_dir)

    assert first_result.changed_files == [utils_path, infer_path]
    assert second_result.changed_files == []
    assert utils_path.read_text(encoding="utf-8") == first_utils
    assert infer_path.read_text(encoding="utf-8") == first_infer

    assert '_REF_CACHE_DIR = "indextts2_ref_cache"' in first_utils
    assert "INDEXTTS2_WAV_CACHE_DIR" not in first_utils
    assert "indextts2_wav_cache" not in first_utils
    assert "cache_dir = os.path.join(tempfile.gettempdir(), _REF_CACHE_DIR)" in first_utils
    assert "hashlib.sha256()" in first_utils
    assert "sf.info(path)" in first_utils
    assert "sf.read(path, frames=1, always_2d=False)" in first_utils
    assert "np.asarray(data).size > 0" in first_utils
    assert 'prefix=f".{os.path.basename(path)}.",' in first_utils
    assert 'suffix=".wav",' in first_utils
    assert "dir=cache_dir," in first_utils
    assert "os.replace(tmp_path, path)" in first_utils
    assert "finally:" in first_utils
    assert "if os.path.exists(tmp_path):" in first_utils

    assert "self.qwen_emo_path = os.path.join(self.model_dir, qwen_subdir)" in first_infer
    assert "self.qwen_emo = None" in first_infer
    assert "def _get_qwen_emo(self):" in first_infer
    assert "self._get_qwen_emo().inference(emo_text)" in first_infer
    assert "do_sample=do_sample" in first_infer
    assert "do_sample=True" not in first_infer


def test_patch_plugin_supports_current_upstream_qwen_initialization(tmp_path):
    patch_module = load_module()
    plugin_dir, utils_path, infer_path = create_minimal_plugin_with_infer(
        tmp_path,
        CURRENT_UPSTREAM_INFER_V2_SAMPLE,
    )

    first_result = patch_module.patch_plugin(plugin_dir)
    first_infer = infer_path.read_text(encoding="utf-8")
    second_result = patch_module.patch_plugin(plugin_dir)

    assert first_result.changed_files == [utils_path, infer_path]
    assert second_result.changed_files == []
    assert infer_path.read_text(encoding="utf-8") == first_infer
    assert "qwen_subdir = str(self.cfg.qwen_emo_path).strip()" in first_infer
    assert "self.qwen_emo_path = os.path.join(self.model_dir, qwen_subdir)" in first_infer
    assert "self.qwen_emo = None" in first_infer
    assert "self._get_qwen_emo().inference(emo_text)" in first_infer


def test_patch_do_sample_only_updates_inference_speech_argument():
    patch_module = load_module()

    patched = patch_module._patch_infer_v2(INFER_V2_SAMPLE_WITH_UNRELATED_DO_SAMPLE)

    assert "fallback_result = self.audit_generation_defaults(do_sample=True)" in patched
    assert "do_sample=do_sample" in patched
    assert "do_sample=True" not in patched.split("self.gpt.inference_speech(", maxsplit=1)[1]


def test_resolve_target_path_uses_indextts_env(monkeypatch, tmp_path):
    patch_module = load_module()
    plugin_dir = tmp_path / "ComfyUI-Index-TTS"
    monkeypatch.setenv("INDEXTTS2_PLUGIN_DIR", str(plugin_dir))

    assert patch_module.resolve_target_path(None) == plugin_dir


def test_resolve_target_path_requires_target_or_env(monkeypatch):
    patch_module = load_module()
    monkeypatch.delenv("INDEXTTS2_PLUGIN_DIR", raising=False)

    with pytest.raises(ValueError, match="Pass --target or set INDEXTTS2_PLUGIN_DIR"):
        patch_module.resolve_target_path(None)


def test_main_reports_clear_error_without_target(monkeypatch, capsys):
    patch_module = load_module()
    monkeypatch.delenv("INDEXTTS2_PLUGIN_DIR", raising=False)

    exit_code = patch_module.main([])

    assert exit_code == 2
    assert "Pass --target or set INDEXTTS2_PLUGIN_DIR" in capsys.readouterr().err


def test_patch_plugin_rejects_missing_target(tmp_path):
    patch_module = load_module()

    with pytest.raises(FileNotFoundError, match="target plugin directory does not exist"):
        patch_module.patch_plugin(tmp_path / "missing")


def test_patch_plugin_rejects_missing_required_file(tmp_path):
    patch_module = load_module()
    plugin_dir = tmp_path / "ComfyUI-Index-TTS"
    (plugin_dir / "indextts2").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="indextts2/utils.py"):
        patch_module.patch_plugin(plugin_dir)
