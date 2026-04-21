# Selfhost Image Mode Staged Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically switch `StandardPipeline` into staged asset production for image-mode tasks when both TTS and media use selfhost ComfyUI workflows, so the GPU does not bounce between TTS and image models frame-by-frame.

**Architecture:** Keep `standard` as the only pipeline entry point. Add a small execution-mode resolver in `pixelle_video/pipelines/standard.py`, then branch `produce_assets()` into staged, RunningHub, or legacy serial processing. Reuse the existing frame-based storyboard model and the existing `FrameProcessor` step methods so only execution order and progress mapping change.

**Tech Stack:** Python 3.11, asyncio, dataclasses, ComfyKit workflow resolution, pytest

---

## File Map

- `pixelle_video/pipelines/standard.py`: add execution-mode resolution, staged asset-production helpers, and staged progress emission while preserving the existing RunningHub and serial paths.
- `tests/test_standard_pipeline_staged_mode.py`: focused tests for trigger detection, staged ordering, fail-fast behavior, progress monotonicity, and fallback behavior.

### Task 1: Add Execution-Mode Resolution for `StandardPipeline`

**Files:**
- Create: `tests/test_standard_pipeline_staged_mode.py`
- Modify: `pixelle_video/pipelines/standard.py`

- [ ] **Step 1: Write the failing execution-mode tests**

Create `tests/test_standard_pipeline_staged_mode.py` with this initial content:

```python
from types import SimpleNamespace

from pixelle_video.models.storyboard import StoryboardConfig
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


def _workflow_info(key: str) -> dict:
    source, name = key.split("/", 1)
    return {
        "name": name,
        "display_name": f"{name} - {source.title()}",
        "source": source,
        "path": f"workflows/{key}",
        "key": key,
    }


class _ResolverService:
    def __init__(self, defaults: dict[str, str]):
        self.defaults = defaults

    def _resolve_workflow(self, workflow=None, workflow_domain=None):
        key = workflow or self.defaults[workflow_domain or "tts"]
        return _workflow_info(key)


class _DummyCore:
    def __init__(self, *, tts_defaults=None, media_defaults=None):
        self.config = {}
        self.llm = object()
        self.video = object()
        self.frame_processor = SimpleNamespace()
        self.tts = _ResolverService(tts_defaults or {"tts": "selfhost/tts_edge.json"})
        self.media = _ResolverService(
            media_defaults
            or {
                "image": "selfhost/image_z_image_turbo.json",
                "video": "runninghub/video_wan2.1_fusionx.json",
            }
        )


def _build_ctx(
    *,
    frame_template: str = "1080x1920/image_default.html",
    tts_inference_mode: str = "comfyui",
    tts_workflow: str | None = None,
    media_workflow: str | None = None,
) -> PipelineContext:
    ctx = PipelineContext(input_text="topic", params={})
    ctx.config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        task_id="task-1",
        tts_inference_mode=tts_inference_mode,
        tts_workflow=tts_workflow,
        media_workflow=media_workflow,
        frame_template=frame_template,
    )
    return ctx


def test_resolve_asset_execution_mode_uses_staged_mode_for_default_selfhost_image_workflows():
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_ctx()

    execution_mode = pipeline._resolve_asset_execution_mode(ctx)

    assert execution_mode.template_type == "image"
    assert execution_mode.tts_workflow_key == "selfhost/tts_edge.json"
    assert execution_mode.media_workflow_key == "selfhost/image_z_image_turbo.json"
    assert execution_mode.media_domain == "image"
    assert execution_mode.is_runninghub is False
    assert execution_mode.use_staged_mode is True


def test_resolve_asset_execution_mode_disables_staged_mode_for_explicit_video_workflow():
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_ctx(media_workflow="selfhost/video_wan2.1_fusionx.json")

    execution_mode = pipeline._resolve_asset_execution_mode(ctx)

    assert execution_mode.template_type == "image"
    assert execution_mode.media_domain == "video"
    assert execution_mode.media_workflow_key == "selfhost/video_wan2.1_fusionx.json"
    assert execution_mode.use_staged_mode is False


def test_resolve_asset_execution_mode_disables_staged_mode_for_local_tts():
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_ctx(tts_inference_mode="local")

    execution_mode = pipeline._resolve_asset_execution_mode(ctx)

    assert execution_mode.tts_workflow_key is None
    assert execution_mode.use_staged_mode is False
```

