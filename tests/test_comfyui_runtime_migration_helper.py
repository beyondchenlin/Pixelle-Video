import json
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="ComfyUI runtime migration helper is Windows-only.",
)


def test_migration_script_creates_required_runtime_directories(tmp_path):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "migrate_comfyui_runtime_to_e_drive.ps1"
    target_base_path = tmp_path / "comfyui-runtime"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"basePath": str(tmp_path / "old-runtime")}),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-TargetBasePath",
            str(target_base_path),
            "-ConfigPath",
            str(config_path),
            "-Apply",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert json.loads(config_path.read_text(encoding="utf-8-sig"))["basePath"] == str(target_base_path)
    for directory_name in ("input", "output", "user", "custom_nodes"):
        assert (target_base_path / directory_name).is_dir()
