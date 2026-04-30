import importlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

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


ENGINE_SAMPLE = """class IndexTTS2Engine:
    def generate(self, tts, text, max_tokens_per_sentence=120, **gen_kwargs):
        result = tts.infer(
            text=text,
            output_path=None,
            max_text_tokens_per_segment=int(max_tokens_per_sentence) if max_tokens_per_sentence else 120,
            **gen_kwargs,
        )
        return result
"""


MODEL_LOADER_SAMPLE = """import os
import sys
import gc
import torch
from typing import Optional, Dict, Any


class IndexTTS2Loader:
    DEFAULT_DIRNAME = "IndexTTS-2"

    def __init__(self, models_root: Optional[str] = None, device: Optional[str] = None, dtype: Optional[str] = None):
        self._models_root = models_root or "models"
        self._model_dir = os.path.join(self._models_root, self.DEFAULT_DIRNAME)
        self._device = torch.device(device) if device else torch.device("cuda")
        self._dtype = torch.float16
        self._cache: Dict[str, Any] = {}

    def get_tts(self):
        if "tts" in self._cache:
            return self._cache["tts"]
        self._cache["tts"] = object()
        return self._cache["tts"]

    def unload_tts(self) -> None:
        try:
            tts = self._cache.pop("tts", None)
            del tts
        except Exception:
            pass
        try:
            gc.collect()
        except Exception:
            pass
        try:
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
        except Exception:
            pass
"""


PLUGIN_INIT_SAMPLE = '''"""IndexTTS custom node."""

import os
import sys

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
'''


def load_module():
    module_name = "tools.patch_indextts2_plugin"
    module_path = Path(__file__).resolve().parents[1] / "tools" / "patch_indextts2_plugin.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def create_minimal_plugin(tmp_path):
    plugin_dir = tmp_path / "ComfyUI-Index-TTS"
    utils_path = plugin_dir / "indextts2" / "utils.py"
    infer_path = plugin_dir / "indextts2" / "vendor" / "indextts" / "infer_v2.py"
    loader_path = plugin_dir / "indextts2" / "model_loader.py"
    init_path = plugin_dir / "__init__.py"
    utils_path.parent.mkdir(parents=True)
    infer_path.parent.mkdir(parents=True)
    utils_path.write_text(UTILS_SAMPLE, encoding="utf-8")
    infer_path.write_text(INFER_V2_SAMPLE, encoding="utf-8")
    loader_path.write_text(MODEL_LOADER_SAMPLE, encoding="utf-8")
    init_path.write_text(PLUGIN_INIT_SAMPLE, encoding="utf-8")
    return plugin_dir, utils_path, infer_path


def create_minimal_plugin_with_infer(tmp_path, infer_text):
    plugin_dir, utils_path, infer_path = create_minimal_plugin(tmp_path)
    infer_path.write_text(infer_text, encoding="utf-8")
    return plugin_dir, utils_path, infer_path


def create_minimal_plugin_with_engine(tmp_path, engine_text=ENGINE_SAMPLE):
    plugin_dir, utils_path, infer_path = create_minimal_plugin(tmp_path)
    engine_path = plugin_dir / "indextts2" / "infer.py"
    engine_path.write_text(engine_text, encoding="utf-8")
    return plugin_dir, utils_path, infer_path, engine_path


def create_minimal_plugin_with_loader_and_init(tmp_path):
    plugin_dir, utils_path, infer_path = create_minimal_plugin(tmp_path)
    loader_path = plugin_dir / "indextts2" / "model_loader.py"
    init_path = plugin_dir / "__init__.py"
    loader_path.write_text(MODEL_LOADER_SAMPLE, encoding="utf-8")
    init_path.write_text(PLUGIN_INIT_SAMPLE, encoding="utf-8")
    return plugin_dir, utils_path, infer_path, loader_path, init_path


