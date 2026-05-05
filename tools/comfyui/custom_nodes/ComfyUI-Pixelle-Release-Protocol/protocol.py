"""Pixelle Release Protocol - 统一的内存释放逻辑。

这个模块不依赖任何第三方插件，直接在 Pixelle 插件内实现对所有支持的
TTS 和图像插件的内存检测与释放。

支持的插件：
- OmniVoice TTS
- GGUF 图像模型
- IndexTTS2
"""

import gc
import sys

import torch

try:
    from typing import Any, List, Tuple, Type, Dict
except ImportError:
    from typing import Any, List
    Tuple = tuple
    Type = type
    Dict = dict

PIXELLE_RELEASE_PROTOCOL_VERSION = 2

_OMNIVOICE_NODE_CLASSES = (
    "OmniVoiceLongformTTS",
    "OmniVoiceVoiceCloneTTS",
)

_MIN_CUDA_ALLOCATED_RELEASE_BYTES = 64 * 1024 * 1024
_MIN_CUDA_ALLOCATED_RELEASE_RATIO = 0.05


def _cuda_snapshot() -> dict:
    """获取当前 CUDA 内存使用情况。"""
    if not torch.cuda.is_available():
        return {}
    device = torch.cuda.current_device()
    return {
        "cuda_allocated": torch.cuda.memory_allocated(device),
        "cuda_reserved": torch.cuda.memory_reserved(device),
    }


def _cuda_allocated_release_is_material(before_bytes: int, after_bytes: int) -> bool:
    """判断内存释放是否有效。"""
    if before_bytes <= 0 or after_bytes >= before_bytes:
        return False
    release_bytes = before_bytes - after_bytes
    relative_threshold = max(1, int(before_bytes * _MIN_CUDA_ALLOCATED_RELEASE_RATIO))
    threshold = min(_MIN_CUDA_ALLOCATED_RELEASE_BYTES, relative_threshold)
    return release_bytes >= threshold


def _find_module_by_keyword(keywords: List[str]) -> dict:
    """根据关键词查找相关模块。"""
    modules = {}
    for module_name, module in sys.modules.items():
        if module is None:
            continue
        keyword_found = any(kw.lower() in module_name.lower() for kw in keywords)
        if keyword_found:
            modules[module_name] = module
    return modules


def _find_node_classes(node_class_names: Tuple[str, ...]) -> Dict[str, Type]:
    """查找节点类。"""
    classes = {}
    for module_name, module in list(sys.modules.items()):
        if module is None:
            continue
        for class_name in node_class_names:
            if hasattr(module, class_name):
                cls = getattr(module, class_name)
                if isinstance(cls, type):
                    classes[f"{module_name}.{class_name}"] = cls
    return classes


def _find_model_objects(
    module_keywords: List[str],
    model_attrs: List[str] = None,
    cache_attrs: List[str] = None,
) -> List[str]:
    """查找模型对象。"""
    if model_attrs is None:
        model_attrs = ["_model", "model", "tts_model", "pipe"]
    if cache_attrs is None:
        cache_attrs = ["_cache", "_models", "_model_cache", "MODEL_CACHE"]

    labels = []
    modules = _find_module_by_keyword(module_keywords)

    for mod_name, module in modules.items():
        for attr_name in model_attrs:
            if hasattr(module, attr_name):
                obj = getattr(module, attr_name, None)
                if obj is not None:
                    labels.append(f"{mod_name}.{attr_name}")

        for cache_name in cache_attrs:
            cache = getattr(module, cache_name, None)
            if isinstance(cache, dict) and cache:
                for key in cache.keys():
                    labels.append(f"{mod_name}.{cache_name}[{key}]")

    return sorted(set(labels))


