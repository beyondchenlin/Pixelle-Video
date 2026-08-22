from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from api.tasks.artifacts import LocalArtifactStore
from api.tasks.executors import TaskExecutorRegistry
from api.tasks.models import TaskProgress, TaskStatus, TaskType
from api.video.executor_factory import register_video_generation_executor
from api.video.task_submitter import TaskManagerVideoGenerationTaskSubmitter
from web.components import output_preview
from web.state import async_runtime
from web.state import session as web_session
from web.state.video_generation_client import (
    InProcessVideoGenerationClient,
    normalize_video_generation_task_id,
    read_video_generation_task_id,
    write_video_generation_task_id,
)


def test_process_runtime_is_not_collected_with_stale_browser_sessions(monkeypatch):
    class FakeRuntime:
        def __init__(self) -> None:
            self.closed = False

        def close(self, async_cleanup=None):
            self.closed = True
            return True

    process_runtime = FakeRuntime()
    stale_runtime = FakeRuntime()
    async_runtime._RUNTIMES.clear()
    async_runtime._RUNTIMES.update(
        {
            async_runtime.PROCESS_RUNTIME_KEY: async_runtime.ManagedAsyncRuntime(
                runtime=process_runtime
            ),
            "stale": async_runtime.ManagedAsyncRuntime(runtime=stale_runtime),
        }
    )
    monkeypatch.setattr(async_runtime, "session_exists", lambda _key: False)

    try:
        async_runtime._cleanup_stale_runtimes("current")
        assert async_runtime.PROCESS_RUNTIME_KEY in async_runtime._RUNTIMES
        assert "stale" not in async_runtime._RUNTIMES
        assert process_runtime.closed is False
        assert stale_runtime.closed is True
    finally:
        async_runtime._RUNTIMES.clear()


def test_process_runtime_never_inherits_streamlit_session_context(monkeypatch):
    attached = []
    fake_context = SimpleNamespace(session_id="browser-session")
    monkeypatch.setattr(
        async_runtime,
        "get_script_run_ctx",
        lambda suppress_warning=True: fake_context,
    )
    monkeypatch.setattr(
        async_runtime,
        "add_script_run_ctx",
        lambda thread, ctx=None: attached.append((thread, ctx)),
    )

    runtime = async_runtime.AsyncRuntime(
        "process-test",
        attach_streamlit_context=False,
    )
    try:
        assert runtime.run(asyncio.sleep(0, result=42)) == 42
    finally:
        runtime.close()

    assert attached == []


def test_process_runtime_is_shutdown_after_session_runtimes():
    close_order = []

    class FakeRuntime:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self, async_cleanup=None):
            close_order.append(self.name)
            return True

    async_runtime._RUNTIMES.clear()
    async_runtime._RUNTIMES.update(
        {
            async_runtime.PROCESS_RUNTIME_KEY: async_runtime.ManagedAsyncRuntime(
                runtime=FakeRuntime("process")
            ),
            "session": async_runtime.ManagedAsyncRuntime(runtime=FakeRuntime("session")),
        }
    )

    async_runtime.shutdown_all_async_runtimes()

    assert close_order == ["session", "process"]


@pytest.mark.asyncio
async def test_browser_session_cleanup_does_not_stop_process_task_resources(monkeypatch):
    events = []

    class Core:
        async def cleanup(self):
            events.append("session_core_cleanup")

    from pixelle_video.services.frame_html import HTMLFrameGenerator

    monkeypatch.setattr(
        HTMLFrameGenerator,
        "close_browser",
        lambda: asyncio.sleep(0, result=events.append("browser_close")),
    )
    web_session._PIXELLE_VIDEO_SESSIONS.clear()
    web_session._PIXELLE_VIDEO_SESSIONS["stale"] = web_session._PixelleVideoSessionState(
        pixelle_video=Core()
    )
    try:
        await web_session._cleanup_pixelle_video_session("stale")
        assert events == ["session_core_cleanup"]
    finally:
        web_session._PIXELLE_VIDEO_SESSIONS.clear()


def test_local_artifact_path_resolution_blocks_traversal_and_missing_files(tmp_path):
    store = LocalArtifactStore(output_root=tmp_path)
    artifact = tmp_path / "task" / "final.mp4"
    artifact.parent.mkdir()
    artifact.write_bytes(b"video")

    assert store.resolve_local_path("task/final.mp4") == artifact.resolve()
    assert store.resolve_local_path("../secret.txt") is None
    assert store.resolve_local_path("task/missing.mp4") is None


@pytest.mark.asyncio
async def test_video_executor_releases_task_owned_core_and_returns_ui_metadata(tmp_path):
    output = tmp_path / "generated.mp4"
    released = []

    class Core:
        async def generate_video(self, **_kwargs):
            output.write_bytes(b"video")
            return SimpleNamespace(
                video_path=str(output),
                duration=3.5,
                cover_path="cover.png",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                storyboard=SimpleNamespace(
                    title="Demo",
                    frames=[object(), object()],
                    config=SimpleNamespace(
                        canvas_width=1080,
                        canvas_height=1920,
                        frame_template="portrait.html",
                    ),
                ),
            )

    core = Core()
    registry = TaskExecutorRegistry()
    register_video_generation_executor(
        registry,
        core_provider=lambda: core,
        core_releaser=lambda value: released.append(value),
        artifact_store=LocalArtifactStore(output_root=tmp_path / "artifacts"),
    )

    result = await registry.execute(
        TaskType.VIDEO_GENERATION,
        task_id="task-id",
        request_params={"text": "demo"},
    )

    assert released == [core]
    assert result["title"] == "Demo"
    assert result["frame_count"] == 2
    assert result["canvas_width"] == 1080
    assert result["canvas_height"] == 1920


