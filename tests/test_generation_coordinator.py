import asyncio
from types import SimpleNamespace

import pytest

from pixelle_video.service import PixelleVideoCore
from pixelle_video.services.generation_coordinator import (
    GenerationCoordinator,
    build_generation_fingerprint,
)


def test_generation_fingerprint_ignores_runtime_only_fields():
    first = build_generation_fingerprint(
        text="demo",
        pipeline="standard",
        params={
            "storyboard_mode": "smart",
            "storyboard_count_mode": "manual",
            "storyboard_scene_count": 5,
            "request_id": "req-one",
            "session_id": "sess-one",
            "api_task_id": "api-one",
            "progress_callback": lambda _event: None,
            "title": None,
            "template_params": {"accent": "#fff", "unused": None},
        },
    )
    second = build_generation_fingerprint(
        text="demo",
        pipeline="standard",
        params={
            "template_params": {"unused": None, "accent": "#fff"},
            "storyboard_mode": "smart",
            "storyboard_count_mode": "manual",
            "storyboard_scene_count": 5,
            "request_id": "req-two",
            "session_id": "sess-two",
            "api_task_id": "api-two",
            "progress_callback": lambda _event: None,
        },
    )
    changed = build_generation_fingerprint(
        text="demo",
        pipeline="standard",
        params={
            "storyboard_mode": "smart",
            "storyboard_count_mode": "manual",
            "storyboard_scene_count": 6,
            "template_params": {"accent": "#fff"},
        },
    )

    assert first == second
    assert first != changed


@pytest.mark.asyncio
async def test_core_generate_video_reuses_identical_inflight_generation():
    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowPipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            started.set()
            await release.wait()
            return SimpleNamespace(text=text, kwargs=kwargs, marker=object())

    core = PixelleVideoCore()
    pipeline = _SlowPipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    first = asyncio.create_task(
        core.generate_video(
            text="demo",
            storyboard_mode="smart",
            storyboard_count_mode="manual",
            storyboard_scene_count=5,
            frame_template="1080x1920/image_default.html",
            request_id="req-one",
            session_id="sess-one",
            progress_callback=lambda _event: None,
        )
    )
    await started.wait()

    second = asyncio.create_task(
        core.generate_video(
            text="demo",
            storyboard_mode="smart",
            storyboard_count_mode="manual",
            storyboard_scene_count=5,
            frame_template="1080x1920/image_default.html",
            request_id="req-two",
            session_id="sess-two",
            progress_callback=lambda _event: None,
        )
    )
    await asyncio.sleep(0)

    assert pipeline.calls == 1

    release.set()
    first_result, second_result = await asyncio.gather(first, second)

    assert first_result is second_result
    assert pipeline.calls == 1


@pytest.mark.asyncio
async def test_core_generate_video_releases_fingerprint_after_completion():
    class _Pipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            return SimpleNamespace(text=text, call_number=self.calls)

    core = PixelleVideoCore()
    pipeline = _Pipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    first = await core.generate_video(text="demo", storyboard_mode="smart")
    second = await core.generate_video(text="demo", storyboard_mode="smart")

    assert first.call_number == 1
    assert second.call_number == 2
    assert pipeline.calls == 2


@pytest.mark.asyncio
async def test_core_generate_video_releases_fingerprint_after_failure():
    class _FlakyPipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary failure")
            return SimpleNamespace(text=text, call_number=self.calls)

    core = PixelleVideoCore()
    pipeline = _FlakyPipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    with pytest.raises(RuntimeError, match="temporary failure"):
        await core.generate_video(text="demo", storyboard_mode="smart")

    result = await core.generate_video(text="demo", storyboard_mode="smart")

    assert result.call_number == 2
    assert pipeline.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_params", [{"n_scenes": 5}, {"split_mode": "sentence"}])
async def test_core_generate_video_rejects_legacy_storyboard_fields_for_standard_pipeline(legacy_params):
    class _Pipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            return SimpleNamespace(text=text, kwargs=kwargs)

    core = PixelleVideoCore()
    pipeline = _Pipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    with pytest.raises(ValueError, match="legacy storyboard parameter"):
        await core.generate_video(text="demo", **legacy_params)

    assert pipeline.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_params",
    [
        {"mode": "bogus"},
        {"storyboard_mode": "bogus"},
        {"storyboard_count_mode": "bogus"},
        {"script_length_mode": "bogus"},
        {"script_length_mode": "custom", "script_target_words": 0},
    ],
)
async def test_core_generate_video_rejects_invalid_contract_enums_for_standard_pipeline(invalid_params):
    class _Pipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            return SimpleNamespace(text=text, kwargs=kwargs)

    core = PixelleVideoCore()
    pipeline = _Pipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    with pytest.raises(ValueError, match="unsupported|invalid"):
        await core.generate_video(text="demo", **invalid_params)

    assert pipeline.calls == 0


@pytest.mark.asyncio
async def test_core_generate_video_rejects_scene_count_above_contract_limit():
    class _Pipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            return SimpleNamespace(text=text, kwargs=kwargs)

    core = PixelleVideoCore()
    pipeline = _Pipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    with pytest.raises(ValueError, match="storyboard_scene_count"):
        await core.generate_video(
            text="demo",
            storyboard_count_mode="manual",
            storyboard_scene_count=31,
        )

    assert pipeline.calls == 0


@pytest.mark.asyncio
async def test_core_initialize_does_not_register_custom_template_pipeline_by_default(monkeypatch):
    import pixelle_video.service as service_module

    class _DummyService:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _DummyPipeline:
        def __init__(self, core):
            self.core = core

    monkeypatch.setattr(service_module, "LLMService", _DummyService)
    monkeypatch.setattr(service_module, "TTSService", _DummyService)
    monkeypatch.setattr(service_module, "MediaService", _DummyService)
    monkeypatch.setattr(service_module, "ImageAnalysisService", _DummyService)
    monkeypatch.setattr(service_module, "VideoAnalysisService", _DummyService)
    monkeypatch.setattr(service_module, "VideoService", _DummyService)
    monkeypatch.setattr(service_module, "FrameProcessor", _DummyService)
    monkeypatch.setattr(service_module, "PersistenceService", _DummyService)
    monkeypatch.setattr(service_module, "HistoryManager", _DummyService)
    monkeypatch.setattr(service_module, "AlignmentService", _DummyService)
    monkeypatch.setattr(service_module, "AudioEditService", _DummyService)
    monkeypatch.setattr(service_module, "HyperFramesProjectService", _DummyService)
    monkeypatch.setattr(service_module, "HyperFramesRenderer", _DummyService)
    monkeypatch.setattr(service_module, "StandardPipeline", _DummyPipeline)
    monkeypatch.setattr(service_module, "AssetBasedPipeline", _DummyPipeline)

    core = PixelleVideoCore()
    await core.initialize()

    assert set(core.pipelines) == {"standard", "asset_based"}


@pytest.mark.asyncio
async def test_generation_coordinator_keeps_shared_task_after_owner_cancellation():
    coordinator = GenerationCoordinator()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "generated"

    owner = asyncio.create_task(coordinator.run("same-request", factory))
    await started.wait()
    duplicate = asyncio.create_task(coordinator.run("same-request", factory))
    await asyncio.sleep(0)

    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner

    assert calls == 1
    assert coordinator.inflight_count() == 1

    release.set()
    assert await duplicate == "generated"
    await asyncio.sleep(0)
    assert coordinator.inflight_count() == 0