def _clear_module_attrs(
    module_keywords: List[str],
    model_attrs: List[str] = None,
    cache_attrs: List[str] = None,
) -> List[str]:
    """清除模块属性。"""
    if model_attrs is None:
        model_attrs = ["_model", "model", "tts_model", "pipe", "_omnivoice"]
    if cache_attrs is None:
        cache_attrs = ["_cache", "_models", "_model_cache", "MODEL_CACHE", "_instances"]

    errors = []
    modules = _find_module_by_keyword(module_keywords)

    for mod_name, module in modules.items():
        for attr_name in model_attrs:
            if hasattr(module, attr_name):
                try:
                    setattr(module, attr_name, None)
                except Exception as exc:
                    errors.append(f"{mod_name}.{attr_name}: {exc}")

        for cache_name in cache_attrs:
            cache = getattr(module, cache_name, None)
            if isinstance(cache, dict):
                try:
                    cache.clear()
                except Exception as exc:
                    errors.append(f"{mod_name}.{cache_name}: {exc}")

    return errors


def _standard_cleanup() -> List[str]:
    """标准 ComfyUI 清理。"""
    errors = []
    try:
        import comfy.model_management
        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache()
    except Exception as exc:
        errors.append(str(exc))
    return errors


def _torch_cleanup() -> List[str]:
    """PyTorch 清理。"""
    errors = []
    try:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception as exc:
        errors.append(str(exc))
    return errors


def omnivoice_health() -> dict:
    """OmniVoice 健康检查。"""
    objects_seen = _find_model_objects(["omnivoice", "omni_voice"])
    snapshot = _cuda_snapshot()
    return {
        "ok": True,
        "extension": "omnivoice",
        "release_endpoint": "/pixelle/omnivoice/free",
        "objects_seen": objects_seen,
        "cuda_allocated": snapshot.get("cuda_allocated", 0),
        "cuda_reserved": snapshot.get("cuda_reserved", 0),
    }


def omnivoice_release() -> dict:
    """释放 OmniVoice 内存。"""
    errors = []
    before = _cuda_snapshot()
    objects_seen = _find_model_objects(["omnivoice", "omni_voice"])

    errors.extend(_clear_module_attrs(["omnivoice", "omni_voice"]))
    errors.extend(_standard_cleanup())
    errors.extend(_torch_cleanup())

    after = _cuda_snapshot()
    cuda_decreased = _cuda_allocated_release_is_material(
        before.get("cuda_allocated", 0),
        after.get("cuda_allocated", 0),
    )

    return {
        "ok": True,
        "extension": "omnivoice",
        "released": len(objects_seen) > 0 or cuda_decreased,
        "cuda_before": before.get("cuda_allocated", 0),
        "cuda_after": after.get("cuda_allocated", 0),
        "errors": errors,
    }


def gguf_health() -> dict:
    """GGUF 健康检查。"""
    objects_seen = _find_model_objects(
        ["gguf"],
        model_attrs=["_model", "model", "unet", "clip", "vae"],
        cache_attrs=["_cache", "model_cache", "lora_cache"],
    )
    snapshot = _cuda_snapshot()
    return {
        "ok": True,
        "extension": "gguf",
        "release_endpoint": "/pixelle/gguf/free",
        "objects_seen": objects_seen,
        "cuda_allocated": snapshot.get("cuda_allocated", 0),
        "cuda_reserved": snapshot.get("cuda_reserved", 0),
    }


def gguf_release() -> dict:
    """释放 GGUF 内存。"""
    errors = []
    before = _cuda_snapshot()
    objects_seen = _find_model_objects(
        ["gguf"],
        model_attrs=["_model", "model", "unet", "clip", "vae"],
        cache_attrs=["_cache", "model_cache", "lora_cache"],
    )

    errors.extend(_clear_module_attrs(
        ["gguf"],
        model_attrs=["_model", "model", "unet", "clip", "vae", "pipe"],
        cache_attrs=["_cache", "model_cache", "lora_cache"],
    ))
    errors.extend(_standard_cleanup())
    errors.extend(_torch_cleanup())

    after = _cuda_snapshot()
    cuda_decreased = _cuda_allocated_release_is_material(
        before.get("cuda_allocated", 0),
        after.get("cuda_allocated", 0),
    )

    return {
        "ok": True,
        "extension": "gguf",
        "released": len(objects_seen) > 0 or cuda_decreased,
        "cuda_before": before.get("cuda_allocated", 0),
        "cuda_after": after.get("cuda_allocated", 0),
        "errors": errors,
    }


