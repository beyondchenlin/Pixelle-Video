import argparse
import ast
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

INDEXTTS2_PLUGIN_ENV = "INDEXTTS2_PLUGIN_DIR"
UTILS_RELATIVE_PATH = Path("indextts2") / "utils.py"
INFER_V2_RELATIVE_PATH = Path("indextts2") / "vendor" / "indextts" / "infer_v2.py"
ENGINE_RELATIVE_PATH = Path("indextts2") / "infer.py"
MODEL_LOADER_RELATIVE_PATH = Path("indextts2") / "model_loader.py"
PLUGIN_INIT_RELATIVE_PATH = Path("__init__.py")
PIXELLE_ROUTES_RELATIVE_PATH = Path("pixelle_routes.py")


@dataclass(frozen=True)
class PatchResult:
    changed_files: list[Path]


def resolve_target_path(target_arg: str | os.PathLike[str] | None) -> Path:
    if target_arg:
        return Path(target_arg)

    target_env = os.environ.get(INDEXTTS2_PLUGIN_ENV)
    if target_env:
        return Path(target_env)

    raise ValueError(f"Pass --target or set {INDEXTTS2_PLUGIN_ENV} to the ComfyUI-Index-TTS directory")


def patch_plugin(target: str | os.PathLike[str]) -> PatchResult:
    plugin_dir = Path(target)
    if not plugin_dir.exists():
        raise FileNotFoundError(f"target plugin directory does not exist: {plugin_dir}")
    if not plugin_dir.is_dir():
        raise NotADirectoryError(f"target plugin path is not a directory: {plugin_dir}")

    utils_path = plugin_dir / UTILS_RELATIVE_PATH
    infer_path = plugin_dir / INFER_V2_RELATIVE_PATH
    engine_path = plugin_dir / ENGINE_RELATIVE_PATH
    model_loader_path = plugin_dir / MODEL_LOADER_RELATIVE_PATH
    plugin_init_path = plugin_dir / PLUGIN_INIT_RELATIVE_PATH
    routes_path = plugin_dir / PIXELLE_ROUTES_RELATIVE_PATH
    _require_file(utils_path, UTILS_RELATIVE_PATH)
    _require_file(infer_path, INFER_V2_RELATIVE_PATH)
    _require_file(model_loader_path, MODEL_LOADER_RELATIVE_PATH)
    _require_file(plugin_init_path, PLUGIN_INIT_RELATIVE_PATH)

    changed_files: list[Path] = []
    if _patch_file(utils_path, _patch_utils):
        changed_files.append(utils_path)
    if _patch_file(infer_path, _patch_infer_v2):
        changed_files.append(infer_path)
    if engine_path.exists() and _patch_file(engine_path, _patch_engine):
        changed_files.append(engine_path)
    if _patch_file(model_loader_path, _patch_model_loader):
        changed_files.append(model_loader_path)
    if _patch_file(plugin_init_path, _patch_plugin_init):
        changed_files.append(plugin_init_path)
    if _write_stable_file(routes_path, STABLE_PIXELLE_ROUTES):
        changed_files.append(routes_path)
    return PatchResult(changed_files=changed_files)


def _require_file(path: Path, relative_path: Path) -> None:
    display_path = relative_path.as_posix()
    if not path.exists():
        raise FileNotFoundError(f"required plugin file is missing: {display_path}")
    if not path.is_file():
        raise FileNotFoundError(f"required plugin path is not a file: {display_path}")


def _patch_file(path: Path, patcher) -> bool:
    original = path.read_text(encoding="utf-8")
    patched = patcher(original)
    if patched == original:
        return False
    path.write_text(patched, encoding="utf-8")
    return True