@pytest.mark.asyncio
async def test_video_executor_releases_task_owned_core_after_failure(tmp_path):
    released = []

    class Core:
        async def generate_video(self, **_kwargs):
            raise RuntimeError("generation failed")

    core = Core()
    registry = TaskExecutorRegistry()
    register_video_generation_executor(
        registry,
        core_provider=lambda: core,
        core_releaser=lambda value: released.append(value),
        artifact_store=LocalArtifactStore(output_root=tmp_path),
    )

    with pytest.raises(RuntimeError, match="generation failed"):
        await registry.execute(
            TaskType.VIDEO_GENERATION,
            task_id="task-id",
            request_params={"text": "demo"},
        )

    assert released == [core]


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_hide_generation_failure(tmp_path):
    class Core:
        async def generate_video(self, **_kwargs):
            raise ValueError("primary failure")

    async def failing_cleanup(_core):
        raise RuntimeError("cleanup failure")

    registry = TaskExecutorRegistry()
    register_video_generation_executor(
        registry,
        core_provider=Core,
        core_releaser=failing_cleanup,
        artifact_store=LocalArtifactStore(output_root=tmp_path),
    )

    with pytest.raises(ValueError, match="primary failure"):
        await registry.execute(
            TaskType.VIDEO_GENERATION,
            task_id="task-id",
            request_params={"text": "demo"},
        )


def test_task_id_round_trip_is_canonical_and_preserves_other_query_parameters():
    task_id = "0f32fbe0-6ac3-4bb0-a673-6f98deae3528"
    query_params = {"language": "zh_CN"}

    write_video_generation_task_id(query_params, task_id)

    assert read_video_generation_task_id(query_params) == task_id
    assert query_params["language"] == "zh_CN"
    assert normalize_video_generation_task_id(task_id.upper()) is None
    assert normalize_video_generation_task_id("../../secret") is None


def test_inprocess_video_client_uses_fingerprint_and_returns_persisted_snapshot():
    task_id = "0f32fbe0-6ac3-4bb0-a673-6f98deae3528"
    calls = []
    snapshot = SimpleNamespace(
        task_id=task_id,
        status=TaskStatus.RUNNING,
        progress=TaskProgress(percentage=25),
    )

    class Submitter:
        async def reserve_video_generation(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(task_id=task_id, created=True, reused_reason=None)

        async def get_video_generation_task(self, requested_task_id):
            assert requested_task_id == task_id
            return snapshot

    client = InProcessVideoGenerationClient(
        submitter=Submitter(),
        async_runner=asyncio.run,
    )

    submission = client.submit({"text": "demo", "request_id": "req-a"})

    assert submission.task_id == task_id
    assert len(calls[0]["generation_fingerprint"]) == 64
    assert calls[0]["request_params"]["generation_fingerprint"] == calls[0][
        "generation_fingerprint"
    ]
    assert client.get(task_id) is snapshot
    assert client.get("../../secret") is None


@pytest.mark.asyncio
async def test_task_submitter_returns_projection_without_request_parameters(tmp_path):
    task_id = "0f32fbe0-6ac3-4bb0-a673-6f98deae3528"
    artifact = tmp_path / task_id / "final.mp4"
    artifact.parent.mkdir()
    artifact.write_bytes(b"video")
    task = SimpleNamespace(
        task_id=task_id,
        task_type=TaskType.VIDEO_GENERATION,
        status=TaskStatus.COMPLETED,
        progress=TaskProgress(percentage=100),
        result={"storage_key": f"{task_id}/final.mp4"},
        request_params={"ref_audio": "private/path.wav"},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        started_at=None,
        completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    manager = SimpleNamespace(
        get_task=lambda _task_id: asyncio.sleep(0, result=task),
        registry=SimpleNamespace(
            artifact_store=LocalArtifactStore(output_root=tmp_path)
        ),
    )

    snapshot = await TaskManagerVideoGenerationTaskSubmitter(
        manager
    ).get_video_generation_task(task_id)

    assert snapshot.video_path == str(artifact.resolve())
    assert not hasattr(snapshot, "request_params")


def test_generation_request_omits_session_bound_progress_callback():
    request = output_preview.build_single_generation_request(
        {"text": "demo", "tts_inference_mode": "local"},
        progress_callback=None,
        session_state={},
    )

    assert "progress_callback" not in request


def test_task_monitor_projects_running_progress_after_refresh(monkeypatch):
    task_id = "0f32fbe0-6ac3-4bb0-a673-6f98deae3528"
    captured = {"progress": [], "captions": []}

    class FakeStreamlit:
        def __init__(self) -> None:
            self.session_state = {}
            self.query_params = {"generation_task": task_id, "language": "zh_CN"}

        def progress(self, value):
            captured["progress"].append(value)

        def caption(self, value):
            captured["captions"].append(value)

        def error(self, value):
            raise AssertionError(value)

    snapshot = SimpleNamespace(
        task_id=task_id,
        status=TaskStatus.RUNNING,
        progress=TaskProgress(
            percentage=42.8,
            message="rendering",
            event_type="rendering_ffmpeg_manifest",
        ),
    )
    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview, "tr", lambda key, **_kwargs: key)

    output_preview._render_video_task_monitor(
        SimpleNamespace(get=lambda _task_id: snapshot),
        task_id,
    )

    assert captured["progress"] == [42]
    assert len(captured["captions"]) == 1
    assert captured["captions"][0] != "rendering"
    assert output_preview.st.session_state[output_preview.SINGLE_VIDEO_GENERATING_KEY] is True
    assert output_preview.st.query_params["language"] == "zh_CN"


def test_missing_task_clears_only_generation_query_parameter(monkeypatch):
    task_id = "0f32fbe0-6ac3-4bb0-a673-6f98deae3528"
    errors = []

    class FakeStreamlit:
        def __init__(self) -> None:
            self.session_state = {}
            self.query_params = {"generation_task": task_id, "language": "zh_CN"}

        def error(self, value):
            errors.append(value)

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview, "tr", lambda key, **_kwargs: key)

    output_preview._render_video_task_monitor(
        SimpleNamespace(get=lambda _task_id: None),
        task_id,
    )

    assert errors == ["status.generation_task_not_found"]
    assert output_preview.st.query_params == {"language": "zh_CN"}
    assert output_preview.st.session_state[output_preview.SINGLE_VIDEO_GENERATING_KEY] is False