- [ ] **Step 2: Run the execution-mode tests to verify they fail**

Run: `pytest tests/test_standard_pipeline_staged_mode.py -k "resolve_asset_execution_mode" -v`
Expected: FAIL with `AttributeError: 'StandardPipeline' object has no attribute '_resolve_asset_execution_mode'`.

- [ ] **Step 3: Add the minimal execution-mode resolver**

Update `pixelle_video/pipelines/standard.py`:

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Literal, List

from pixelle_video.config.workflow_defaults import infer_workflow_domain
```

Add this dataclass near the imports and before `StandardPipeline`:

```python
@dataclass(frozen=True)
class AssetExecutionMode:
    template_type: Literal["static", "image", "video"]
    tts_workflow_key: Optional[str]
    media_workflow_key: Optional[str]
    media_domain: Literal["static", "image", "video"]
    is_runninghub: bool
    use_staged_mode: bool
```

Add these helpers inside `StandardPipeline` before `produce_assets()`:

```python
    def _resolve_media_domain(
        self,
        config: StoryboardConfig,
    ) -> Literal["static", "image", "video"]:
        template_type = get_template_type(Path(config.frame_template).name)
        if template_type == "static":
            return "static"

        configured_domain = infer_workflow_domain(config.media_workflow)
        if configured_domain == "video":
            return "video"
        if configured_domain == "image":
            return "image"

        return template_type

    def _resolve_asset_execution_mode(self, ctx: PipelineContext) -> AssetExecutionMode:
        config = ctx.config
        template_type = get_template_type(Path(config.frame_template).name)
        media_domain = self._resolve_media_domain(config)

        tts_workflow_key = None
        if config.tts_inference_mode == "comfyui":
            tts_workflow_key = self.core.tts._resolve_workflow(
                workflow=config.tts_workflow,
            )["key"]

        media_workflow_key = None
        if media_domain != "static":
            media_workflow_key = self.core.media._resolve_workflow(
                workflow=config.media_workflow,
                workflow_domain=media_domain,
            )["key"]

        is_runninghub = any(
            key and key.startswith("runninghub/")
            for key in (tts_workflow_key, media_workflow_key)
        )
        use_staged_mode = (
            template_type == "image"
            and media_domain == "image"
            and config.tts_inference_mode == "comfyui"
            and bool(tts_workflow_key and tts_workflow_key.startswith("selfhost/"))
            and bool(media_workflow_key and media_workflow_key.startswith("selfhost/"))
        )

        return AssetExecutionMode(
            template_type=template_type,
            tts_workflow_key=tts_workflow_key,
            media_workflow_key=media_workflow_key,
            media_domain=media_domain,
            is_runninghub=is_runninghub,
            use_staged_mode=use_staged_mode,
        )
```

- [ ] **Step 4: Run the execution-mode tests to verify they pass**

Run: `pytest tests/test_standard_pipeline_staged_mode.py -k "resolve_asset_execution_mode" -v`
Expected: PASS for all three execution-mode tests.

- [ ] **Step 5: Commit the execution-mode resolver**

```bash
git add pixelle_video/pipelines/standard.py tests/test_standard_pipeline_staged_mode.py
git commit -m "feat: resolve standard pipeline asset execution mode"
```

### Task 2: Add Staged Selfhost Image Asset Production

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `tests/test_standard_pipeline_staged_mode.py`

- [ ] **Step 1: Extend the test file with staged order and fail-fast coverage**

Append this code to `tests/test_standard_pipeline_staged_mode.py`:

```python
import pytest