def load_utils_module(utils_path):
    module_name = f"patched_indextts2_utils_{utils_path.parent.parent.name}"
    spec = importlib.util.spec_from_file_location(module_name, utils_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_patch_plugin_updates_minimal_samples_idempotently(tmp_path):
    patch_module = load_module()
    plugin_dir, utils_path, infer_path = create_minimal_plugin(tmp_path)
    loader_path = plugin_dir / "indextts2" / "model_loader.py"
    init_path = plugin_dir / "__init__.py"
    routes_path = plugin_dir / "pixelle_routes.py"

    first_result = patch_module.patch_plugin(plugin_dir)
    first_utils = utils_path.read_text(encoding="utf-8")
    first_infer = infer_path.read_text(encoding="utf-8")
    second_result = patch_module.patch_plugin(plugin_dir)

    assert first_result.changed_files == [
        utils_path,
        infer_path,
        loader_path,
        init_path,
        routes_path,
    ]
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
    loader_path = plugin_dir / "indextts2" / "model_loader.py"
    init_path = plugin_dir / "__init__.py"
    routes_path = plugin_dir / "pixelle_routes.py"

    first_result = patch_module.patch_plugin(plugin_dir)
    first_infer = infer_path.read_text(encoding="utf-8")
    second_result = patch_module.patch_plugin(plugin_dir)

    assert first_result.changed_files == [
        utils_path,
        infer_path,
        loader_path,
        init_path,
        routes_path,
    ]
    assert second_result.changed_files == []
    assert infer_path.read_text(encoding="utf-8") == first_infer
    assert "qwen_subdir = str(self.cfg.qwen_emo_path).strip()" in first_infer
    assert "self.qwen_emo_path = os.path.join(self.model_dir, qwen_subdir)" in first_infer
    assert "self.qwen_emo = None" in first_infer
    assert "self._get_qwen_emo().inference(emo_text)" in first_infer


def test_patch_utils_preserves_top_level_content_after_save_temp_wav(tmp_path):
    patch_module = load_module()
    plugin_dir, utils_path, infer_path = create_minimal_plugin(tmp_path)
    utils_path.write_text(
        UTILS_SAMPLE
        + """
SENTINEL_AFTER_SAVE_TEMP_WAV = "keep"


class HelperAfterSaveTempWav:
    value = SENTINEL_AFTER_SAVE_TEMP_WAV
""",
        encoding="utf-8",
    )

    patch_module.patch_plugin(plugin_dir)
    patched_utils = utils_path.read_text(encoding="utf-8")

    assert 'SENTINEL_AFTER_SAVE_TEMP_WAV = "keep"' in patched_utils
    assert "class HelperAfterSaveTempWav:" in patched_utils
    assert "value = SENTINEL_AFTER_SAVE_TEMP_WAV" in patched_utils


def test_patched_save_temp_wav_reuses_and_repairs_cached_wav(monkeypatch, tmp_path):
    patch_module = load_module()
    plugin_dir, utils_path, infer_path = create_minimal_plugin(tmp_path)
    patch_module.patch_plugin(plugin_dir)
    patched_utils = load_utils_module(utils_path)
    monkeypatch.setattr(patched_utils.tempfile, "gettempdir", lambda: str(tmp_path))

    wave = np.asarray([0.0, 0.25, -0.25, 0.5], dtype=np.float32)
    sr = 24000
    first_path = patched_utils.save_temp_wav((wave, sr))
    second_path = patched_utils.save_temp_wav((wave.copy(), sr))

    assert second_path == first_path
    with open(first_path, "wb") as handle:
        handle.write(b"not a valid wav")

    repaired_path = patched_utils.save_temp_wav((wave.copy(), sr))
    info = sf.info(repaired_path)

    assert repaired_path == first_path
    assert int(info.samplerate) == sr
    assert int(info.frames) > 0


def test_patch_do_sample_only_updates_inference_speech_argument():
    patch_module = load_module()

    patched = patch_module._patch_infer_v2(INFER_V2_SAMPLE_WITH_UNRELATED_DO_SAMPLE)

    assert "fallback_result = self.audit_generation_defaults(do_sample=True)" in patched
    assert "do_sample=do_sample" in patched
    assert "do_sample=True" not in patched.split("self.gpt.inference_speech(", maxsplit=1)[1]


def test_patch_plugin_forwards_sentence_token_cap_to_infer_v2(tmp_path):
    patch_module = load_module()
    plugin_dir, utils_path, infer_path, engine_path = create_minimal_plugin_with_engine(tmp_path)

    first_result = patch_module.patch_plugin(plugin_dir)
    first_engine = engine_path.read_text(encoding="utf-8")
    second_result = patch_module.patch_plugin(plugin_dir)

    assert engine_path in first_result.changed_files
    assert second_result.changed_files == []
    assert engine_path.read_text(encoding="utf-8") == first_engine
    assert "max_text_tokens_per_sentence=int(max_tokens_per_sentence)" in first_engine
    assert "max_text_tokens_per_segment" not in first_engine


def test_patch_plugin_adds_indextts2_release_contract_idempotently(tmp_path):
    patch_module = load_module()
    plugin_dir, utils_path, infer_path, loader_path, init_path = create_minimal_plugin_with_loader_and_init(tmp_path)
    routes_path = plugin_dir / "pixelle_routes.py"

    first_result = patch_module.patch_plugin(plugin_dir)
    first_loader = loader_path.read_text(encoding="utf-8")
    first_init = init_path.read_text(encoding="utf-8")
    first_routes = routes_path.read_text(encoding="utf-8")
    second_result = patch_module.patch_plugin(plugin_dir)

    assert loader_path in first_result.changed_files
    assert init_path in first_result.changed_files
    assert routes_path in first_result.changed_files
    assert second_result.changed_files == []

    assert loader_path.read_text(encoding="utf-8") == first_loader
    assert init_path.read_text(encoding="utf-8") == first_init
    assert routes_path.read_text(encoding="utf-8") == first_routes

    assert "weakref.WeakSet()" in first_loader
    assert "_INDEXTTS2_LOADER_REGISTRY.add(self)" in first_loader
    assert "def unload_all_indextts2" in first_loader
    assert "cuda_allocated_before" in first_loader
    assert "torch.cuda.ipc_collect()" in first_loader
    assert "semantic_model" in first_loader
    assert "bigvgan" in first_loader

    assert "from . import pixelle_routes as _pixelle_routes" in first_init
    assert '@PromptServer.instance.routes.get("/pixelle/indextts2/health")' in first_routes
    assert '@PromptServer.instance.routes.post("/pixelle/indextts2/free")' in first_routes
    assert "indextts2_release_health()" in first_routes
    assert "unload_all_indextts2()" in first_routes
    assert '"release_endpoint": "/pixelle/indextts2/free"' in first_loader


def test_patch_plugin_requires_model_loader_for_release_contract(tmp_path):
    patch_module = load_module()
    plugin_dir, utils_path, infer_path = create_minimal_plugin(tmp_path)
    (plugin_dir / "indextts2" / "model_loader.py").unlink()

    with pytest.raises(FileNotFoundError, match="indextts2/model_loader.py"):
        patch_module.patch_plugin(plugin_dir)


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
