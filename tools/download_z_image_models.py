from __future__ import annotations

import argparse
import shutil
import tempfile
import time
from pathlib import Path

from modelscope.hub.file_download import model_file_download

from pixelle_video.utils.z_image_downloads import build_z_image_download_tasks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Z-Image model files from ModelScope into ComfyUI model directories."
    )
    parser.add_argument(
        "--model-root",
        default=r"E:\comfyui\comfyui\models",
        help="ComfyUI models root directory.",
    )
    parser.add_argument(
        "--include-turbo-nvfp4",
        action="store_true",
        help="Also download the lower-VRAM z_image_turbo_nvfp4.safetensors file.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=5,
        help="Retry count per file.",
    )
    return parser.parse_args()


def download_tasks(model_root: Path, *, include_turbo_nvfp4: bool, retries: int) -> None:
    tasks = build_z_image_download_tasks(
        model_root,
        include_turbo_nvfp4=include_turbo_nvfp4,
    )

    temp_root = Path(tempfile.mkdtemp(prefix="modelscope_z_image_", dir=str(model_root.parent)))
    try:
        for task in tasks:
            task.target_path.parent.mkdir(parents=True, exist_ok=True)

            if task.target_path.exists():
                actual_size = task.target_path.stat().st_size
                if actual_size == task.expected_size:
                    print(f"SKIP {task.target_path} | size={actual_size}")
                    continue
                print(
                    f"REMOVE BROKEN {task.target_path} | size={actual_size} | "
                    f"expect={task.expected_size}"
                )
                task.target_path.unlink()

            for attempt in range(1, retries + 1):
                try:
                    print(f"DOWNLOADING {task.file_path} | attempt {attempt}")
                    downloaded_path = Path(
                        model_file_download(
                            model_id=task.repo_id,
                            file_path=task.file_path,
                            local_dir=str(temp_root),
                        )
                    )

                    if not downloaded_path.exists():
                        raise FileNotFoundError(f"Downloaded file missing: {downloaded_path}")

                    if task.target_path.exists():
                        task.target_path.unlink()

                    shutil.move(str(downloaded_path), str(task.target_path))

                    actual_size = task.target_path.stat().st_size
                    if actual_size != task.expected_size:
                        raise RuntimeError(
                            f"size mismatch: actual={actual_size}, expected={task.expected_size}"
                        )

                    print(f"DONE {task.target_path} | size={actual_size}")
                    break
                except Exception as exc:
                    print(f"RETRY {task.file_path} | attempt {attempt} | {exc}")
                    if attempt == retries:
                        raise
                    time.sleep(attempt * 5)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> None:
    args = parse_args()
    model_root = Path(args.model_root)
    model_root.mkdir(parents=True, exist_ok=True)
    download_tasks(
        model_root,
        include_turbo_nvfp4=args.include_turbo_nvfp4,
        retries=args.retries,
    )


if __name__ == "__main__":
    main()
