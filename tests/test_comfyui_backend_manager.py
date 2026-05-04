from pathlib import Path

import pytest

from pixelle_video.config.schema import ComfyUIBackendProfile
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


def test_managed_backend_profile_managed_false_disables_management(tmp_path):
    profile = ComfyUIBackendProfile(
        url="http://127.0.0.1:8001",
        managed=False,
        data_root=str(tmp_path / "image-data"),
        runtime_dir=str(tmp_path / "runtime" / "image"),
        logs_dir=str(tmp_path / "logs" / "image"),
        database_url=f"sqlite:///{(tmp_path / 'image-data' / 'user' / 'comfyui.db').as_posix()}",
    )
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        profile_name="image",
        profile=profile,
        management_mode="required",
    )

    assert backend.can_manage() is False


@pytest.mark.asyncio
async def test_required_restart_reports_profile_managed_false(tmp_path):
    profile = ComfyUIBackendProfile(
        url="http://127.0.0.1:8001",
        managed=False,
        data_root=str(tmp_path / "image-data"),
        runtime_dir=str(tmp_path / "runtime" / "image"),
        logs_dir=str(tmp_path / "logs" / "image"),
        database_url=f"sqlite:///{(tmp_path / 'image-data' / 'user' / 'comfyui.db').as_posix()}",
    )
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        profile_name="image",
        profile=profile,
        management_mode="required",
    )

    with pytest.raises(RuntimeError, match="profile 'image'.*managed=false"):
        await backend.restart(reason="test-required-mode")


def test_managed_backend_auto_mode_manages_local_profile_ports(tmp_path):
    for profile_name, port in (("image", 8001), ("tts", 8002)):
        profile = ComfyUIBackendProfile(
            url=f"http://127.0.0.1:{port}",
            data_root=str(tmp_path / f"{profile_name}-data"),
            runtime_dir=str(tmp_path / "runtime" / profile_name),
            logs_dir=str(tmp_path / "logs" / profile_name),
            database_url=f"sqlite:///{(tmp_path / f'{profile_name}-data' / 'user' / 'comfyui.db').as_posix()}",
        )
        backend = ManagedComfyUIBackend(
            repo_root=Path.cwd(),
            profile_name=profile_name,
            profile=profile,
            management_mode="auto",
        )

        assert backend.can_manage() is True


def test_managed_backend_uses_profile_runtime_arguments(tmp_path):
    profile = ComfyUIBackendProfile(
        url="http://127.0.0.1:8001",
        data_root=str(tmp_path / "image-data"),
        runtime_dir=str(tmp_path / "runtime" / "image"),
        logs_dir=str(tmp_path / "logs" / "image"),
        database_url=f"sqlite:///{(tmp_path / 'image-data' / 'user' / 'comfyui.db').as_posix()}",
    )
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        profile_name="image",
        profile=profile,
        management_mode="required",
    )

    args = backend._script_args()

    assert "-ProfileName" in args
    assert "image" in args
    assert "-DataRoot" in args
    assert str(tmp_path / "image-data") in args
    assert "-RuntimeDir" in args
    assert str(tmp_path / "runtime" / "image") in args
    assert "-LogsDir" in args
    assert str(tmp_path / "logs" / "image") in args
    assert "-DatabaseUrl" in args
    assert profile.database_url in args
    assert "-Port" in args
    assert "8001" in args


def test_managed_backend_passes_optional_profile_script_arguments(tmp_path):
    python_exe = tmp_path / "venv" / "Scripts" / "python.exe"
    comfyui_root = tmp_path / "ComfyUI"
    frontend_root = comfyui_root / "web_custom_versions" / "desktop_app"
    extra_models_config = tmp_path / "extra_models_config.yaml"
    profile = ComfyUIBackendProfile(
        url="http://localhost:8020",
        python_exe=str(python_exe),
        comfyui_root=str(comfyui_root),
        frontend_root=str(frontend_root),
        extra_models_config=str(extra_models_config),
        data_root=str(tmp_path / "data"),
        runtime_dir=str(tmp_path / "runtime"),
        logs_dir=str(tmp_path / "logs"),
        database_url=f"sqlite:///{(tmp_path / 'data' / 'user' / 'comfyui.db').as_posix()}",
    )
    backend = ManagedComfyUIBackend(
        repo_root=Path.cwd(),
        profile_name="image",
        profile=profile,
        management_mode="required",
    )

    args = backend._script_args()

    assert "-PythonExe" in args
    assert str(python_exe) in args
    assert "-ComfyUIRoot" in args
    assert str(comfyui_root) in args
    assert "-FrontEndRoot" in args
    assert str(frontend_root) in args
    assert "-ExtraModelsConfig" in args
    assert str(extra_models_config) in args
