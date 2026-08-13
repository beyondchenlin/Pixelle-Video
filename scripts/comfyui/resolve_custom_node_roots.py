"""Read the custom-node roots registered by ComfyUI's own path loader."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path


class CustomNodeRootResolutionError(RuntimeError):
    """Raised when ComfyUI cannot expose its effective custom-node roots."""


def _load_extra_path_config(loader: Callable[[str], object], path: Path) -> None:
    try:
        loader(str(path))
    except Exception as exc:
        raise CustomNodeRootResolutionError(
            f"could not load ComfyUI path configuration: {path}"
        ) from exc


def _require_module_below_root(module: object, comfyui_root: Path) -> None:
    module_file = getattr(module, "__file__", None)
    try:
        is_below_root = bool(
            module_file
            and Path(module_file).resolve().is_relative_to(comfyui_root.resolve())
        )
    except OSError:
        is_below_root = False
    if not is_below_root:
        raise CustomNodeRootResolutionError(
            f"ComfyUI path module was imported outside the configured root: {comfyui_root}"
        )


def resolve_custom_node_roots(
    *,
    comfyui_root: Path,
    base_directory: Path,
    extra_models_config: Path | None,
) -> list[str]:
    absolute_comfyui_root = Path(os.path.abspath(comfyui_root))
    absolute_base_directory = Path(os.path.abspath(base_directory))
    original_argv = sys.argv
    original_path = sys.path[:]
    original_dont_write_bytecode = sys.dont_write_bytecode
    sys.argv = [
        "resolve_custom_node_roots",
        "--base-directory",
        str(absolute_base_directory),
    ]
    sys.path.insert(0, str(absolute_comfyui_root))
    sys.dont_write_bytecode = True

    try:
        try:
            comfy_options = importlib.import_module("comfy.options")
            comfy_options.enable_args_parsing()
            folder_paths = importlib.import_module("folder_paths")
            extra_config = importlib.import_module("utils.extra_config")
            for module in (comfy_options, folder_paths, extra_config):
                _require_module_below_root(module, absolute_comfyui_root)
        except Exception as exc:
            raise CustomNodeRootResolutionError(
                f"could not initialize ComfyUI path resolution from: {absolute_comfyui_root}"
            ) from exc

        built_in_config = absolute_comfyui_root / "extra_model_paths.yaml"
        if built_in_config.is_file():
            _load_extra_path_config(extra_config.load_extra_path_config, built_in_config)
        if extra_models_config is not None:
            _load_extra_path_config(
                extra_config.load_extra_path_config,
                Path(os.path.abspath(extra_models_config)),
            )

        try:
            roots = folder_paths.get_folder_paths("custom_nodes")
        except Exception as exc:
            raise CustomNodeRootResolutionError(
                "ComfyUI did not expose its custom-node search paths"
            ) from exc
        if not isinstance(roots, list) or not all(
            isinstance(root, str) and root for root in roots
        ):
            raise CustomNodeRootResolutionError(
                "ComfyUI returned invalid custom-node search paths"
            )
        return [os.path.normpath(os.path.abspath(root)) for root in roots]
    finally:
        sys.argv = original_argv
        sys.path[:] = original_path
        sys.dont_write_bytecode = original_dont_write_bytecode


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comfyui-root", type=Path, required=True)
    parser.add_argument("--base-directory", type=Path, required=True)
    parser.add_argument("--extra-models-config", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            roots = resolve_custom_node_roots(
                comfyui_root=args.comfyui_root,
                base_directory=args.base_directory,
                extra_models_config=args.extra_models_config,
            )
    except CustomNodeRootResolutionError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True))
        return 2
    print(json.dumps({"roots": roots}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
