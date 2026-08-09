from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "scripts" / "comfyui"


def test_comfyui_backend_readmes_are_split_by_language() -> None:
    legacy_readme = SCRIPT_DIR / "README.md"
    chinese_readme = SCRIPT_DIR / "README.zh-CN.md"
    english_readme = SCRIPT_DIR / "README.en-US.md"

    assert not legacy_readme.exists()
    assert chinese_readme.exists()
    assert english_readme.exists()

    chinese_text = chinese_readme.read_text(encoding="utf-8")
    english_text = english_readme.read_text(encoding="utf-8")

    assert "Pixelle ComfyUI 后端脚本" in chinese_text
    assert "双击 `.ps1`" in chinese_text
    assert "双击 `.bat`" in chinese_text
    assert "Pixelle ComfyUI Backend Scripts" in english_text
    assert "Double-clicking `.ps1`" in english_text
    assert "Double-click `.bat`" in english_text


def test_windows_batch_launchers_run_matching_powershell_scripts() -> None:
    for command_name in ("check_backend", "start_backend", "stop_backend"):
        batch_path = SCRIPT_DIR / f"{command_name}.bat"
        script_name = f"{command_name}.ps1"

        assert batch_path.exists()
        text = batch_path.read_text(encoding="ascii")

        assert "@echo off" in text
        assert "powershell" in text.lower()
        assert "-NoProfile" in text
        assert "-ExecutionPolicy Bypass" in text
        assert f'"%~dp0{script_name}"' in text
        assert "%*" in text
        assert "pause" in text.lower()


def test_obsolete_dual_backend_batch_launchers_are_removed() -> None:
    obsolete_launchers = (
        "start_image_backend.bat",
        "start_tts_backend.bat",
        "stop_image_backend.bat",
        "stop_tts_backend.bat",
        "check_image_backend.bat",
        "check_tts_backend.bat",
    )

    for filename in obsolete_launchers:
        assert not (SCRIPT_DIR / filename).exists()


def test_root_readmes_document_fixed_local_backend_ports() -> None:
    expected_tokens = (
        "uv run uvicorn api.app:app --host 127.0.0.1 --port 8888",
        "http://localhost:8888/health",
        "http://localhost:8501",
        "http://127.0.0.1:8000",
        r"scripts\comfyui\start_backend.bat",
        r"scripts\comfyui\stop_backend.bat",
        r"scripts\comfyui\check_backend.bat",
    )
    forbidden_tokens = (
        "http://127.0.0.1:8001",
        "http://127.0.0.1:8002",
        r"scripts\comfyui\start_image_backend.bat",
        r"scripts\comfyui\start_tts_backend.bat",
        r"scripts\comfyui\stop_image_backend.bat",
        r"scripts\comfyui\stop_tts_backend.bat",
        "uv run uvicorn api.app:app --host 127.0.0.1 --port 8001",
        "http://localhost:8001/health",
        "http://localhost:8001/docs",
        "http://localhost:8001/api",
    )

    for readme_name in ("README.md", "README_EN.md"):
        text = (REPO_ROOT / readme_name).read_text(encoding="utf-8")

        for token in expected_tokens:
            assert token in text
        for token in forbidden_tokens:
            assert token not in text


def test_obsolete_omnivoice_qwen_asr_compat_script_is_removed() -> None:
    assert not (SCRIPT_DIR / "sync_omnivoice_qwen_asr_compat.ps1").exists()
