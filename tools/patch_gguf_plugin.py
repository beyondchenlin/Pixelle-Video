import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

GGUF_PLUGIN_ENV = "GGUF_PLUGIN_DIR"
PLUGIN_INIT_RELATIVE_PATH = Path("__init__.py")
PIXELLE_ROUTES_RELATIVE_PATH = Path("pixelle_routes.py")


@dataclass(frozen=True)
class PatchResult:
    changed_files: list[Path]


def resolve_target_path(target_arg: str | os.PathLike[str] | None) -> Path:
    if target_arg:
        return Path(target_arg)

    target_env = os.environ.get(GGUF_PLUGIN_ENV)
    if target_env:
        return Path(target_env)

    raise ValueError(f"Pass --target or set {GGUF_PLUGIN_ENV} to the ComfyUI-GGUF directory")


def patch_plugin(target: str | os.PathLike[str]) -> PatchResult:
    plugin_dir = Path(target)
    if not plugin_dir.exists():
        raise FileNotFoundError(f"target plugin directory does not exist: {plugin_dir}")
    if not plugin_dir.is_dir():
        raise NotADirectoryError(f"target plugin path is not a directory: {plugin_dir}")

    plugin_init_path = plugin_dir / PLUGIN_INIT_RELATIVE_PATH
    routes_path = plugin_dir / PIXELLE_ROUTES_RELATIVE_PATH
    _require_file(plugin_init_path, PLUGIN_INIT_RELATIVE_PATH)

    changed_files: list[Path] = []
    if _patch_file(plugin_init_path, _patch_plugin_init):
        changed_files.append(plugin_init_path)
    if _write_stable_file(routes_path, STABLE_PIXELLE_GGUF_ROUTES):
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


STABLE_PIXELLE_GGUF_ROUTES = '''import gc
import sys

import torch
from aiohttp import web
from server import PromptServer


_PIXELLE_GGUF_RELEASE_CONTRACT_REVISION = 2


def _cuda_snapshot() -> dict:
    if not torch.cuda.is_available():
        return {}
    device = torch.cuda.current_device()
    return {
        "cuda_allocated": int(torch.cuda.memory_allocated(device)),
        "cuda_reserved": int(torch.cuda.memory_reserved(device)),
    }


def _find_gguf_objects() -> list[str]:
    labels = []
    modules = [
        module
        for module_name, module in list(sys.modules.items())
        if module_name.endswith("ComfyUI-GGUF.nodes") or module_name.endswith("ComfyUI_GGUF.nodes")
    ]
    for module in modules:
        model_patcher_cls = getattr(module, "GGUFModelPatcher", None)
        if model_patcher_cls is None:
            continue
        for obj in gc.get_objects():
            try:
                if isinstance(obj, model_patcher_cls):
                    labels.append("GGUFModelPatcher")
            except Exception:
                continue
    return sorted(set(labels))


_MIN_CUDA_ALLOCATED_RELEASE_BYTES = 64 * 1024 * 1024
_MIN_CUDA_ALLOCATED_RELEASE_RATIO = 0.05


def _cuda_allocated_release_is_material(before_bytes: int, after_bytes: int) -> bool:
    if before_bytes <= 0 or after_bytes >= before_bytes:
        return False
    release_bytes = before_bytes - after_bytes
    relative_threshold = max(1, int(before_bytes * _MIN_CUDA_ALLOCATED_RELEASE_RATIO))
    threshold = min(_MIN_CUDA_ALLOCATED_RELEASE_BYTES, relative_threshold)
    return release_bytes >= threshold


def gguf_release_health() -> dict:
    objects_seen = _find_gguf_objects()
    snapshot = _cuda_snapshot()
    return {
        "protocol_version": 2,
        "contract_revision": _PIXELLE_GGUF_RELEASE_CONTRACT_REVISION,
        "ok": True,
        "extension": "gguf",
        "release_endpoint": "/pixelle/gguf/free",
        "safe_to_continue": True,
        "objects_seen": objects_seen,
        "residual_objects": [],
        "errors": [],
        "cuda_allocated": snapshot.get("cuda_allocated", 0),
        "cuda_reserved": snapshot.get("cuda_reserved", 0),
    }


def unload_gguf_models() -> dict:
    errors = []
    before = _cuda_snapshot()
    objects_seen = _find_gguf_objects()
    try:
        import comfy.model_management

        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache()
    except Exception as exc:
        errors.append(str(exc))
    try:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception as exc:
        errors.append(str(exc))

    diagnostic_objects = _find_gguf_objects()
    after = _cuda_snapshot()
    cuda_allocated_before = before.get("cuda_allocated", 0)
    cuda_allocated_after = after.get("cuda_allocated", 0)
    cuda_allocated_decreased = _cuda_allocated_release_is_material(
        cuda_allocated_before,
        cuda_allocated_after,
    )
    residual_objects = []
    release_confirmation_reason = "gguf_objects_released"
    if diagnostic_objects and not cuda_allocated_decreased:
        residual_objects = diagnostic_objects
        release_confirmation_reason = "gguf_objects_residual"
    elif errors:
        release_confirmation_reason = "gguf_release_errors"
    elif cuda_allocated_decreased:
        release_confirmation_reason = "gguf_cuda_allocated_decreased"
    safe_to_continue = not errors and not residual_objects
    return {
        "protocol_version": 2,
        "contract_revision": _PIXELLE_GGUF_RELEASE_CONTRACT_REVISION,
        "extension": "gguf",
        "released": bool(objects_seen) or cuda_allocated_decreased,
        "safe_to_continue": safe_to_continue,
        "release_confirmation_reason": release_confirmation_reason,
        "objects_seen": objects_seen,
        "objects_released": [item for item in objects_seen if item not in diagnostic_objects],
        "diagnostic_objects": diagnostic_objects,
        "residual_objects": residual_objects,
        "errors": errors,
        "cuda_allocated_before": cuda_allocated_before,
        "cuda_allocated_after": cuda_allocated_after,
        "cuda_reserved_before": before.get("cuda_reserved", 0),
        "cuda_reserved_after": after.get("cuda_reserved", 0),
    }


@PromptServer.instance.routes.get("/pixelle/gguf/health")
async def pixelle_health_gguf(request):
    return web.json_response(gguf_release_health())


@PromptServer.instance.routes.post("/pixelle/gguf/free")
async def pixelle_free_gguf(request):
    result = unload_gguf_models()
    status = 500 if result.get("errors") else 200
    return web.json_response(result, status=status)
'''


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Patch ComfyUI-GGUF with Pixelle release protocol endpoints.",
    )
    parser.add_argument(
        "--target",
        help=f"Path to ComfyUI-GGUF plugin directory. Defaults to ${GGUF_PLUGIN_ENV}.",
    )
    args = parser.parse_args(argv)

    target = resolve_target_path(args.target)
    result = patch_plugin(target)
    if result.changed_files:
        print("Patched files:")
        for path in result.changed_files:
            print(f"- {path}")
    else:
        print("ComfyUI-GGUF Pixelle release patch already up to date.")
    print("Restart ComfyUI for the GGUF release endpoints to take effect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
