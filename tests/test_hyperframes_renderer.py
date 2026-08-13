import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import pixelle_video.service as service_module
from pixelle_video.service import PixelleVideoCore
from pixelle_video.services.alignment_service import AlignmentService
from pixelle_video.services.audio_edit_service import AudioEditService
from pixelle_video.services.hyperframes_project_service import HyperFramesProjectService
from pixelle_video.services.hyperframes_renderer import HyperFramesRenderer


def _write_bridge_runtime(bridge_root: Path) -> Path:
    dependencies = {
        "@hyperframes/producer": "0.7.107",
        "puppeteer": "25.6.0",
        "yauzl": "3.4.0",
    }
    bridge_script = bridge_root / "src" / "render.mjs"
    bridge_script.parent.mkdir(parents=True, exist_ok=True)
    bridge_script.write_text("// bridge placeholder", encoding="utf-8")
    for script_name in ("runtime_contract.mjs", "verify-runtime.mjs"):
        (bridge_root / "src" / script_name).write_text(
            "// runtime verifier placeholder",
            encoding="utf-8",
        )
    (bridge_root / "package.json").write_text(
        json.dumps({"dependencies": dependencies}),
        encoding="utf-8",
    )
    (bridge_root / "package-lock.json").write_text(
        json.dumps({"packages": {"": {"dependencies": dependencies}}}),
        encoding="utf-8",
    )
    for dependency_name, version in dependencies.items():
        manifest = (
            bridge_root
            / "node_modules"
            / Path(*dependency_name.split("/"))
            / "package.json"
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"version": version}), encoding="utf-8")
    return bridge_script


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


def _stub_successful_bridge(monkeypatch, renderer, output_path: Path, captured=None) -> None:
    renderer._runtime_validated = True

    def fake_run(request):
        if captured is not None:
            captured["command"] = list(request.command)
            captured["cwd"] = str(request.project_path)
            captured["env"] = request.environment
            captured["stdout_log"] = request.stdout_log
            captured["stderr_log"] = request.stderr_log
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"video")
        request.stdout_log.write_text(
            json.dumps({"output_path": str(output_path)}),
            encoding="utf-8",
        )
        request.stderr_log.write_text("", encoding="utf-8")
        return 0

    monkeypatch.setattr(renderer, "_run_bridge_sync", fake_run)


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

    renderer = HyperFramesRenderer(
        node_executable="node-custom",
        bridge_script=str(bridge_script),
        template_root=str(template_root),
    )
    _stub_successful_bridge(monkeypatch, renderer, expected_output, captured)

    output_path = renderer.render(str(project_dir))

    assert output_path == str(expected_output)
    assert captured["command"] == [
        "node-custom",
        str(bridge_script),
        "--project-dir",
        str(project_dir),
        "--output-path",
        str(expected_output),
        "--use-gpu",
    ]
    assert captured["cwd"] == str(project_dir)
    assert (project_dir / "index.html").read_text(encoding="utf-8") == "<!doctype html><title>template</title>"
    assert (project_dir / "compositions" / "captions.html").exists()
    assert (project_dir / "runtime" / "vendor" / "gsap.min.js").exists()


def test_render_preserves_compiled_project_entrypoint_when_present(monkeypatch, tmp_path):
    project_dir = tmp_path / "output" / "task-compiled" / "hyperframes"
    compositions_dir = project_dir / "compositions"
    compositions_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(project_dir, task_id="task-compiled")
    (project_dir / "index.html").write_text(
        "<!doctype html><title>compiled</title>",
        encoding="utf-8",
    )
    (compositions_dir / "captions.html").write_text(
        "<div data-composition-id='captions'></div>",
        encoding="utf-8",
    )

    bridge_script = tmp_path / "render.mjs"
    bridge_script.write_text("// bridge placeholder", encoding="utf-8")

    renderer = HyperFramesRenderer(
        bridge_script=str(bridge_script),
        template_root=str(tmp_path / "missing-templates"),
    )
    _stub_successful_bridge(
        monkeypatch,
        renderer,
        project_dir / "renders" / "task-compiled.mp4",
    )

    renderer.render(str(project_dir))

    assert (project_dir / "index.html").read_text(encoding="utf-8") == "<!doctype html><title>compiled</title>"


