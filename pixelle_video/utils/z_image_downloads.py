from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_COMFYUI_MODEL_ROOT = Path(r"E:\ComfyUIData\models")


@dataclass(frozen=True)
class DownloadTask:
    repo_id: str
    file_path: str
    target_path: Path
    expected_size: int


def _legacy_qwen3_text_encoder_task(model_root: Path) -> DownloadTask:
    return DownloadTask(
        repo_id="Comfy-Org/z_image",
        file_path="split_files/text_encoders/qwen_3_4b.safetensors",
        target_path=model_root / "text_encoders" / "qwen_3_4b.safetensors",
        expected_size=8044982048,
    )


def _append_unique_task(tasks: list[DownloadTask], task: DownloadTask) -> None:
    if task.target_path not in {existing.target_path for existing in tasks}:
        tasks.append(task)


def build_z_image_download_tasks(
    model_root: Path,
    *,
    include_legacy_bf16: bool = False,
    include_turbo_nvfp4: bool = False,
) -> list[DownloadTask]:
    tasks = [
        DownloadTask(
            repo_id="unsloth/Z-Image-Turbo-GGUF",
            file_path="z-image-turbo-Q4_K_M.gguf",
            target_path=model_root / "unet" / "z-image-turbo-Q4_K_M.gguf",
            expected_size=5017613376,
        ),
        DownloadTask(
            repo_id="unsloth/Qwen3-4B-GGUF",
            file_path="Qwen3-4B-Q4_K_M.gguf",
            target_path=model_root / "text_encoders" / "Qwen3-4B-Q4_K_M.gguf",
            expected_size=2497281312,
        ),
        DownloadTask(
            repo_id="Comfy-Org/z_image",
            file_path="split_files/vae/ae.safetensors",
            target_path=model_root / "vae" / "ae.safetensors",
            expected_size=335304388,
        ),
    ]

    if include_legacy_bf16:
        tasks.extend(
            [
                _legacy_qwen3_text_encoder_task(model_root),
                DownloadTask(
                    repo_id="Comfy-Org/z_image",
                    file_path="split_files/diffusion_models/z_image_bf16.safetensors",
                    target_path=model_root / "diffusion_models" / "z_image_bf16.safetensors",
                    expected_size=12309866400,
                ),
                DownloadTask(
                    repo_id="Comfy-Org/z_image_turbo",
                    file_path="split_files/diffusion_models/z_image_turbo_bf16.safetensors",
                    target_path=model_root
                    / "diffusion_models"
                    / "z_image_turbo_bf16.safetensors",
                    expected_size=12309866400,
                ),
            ]
        )

    if include_turbo_nvfp4:
        _append_unique_task(tasks, _legacy_qwen3_text_encoder_task(model_root))
        tasks.append(
            DownloadTask(
                repo_id="Comfy-Org/z_image_turbo",
                file_path="split_files/diffusion_models/z_image_turbo_nvfp4.safetensors",
                target_path=model_root / "diffusion_models" / "z_image_turbo_nvfp4.safetensors",
                expected_size=4509509600,
            )
        )

    return tasks
