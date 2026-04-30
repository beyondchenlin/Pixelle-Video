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