def indextts2_health() -> dict:
    """IndexTTS2 健康检查。"""
    objects_seen = _find_model_objects(
        ["indextts", "index_tts"],
        model_attrs=["_model", "model", "tts_model", "vocoder"],
        cache_attrs=["_cache", "model_cache"],
    )
    snapshot = _cuda_snapshot()
    return {
        "ok": True,
        "extension": "indextts2",
        "release_endpoint": "/pixelle/indextts2/free",
        "objects_seen": objects_seen,
        "cuda_allocated": snapshot.get("cuda_allocated", 0),
        "cuda_reserved": snapshot.get("cuda_reserved", 0),
    }


def indextts2_release() -> dict:
    """释放 IndexTTS2 内存。"""
    errors = []
    before = _cuda_snapshot()
    objects_seen = _find_model_objects(
        ["indextts", "index_tts"],
        model_attrs=["_model", "model", "tts_model", "vocoder"],
        cache_attrs=["_cache", "model_cache"],
    )

    errors.extend(_clear_module_attrs(
        ["indextts", "index_tts"],
        model_attrs=["_model", "model", "tts_model", "vocoder", "pipe"],
        cache_attrs=["_cache", "model_cache"],
    ))
    errors.extend(_standard_cleanup())
    errors.extend(_torch_cleanup())

    after = _cuda_snapshot()
    cuda_decreased = _cuda_allocated_release_is_material(
        before.get("cuda_allocated", 0),
        after.get("cuda_allocated", 0),
    )

    return {
        "ok": True,
        "extension": "indextts2",
        "released": len(objects_seen) > 0 or cuda_decreased,
        "cuda_before": before.get("cuda_allocated", 0),
        "cuda_after": after.get("cuda_allocated", 0),
        "errors": errors,
    }


def unified_health() -> dict:
    """统一健康检查。"""
    extensions = {}

    try:
        extensions["omnivoice"] = {"ok": True, "endpoint": "/pixelle/omnivoice/free"}
    except Exception:
        extensions["omnivoice"] = {"ok": False, "endpoint": "/pixelle/omnivoice/free"}

    try:
        extensions["gguf"] = {"ok": True, "endpoint": "/pixelle/gguf/free"}
    except Exception:
        extensions["gguf"] = {"ok": False, "endpoint": "/pixelle/gguf/free"}

    try:
        extensions["indextts2"] = {"ok": True, "endpoint": "/pixelle/indextts2/free"}
    except Exception:
        extensions["indextts2"] = {"ok": False, "endpoint": "/pixelle/indextts2/free"}

    snapshot = _cuda_snapshot()
    return {
        "ok": True,
        "protocol_version": PIXELLE_RELEASE_PROTOCOL_VERSION,
        "extensions": extensions,
        "cuda_allocated": snapshot.get("cuda_allocated", 0),
        "cuda_reserved": snapshot.get("cuda_reserved", 0),
    }


def unified_release() -> dict:
    """统一释放内存。"""
    released = {}

    try:
        result = omnivoice_release()
        released["omnivoice"] = result.get("released", False)
    except Exception:
        released["omnivoice"] = False

    try:
        result = gguf_release()
        released["gguf"] = result.get("released", False)
    except Exception:
        released["gguf"] = False

    try:
        result = indextts2_release()
        released["indextts2"] = result.get("released", False)
    except Exception:
        released["indextts2"] = False

    return {
        "ok": True,
        "released": released,
    }
