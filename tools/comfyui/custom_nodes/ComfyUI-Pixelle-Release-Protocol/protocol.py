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
from typing import List

import torch

PIXELLE_RELEASE_PROTOCOL_VERSION = 2
PIXELLE_RELEASE_CONTRACT_REVISION = 1

_EXTENSION_RELEASE_CONTRACT_REVISIONS = {
    "omnivoice": 1,
    "gguf": 2,
    "indextts2": 1,
}
_EXTENSION_RELEASE_ENDPOINTS = {
    "omnivoice": "/pixelle/free",
    "gguf": "/pixelle/free",
    "indextts2": "/pixelle/free",
}
_EXTENSION_HEALTH_ENDPOINTS = {
    "omnivoice": "/pixelle/health",
    "gguf": "/pixelle/health",
    "indextts2": "/pixelle/health",
}
_EXTENSION_LEGACY_RELEASE_ENDPOINTS = {
    "omnivoice": "/pixelle/omnivoice/free",
    "gguf": "/pixelle/gguf/free",
    "indextts2": "/pixelle/indextts2/free",
}
_EXTENSION_LEGACY_HEALTH_ENDPOINTS = {
    "omnivoice": "/pixelle/omnivoice/health",
    "gguf": "/pixelle/gguf/health",
    "indextts2": "/pixelle/indextts2/health",
}

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


def _find_instance_states_by_keyword(keywords: List[str]) -> list[tuple[str, dict]]:
    """查找扩展实例的属性字典；仅在显式释放阶段执行。"""
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    matches = []
    for instance in gc.get_objects():
        instance_type = type(instance)
        type_name = f"{instance_type.__module__}.{instance_type.__name__}"
        if not any(keyword in type_name.lower() for keyword in lowered_keywords):
            continue
        try:
            state = vars(instance)
        except (TypeError, ValueError):
            continue
        if isinstance(state, dict):
            matches.append((type_name, state))
    return matches