from pixelle_video.models.storyboard import Storyboard, StoryboardFrame


class _RecordingFrameProcessor:
    def __init__(self, *, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    async def _step_generate_audio(self, frame, config):
        self.calls.append(("audio", frame.index))
        if self.fail_on == ("audio", frame.index):
            raise RuntimeError(f"audio failed for frame {frame.index}")
        frame.audio_path = f"audio-{frame.index}.mp3"
        frame.duration = float(frame.index + 1)

    async def _step_generate_media(self, frame, config):
        self.calls.append(("media", frame.index))
        if self.fail_on == ("media", frame.index):
            raise RuntimeError(f"media failed for frame {frame.index}")
        frame.media_type = "image"
        frame.image_path = f"image-{frame.index}.png"

    async def _step_compose_frame(self, frame, storyboard, config):
        self.calls.append(("compose", frame.index))
        frame.composed_image_path = f"composed-{frame.index}.png"

    async def _step_create_video_segment(self, frame, config):
        self.calls.append(("segment", frame.index))
        frame.video_segment_path = f"segment-{frame.index}.mp4"


def _build_storyboard_ctx(**kwargs) -> PipelineContext:
    ctx = _build_ctx(**kwargs)
    ctx.storyboard = Storyboard(
        title="Demo",
        config=ctx.config,
        frames=[
            StoryboardFrame(index=0, narration="scene 1", image_prompt="prompt 1"),
            StoryboardFrame(index=1, narration="scene 2", image_prompt="prompt 2"),
        ],
    )
    return ctx


@pytest.mark.asyncio
async def test_produce_assets_runs_staged_selfhost_image_flow_in_phase_order():
    core = _DummyCore()
    core.frame_processor = _RecordingFrameProcessor()
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx()

    await pipeline.produce_assets(ctx)

    assert core.frame_processor.calls == [
        ("audio", 0),
        ("audio", 1),
        ("media", 0),
        ("media", 1),
        ("compose", 0),
        ("compose", 1),
        ("segment", 0),
        ("segment", 1),
    ]
    assert ctx.storyboard.total_duration == 3.0
    assert [frame.video_segment_path for frame in ctx.storyboard.frames] == [
        "segment-0.mp4",
        "segment-1.mp4",
    ]


@pytest.mark.asyncio
async def test_produce_assets_aborts_immediately_on_staged_image_failure():
    core = _DummyCore()
    core.frame_processor = _RecordingFrameProcessor(fail_on=("media", 1))
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx()

    with pytest.raises(RuntimeError, match="media failed for frame 1"):
        await pipeline.produce_assets(ctx)

    assert core.frame_processor.calls == [
        ("audio", 0),
        ("audio", 1),
        ("media", 0),
        ("media", 1),
    ]
    assert ctx.storyboard.frames[0].video_segment_path is None
    assert ctx.storyboard.frames[1].video_segment_path is None
```

- [ ] **Step 2: Run the staged-order tests to verify they fail**

Run: `pytest tests/test_standard_pipeline_staged_mode.py -k "staged_selfhost_image_flow or staged_image_failure" -v`
Expected: FAIL because `produce_assets()` still uses the existing frame-by-frame path and never calls the staged `audio -> audio -> media -> media -> compose -> compose -> segment -> segment` ordering.

- [ ] **Step 3: Add the staged branch and fail-fast execution order**

Update `pixelle_video/pipelines/standard.py` with these helpers:

```python
    async def _produce_assets_staged(
        self,
        ctx: PipelineContext,
    ) -> None:
        storyboard = ctx.storyboard
        config = ctx.config

        logger.info("Using staged selfhost image processing")

        for frame in storyboard.frames:
            await self.core.frame_processor._step_generate_audio(frame, config)

        for frame in storyboard.frames:
            await self.core.frame_processor._step_generate_media(frame, config)

        for frame in storyboard.frames:
            await self.core.frame_processor._step_compose_frame(
                frame,
                storyboard,
                config,
            )

        for frame in storyboard.frames:
            await self.core.frame_processor._step_create_video_segment(frame, config)
            storyboard.total_duration += frame.duration
```

Then change the top of `produce_assets()` to branch through `AssetExecutionMode`:

```python
        execution_mode = self._resolve_asset_execution_mode(ctx)

        from pixelle_video.config import config_manager
        runninghub_concurrent_limit = config_manager.config.comfyui.runninghub_concurrent_limit or 1

        if execution_mode.use_staged_mode:
            await self._produce_assets_staged(ctx)
            logger.info(
                f"All frames processed in staged mode (total duration: {storyboard.total_duration:.2f}s)"
            )
            return

        if execution_mode.is_runninghub and runninghub_concurrent_limit > 1:
            logger.info(
                f"Using parallel processing for RunningHub workflows (max {runninghub_concurrent_limit} concurrent)"
            )
```

Leave the rest of the existing RunningHub and serial frame-processing logic unchanged for this task. Let exceptions from `_step_generate_audio()` and `_step_generate_media()` bubble so failure stays fail-fast.

- [ ] **Step 4: Run the staged-order tests to verify they pass**

Run: `pytest tests/test_standard_pipeline_staged_mode.py -k "staged_selfhost_image_flow or staged_image_failure" -v`
Expected: PASS for both staged-order tests.

- [ ] **Step 5: Commit the staged asset-production branch**

```bash
git add pixelle_video/pipelines/standard.py tests/test_standard_pipeline_staged_mode.py
git commit -m "feat: stage selfhost image asset production"
```

### Task 3: Add Staged Progress Mapping and Fallback Regression Coverage

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `tests/test_standard_pipeline_staged_mode.py`

- [ ] **Step 1: Extend the test file with progress and fallback regressions**

Append this code to `tests/test_standard_pipeline_staged_mode.py`:

```python
from pixelle_video.config import config_manager
from pixelle_video.models.progress import ProgressEvent


class _CallableFrameProcessor(_RecordingFrameProcessor):
    def __init__(self):
        super().__init__()
        self.invocations = []

    async def __call__(
        self,
        frame,
        storyboard,
        config,
        total_frames=1,
        progress_callback=None,
    ):
        self.invocations.append(frame.index)
        if progress_callback:
            progress_callback(
                ProgressEvent(
                    event_type="frame_step",
                    progress=0.0,
                    frame_current=frame.index + 1,
                    frame_total=total_frames,
                    step=1,
                    action="audio",
                )
            )
        frame.duration = 1.0
        frame.video_segment_path = f"legacy-{frame.index}.mp4"
        return frame


@pytest.mark.asyncio
async def test_produce_assets_emits_monotonic_staged_progress():
    core = _DummyCore()
    core.frame_processor = _RecordingFrameProcessor()
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx()
    events = []
    ctx.progress_callback = events.append

    await pipeline.produce_assets(ctx)

    frame_events = [event for event in events if event.event_type == "frame_step"]
    assert [(event.step, event.frame_current) for event in frame_events] == [
        (1, 1),
        (1, 2),
        (2, 1),
        (2, 2),
        (3, 1),
        (3, 2),
        (4, 1),
        (4, 2),
    ]
    assert [event.progress for event in frame_events] == sorted(
        event.progress for event in frame_events
    )
    assert frame_events[-1].progress == pytest.approx(0.80)


@pytest.mark.asyncio
async def test_produce_assets_keeps_callable_frame_processor_path_for_runninghub(monkeypatch):
    core = _DummyCore(
        tts_defaults={"tts": "runninghub/tts_edge.json"},
        media_defaults={
            "image": "runninghub/image_flux.json",
            "video": "runninghub/video_wan2.1_fusionx.json",
        },
    )
    core.frame_processor = _CallableFrameProcessor()
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx()
    monkeypatch.setattr(config_manager.config.comfyui, "runninghub_concurrent_limit", 1)

    await pipeline.produce_assets(ctx)

    assert core.frame_processor.invocations == [0, 1]
    assert [frame.video_segment_path for frame in ctx.storyboard.frames] == [
        "legacy-0.mp4",
        "legacy-1.mp4",
    ]
```

- [ ] **Step 2: Run the progress and fallback tests to verify they fail**

Run: `pytest tests/test_standard_pipeline_staged_mode.py -k "monotonic_staged_progress or callable_frame_processor_path_for_runninghub" -v`
Expected: FAIL because staged mode does not yet emit direct progress events, and the branch selection still needs to use the resolved execution mode everywhere.

- [ ] **Step 3: Implement staged progress emission and fully wire fallback branching through the resolved execution mode**

Add these helpers to `pixelle_video/pipelines/standard.py`:

```python
    def _stage_progress(
        self,
        stage_start: float,
        stage_end: float,
        frame_current: int,
        frame_total: int,
    ) -> float:
        if frame_total <= 0:
            return stage_end
        frame_fraction = frame_current / frame_total
        return stage_start + ((stage_end - stage_start) * frame_fraction)

    def _report_staged_frame_progress(
        self,
        callback,
        *,
        stage_start: float,
        stage_end: float,
        frame_current: int,
        frame_total: int,
        step: int,
        action: str,
    ) -> None:
        self._report_progress(
            callback,
            "frame_step",
            self._stage_progress(stage_start, stage_end, frame_current, frame_total),
            frame_current=frame_current,
            frame_total=frame_total,
            step=step,
            action=action,
        )
```

Update `_produce_assets_staged()` to emit progress directly while reusing the per-step generation helpers:

```python
    async def _produce_assets_staged(
        self,
        ctx: PipelineContext,
    ) -> None:
        storyboard = ctx.storyboard
        config = ctx.config
        total_frames = len(storyboard.frames)

        logger.info("Using staged selfhost image processing")

        for frame in storyboard.frames:
            self._report_staged_frame_progress(
                ctx.progress_callback,
                stage_start=0.20,
                stage_end=0.35,
                frame_current=frame.index + 1,
                frame_total=total_frames,
                step=1,
                action="audio",
            )
            await self.core.frame_processor._step_generate_audio(frame, config)

        for frame in storyboard.frames:
            self._report_staged_frame_progress(
                ctx.progress_callback,
                stage_start=0.35,
                stage_end=0.50,
                frame_current=frame.index + 1,
                frame_total=total_frames,
                step=2,
                action="media",
            )
            await self.core.frame_processor._step_generate_media(frame, config)

        for frame in storyboard.frames:
            self._report_staged_frame_progress(
                ctx.progress_callback,
                stage_start=0.50,
                stage_end=0.65,
                frame_current=frame.index + 1,
                frame_total=total_frames,
                step=3,
                action="compose",
            )
            await self.core.frame_processor._step_compose_frame(
                frame,
                storyboard,
                config,
            )

        for frame in storyboard.frames:
            self._report_staged_frame_progress(
                ctx.progress_callback,
                stage_start=0.65,
                stage_end=0.80,
                frame_current=frame.index + 1,
                frame_total=total_frames,
                step=4,
                action="video",
            )
            await self.core.frame_processor._step_create_video_segment(frame, config)
            storyboard.total_duration += frame.duration
```

Finally, keep the existing RunningHub and serial logic but use `execution_mode.is_runninghub` instead of the old raw `config.tts_workflow.startswith("runninghub/")` check.

- [ ] **Step 4: Run the full staged-mode test file**

Run: `pytest tests/test_standard_pipeline_staged_mode.py -v`
Expected: PASS for the execution-mode, staged-order, fail-fast, progress, and RunningHub fallback tests.

- [ ] **Step 5: Commit the staged progress and regression coverage**

```bash
git add pixelle_video/pipelines/standard.py tests/test_standard_pipeline_staged_mode.py
git commit -m "test: cover staged pipeline progress and fallbacks"
```
