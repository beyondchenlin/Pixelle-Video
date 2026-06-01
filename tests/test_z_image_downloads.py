import json
from pathlib import Path

from pixelle_video.utils.z_image_downloads import (
    DEFAULT_COMFYUI_MODEL_ROOT,
    build_z_image_download_tasks,
)


def test_default_comfyui_model_root_matches_desktop_runtime_layout():
    assert DEFAULT_COMFYUI_MODEL_ROOT == Path(r"E:\ComfyUIData\models")


def test_build_z_image_download_tasks_defaults_to_gguf_q4_workflow_dependencies():
    model_root = DEFAULT_COMFYUI_MODEL_ROOT

    tasks = build_z_image_download_tasks(model_root)

    assert [(task.repo_id, task.file_path, task.target_path, task.expected_size) for task in tasks] == [
        (
            "unsloth/Z-Image-Turbo-GGUF",
            "z-image-turbo-Q4_K_M.gguf",
            model_root / "unet" / "z-image-turbo-Q4_K_M.gguf",
            5017613376,
        ),
        (
            "unsloth/Qwen3-4B-GGUF",
            "Qwen3-4B-Q4_K_M.gguf",
            model_root / "text_encoders" / "Qwen3-4B-Q4_K_M.gguf",
            2497281312,
        ),
        (
            "Comfy-Org/z_image",
            "split_files/vae/ae.safetensors",
            model_root / "vae" / "ae.safetensors",
            335304388,
        ),
    ]


def test_default_download_tasks_cover_z_image_turbo_gguf_workflow_models():
    workflow = json.loads(
        Path("workflows/selfhost/image_z_image_turbo_gguf.json").read_text(
            encoding="utf-8"
        )
    )
    downloaded_file_names = {
        task.target_path.name
        for task in build_z_image_download_tasks(DEFAULT_COMFYUI_MODEL_ROOT)
    }

    assert workflow["37"]["inputs"]["unet_name"] in downloaded_file_names
    assert workflow["38"]["inputs"]["clip_name"] in downloaded_file_names
    assert workflow["39"]["inputs"]["vae_name"] in downloaded_file_names


def test_build_z_image_download_tasks_can_include_legacy_bf16_workflow_dependencies():
    model_root = DEFAULT_COMFYUI_MODEL_ROOT

    tasks = build_z_image_download_tasks(model_root, include_legacy_bf16=True)

    assert [(task.repo_id, task.file_path, task.target_path, task.expected_size) for task in tasks[-3:]] == [
        (
            "Comfy-Org/z_image",
            "split_files/text_encoders/qwen_3_4b.safetensors",
            model_root / "text_encoders" / "qwen_3_4b.safetensors",
            8044982048,
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
    model_root = DEFAULT_COMFYUI_MODEL_ROOT

    tasks = build_z_image_download_tasks(model_root, include_turbo_nvfp4=True)
    task_names = [task.target_path.name for task in tasks]

    assert "qwen_3_4b.safetensors" in task_names
    assert tasks[-1].repo_id == "Comfy-Org/z_image_turbo"
    assert tasks[-1].file_path == "split_files/diffusion_models/z_image_turbo_nvfp4.safetensors"
    assert tasks[-1].target_path == model_root / "diffusion_models" / "z_image_turbo_nvfp4.safetensors"
    assert tasks[-1].expected_size == 4509509600