def test_validate_runtime_checks_bridge_browser_once_and_reuses_bridge_cache(
    monkeypatch,
    tmp_path,
):
    bridge_root = tmp_path / "tools" / "hyperframes_bridge"
    bridge_script = _write_bridge_runtime(bridge_root)
    captured: dict[str, object] = {"calls": 0}

    def fake_run(command, **kwargs):
        captured["calls"] = int(captured["calls"]) + 1
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(shutil, "which", lambda _executable: "node-resolved")
    monkeypatch.setattr(subprocess, "run", fake_run)
    renderer = HyperFramesRenderer(bridge_script=str(bridge_script))

    renderer.validate_runtime()
    renderer.validate_runtime()

    assert captured["calls"] == 1
    assert captured["cwd"] == bridge_root
    assert captured["command"] == [
        "node-resolved",
        str(bridge_root / "src" / "verify-runtime.mjs"),
    ]
    assert captured["env"]["PUPPETEER_CACHE_DIR"] == str(
        bridge_root / ".cache" / "puppeteer"
    )


def test_validate_runtime_reports_missing_locked_dependency_before_node_launch(
    monkeypatch,
    tmp_path,
):
    bridge_root = tmp_path / "tools" / "hyperframes_bridge"
    bridge_script = _write_bridge_runtime(bridge_root)
    (bridge_root / "node_modules" / "yauzl" / "package.json").unlink()
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("node must not launch for missing files"),
    )

    with pytest.raises(RuntimeError, match="runtime is incomplete") as error_info:
        HyperFramesRenderer(bridge_script=str(bridge_script)).validate_runtime()

    assert "install-runtime-dependencies" in str(error_info.value)


def test_validate_runtime_redacts_and_does_not_cache_failure(monkeypatch, tmp_path):
    bridge_root = tmp_path / "tools" / "hyperframes_bridge"
    bridge_script = _write_bridge_runtime(bridge_root)
    calls = 0

    def fake_run(command, **_kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(
            command,
            1 if calls == 1 else 0,
            "",
            "Authorization: Bearer bridge-secret\n" + ("x" * 5000) if calls == 1 else "",
        )

    monkeypatch.setattr(shutil, "which", lambda _executable: "node-resolved")
    monkeypatch.setattr(subprocess, "run", fake_run)
    renderer = HyperFramesRenderer(bridge_script=str(bridge_script))

    with pytest.raises(RuntimeError) as error_info:
        renderer.validate_runtime()
    assert "bridge-secret" not in str(error_info.value)
    assert "[truncated]" in str(error_info.value)

    renderer.validate_runtime()
    assert calls == 2


def test_render_public_entrypoint_cannot_bypass_runtime_validation(monkeypatch):
    renderer = HyperFramesRenderer()
    calls = 0

    def validate_runtime():
        nonlocal calls
        calls += 1

    monkeypatch.setattr(renderer, "validate_runtime", validate_runtime)
    monkeypatch.setattr(
        renderer,
        "_prepare_render_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("request stopped")),
    )

    with pytest.raises(RuntimeError, match="request stopped"):
        renderer.render("unused")

    assert calls == 1


@pytest.mark.asyncio
async def test_render_async_public_entrypoint_cannot_bypass_runtime_validation(monkeypatch):
    renderer = HyperFramesRenderer()
    calls = 0

    def validate_runtime():
        nonlocal calls
        calls += 1

    monkeypatch.setattr(renderer, "validate_runtime", validate_runtime)
    monkeypatch.setattr(
        renderer,
        "_prepare_render_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("request stopped")),
    )

    with pytest.raises(RuntimeError, match="request stopped"):
        await renderer.render_async("unused")

    assert calls == 1


def test_render_allows_compiled_project_without_manifest_when_output_path_is_explicit(
    monkeypatch,
    tmp_path,
):
    project_dir = tmp_path / "output" / "task-compiled" / "hyperframes"
    compositions_dir = project_dir / "compositions"
    compositions_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "index.html").write_text(
        "<!doctype html><title>compiled</title>",
        encoding="utf-8",
    )
    (compositions_dir / "captions.html").write_text(
        "<div data-composition-id='captions'></div>",
        encoding="utf-8",
    )

    bridge_script = tmp_path / "render.mjs"
    bridge_script.write_text("// bridge placeholder", encoding="utf-8")
    explicit_output = project_dir / "renders" / "task-compiled.mp4"

    renderer = HyperFramesRenderer(
        bridge_script=str(bridge_script),
        template_root=str(tmp_path / "missing-templates"),
    )
    _stub_successful_bridge(monkeypatch, renderer, explicit_output)

    output_path = renderer.render(
        str(project_dir),
        output_path=str(explicit_output),
    )

    assert output_path == str(explicit_output)


