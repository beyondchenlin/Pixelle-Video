import argparse
import os
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIRNAME = "ComfyUI-Pixelle-TTS"
CUSTOM_NODES_DIRNAME = "custom_nodes"
COMFYUI_CUSTOM_NODES_ENV = "COMFYUI_CUSTOM_NODES_DIR"
COMFYUI_ROOT_ENV = "COMFYUI_ROOT"
COMFYUI_PYTHON_ENV = "COMFYUI_PYTHON"
DEFAULT_SOURCE = REPO_ROOT / "tools" / "comfyui" / "custom_nodes" / PLUGIN_DIRNAME
IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc")


def _validate_sync_target(target: Path) -> None:
    resolved = target.resolve()
    if resolved == Path(resolved.anchor):
        raise ValueError(f"refusing to sync into filesystem root: {resolved}")
    if resolved.name != PLUGIN_DIRNAME:
        raise ValueError(f"target must point to the {PLUGIN_DIRNAME} plugin directory: {resolved}")
    if resolved.parent.name != CUSTOM_NODES_DIRNAME:
        raise ValueError(f"target must be a plugin directory inside {CUSTOM_NODES_DIRNAME}: {resolved}")


def resolve_target_path(target_arg: str | None) -> Path:
    if target_arg:
        return Path(target_arg)

    custom_nodes_dir = os.environ.get(COMFYUI_CUSTOM_NODES_ENV)
    if custom_nodes_dir:
        return Path(custom_nodes_dir) / PLUGIN_DIRNAME

    comfyui_root = os.environ.get(COMFYUI_ROOT_ENV)
    if comfyui_root:
        return Path(comfyui_root) / CUSTOM_NODES_DIRNAME / PLUGIN_DIRNAME

    raise ValueError(
        "Pass --target or set COMFYUI_CUSTOM_NODES_DIR/COMFYUI_ROOT before syncing the plugin"
    )


def resolve_python_executable(python_arg: str | None) -> Path:
    if python_arg:
        return Path(python_arg)

    python_env = os.environ.get(COMFYUI_PYTHON_ENV)
    if python_env:
        return Path(python_env)

    comfyui_root = os.environ.get(COMFYUI_ROOT_ENV)
    if comfyui_root:
        candidate = Path(comfyui_root) / ".venv" / "Scripts" / "python.exe"
        if candidate.exists():
            return candidate

    raise ValueError("Pass --python or set COMFYUI_PYTHON before installing plugin requirements")


def sync_tree(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"source path does not exist: {source}")

    _validate_sync_target(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        shutil.rmtree(target)

    shutil.copytree(source, target, ignore=IGNORE_PATTERNS)


def install_requirements(python_executable: Path, requirements_file: Path) -> None:
    if not python_executable.exists():
        raise FileNotFoundError(f"python executable does not exist: {python_executable}")
    if not requirements_file.exists():
        raise FileNotFoundError(f"requirements file does not exist: {requirements_file}")

    subprocess.run(
        [str(python_executable), "-m", "pip", "install", "-r", str(requirements_file)],
        check=True,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Sync the Pixelle TTS custom node into ComfyUI.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--target")
    parser.add_argument("--python", dest="python_executable")
    parser.add_argument("--skip-install", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    target = resolve_target_path(args.target)

    sync_tree(source, target)

    if not args.skip_install:
        python_executable = resolve_python_executable(args.python_executable)
        install_requirements(python_executable, target / "requirements.txt")

    print(f"Synced Pixelle TTS custom node to: {target}")


if __name__ == "__main__":
    main()