def _find_model_objects(
    module_keywords: List[str],
    model_attrs: List[str] = None,
    cache_attrs: List[str] = None,
    instance_states: list[tuple[str, dict]] = None,
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
                labels.append(f"{mod_name}.{cache_name}[entries={len(cache)}]")

    if instance_states is None:
        instance_states = _find_instance_states_by_keyword(module_keywords)
    for type_name, state in instance_states:
        for attr_name in model_attrs:
            if state.get(attr_name) is not None:
                labels.append(f"{type_name}.{attr_name}")
        for cache_name in cache_attrs:
            cache = state.get(cache_name)
            if isinstance(cache, dict) and cache:
                labels.append(f"{type_name}.{cache_name}[entries={len(cache)}]")

    return sorted(set(labels))


def _clear_module_attrs(
    module_keywords: List[str],
    model_attrs: List[str] = None,
    cache_attrs: List[str] = None,
    instance_states: list[tuple[str, dict]] = None,
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
                    errors.append(f"{mod_name}.{attr_name}: {type(exc).__name__}")

        for cache_name in cache_attrs:
            cache = getattr(module, cache_name, None)
            if isinstance(cache, dict):
                try:
                    cache.clear()
                except Exception as exc:
                    errors.append(f"{mod_name}.{cache_name}: {type(exc).__name__}")

    if instance_states is None:
        instance_states = _find_instance_states_by_keyword(module_keywords)
    for type_name, state in instance_states:
        for attr_name in model_attrs:
            if state.get(attr_name) is not None:
                state[attr_name] = None
        for cache_name in cache_attrs:
            cache = state.get(cache_name)
            if isinstance(cache, dict):
                try:
                    cache.clear()
                except Exception as exc:
                    errors.append(f"{type_name}.{cache_name}: {type(exc).__name__}")

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
        errors.append(type(exc).__name__)
    return errors


def _extension_health(extension: str) -> dict:
    """常量时间返回协议能力，不扫描模型对象，也不访问显卡状态。"""
    return {
        "protocol_version": PIXELLE_RELEASE_PROTOCOL_VERSION,
        "contract_revision": _EXTENSION_RELEASE_CONTRACT_REVISIONS[extension],
        "ok": True,
        "extension": extension,
        "health_endpoint": _EXTENSION_HEALTH_ENDPOINTS[extension],
        "release_endpoint": _EXTENSION_RELEASE_ENDPOINTS[extension],
        "legacy_health_endpoint": _EXTENSION_LEGACY_HEALTH_ENDPOINTS[extension],
        "legacy_release_endpoint": _EXTENSION_LEGACY_RELEASE_ENDPOINTS[extension],
        "safe_to_continue": True,
    }


def _release_extension_models(
    extension: str,
    module_keywords: List[str],
    *,
    model_attrs: List[str] = None,
    cache_attrs: List[str] = None,
) -> dict:
    """显式释放单个扩展的私有模型引用，不卸载其他客户端的模型。"""
    before = _cuda_snapshot()
    instance_states = _find_instance_states_by_keyword(module_keywords)
    objects_seen = _find_model_objects(
        module_keywords,
        model_attrs=model_attrs,
        cache_attrs=cache_attrs,
        instance_states=instance_states,
    )
    errors = _clear_module_attrs(
        module_keywords,
        model_attrs=model_attrs,
        cache_attrs=cache_attrs,
        instance_states=instance_states,
    )
    errors.extend(_torch_cleanup())
    diagnostic_objects = _find_model_objects(
        module_keywords,
        model_attrs=model_attrs,
        cache_attrs=cache_attrs,
    )
    after = _cuda_snapshot()
    cuda_allocated_before = before.get("cuda_allocated", 0)
    cuda_allocated_after = after.get("cuda_allocated", 0)
    cuda_allocated_decreased = _cuda_allocated_release_is_material(
        cuda_allocated_before,
        cuda_allocated_after,
    )

    residual_objects = diagnostic_objects
    if errors:
        release_confirmation_reason = f"{extension}_release_errors"
    elif residual_objects:
        release_confirmation_reason = f"{extension}_objects_residual"
    elif cuda_allocated_decreased:
        release_confirmation_reason = f"{extension}_cuda_allocated_decreased"
    elif not objects_seen:
        release_confirmation_reason = f"{extension}_no_private_objects"
    else:
        release_confirmation_reason = f"{extension}_objects_released"
    safe_to_continue = not errors and not residual_objects

    return {
        "protocol_version": PIXELLE_RELEASE_PROTOCOL_VERSION,
        "contract_revision": _EXTENSION_RELEASE_CONTRACT_REVISIONS[extension],
        "extension": extension,
        "released": bool(objects_seen) or cuda_allocated_decreased,
        "safe_to_continue": safe_to_continue,
        "release_confirmation_reason": release_confirmation_reason,
        "objects_seen": objects_seen,
        "objects_released": [
            item for item in objects_seen if item not in diagnostic_objects
        ],
        "diagnostic_objects": diagnostic_objects,
        "residual_objects": residual_objects,
        "errors": errors,
        "cuda_allocated_before": cuda_allocated_before,
        "cuda_allocated_after": cuda_allocated_after,
        "cuda_reserved_before": before.get("cuda_reserved", 0),
        "cuda_reserved_after": after.get("cuda_reserved", 0),
    }


def omnivoice_health() -> dict:
    return _extension_health("omnivoice")


def omnivoice_release() -> dict:
    return _release_extension_models(
        "omnivoice",
        ["omnivoice", "omni_voice"],
        model_attrs=[
            "_model",
            "model",
            "tts_model",
            "omnivoice",
            "pipe",
            "_omnivoice",
        ],
        cache_attrs=[
            "_cache",
            "_models",
            "_model_cache",
            "MODEL_CACHE",
            "_instances",
        ],
    )


def gguf_health() -> dict:
    return _extension_health("gguf")


def gguf_release() -> dict:
    return _release_extension_models(
        "gguf",
        ["gguf"],
        model_attrs=["_model", "model", "unet", "clip", "vae", "pipe"],
        cache_attrs=["_cache", "model_cache", "lora_cache"],
    )


def indextts2_health() -> dict:
    return _extension_health("indextts2")


def indextts2_release() -> dict:
    return _release_extension_models(
        "indextts2",
        ["indextts", "index_tts"],
        model_attrs=["_model", "model", "tts_model", "vocoder", "pipe"],
        cache_attrs=["_cache", "model_cache"],
    )


def unified_health() -> dict:
    """统一声明释放能力；此路径必须保持无副作用和常量时间。"""
    return {
        "ok": True,
        "protocol_version": PIXELLE_RELEASE_PROTOCOL_VERSION,
        "contract_revision": PIXELLE_RELEASE_CONTRACT_REVISION,
        "extensions": {
            extension: _extension_health(extension)
            for extension in _EXTENSION_RELEASE_ENDPOINTS
        },
    }


def unified_release(extensions: List[str] = None) -> dict:
    """只释放调用方明确指定的扩展；省略参数时兼容旧调用并释放全部。"""
    release_handlers = {
        "omnivoice": omnivoice_release,
        "gguf": gguf_release,
        "indextts2": indextts2_release,
    }
    requested_extensions = list(release_handlers) if extensions is None else extensions
    if (
        not isinstance(requested_extensions, list)
        or not requested_extensions
        or any(not isinstance(extension, str) for extension in requested_extensions)
    ):
        raise ValueError("extensions must be a non-empty list of strings")
    unknown_extensions = [
        extension
        for extension in requested_extensions
        if extension not in release_handlers
    ]
    if unknown_extensions:
        raise ValueError(f"unsupported extensions: {sorted(set(unknown_extensions))}")

    results = {}
    for extension in dict.fromkeys(requested_extensions):
        try:
            results[extension] = release_handlers[extension]()
        except Exception as exc:
            results[extension] = {
                "protocol_version": PIXELLE_RELEASE_PROTOCOL_VERSION,
                "contract_revision": _EXTENSION_RELEASE_CONTRACT_REVISIONS[extension],
                "extension": extension,
                "released": False,
                "safe_to_continue": False,
                "release_confirmation_reason": f"{extension}_release_exception",
                "objects_seen": [],
                "objects_released": [],
                "diagnostic_objects": [],
                "residual_objects": [],
                "errors": [type(exc).__name__],
                "cuda_allocated_before": 0,
                "cuda_allocated_after": 0,
                "cuda_reserved_before": 0,
                "cuda_reserved_after": 0,
            }
    safe_to_continue = all(
        bool(result.get("safe_to_continue")) for result in results.values()
    )

    return {
        "ok": safe_to_continue,
        "protocol_version": PIXELLE_RELEASE_PROTOCOL_VERSION,
        "contract_revision": PIXELLE_RELEASE_CONTRACT_REVISION,
        "released": {
            extension: bool(result.get("released"))
            for extension, result in results.items()
        },
        "safe_to_continue": safe_to_continue,
        "results": results,
    }