def _write_stable_file(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8") if path.exists() else None
    if original == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def _ensure_import(text: str, import_line: str) -> str:
    if re.search(rf"^{re.escape(import_line)}$", text, flags=re.MULTILINE):
        return text

    lines = text.splitlines()
    insert_at = 0
    while insert_at < len(lines):
        line = lines[insert_at]
        if line.startswith("import ") or line.startswith("from "):
            insert_at += 1
            continue
        if not line.strip():
            insert_at += 1
            continue
        break
    lines.insert(insert_at, import_line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _ensure_from_import_names(text: str, module_name: str, names: tuple[str, ...]) -> str:
    lines = text.splitlines()
    import_pattern = re.compile(rf"^from\s+{re.escape(module_name)}\s+import\s+(?P<names>.+)$")
    for index, line in enumerate(lines):
        match = import_pattern.match(line)
        if not match:
            continue
        imported_names = {
            item.strip()
            for item in match.group("names").split(",")
            if item.strip() and " as " not in item.strip()
        }
        imported_names.update(names)
        lines[index] = f"from {module_name} import {', '.join(sorted(imported_names))}"
        return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return _ensure_import(text, f"from {module_name} import {', '.join(names)}")


def _patch_utils(text: str) -> str:
    text = _ensure_import(text, "import hashlib")
    text = re.sub(r"^INDEXTTS2_WAV_CACHE_DIR\s*=.*\n\n?", "", text, flags=re.MULTILINE)

    if "def _is_valid_cached_wav" in text:
        text = _replace_function(text, "_is_valid_cached_wav", STABLE_IS_VALID_CACHED_WAV)
    else:
        text = text.replace("\ndef save_temp_wav", "\n" + STABLE_IS_VALID_CACHED_WAV + "def save_temp_wav", 1)

    if "_REF_CACHE_DIR" in text:
        text = re.sub(
            r'^_REF_CACHE_DIR\s*=.*$',
            '_REF_CACHE_DIR = "indextts2_ref_cache"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        text = text.replace(
            "\ndef _is_valid_cached_wav",
            '\n_REF_CACHE_DIR = "indextts2_ref_cache"\n\n\ndef _is_valid_cached_wav',
            1,
        )

    return _replace_function(text, "save_temp_wav", STABLE_SAVE_TEMP_WAV)


STABLE_IS_VALID_CACHED_WAV = '''def _is_valid_cached_wav(path: str, sr: int) -> bool:
    try:
        info = sf.info(path)
        if int(info.samplerate) != int(sr) or int(info.frames) <= 0:
            return False
        data, read_sr = sf.read(path, frames=1, always_2d=False)
        return int(read_sr) == int(sr) and np.asarray(data).size > 0
    except Exception:
        return False


'''


STABLE_SAVE_TEMP_WAV = '''def save_temp_wav(wave_sr: Tuple[np.ndarray, int]) -> str:
    """
    Save (wave, sr) to a temporary mono WAV file and return the path.
    Wave is expected in float32 [-1, 1] range or int16.
    """
    wave, sr = wave_sr
    if wave is None:
        raise ValueError("wave is None")
    if wave.ndim > 1:
        # force mono
        wave = wave.reshape(-1)
    # ensure float32
    if wave.dtype != np.float32:
        if wave.dtype == np.int16:
            wave = (wave.astype(np.float32) / 32768.0).clip(-1.0, 1.0)
        else:
            wave = wave.astype(np.float32)
    else:
        wave = np.asarray(wave, dtype=np.float32)
    wave = np.ascontiguousarray(wave)
    sr = int(sr)
    digest = hashlib.sha256()
    digest.update(str(sr).encode("ascii"))
    digest.update(str(wave.dtype).encode("ascii"))
    digest.update(str(wave.shape).encode("ascii"))
    digest.update(wave.tobytes())
    cache_dir = os.path.join(tempfile.gettempdir(), _REF_CACHE_DIR)
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"indextts2_{digest.hexdigest()[:24]}.wav")
    if os.path.exists(path) and _is_valid_cached_wav(path, sr):
        return path

    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}.",
        suffix=".wav",
        dir=cache_dir,
    )
    os.close(fd)
    try:
        sf.write(tmp_path, wave, int(sr))
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return path
'''


def _replace_function(text: str, function_name: str, replacement: str) -> str:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ValueError(f"could not parse file while locating function to patch: {function_name}") from exc

    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    ]
    if len(matches) != 1:
        raise ValueError(f"could not find function to patch: {function_name}")

    node = matches[0]
    if node.end_lineno is None:
        raise ValueError(f"could not determine function bounds while patching: {function_name}")

    start_lineno = node.lineno
    if node.decorator_list:
        start_lineno = min(decorator.lineno for decorator in node.decorator_list)

    lines = text.splitlines(keepends=True)
    end_index = node.end_lineno
    while end_index < len(lines) and not lines[end_index].strip():
        end_index += 1
    return "".join(lines[: start_lineno - 1]) + replacement + "".join(lines[end_index:])


def _patch_infer_v2(text: str) -> str:
    text = _patch_qwen_initialization(text)
    text = _ensure_qwen_getter(text)
    text = _patch_use_emo_text_getter(text)
    text = _patch_do_sample_argument(text)
    return text


def _patch_engine(text: str) -> str:
    if (
        "max_text_tokens_per_sentence=int(max_tokens_per_sentence)" in text
        and "max_text_tokens_per_segment=int(max_tokens_per_sentence)" not in text
    ):
        return text

    patched, count = re.subn(
        r"\bmax_text_tokens_per_segment\s*=\s*int\(max_tokens_per_sentence\)\s*"
        r"if\s*max_tokens_per_sentence\s*else\s*120\s*,",
        "max_text_tokens_per_sentence=int(max_tokens_per_sentence) if max_tokens_per_sentence else 120,",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError("could not find max_tokens_per_sentence forwarding call to patch")
    return patched


def _patch_model_loader(text: str) -> str:
    text = _ensure_import(text, "import threading")
    text = _ensure_import(text, "import weakref")
    text = _ensure_from_import_names(text, "typing", ("Any",))

    if "def unload_all_indextts2" not in text:
        text, count = re.subn(
            r"^class IndexTTS2Loader:",
            STABLE_INDEXTTS2_RELEASE_SUPPORT + "class IndexTTS2Loader:",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise ValueError("could not find IndexTTS2Loader class to patch")
    else:
        text = _replace_function(
            text,
            "unload_all_indextts2",
            STABLE_UNLOAD_ALL_INDEXTTS2,
        )

    text = _ensure_model_loader_release_globals(text)
    text = _ensure_model_loader_release_functions(text)

    if "def indextts2_release_health" not in text:
        text, count = re.subn(
            r"^class IndexTTS2Loader:",
            STABLE_INDEXTTS2_HEALTH + "class IndexTTS2Loader:",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise ValueError("could not find IndexTTS2Loader class to patch health contract")
    else:
        text = _replace_function(
            text,
            "indextts2_release_health",
            STABLE_INDEXTTS2_HEALTH,
        )

    if "def _describe_loader_objects" not in text:
        text, count = re.subn(
            r"^def unload_all_indextts2",
            STABLE_INDEXTTS2_OBJECT_HELPERS + "def unload_all_indextts2",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise ValueError("could not find unload_all_indextts2 insertion point")

    if "def _hook_comfy_soft_empty_cache" not in text:
        text, count = re.subn(
            r"^class IndexTTS2Loader:",
            STABLE_INDEXTTS2_COMFY_HOOK + "class IndexTTS2Loader:",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise ValueError("could not find IndexTTS2Loader class to patch ComfyUI hook")

    if "_INDEXTTS2_LOADER_REGISTRY.add(self)" not in text:
        patched, count = re.subn(
            r"(?P<indent>\s*)self\._cache(?:\s*:\s*[^=]+)?\s*=\s*\{\}\s*$",
            "\\g<0>\n\\g<indent>with _INDEXTTS2_LOADER_REGISTRY_LOCK:\n"
            "\\g<indent>    _INDEXTTS2_LOADER_REGISTRY.add(self)",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise ValueError("could not find IndexTTS2Loader cache initialization to patch")
        text = patched

    return _replace_function(text, "unload_tts", STABLE_UNLOAD_TTS)


_INDEXTTS2_RELEASE_GLOBALS = [
    ("_INDEXTTS2_LOADER_REGISTRY", "_INDEXTTS2_LOADER_REGISTRY = weakref.WeakSet()\n"),
    ("_INDEXTTS2_LOADER_REGISTRY_LOCK", "_INDEXTTS2_LOADER_REGISTRY_LOCK = threading.RLock()\n"),
    ("_INDEXTTS2_SOFT_EMPTY_CACHE_PATCHED", "_INDEXTTS2_SOFT_EMPTY_CACHE_PATCHED = False\n"),
    (
        "_INDEXTTS2_TTS_ATTRS",
        '''_INDEXTTS2_TTS_ATTRS = (
    "gpt",
    "semantic_model",
    "semantic_codec",
    "s2mel",
    "campplus_model",
    "bigvgan",
    "qwen_emo",
    "extract_features",
    "semantic_mean",
    "semantic_std",
    "tokenizer",
    "model",
)
''',
    ),
    ("_INDEXTTS2_CACHE_MODEL_KEYS", '_INDEXTTS2_CACHE_MODEL_KEYS = ("tts",)\n'),
]


def _ensure_model_loader_release_globals(text: str) -> str:
    for name, replacement in _INDEXTTS2_RELEASE_GLOBALS:
        if _has_top_level_assignment(text, name):
            text = _replace_top_level_assignment(text, name, replacement)

    missing = [
        replacement
        for name, replacement in _INDEXTTS2_RELEASE_GLOBALS
        if not _has_top_level_assignment(text, name)
    ]
    if not missing:
        return text
    return _insert_before_release_support(text, "".join(missing) + "\n")


def _ensure_model_loader_release_functions(text: str) -> str:
    required_functions = [
        ("_weakref_or_none", STABLE_WEAKREF_OR_NONE),
    ]
    for function_name, replacement in required_functions:
        if f"def {function_name}" in text:
            text = _replace_function(text, function_name, replacement)
        else:
            text = _insert_before_release_support(text, replacement)
    return text


def _has_top_level_assignment(text: str, name: str) -> bool:
    return _find_top_level_assignment(text, name) is not None


def _replace_top_level_assignment(text: str, name: str, replacement: str) -> str:
    node = _find_top_level_assignment(text, name)
    if node is None:
        return text
    if node.end_lineno is None:
        raise ValueError(f"could not determine assignment bounds while patching: {name}")
    lines = text.splitlines(keepends=True)
    return "".join(lines[: node.lineno - 1]) + replacement + "".join(lines[node.end_lineno :])


def _find_top_level_assignment(text: str, name: str) -> ast.Assign | ast.AnnAssign | None:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ValueError(f"could not parse model_loader.py while locating assignment: {name}") from exc
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return node
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return node
    return None


def _insert_before_release_support(text: str, snippet: str) -> str:
    anchors = [
        r"^_INDEXTTS2_LOADER_REGISTRY\s*=",
        r"^_INDEXTTS2_LOADER_REGISTRY_LOCK\s*=",
        r"^_INDEXTTS2_SOFT_EMPTY_CACHE_PATCHED\s*=",
        r"^_INDEXTTS2_TTS_ATTRS\s*=",
        r"^_INDEXTTS2_CACHE_MODEL_KEYS\s*=",
        r"^def _cuda_memory_stats",
        r"^def _clear_cuda_cache",
        r"^def _release_tts_object",
        r"^def _weakref_or_none",
        r"^def _describe_loader_objects",
        r"^def unload_all_indextts2",
        r"^def indextts2_release_health",
        r"^def _hook_comfy_soft_empty_cache",
        r"^class IndexTTS2Loader:",
    ]
    for anchor in anchors:
        patched, count = re.subn(anchor, snippet + r"\g<0>", text, count=1, flags=re.MULTILINE)
        if count == 1:
            return patched
    raise ValueError("could not find insertion point for IndexTTS2 release globals")


STABLE_INDEXTTS2_RELEASE_SUPPORT = '''_INDEXTTS2_LOADER_REGISTRY = weakref.WeakSet()
_INDEXTTS2_LOADER_REGISTRY_LOCK = threading.RLock()
_INDEXTTS2_SOFT_EMPTY_CACHE_PATCHED = False
_INDEXTTS2_TTS_ATTRS = (
    "gpt",
    "semantic_model",
    "semantic_codec",
    "s2mel",
    "campplus_model",
    "bigvgan",
    "qwen_emo",
    "extract_features",
    "semantic_mean",
    "semantic_std",
    "tokenizer",
    "model",
)
_INDEXTTS2_CACHE_MODEL_KEYS = ("tts",)


def _cuda_memory_stats() -> dict:
    stats = {
        "cuda_available": False,
        "cuda_allocated": None,
        "cuda_reserved": None,
    }
    try:
        if torch.cuda.is_available():
            stats["cuda_available"] = True
            stats["cuda_allocated"] = int(torch.cuda.memory_allocated())
            stats["cuda_reserved"] = int(torch.cuda.memory_reserved())
    except Exception as exc:
        stats["cuda_error"] = str(exc)
    return stats


def _clear_cuda_cache() -> None:
    try:
        gc.collect()
    except Exception:
        pass
    try:
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


def _release_tts_object(tts: Any) -> None:
    if tts is None:
        return
    for attr in _INDEXTTS2_TTS_ATTRS:
        try:
            if hasattr(tts, attr):
                setattr(tts, attr, None)
        except Exception:
            pass


'''


STABLE_WEAKREF_OR_NONE = '''def _weakref_or_none(value: Any):
    if value is None:
        return None
    try:
        return weakref.ref(value)
    except TypeError:
        return None


'''


STABLE_INDEXTTS2_OBJECT_HELPERS = '''def _describe_loader_objects(loader: Any) -> list[str]:
    objects = []
    cache = getattr(loader, "_cache", None)
    if isinstance(cache, dict):
        for key in _INDEXTTS2_CACHE_MODEL_KEYS:
            if cache.get(key) is not None:
                objects.append(key)
    return objects


def _unique_items(items: list[str]) -> list[str]:
    return sorted({str(item) for item in items if item})


'''


STABLE_UNLOAD_ALL_INDEXTTS2 = '''def unload_all_indextts2() -> dict:
    before = _cuda_memory_stats()
    with _INDEXTTS2_LOADER_REGISTRY_LOCK:
        loaders = list(_INDEXTTS2_LOADER_REGISTRY)

    loaders_released = 0
    objects_seen = []
    objects_released = []
    residual_objects = []
    errors = []
    for loader in loaders:
        try:
            objects_seen.extend(_describe_loader_objects(loader))
            release_result = loader.unload_tts()
            if release_result.get("released"):
                loaders_released += 1
            objects_released.extend(release_result.get("objects_released", []))
            residual_objects.extend(release_result.get("residual_objects", []))
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

    _clear_cuda_cache()
    with _INDEXTTS2_LOADER_REGISTRY_LOCK:
        loaders_after = list(_INDEXTTS2_LOADER_REGISTRY)
    for loader in loaders_after:
        residual_objects.extend(_describe_loader_objects(loader))

    objects_seen = _unique_items(objects_seen)
    objects_released = _unique_items(objects_released)
    residual_objects = _unique_items(residual_objects)
    after = _cuda_memory_stats()
    safe_to_continue = not residual_objects and not errors
    return {
        "protocol_version": 2,
        "safe_to_continue": safe_to_continue,
        "released": bool(objects_released),
        "loaders_seen": len(loaders),
        "loaders_released": loaders_released,
        "objects_seen": objects_seen,
        "objects_released": objects_released,
        "residual_objects": residual_objects,
        "errors": errors,
        "cuda_allocated_before": before.get("cuda_allocated"),
        "cuda_allocated_after": after.get("cuda_allocated"),
        "cuda_reserved_before": before.get("cuda_reserved"),
        "cuda_reserved_after": after.get("cuda_reserved"),
    }


'''


STABLE_INDEXTTS2_COMFY_HOOK = '''def _hook_comfy_soft_empty_cache() -> None:
    global _INDEXTTS2_SOFT_EMPTY_CACHE_PATCHED
    if _INDEXTTS2_SOFT_EMPTY_CACHE_PATCHED:
        return
    try:
        import comfy.model_management as model_management
    except Exception:
        return

    original_soft_empty_cache = getattr(model_management, "soft_empty_cache", None)
    if not callable(original_soft_empty_cache):
        return

    def _pixelle_indextts2_soft_empty_cache(*args, **kwargs):
        unload_all_indextts2()
        return original_soft_empty_cache(*args, **kwargs)

    model_management.soft_empty_cache = _pixelle_indextts2_soft_empty_cache
    _INDEXTTS2_SOFT_EMPTY_CACHE_PATCHED = True


_hook_comfy_soft_empty_cache()


'''


STABLE_INDEXTTS2_RELEASE_SUPPORT += (
    STABLE_WEAKREF_OR_NONE
    + STABLE_INDEXTTS2_OBJECT_HELPERS
    + STABLE_UNLOAD_ALL_INDEXTTS2
    + STABLE_INDEXTTS2_COMFY_HOOK
)


STABLE_INDEXTTS2_HEALTH = '''def indextts2_release_health() -> dict:
    with _INDEXTTS2_LOADER_REGISTRY_LOCK:
        loaders = list(_INDEXTTS2_LOADER_REGISTRY)
    residual_objects = []
    for loader in loaders:
        residual_objects.extend(_describe_loader_objects(loader))
    residual_objects = _unique_items(residual_objects)
    return {
        "protocol_version": 2,
        "ok": True,
        "extension": "indextts2",
        "release_endpoint": "/pixelle/indextts2/free",
        "loaders_seen": len(loaders),
        "safe_to_continue": not residual_objects,
        "residual_objects": residual_objects,
    }


'''


STABLE_UNLOAD_TTS = '''    def unload_tts(self) -> dict:
        """
        Best-effort unload of cached TTS instance and free GPU cache to reduce VRAM.
        Safe to call even if not loaded.
        """
        objects_released = []
        residual_objects = []
        try:
            tts = self._cache.pop("tts", None)
            if tts is not None:
                objects_released.append("tts")
            tts_ref = _weakref_or_none(tts)
            _release_tts_object(tts)
            del tts
            if tts_ref is not None and tts_ref() is not None:
                residual_objects.append("tts_external_ref")
        except Exception:
            residual_objects.append("tts_release_error")
        _clear_cuda_cache()
        return {
            "released": bool(objects_released),
            "objects_released": objects_released,
            "residual_objects": residual_objects,
        }
'''


def _patch_plugin_init(text: str) -> str:
    import_line = "from . import pixelle_routes as _pixelle_routes"
    if import_line in text:
        return text

    lines = text.splitlines()
    insert_at = 0
    if lines and lines[0].startswith('"""'):
        insert_at = 1
        while insert_at < len(lines) and not lines[insert_at].endswith('"""'):
            insert_at += 1
        insert_at = min(insert_at + 1, len(lines))

    while insert_at < len(lines) and (
        lines[insert_at].startswith("import ")
        or lines[insert_at].startswith("from ")
        or not lines[insert_at].strip()
    ):
        insert_at += 1

    lines.insert(insert_at, import_line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


STABLE_PIXELLE_ROUTES = '''from aiohttp import web
from server import PromptServer

from .indextts2.model_loader import indextts2_release_health, unload_all_indextts2


@PromptServer.instance.routes.get("/pixelle/indextts2/health")
async def pixelle_health_indextts2(request):
    return web.json_response(indextts2_release_health())


@PromptServer.instance.routes.post("/pixelle/indextts2/free")
async def pixelle_free_indextts2(request):
    result = unload_all_indextts2()
    status = 500 if result.get("errors") else 200
    return web.json_response(result, status=status)
'''


def _patch_qwen_initialization(text: str) -> str:
    if (
        "self.qwen_emo_path = os.path.join(self.model_dir, qwen_subdir)" in text
        and "self.qwen_emo = None" in text
    ):
        return text

    pattern = re.compile(
        r"^(?P<indent>\s*)self\.qwen_emo\s*=\s*QwenEmotion\("
        r"\s*os\.path\.join\(\s*self\.model_dir\s*,\s*"
        r"(?P<subdir>self\.cfg\.qwen_emo_path|qwen_subdir)\s*\)\s*\)\s*$",
        flags=re.MULTILINE,
    )

    def replace(match: re.Match[str]) -> str:
        indent = match.group("indent")
        lines = []
        if match.group("subdir") == "self.cfg.qwen_emo_path":
            lines.append(f"{indent}qwen_subdir = str(self.cfg.qwen_emo_path).strip()")
        lines.extend(
            [
                f"{indent}self.qwen_emo_path = os.path.join(self.model_dir, qwen_subdir)",
                f"{indent}self.qwen_emo = None",
            ]
        )
        return "\n".join(lines)

    patched, count = pattern.subn(replace, text, count=1)
    if count != 1:
        raise ValueError("could not find supported eager QwenEmotion initialization to patch")
    return patched


def _ensure_qwen_getter(text: str) -> str:
    if "def _get_qwen_emo(self):" in text:
        return text

    getter = (
        "    def _get_qwen_emo(self):\n"
        "        if self.qwen_emo is None:\n"
        "            self.qwen_emo = QwenEmotion(self.qwen_emo_path)\n"
        "        return self.qwen_emo\n"
        "\n"
    )
    for anchor in ("\n    @torch.no_grad()\n", "\n    def get_emb("):
        if anchor in text:
            return text.replace(anchor, "\n" + getter + anchor.lstrip("\n"), 1)
    raise ValueError("could not find insertion point for QwenEmotion getter")


def _patch_use_emo_text_getter(text: str) -> str:
    if "self._get_qwen_emo().inference(emo_text)" in text:
        return text
    if "self.qwen_emo.inference(emo_text)" not in text:
        raise ValueError("could not find use_emo_text QwenEmotion inference call to patch")
    return text.replace(
        "self.qwen_emo.inference(emo_text)",
        "self._get_qwen_emo().inference(emo_text)",
        1,
    )


def _patch_do_sample_argument(text: str) -> str:
    call_span = _find_inference_speech_call_span(text)
    if call_span is None:
        raise ValueError("could not find self.gpt.inference_speech call to patch")

    call_start, call_end = call_span
    call_text = text[call_start:call_end]
    if re.search(r"\bdo_sample\s*=\s*do_sample\b", call_text):
        return text

    patched_call, count = re.subn(
        r"\bdo_sample\s*=\s*True\b",
        "do_sample=do_sample",
        call_text,
        count=1,
    )
    if count != 1:
        raise ValueError("could not find do_sample=True argument in self.gpt.inference_speech call to patch")
    return text[:call_start] + patched_call + text[call_end:]


def _find_inference_speech_call_span(text: str) -> tuple[int, int] | None:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ValueError("could not parse infer_v2.py while locating self.gpt.inference_speech call") from exc

    line_starts = _line_start_offsets(text)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_self_gpt_inference_speech(node.func):
            continue
        if node.end_lineno is None or node.end_col_offset is None:
            raise ValueError("could not determine self.gpt.inference_speech call bounds")
        start = line_starts[node.lineno - 1] + node.col_offset
        end = line_starts[node.end_lineno - 1] + node.end_col_offset
        return start, end
    return None


def _line_start_offsets(text: str) -> list[int]:
    starts = [0]
    for match in re.finditer(r"\n", text):
        starts.append(match.end())
    return starts


def _is_self_gpt_inference_speech(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "inference_speech"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "gpt"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "self"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch a ComfyUI-Index-TTS plugin directory for Pixelle's local runtime."
    )
    parser.add_argument(
        "--target",
        help=f"Path to ComfyUI-Index-TTS. Defaults to ${INDEXTTS2_PLUGIN_ENV}.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        target = resolve_target_path(args.target)
        result = patch_plugin(target)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if result.changed_files:
        for path in result.changed_files:
            print(f"patched: {path}")
    else:
        print(f"already patched: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
