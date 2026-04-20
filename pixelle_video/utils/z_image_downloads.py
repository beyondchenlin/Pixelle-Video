from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DownloadTask:
    repo_id: str
    file_path: str
    target_path: Path
    expected_size: int


def build_z_image_download_tasks(
    model_root: Path,
    *,
    include_turbo_nvfp4: bool = False,
) -> list[DownloadTask]:
    tasks = [
        DownloadTask(
            repo_id="Comfy-Org/z_image",
            file_path="split_files/text_encoders/qwen_3_4b.safetensors",
            target_path=model_root / "text_encoders" / "qwen_3_4b.safetensors",
            expected_size=8044982048,
        ),
        DownloadTask(
            repo_id="Comfy-Org/z_image",
            file_path="split_files/vae/ae.safetensors",
            target_path=model_root / "vae" / "ae.safetensors",
            expected_size=335304388,
        ),
        DownloadTask(
            repo_id="Comfy-Org/z_image",
            file_path="split_files/diffusion_models/z_image_bf16.safetensors",
            target_path=model_root / "diffusion_models" / "z_image_bf16.safetensors",
            expected_size=12309866400,
        ),
        DownloadTask(
            repo_id="Comfy-Org/z_image_turbo",
            file_path="split_files/diffusion_models/z_image_turbo_bf16.safetensors",
            target_path=model_root / "diffusion_models" / "z_image_turbo_bf16.safetensors",
            expected_size=12309866400,
        ),
    ]

    if include_turbo_nvfp4:
        tasks.append(
            DownloadTask(
                repo_id="Comfy-Org/z_image_turbo",
                file_path="split_files/diffusion_models/z_image_turbo_nvfp4.safetensors",
                target_path=model_root / "diffusion_models" / "z_image_turbo_nvfp4.safetensors",
                expected_size=4509509600,
            )
        )

    return tasks