def test_single_output_renders_generation_before_workbench_and_gallery(monkeypatch):
    events = []
    monkeypatch.setattr(
        output_preview,
        "_render_generation_section",
        lambda *_args, **_kwargs: events.append("generation"),
    )
    monkeypatch.setattr(
        output_preview,
        "_render_layout_preview_workbench_section",
        lambda *_args, **_kwargs: events.append("workbench"),
    )
    monkeypatch.setattr(
        output_preview,
        "render_recent_video_gallery",
        lambda *_args, **_kwargs: events.append("gallery"),
    )

    output_preview._render_single_output_sections(object(), {"text": "demo"})

    assert events == ["generation", "workbench", "gallery"]


def test_generation_button_submits_background_task_and_persists_task_id(monkeypatch):
    task_id = "0f32fbe0-6ac3-4bb0-a673-6f98deae3528"
    captured = {"requests": []}

    class RerunSignal(BaseException):
        pass

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                output_preview.SINGLE_VIDEO_HANDLED_TASK_KEY: task_id,
            }
            self.query_params = {"language": "zh_CN"}

        def container(self, **_kwargs):
            return Context()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def error(self, value):
            raise AssertionError(value)

        def button(self, *_args, **kwargs):
            assert kwargs["disabled"] is False
            return True

    class Client:
        def get(self, _task_id):
            return None

        def submit(self, request):
            captured["requests"].append(request)
            return SimpleNamespace(task_id=task_id)

    core = SimpleNamespace(generate_video=lambda **_kwargs: pytest.fail("direct call"))
    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **_kwargs: key)
    monkeypatch.setattr(
        output_preview,
        "resolve_video_generation_client",
        lambda _core: Client(),
    )
    monkeypatch.setattr(
        output_preview,
        "safe_rerun",
        lambda: (_ for _ in ()).throw(RerunSignal()),
    )

    with pytest.raises(RerunSignal):
        output_preview._render_generation_section(
            core,
            {"text": "demo", "tts_inference_mode": "local"},
        )

    assert len(captured["requests"]) == 1
    assert "progress_callback" not in captured["requests"][0]
    assert output_preview.st.query_params == {
        "language": "zh_CN",
        "generation_task": task_id,
    }
    assert output_preview.SINGLE_VIDEO_HANDLED_TASK_KEY not in output_preview.st.session_state


def test_generation_button_stays_enabled_for_text_visual_anchor_without_reference(monkeypatch):
    errors = []

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {}
            self.query_params = {}

        def container(self, **_kwargs):
            return Context()

        def markdown(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def error(self, value):
            errors.append(value)

        def button(self, *_args, **kwargs):
            assert kwargs["disabled"] is False
            return False

    class Client:
        def get(self, _task_id):
            return None

        def submit(self, _request):
            pytest.fail("button was not clicked")

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())
    monkeypatch.setattr(output_preview.config_manager, "validate", lambda: True)
    monkeypatch.setattr(output_preview, "tr", lambda key, **_kwargs: key)
    monkeypatch.setattr(
        output_preview,
        "resolve_video_generation_client",
        lambda _core: Client(),
    )

    output_preview._render_generation_section(
        object(),
        {
            "text": "demo",
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
        },
    )

    assert errors == []