def test_render_rejects_video_without_audio_stream(monkeypatch, tmp_path):
    project_dir = tmp_path / "output" / "task-7" / "hyperframes"
    project_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(project_dir, task_id="task-7")

    template_root = tmp_path / "templates"
    _write_template(template_root)

    bridge_script = tmp_path / "render.mjs"
    bridge_script.write_text("// bridge placeholder", encoding="utf-8")

    renderer = HyperFramesRenderer(
        bridge_script=str(bridge_script),
        template_root=str(template_root),
    )
    _stub_successful_bridge(
        monkeypatch,
        renderer,
        project_dir / "renders" / "task-7.mp4",
    )
    monkeypatch.setattr(
        renderer,
        "_probe_output",
        lambda output_path: {
            "has_video": True,
            "has_audio": False,
            "duration": 8.0,
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
        },
    )

    with pytest.raises(RuntimeError, match="audio stream"):
        renderer.render(
            str(project_dir),
            output_path=str(project_dir / "renders" / "task-7.mp4"),
            width=1080,
            height=1920,
            fps=30,
            expected_duration=12.5,
            expect_audio=True,
        )


def test_render_rejects_invalid_template_id_before_joining_paths(tmp_path):
    project_dir = tmp_path / "output" / "task-6" / "hyperframes"
    project_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(project_dir)

    manifest_path = project_dir / "data" / "render_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["template_id"] = "../escape"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    renderer = HyperFramesRenderer(template_root=str(tmp_path / "templates"))

    with pytest.raises(ValueError, match="template_id"):
        renderer.render(str(project_dir))


def test_render_rejects_invalid_task_id_before_deriving_default_output_name(tmp_path):
    project_dir = tmp_path / "output" / "task-6" / "hyperframes"
    project_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(project_dir, task_id="bad/name")

    template_root = tmp_path / "templates"
    _write_template(template_root)

    renderer = HyperFramesRenderer(template_root=str(template_root))

    with pytest.raises(ValueError, match="task_id"):
        renderer.render(str(project_dir))


def test_render_rejects_empty_template_id(tmp_path):
    project_dir = tmp_path / "output" / "task-6" / "hyperframes"
    project_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(project_dir)

    manifest_path = project_dir / "data" / "render_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["template_id"] = "   "
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    renderer = HyperFramesRenderer(template_root=str(tmp_path / "templates"))

    with pytest.raises(ValueError, match="template_id"):
        renderer.render(str(project_dir))


def test_render_request_forwards_fps_to_bridge(tmp_path):
    project_dir = tmp_path / "output" / "task-fps" / "hyperframes"
    compositions_dir = project_dir / "compositions"
    compositions_dir.mkdir(parents=True)
    _write_manifest(project_dir, task_id="task-fps")
    (project_dir / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (compositions_dir / "captions.html").write_text("<div></div>", encoding="utf-8")

    renderer = HyperFramesRenderer()
    request = renderer._prepare_render_request(
        str(project_dir),
        output_path=str(project_dir / "renders" / "task-fps.mp4"),
        width=1280,
        height=720,
        fps=24,
        expected_duration=5.0,
        expect_audio=False,
    )

    assert request.command[-2:] == ("--fps", "24")


@pytest.mark.parametrize("fps", [0, -1, 121, 23.5, True])
def test_render_rejects_invalid_fps_before_launch(tmp_path, fps):
    renderer = HyperFramesRenderer()

    with pytest.raises(ValueError, match="fps"):
        renderer.render(str(tmp_path), fps=fps)


def test_render_rejects_remote_executable_dependencies(tmp_path):
    project_dir = tmp_path / "output" / "task-remote" / "hyperframes"
    compositions_dir = project_dir / "compositions"
    compositions_dir.mkdir(parents=True)
    _write_manifest(project_dir, task_id="task-remote")
    (project_dir / "index.html").write_text(
        '<!doctype html><script src="https://example.invalid/runtime.js"></script>',
        encoding="utf-8",
    )
    (compositions_dir / "captions.html").write_text("<div></div>", encoding="utf-8")

    renderer = HyperFramesRenderer()

    with pytest.raises(RuntimeError, match="remote origins"):
        renderer.render(str(project_dir))


def test_render_timeout_terminates_bridge_and_reports_log_paths(tmp_path):
    project_dir = tmp_path / "output" / "task-timeout" / "hyperframes"
    compositions_dir = project_dir / "compositions"
    compositions_dir.mkdir(parents=True)
    _write_manifest(project_dir, task_id="task-timeout")
    (project_dir / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (compositions_dir / "captions.html").write_text("<div></div>", encoding="utf-8")
    bridge_script = tmp_path / "slow_bridge.py"
    bridge_script.write_text(
        "import sys, time\nprint('bridge-started', file=sys.stderr, flush=True)\ntime.sleep(30)\n",
        encoding="utf-8",
    )
    renderer = HyperFramesRenderer(
        node_executable=sys.executable,
        bridge_script=str(bridge_script),
        render_timeout_seconds=0.2,
    )
    renderer._runtime_validated = True

    with pytest.raises(RuntimeError, match=r"timed out.*Logs"):
        renderer.render(
            str(project_dir),
            output_path=str(project_dir / "renders" / "task-timeout.mp4"),
        )


def test_probe_output_reports_fractional_frame_rate(monkeypatch, tmp_path):
    output_path = tmp_path / "video.mp4"
    output_path.write_bytes(b"video")
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "width": 1280,
                "height": 720,
                "avg_frame_rate": "24000/1001",
            }
        ],
        "format": {"duration": "5.0"},
    }

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )
    probe = HyperFramesRenderer()._probe_output(str(output_path))

    assert probe["fps"] == pytest.approx(23.976, abs=0.001)


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
    monkeypatch.setattr(service_module, "AssetBasedPipeline", DummyPipeline)

    core = PixelleVideoCore()

    await core.initialize()

    assert isinstance(core.alignment_service, AlignmentService)
    assert isinstance(core.audio_edit_service, AudioEditService)
    assert isinstance(core.hyperframes_project_service, HyperFramesProjectService)
    assert isinstance(core.hyperframes_renderer, HyperFramesRenderer)


