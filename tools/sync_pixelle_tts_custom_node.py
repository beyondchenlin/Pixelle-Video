import argparse
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "tools" / "comfyui" / "custom_nodes" / "ComfyUI-Pixelle-TTS"
DEFAULT_TARGET = Path(r"E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS")
DEFAULT_PYTHON = Path(r"C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe")
IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc")


def _validate_sync_target(target: Path) -> None:
    resolved = target.resolve()
    if resolved == Path(resolved.anchor):
        raise ValueError(f"refusing to sync into filesystem root: {resolved}")


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
    parser.add_argument("--target", default=str(DEFAULT_TARGET))
    parser.add_argument("--python", dest="python_executable", default=str(DEFAULT_PYTHON))
    parser.add_argument("--skip-install", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    target = Path(args.target)
    python_executable = Path(args.python_executable)

    sync_tree(source, target)

    if not args.skip_install:
        install_requirements(python_executable, target / "requirements.txt")

    print(f"Synced Pixelle TTS custom node to: {target}")


if __name__ == "__main__":
    main()
