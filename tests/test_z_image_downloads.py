from pathlib import Path

from pixelle_video.utils.z_image_downloads import build_z_image_download_tasks


def test_build_z_image_download_tasks_maps_files_to_comfyui_model_dirs():
    model_root = Path(r"E:\comfyui\comfyui\models")

    tasks = build_z_image_download_tasks(model_root)

    assert [(task.repo_id, task.file_path, task.target_path, task.expected_size) for task in tasks] == [
        (
            "Comfy-Org/z_image",
            "split_files/text_encoders/qwen_3_4b.safetensors",
            model_root / "text_encoders" / "qwen_3_4b.safetensors",
            8044982048,
        ),
        (
            "Comfy-Org/z_image",
            "split_files/vae/ae.safetensors",
            model_root / "vae" / "ae.safetensors",
            335304388,
        ),
        (
            "Comfy-Org/z_image",
            "split_files/diffusion_models/z_image_bf16.safetensors",
            model_root / "diffusion_models" / "z_image_bf16.safetensors",
            12309866400,
        ),
        (
            "Comfy-Org/z_image_turbo",
            "split_files/diffusion_models/z_image_turbo_bf16.safetensors",
            model_root / "diffusion_models" / "z_image_turbo_bf16.safetensors",
            12309866400,
        ),
    ]


def test_build_z_image_download_tasks_can_include_turbo_nvfp4():
    model_root = Path(r"E:\comfyui\comfyui\models")

    tasks = build_z_image_download_tasks(model_root, include_turbo_nvfp4=True)

    assert tasks[-1].repo_id == "Comfy-Org/z_image_turbo"
    assert tasks[-1].file_path == "split_files/diffusion_models/z_image_turbo_nvfp4.safetensors"
    assert tasks[-1].target_path == model_root / "diffusion_models" / "z_image_turbo_nvfp4.safetensors"
    assert tasks[-1].expected_size == 4509509600