@pytest.mark.asyncio
async def test_initialize_wires_hyperframes_project_service_to_pixelle_root(monkeypatch, tmp_path):
    class DummyService:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class DummyPipeline:
        def __init__(self, core):
            self.core = core

    pixelle_root = tmp_path / "pixelle-root"
    pixelle_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(pixelle_root))
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
    monkeypatch.setattr(service_module, "AssetBasedPipeline", DummyPipeline)

    previous_cwd = Path.cwd()
    os.chdir(str(tmp_path))
    try:
        core = PixelleVideoCore()
        await core.initialize()
    finally:
        os.chdir(str(previous_cwd))

    expected_project_dir = pixelle_root / "output" / "task-demo" / "hyperframes"
    assert core.hyperframes_project_service.get_project_dir("task-demo") == expected_project_dir


def test_render_respects_use_gpu_false_from_constructor(monkeypatch, tmp_path):
    project_dir = tmp_path / "output" / "task-gpu-false" / "hyperframes"
    compositions_dir = project_dir / "compositions"
    compositions_dir.mkdir(parents=True)
    _write_manifest(project_dir, task_id="task-gpu-false")
    (project_dir / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (compositions_dir / "captions.html").write_text("<div></div>", encoding="utf-8")

    renderer = HyperFramesRenderer(use_gpu=False)
    captured: dict[str, object] = {}
    expected_output = project_dir / "renders" / "task-gpu-false.mp4"
    _stub_successful_bridge(monkeypatch, renderer, expected_output, captured)

    renderer.render(str(project_dir))
    assert "--use-gpu" not in captured["command"]


def test_render_respects_environment_gpu_kill_switch(monkeypatch, tmp_path):
    project_dir = tmp_path / "output" / "task-gpu-env-false" / "hyperframes"
    compositions_dir = project_dir / "compositions"
    compositions_dir.mkdir(parents=True)
    _write_manifest(project_dir, task_id="task-gpu-env-false")
    (project_dir / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (compositions_dir / "captions.html").write_text("<div></div>", encoding="utf-8")
    monkeypatch.setenv("PIXELLE_HYPERFRAMES_USE_GPU", "false")

    renderer = HyperFramesRenderer()
    captured: dict[str, object] = {}
    expected_output = project_dir / "renders" / "task-gpu-env-false.mp4"
    _stub_successful_bridge(monkeypatch, renderer, expected_output, captured)

    renderer.render(str(project_dir))

    assert renderer.use_gpu is False
    assert "--use-gpu" not in captured["command"]


def test_render_use_gpu_param_overrides_constructor(monkeypatch, tmp_path):
    project_dir = tmp_path / "output" / "task-gpu-override" / "hyperframes"
    compositions_dir = project_dir / "compositions"
    compositions_dir.mkdir(parents=True)
    _write_manifest(project_dir, task_id="task-gpu-override")
    (project_dir / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (compositions_dir / "captions.html").write_text("<div></div>", encoding="utf-8")

    renderer = HyperFramesRenderer(use_gpu=False)
    captured: dict[str, object] = {}
    _stub_successful_bridge(
        monkeypatch,
        renderer,
        project_dir / "renders" / "task-gpu-override.mp4",
        captured,
    )

    renderer.render(str(project_dir), use_gpu=True)
    assert "--use-gpu" in captured["command"]
