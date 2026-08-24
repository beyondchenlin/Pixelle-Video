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

        async def ensure_ready(self, *, reason):
            captured["reason"] = reason
            return SimpleNamespace(
                started=True,
                reused_existing=False,
                ownership="pixelle",
                health={"system": {}},
            )

    monkeypatch.setattr(backend_cli, "ManagedComfyUIBackend", FakeManagedBackend)

    payload = await backend_cli._run_action("start", config_path, "default")

    assert captured["profile_name"] == "default"
    assert captured["working_directory"] == config_path.parent
    assert captured["profile"].shared_base_path == "D:/ComfyData"
    assert captured["reason"] == "manual-start"
    assert payload["result"] == {
        "started": True,
        "already_running": False,
        "ownership": "pixelle",
        "health": {"system": {}},
    }


@pytest.mark.asyncio
async def test_backend_cli_fails_fast_on_invalid_yaml(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("comfyui: [", encoding="utf-8")

    returncode = await backend_cli._main_async(["check", "--config", str(config_path)])

    assert returncode == 1
    assert "Invalid YAML" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_backend_cli_outputs_machine_readable_result(monkeypatch, tmp_path, capsys):
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

    returncode = await backend_cli._main_async(["check", "--config", str(config_path)])
    payload = json.loads(capsys.readouterr().out)

    assert returncode == 0
    assert payload["action"] == "check"
    assert payload["result"]["listener_present"] is True


@pytest.mark.asyncio
async def test_backend_cli_defaults_to_routed_profile(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
comfyui:
  backend_management_mode: required
  backends:
    image:
      url: http://127.0.0.1:8001
  workflow_routing:
    image: image
    tts: image
    default: image
""".strip(),
        encoding="utf-8",
    )
    captured = {}

    class FakeManagedBackend:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def can_manage(self):
            return True

        async def check(self, *, reason):
            return SimpleNamespace(
                action="check",
                returncode=0,
                payload={"listener_present": False},
            )

    monkeypatch.setattr(backend_cli, "ManagedComfyUIBackend", FakeManagedBackend)

    payload = await backend_cli._run_action("check", config_path, None)

    assert captured["profile_name"] == "image"
    assert payload["profile"] == "image"
