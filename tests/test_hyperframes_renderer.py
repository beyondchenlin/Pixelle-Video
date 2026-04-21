import json
import subprocess
from pathlib import Path

import pytest

import pixelle_video.service as service_module
from pixelle_video.service import PixelleVideoCore
from pixelle_video.services.hyperframes_project_service import HyperFramesProjectService
from pixelle_video.services.hyperframes_renderer import HyperFramesRenderer


def _write_manifest(project_dir: Path, task_id: str = "task-6") -> None:
    data_dir = project_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "title": "Demo",
                "width": 1080,
                "height": 1920,
                "fps": 24,
                "template_id": "image_life_insights_light",
                "master_audio_path": None,
                "audio_blocks": [],
                "sentence_units": [],
                "visual_clips": [],
                "caption_cues": [],
            }
        ),
        encoding="utf-8",
    )


def _write_template(template_root: Path) -> None:
    template_dir = template_root / "image_life_insights_light"
    compositions_dir = template_dir / "compositions"
    compositions_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "index.html").write_text("<!doctype html><title>template</title>", encoding="utf-8")
    (compositions_dir / "captions.html").write_text(
        "<template id='captions'></template>",
        encoding="utf-8",
    )


def test_render_materializes_template_and_invokes_node_bridge(monkeypatch, tmp_path):
    project_dir = tmp_path / "output" / "task-6" / "hyperframes"
    project_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(project_dir)

    template_root = tmp_path / "templates"
    _write_template(template_root)

    bridge_script = tmp_path / "render.mjs"
    bridge_script.write_text("// bridge placeholder", encoding="utf-8")

    expected_output = project_dir / "renders" / "task-6.mp4"
    captured: dict[str, object] = {}

    def fake_run(command, capture_output, text, check, cwd):
        captured["command"] = command
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["check"] = check
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps({"output_path": str(expected_output)}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    renderer = HyperFramesRenderer(
        node_executable="node-custom",
        bridge_script=str(bridge_script),
        template_root=str(template_root),
    )

    output_path = renderer.render(str(project_dir))

    assert output_path == str(expected_output)
    assert captured["command"] == [
        "node-custom",
        str(bridge_script),
        "--project-dir",
        str(project_dir),
        "--output-path",
        str(expected_output),
    ]
    assert captured["cwd"] == str(project_dir)
    assert (project_dir / "index.html").read_text(encoding="utf-8") == "<!doctype html><title>template</title>"
    assert (project_dir / "compositions" / "captions.html").exists()


@pytest.mark.asyncio
async def test_initialize_wires_hyperframes_services(monkeypatch):
    class DummyService:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class DummyPipeline:
        def __init__(self, core):
            self.core = core

    monkeypatch.setattr(service_module, "LLMService", DummyService)
    monkeypatch.setattr(service_module, "TTSService", DummyService)
    monkeypatch.setattr(service_module, "MediaService", DummyService)
    monkeypatch.setattr(service_module, "ImageAnalysisService", DummyService)
    monkeypatch.setattr(service_module, "VideoAnalysisService", DummyService)
    monkeypatch.setattr(service_module, "VideoService", DummyService)
    monkeypatch.setattr(service_module, "FrameProcessor", DummyService)
    monkeypatch.setattr(service_module, "PersistenceService", DummyService)
    monkeypatch.setattr(service_module, "HistoryManager", DummyService)
    monkeypatch.setattr(service_module, "StandardPipeline", DummyPipeline)
    monkeypatch.setattr(service_module, "CustomPipeline", DummyPipeline)
    monkeypatch.setattr(service_module, "AssetBasedPipeline", DummyPipeline)

    core = PixelleVideoCore()

    await core.initialize()

    assert isinstance(core.hyperframes_project_service, HyperFramesProjectService)
    assert isinstance(core.hyperframes_renderer, HyperFramesRenderer)
