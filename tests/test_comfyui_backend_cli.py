import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.comfyui import backend_cli


def _write_config(path: Path) -> None:
    path.write_text(
        """
comfyui:
  comfyui_url: http://127.0.0.1:8000
  backend_management_mode: auto
  backends:
    default:
      url: http://127.0.0.1:8000
      managed: true
      python_exe: D:/Comfy/python.exe
      comfyui_root: D:/ComfyUI
      data_root: D:/ComfyData/pixelle
      shared_base_path: D:/ComfyData
      runtime_dir: _runtime/comfyui
      logs_dir: logs/comfyui
  workflow_routing:
    image: default
    tts: default
    default: default
""".strip(),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_backend_cli_reads_default_profile_from_config(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    captured = {}

    class FakeManagedBackend:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def can_manage(self):
            return True

        async def start(self, *, reason):
            captured["reason"] = reason
            return SimpleNamespace(action="start", returncode=0, payload={"started": True})

    monkeypatch.setattr(backend_cli, "ManagedComfyUIBackend", FakeManagedBackend)

    payload = await backend_cli._run_action("start", config_path, "default")

    assert captured["profile_name"] == "default"
    assert captured["profile"].shared_base_path == "D:/ComfyData"
    assert captured["reason"] == "manual-start"
    assert payload["result"] == {"started": True}


def test_backend_cli_fails_fast_on_invalid_yaml(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("comfyui: [", encoding="utf-8")

    returncode = backend_cli.main(["check", "--config", str(config_path)])

    assert returncode == 1
    assert "Invalid YAML" in capsys.readouterr().err


def test_backend_cli_outputs_machine_readable_result(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    async def fake_run_action(action, resolved_config_path, profile_name):
        return {
            "action": action,
            "profile": profile_name,
            "config_path": str(resolved_config_path),
            "result": {"listener_present": True},
        }

    monkeypatch.setattr(backend_cli, "_run_action", fake_run_action)

    returncode = backend_cli.main(["check", "--config", str(config_path)])
    payload = json.loads(capsys.readouterr().out)

    assert returncode == 0
    assert payload["action"] == "check"
    assert payload["result"]["listener_present"] is True
