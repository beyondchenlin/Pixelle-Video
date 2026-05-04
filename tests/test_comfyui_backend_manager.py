from pathlib import Path

from pixelle_video.services.comfyui_backend_manager import ManagedComfyUIBackend


def test_managed_backend_auto_mode_only_manages_local_pixelle_port():
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="auto",
    )

    assert backend.can_manage() is True


def test_managed_backend_auto_mode_does_not_manage_default_desktop_port():
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8188",
        management_mode="auto",
    )

    assert backend.can_manage() is False


def test_managed_backend_required_mode_forces_management():
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://192.168.1.10:9000",
        management_mode="required",
    )

    assert backend.can_manage() is True


def test_managed_backend_disabled_mode_never_manages():
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        comfyui_url="http://127.0.0.1:8000",
        management_mode="disabled",
    )

    assert backend.can_manage() is False
