# Render Backend Manifest Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved three-backend render architecture: `legacy`, `hyperframes_compiled`, and `ffmpeg_manifest`, with shared template visual assets, clip-level element motion assets, and manifest-driven execution.

**Architecture:** Add a shared asset materialization layer before final rendering. Extend `RenderManifest` so visual clips can carry template and element-motion metadata, then route final output through a capability resolver into `legacy`, `hyperframes_compiled`, or `ffmpeg_manifest`.

**Tech Stack:** Python dataclasses, Pydantic config, Streamlit UI, Playwright HTML screenshots, FFmpeg via existing `VideoService`, pytest.

---

## Execution Constraints

- Do not use `git worktree`; this repository's `AGENTS.md` forbids worktree-based isolation.
- Before each task, run `git status --short` and only stage the files named in that task.
- Each task below is one atomic commit. Push immediately after each commit unless the user explicitly says not to.
- Existing dirty files outside the task are user or prior-session changes. Do not revert them.
- Run the task's targeted tests before committing. If unrelated dirty tests prevent a clean run, record the exact failure and continue only after confirming the failure is unrelated to the task's files.

## File Structure

- `pixelle_video/render_backend.py`  
  Owns supported final render backend identifiers.

- `pixelle_video/models/render_package.py`  
  Owns `RenderManifest`, `VisualClip`, and clip-level render metadata.

- `pixelle_video/models/render_execution_plan.py`  
  New model for requested/effective backend, fallback reason, artifacts, and diagnostics.

- `pixelle_video/models/template_visual_asset.py`  
  New model for HTML template materialization outputs and template capability summaries.

- `pixelle_video/services/template_visual_materializer.py`  
  New service wrapping `HTMLFrameGenerator` and text policy handling.

- `pixelle_video/services/element_motion_materializer.py`  
  New service connecting `ElementSegmentationService` and `PythonElementAnimationRenderer` to frame/clip artifacts.

- `pixelle_video/services/render_capability_resolver.py`  
  New service resolving requested backend to effective backend.

- `pixelle_video/services/ffmpeg_manifest_renderer.py`  
  New final renderer for simple manifest-driven FFmpeg composition.

- `pixelle_video/pipelines/standard.py`  
  Orchestrates materializers, backend resolution, manifest creation, and post-production routing.

- `pixelle_video/services/frame_processor.py`  
  Uses the template visual materializer instead of directly owning all HTML template logic.

- `pixelle_video/services/hyperframes_project_service.py` and `pixelle_video/models/template_render_context.py`  
  Carry clip-level element animation manifests into compiled HyperFrames projects.

- `web/components/style_config.py`, `web/utils/render_backend_ui.py`, `web/i18n/locales/en_US.json`, `web/i18n/locales/zh_CN.json`  
  Expose and report the new backend and fallback metadata.

---

### Task 1: Add `ffmpeg_manifest` as a First-Class Render Backend

**Files:**
- Modify: `pixelle_video/render_backend.py`
- Modify: `pixelle_video/config/schema.py`
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/pipelines/storyboard_config.py`
- Modify: `web/components/style_config.py`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `web/i18n/locales/zh_CN.json`
- Test: `tests/test_render_backend_ui.py`
- Test: `tests/test_render_package_models.py`

- [ ] **Step 1: Write failing tests for backend support**

Add these assertions to `tests/test_render_backend_ui.py`:

```python
def test_render_backend_ui_includes_ffmpeg_manifest(monkeypatch):
    captured = {}

    class FakeStreamlit:
        def radio(self, label, options, *, index, horizontal, format_func, key, help=None):
            captured["options"] = options
            captured["formatted"] = [format_func(option) for option in options]
            captured["index"] = index
            return "ffmpeg_manifest"

        def caption(self, body):
            captured["caption"] = body

    fake_config = type(
        "ConfigManager",
        (),
        {
            "config": type(
                "Config",
                (),
                {"render": type("Render", (), {"backend": "ffmpeg_manifest"})()},
            )(),
        },
    )()

    monkeypatch.setattr(style_config, "st", FakeStreamlit())
    monkeypatch.setattr(style_config, "config_manager", fake_config)
    monkeypatch.setattr("web.components.style_config.tr", lambda key, **kwargs: key)

    selected = style_config.render_render_backend_selector()

    assert selected == "ffmpeg_manifest"
    assert captured["options"] == ["legacy", "hyperframes_compiled", "ffmpeg_manifest"]
    assert captured["formatted"][-1] == "render_backend.option.ffmpeg_manifest"
    assert captured["caption"] == "render_backend.caption.ffmpeg_manifest"
```

Add this test to `tests/test_render_package_models.py`:

```python
def test_storyboard_config_accepts_ffmpeg_manifest_backend():
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        render_backend="ffmpeg_manifest",
    )

    assert config.render_backend == "ffmpeg_manifest"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_render_backend_ui.py::test_render_backend_ui_includes_ffmpeg_manifest tests/test_render_package_models.py::test_storyboard_config_accepts_ffmpeg_manifest_backend -q
```

Expected: FAIL because `ffmpeg_manifest` is not in `SUPPORTED_RENDER_BACKENDS`.

- [ ] **Step 3: Implement backend constants and UI labels**

Update `pixelle_video/render_backend.py`:

```python
from typing import Final, Literal, cast

RenderBackend = Literal["legacy", "hyperframes_compiled", "ffmpeg_manifest"]

LEGACY_RENDER_BACKEND: Final[RenderBackend] = "legacy"
HYPERFRAMES_COMPILED_RENDER_BACKEND: Final[RenderBackend] = "hyperframes_compiled"
FFMPEG_MANIFEST_RENDER_BACKEND: Final[RenderBackend] = "ffmpeg_manifest"
DEFAULT_RENDER_BACKEND: Final[RenderBackend] = LEGACY_RENDER_BACKEND
SUPPORTED_RENDER_BACKENDS: Final[tuple[RenderBackend, ...]] = (
    LEGACY_RENDER_BACKEND,
    HYPERFRAMES_COMPILED_RENDER_BACKEND,
    FFMPEG_MANIFEST_RENDER_BACKEND,
)
```

Add i18n entries:

```json
"render_backend.option.ffmpeg_manifest": "FFmpeg Manifest",
"render_backend.caption.ffmpeg_manifest": "Uses a manifest-driven FFmpeg path for simple image, video, audio, ASS, and overlay composition."
```

For `zh_CN.json`:

```json
"render_backend.option.ffmpeg_manifest": "FFmpeg Manifest",
"render_backend.caption.ffmpeg_manifest": "使用 manifest 驱动的 FFmpeg 高速链路，适合简单图片、视频、音频、ASS 和 overlay 合成。"
```

- [ ] **Step 4: Run targeted tests**

Run:

```bash
pytest tests/test_render_backend_ui.py tests/test_render_package_models.py -q
```

Expected: PASS for backend-related tests. Existing unrelated failures caused by dirty files must be recorded with file names.

- [ ] **Step 5: Commit and push**

```bash
git add pixelle_video/render_backend.py pixelle_video/config/schema.py pixelle_video/models/storyboard.py pixelle_video/pipelines/storyboard_config.py web/components/style_config.py web/i18n/locales/en_US.json web/i18n/locales/zh_CN.json tests/test_render_backend_ui.py tests/test_render_package_models.py
git commit -m "feat: add ffmpeg manifest render backend option"
git push origin dev
```

---

### Task 2: Extend Render Models and Add `RenderExecutionPlan`

**Files:**
- Modify: `pixelle_video/models/render_package.py`
- Create: `pixelle_video/models/render_execution_plan.py`
- Test: `tests/test_render_package_models.py`
- Test: `tests/test_render_execution_plan.py`

- [ ] **Step 1: Write failing model tests**

Add to `tests/test_render_package_models.py`:

```python
def test_visual_clip_round_trips_template_and_motion_metadata():
    clip = VisualClip(
        id="clip-1",
        frame_index=0,
        start=0.0,
        end=2.0,
        media_path="frames/frame_000.png",
        media_type="image",
        source_kind="template_frame",
        media_role="final_frame",
        template_id="image_default",
        template_path="1080x1920/image_default.html",
        text_policy="caption_renderer",
        element_animation_manifest_path="element/frame_000.json",
        source_media_path="raw/frame_000.png",
        diagnostics={"template_has_text_slot": True},
    )

    restored = VisualClip.from_dict(clip.to_dict())

    assert restored.source_kind == "template_frame"
    assert restored.media_role == "final_frame"
    assert restored.template_id == "image_default"
    assert restored.element_animation_manifest_path == "element/frame_000.json"
    assert restored.diagnostics["template_has_text_slot"] is True
```

Create `tests/test_render_execution_plan.py`:

```python
from pixelle_video.models.render_execution_plan import (
    RenderExecutionArtifact,
    RenderExecutionPlan,
)


def test_render_execution_plan_round_trips_backend_and_artifacts():
    plan = RenderExecutionPlan(
        requested_backend="ffmpeg_manifest",
        effective_backend="legacy",
        fallback_reason="template requires browser prerender",
        template_materialization_mode="html_prerender",
        element_motion_mode="python_ffmpeg",
        subtitle_mode="ass",
        audio_strategy="master_track",
        artifacts=[
            RenderExecutionArtifact(
                role="template_frame",
                path="frames/frame_000.png",
                frame_index=0,
            )
        ],
        diagnostics={"ffmpeg_supported": False},
    )

    restored = RenderExecutionPlan.from_dict(plan.to_dict())

    assert restored.requested_backend == "ffmpeg_manifest"
    assert restored.effective_backend == "legacy"
    assert restored.fallback_reason == "template requires browser prerender"
    assert restored.artifacts[0].role == "template_frame"
    assert restored.diagnostics["ffmpeg_supported"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_render_package_models.py::test_visual_clip_round_trips_template_and_motion_metadata tests/test_render_execution_plan.py -q
```

Expected: FAIL because the new fields and model do not exist.

- [ ] **Step 3: Implement model changes**

Extend `VisualClip` in `pixelle_video/models/render_package.py`:

```python
@dataclass
class VisualClip:
    id: str
    frame_index: int
    start: float
    end: float
    media_path: str
    media_type: str
    track_index: int = 0
    source_kind: str = "raw_media"
    media_role: str = "foreground"
    template_id: Optional[str] = None
    template_path: Optional[str] = None
    text_policy: str = "caption_renderer"
    element_animation_manifest_path: Optional[str] = None
    source_media_path: Optional[str] = None
    diagnostics: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.start = float(self.start)
        self.end = float(self.end)
        self.track_index = int(self.track_index)
        self.diagnostics = _freeze_json_mapping(self.diagnostics)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["diagnostics"] = thaw_json_value(self.diagnostics)
        return data
```

Create `pixelle_video/models/render_execution_plan.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from pixelle_video.models.text_overlay import (
    FrozenJSONValue,
    freeze_json_value,
    thaw_json_value,
)


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, FrozenJSONValue]:
    frozen = freeze_json_value(dict(value or {}))
    if not isinstance(frozen, Mapping):
        raise TypeError("Expected a mapping")
    return frozen


@dataclass(frozen=True)
class RenderExecutionArtifact:
    role: str
    path: str
    frame_index: int | None = None
    diagnostics: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", _freeze_mapping(self.diagnostics))

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "path": self.path,
            "frame_index": self.frame_index,
            "diagnostics": thaw_json_value(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RenderExecutionArtifact":
        return cls(
            role=str(data["role"]),
            path=str(data["path"]),
            frame_index=(
                int(data["frame_index"]) if data.get("frame_index") is not None else None
            ),
            diagnostics=data.get("diagnostics", {}),
        )


@dataclass(frozen=True)
class RenderExecutionPlan:
    requested_backend: str
    effective_backend: str
    fallback_reason: str | None = None
    template_materialization_mode: str = "none"
    element_motion_mode: str = "disabled"
    subtitle_mode: str = "disabled"
    audio_strategy: str = "per_frame"
    artifacts: list[RenderExecutionArtifact] = field(default_factory=list)
    diagnostics: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", _freeze_mapping(self.diagnostics))

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_backend": self.requested_backend,
            "effective_backend": self.effective_backend,
            "fallback_reason": self.fallback_reason,
            "template_materialization_mode": self.template_materialization_mode,
            "element_motion_mode": self.element_motion_mode,
            "subtitle_mode": self.subtitle_mode,
            "audio_strategy": self.audio_strategy,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "diagnostics": thaw_json_value(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RenderExecutionPlan":
        return cls(
            requested_backend=str(data["requested_backend"]),
            effective_backend=str(data["effective_backend"]),
            fallback_reason=data.get("fallback_reason"),
            template_materialization_mode=str(
                data.get("template_materialization_mode", "none")
            ),
            element_motion_mode=str(data.get("element_motion_mode", "disabled")),
            subtitle_mode=str(data.get("subtitle_mode", "disabled")),
            audio_strategy=str(data.get("audio_strategy", "per_frame")),
            artifacts=[
                RenderExecutionArtifact.from_dict(item)
                for item in data.get("artifacts", [])
            ],
            diagnostics=data.get("diagnostics", {}),
        )
```

- [ ] **Step 4: Run model tests**

Run:

```bash
pytest tests/test_render_package_models.py::test_visual_clip_round_trips_template_and_motion_metadata tests/test_render_execution_plan.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit and push**

```bash
git add pixelle_video/models/render_package.py pixelle_video/models/render_execution_plan.py tests/test_render_package_models.py tests/test_render_execution_plan.py
git commit -m "feat: add render execution plan contract"
git push origin dev
```

---

### Task 3: Add Template Visual Materializer

**Files:**
- Create: `pixelle_video/models/template_visual_asset.py`
- Create: `pixelle_video/services/template_visual_materializer.py`
- Test: `tests/test_template_visual_materializer.py`

- [ ] **Step 1: Write failing materializer tests**

Create `tests/test_template_visual_materializer.py`:

```python
from pathlib import Path

import pytest

from pixelle_video.services.template_visual_materializer import (
    TemplateVisualMaterializer,
    resolve_template_body_text,
)


def test_resolve_template_body_text_defaults_to_caption_renderer():
    assert resolve_template_body_text("Narration", "caption_renderer") == ""
    assert resolve_template_body_text("Narration", "none") == ""
    assert resolve_template_body_text("Narration", "template_body") == "Narration"
    assert resolve_template_body_text("Narration", "explicit_both") == "Narration"


@pytest.mark.asyncio
async def test_template_visual_materializer_renders_html_with_text_policy(tmp_path, monkeypatch):
    calls = {}

    class FakeGenerator:
        width = 1080
        height = 1920

        def __init__(self, template_path):
            calls["template_path"] = template_path

        async def generate_frame(self, *, title, text, image, ext, output_path):
            calls["title"] = title
            calls["text"] = text
            calls["image"] = image
            calls["ext"] = dict(ext)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"png")
            return output_path

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        FakeGenerator,
    )

    materializer = TemplateVisualMaterializer()
    result = await materializer.materialize_frame(
        title="Demo",
        narration="Narration",
        media_path="raw.png",
        frame_index=0,
        template_path="templates/1080x1920/image_default.html",
        template_id="image_default",
        output_path=tmp_path / "frame.png",
        text_policy="caption_renderer",
        template_params={"accent": "#fff"},
    )

    assert result.path == str(tmp_path / "frame.png")
    assert result.text_policy == "caption_renderer"
    assert calls["text"] == ""
    assert calls["ext"] == {"index": 1, "accent": "#fff"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_template_visual_materializer.py -q
```

Expected: FAIL because the new module does not exist.

- [ ] **Step 3: Implement template asset model and service**

Create `pixelle_video/models/template_visual_asset.py`:

```python
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class TemplateVisualAsset:
    path: str
    frame_index: int
    template_id: str
    template_path: str
    width: int
    height: int
    media_path: str | None
    text_policy: str
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
```

Create `pixelle_video/services/template_visual_materializer.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pixelle_video.models.template_visual_asset import TemplateVisualAsset
from pixelle_video.services.frame_html import HTMLFrameGenerator

VALID_TEMPLATE_TEXT_POLICIES = {
    "caption_renderer",
    "template_body",
    "none",
    "explicit_both",
}


def resolve_template_body_text(narration: str, text_policy: str) -> str:
    if text_policy not in VALID_TEMPLATE_TEXT_POLICIES:
        raise ValueError(f"unsupported template text policy: {text_policy}")
    if text_policy in {"template_body", "explicit_both"}:
        return narration
    return ""


class TemplateVisualMaterializer:
    async def materialize_frame(
        self,
        *,
        title: str,
        narration: str,
        media_path: str | None,
        frame_index: int,
        template_path: str,
        template_id: str,
        output_path: str | Path,
        text_policy: str,
        template_params: Mapping[str, Any] | None = None,
    ) -> TemplateVisualAsset:
        generator = HTMLFrameGenerator(str(template_path))
        ext = {"index": int(frame_index) + 1}
        ext.update(dict(template_params or {}))
        resolved_output = str(output_path)
        rendered_path = await generator.generate_frame(
            title=title,
            text=resolve_template_body_text(narration, text_policy),
            image=media_path or "",
            ext=ext,
            output_path=resolved_output,
        )
        return TemplateVisualAsset(
            path=rendered_path,
            frame_index=int(frame_index),
            template_id=template_id,
            template_path=str(template_path),
            width=generator.width,
            height=generator.height,
            media_path=media_path,
            text_policy=text_policy,
            diagnostics={
                "template_params_count": len(ext) - 1,
            },
        )
```

- [ ] **Step 4: Run materializer tests**

Run:

```bash
pytest tests/test_template_visual_materializer.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit and push**

```bash
git add pixelle_video/models/template_visual_asset.py pixelle_video/services/template_visual_materializer.py tests/test_template_visual_materializer.py
git commit -m "feat: add template visual materializer"
git push origin dev
```

---

### Task 4: Route Frame Composition Through the Template Visual Materializer

**Files:**
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/services/frame_processor.py`
- Modify: `pixelle_video/services/persistence.py`
- Test: `tests/test_frame_processor_negative_prompt.py`
- Test: `tests/test_standard_pipeline_staged_mode.py`
- Test: `tests/test_template_visual_materializer.py`

- [ ] **Step 1: Write failing tests for text policy and frame fields**

Add to `tests/test_standard_pipeline_staged_mode.py`:

```python
@pytest.mark.asyncio
async def test_legacy_staged_compose_defaults_to_caption_renderer_text_policy(monkeypatch):
    core = _DummyCore()
    core.frame_processor = _RecordingFrameProcessor()
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx()
    ctx.config.template_text_policy = "caption_renderer"

    compose_calls = []

    async def fake_compose(frame, storyboard, config, *, body_text_override=None):
        compose_calls.append((frame.index, body_text_override))
        frame.composed_image_path = f"composed-{frame.index}.png"

    monkeypatch.setattr(core.frame_processor, "_step_compose_frame", fake_compose)

    await pipeline.produce_assets(ctx)

    assert compose_calls == [(0, ""), (1, "")]
```

Add to `tests/test_render_package_models.py`:

```python
def test_storyboard_config_defaults_template_text_policy_to_caption_renderer():
    config = StoryboardConfig(media_width=1080, media_height=1920)

    assert config.template_text_policy == "caption_renderer"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_standard_pipeline_staged_mode.py::test_legacy_staged_compose_defaults_to_caption_renderer_text_policy tests/test_render_package_models.py::test_storyboard_config_defaults_template_text_policy_to_caption_renderer -q
```

Expected: FAIL because `template_text_policy` is not defined.

- [ ] **Step 3: Add config and frame fields**

Add to `StoryboardConfig` in `pixelle_video/models/storyboard.py`:

```python
template_text_policy: str = "caption_renderer"
```

Add validation in `__post_init__`:

```python
if self.template_text_policy not in {
    "caption_renderer",
    "template_body",
    "none",
    "explicit_both",
}:
    raise ValueError(
        "template_text_policy must be one of "
        "['caption_renderer', 'template_body', 'none', 'explicit_both']"
    )
```

Add optional fields to `StoryboardFrame`:

```python
template_visual_path: Optional[str] = None
element_animation_manifest_path: Optional[str] = None
element_motion_video_path: Optional[str] = None
```

Persist `template_text_policy` in `pixelle_video/services/persistence.py` inside `_config_to_dict` and `_dict_to_config`.

- [ ] **Step 4: Use materializer in frame processor**

In `pixelle_video/services/frame_processor.py`, replace direct `HTMLFrameGenerator.generate_frame(...)` in `_compose_frame_html` with:

```python
from pathlib import Path

from pixelle_video.services.template_visual_materializer import (
    TemplateVisualMaterializer,
)

template_id = Path(template_path).stem
text_policy = getattr(config, "template_text_policy", "caption_renderer")
if body_text_override is not None:
    text_policy = "template_body" if body_text_override else "caption_renderer"

asset = await TemplateVisualMaterializer().materialize_frame(
    title=storyboard.title,
    narration=_resolve_body_text(
        frame.narration,
        None,
        punctuation_mode=config.caption_punctuation_mode,
    ),
    media_path=media_path,
    frame_index=frame.index,
    template_path=template_path,
    template_id=template_id,
    output_path=output_path,
    text_policy=text_policy,
    template_params=config.template_params or {},
)
frame.template_visual_path = asset.path
return asset.path
```

Keep `body_text_override` as a compatibility switch so existing HyperFrames shell-only calls keep passing an empty body.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
pytest tests/test_template_visual_materializer.py tests/test_frame_processor_negative_prompt.py tests/test_standard_pipeline_staged_mode.py::test_legacy_staged_compose_defaults_to_caption_renderer_text_policy tests/test_render_package_models.py::test_storyboard_config_defaults_template_text_policy_to_caption_renderer -q
```

Expected: PASS.

Commit:

```bash
git add pixelle_video/models/storyboard.py pixelle_video/services/frame_processor.py pixelle_video/services/persistence.py tests/test_frame_processor_negative_prompt.py tests/test_standard_pipeline_staged_mode.py tests/test_render_package_models.py
git commit -m "feat: route frame templates through visual materializer"
git push origin dev
```

---

### Task 5: Add Element Motion Materializer and Frame-Level Artifacts

**Files:**
- Create: `pixelle_video/services/element_motion_materializer.py`
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/services/frame_processor.py`
- Test: `tests/test_element_motion_materializer.py`
- Test: `tests/test_standard_pipeline_staged_mode.py`

- [ ] **Step 1: Write failing tests for element motion materialization**

Create `tests/test_element_motion_materializer.py`:

```python
from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.models.element_animation import (
    ElementAnimationBackground,
    ElementAnimationCanvas,
    ElementAnimationManifest,
    ElementAnimationRender,
    ElementAnimationSegmentation,
    ElementAnimationTimeline,
)
from pixelle_video.services.element_motion_materializer import ElementMotionMaterializer


@pytest.mark.asyncio
async def test_element_motion_materializer_writes_manifest_and_python_video(tmp_path):
    manifest = ElementAnimationManifest(
        source_image_path="frame.png",
        canvas=ElementAnimationCanvas(width=1080, height=1920),
        timeline=ElementAnimationTimeline(duration=2.0, fps=30),
        background=ElementAnimationBackground(
            mode="source_image_low_motion",
            image_path="frame.png",
        ),
        segmentation=ElementAnimationSegmentation(
            provider="test",
            workflow="segment.json",
            prompt=None,
            candidate_limit=1,
            selected_count=1,
        ),
        elements=[],
        render=ElementAnimationRender(backend="python_ffmpeg"),
    )

    class FakeSegmentation:
        async def segment_image(self, **kwargs):
            return manifest

    class FakeRenderer:
        def render_video(self, render_manifest, output_path):
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"video")
            return output_path

    materializer = ElementMotionMaterializer(
        segmentation_service=FakeSegmentation(),
        python_renderer=FakeRenderer(),
    )
    frame = SimpleNamespace(index=0, duration=2.0)

    result = await materializer.materialize_frame(
        frame=frame,
        source_image_path="frame.png",
        task_id="task-1",
        output_dir=tmp_path,
        width=1080,
        height=1920,
        fps=30,
        backend="python_ffmpeg",
        selected_count=1,
        candidate_limit=1,
        prompt=None,
        workflow="segment.json",
        intensity="medium",
    )

    assert Path(result.manifest_path).exists()
    assert result.motion_video_path is not None
    assert Path(result.motion_video_path).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_element_motion_materializer.py -q
```

Expected: FAIL because `ElementMotionMaterializer` does not exist.

- [ ] **Step 3: Implement materializer**

Create `pixelle_video/services/element_motion_materializer.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pixelle_video.models.element_animation import ElementAnimationManifest
from pixelle_video.services.element_animation_renderer import PythonElementAnimationRenderer


@dataclass(frozen=True)
class ElementMotionArtifact:
    manifest_path: str
    motion_video_path: str | None


class ElementMotionMaterializer:
    def __init__(self, *, segmentation_service: Any, python_renderer: Any | None = None):
        self.segmentation_service = segmentation_service
        self.python_renderer = python_renderer or PythonElementAnimationRenderer()

    async def materialize_frame(
        self,
        *,
        frame: Any,
        source_image_path: str,
        task_id: str,
        output_dir: str | Path,
        width: int,
        height: int,
        fps: int,
        backend: str,
        selected_count: int,
        candidate_limit: int,
        prompt: str | None,
        workflow: str,
        intensity: str,
        audio_path: str | None = None,
    ) -> ElementMotionArtifact:
        stable_dir = Path(output_dir) / "element_motion" / f"frame_{int(frame.index):03d}"
        stable_dir.mkdir(parents=True, exist_ok=True)
        duration = max(float(getattr(frame, "duration", 0.0) or 0.0), 0.1)
        manifest: ElementAnimationManifest = await self.segmentation_service.segment_image(
            image_path=source_image_path,
            task_id=task_id,
            frame_index=int(frame.index),
            output_dir=str(output_dir),
            width=int(width),
            height=int(height),
            duration=duration,
            fps=int(fps),
            selected_count=int(selected_count),
            candidate_limit=int(candidate_limit),
            prompt=prompt,
            workflow=workflow,
            backend=backend,
            intensity=intensity,
            audio_path=audio_path,
        )
        manifest_path = stable_dir / "element_animation_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        motion_video_path = None
        if backend == "python_ffmpeg":
            motion_video_path = str(stable_dir / "motion.mp4")
            self.python_renderer.render_video(manifest, motion_video_path)
        return ElementMotionArtifact(
            manifest_path=str(manifest_path),
            motion_video_path=motion_video_path,
        )
```

- [ ] **Step 4: Integrate into standard pipeline**

In `StandardPipeline.produce_assets`, after frame composition and before segment creation, call a helper:

```python
await self._materialize_element_motion_for_frame(ctx, frame)
```

Add helper:

```python
async def _materialize_element_motion_for_frame(self, ctx: PipelineContext, frame) -> None:
    config = ctx.config
    if not getattr(config, "element_animation_enabled", False):
        return
    source_image_path = frame.composed_image_path or frame.image_path
    if not source_image_path:
        return
    from pixelle_video.services.element_motion_materializer import ElementMotionMaterializer
    from pixelle_video.services.element_segmentation import ElementSegmentationService

    artifact = await ElementMotionMaterializer(
        segmentation_service=ElementSegmentationService(self.core),
    ).materialize_frame(
        frame=frame,
        source_image_path=source_image_path,
        task_id=ctx.task_id or config.task_id or "",
        output_dir=ctx.task_dir or Path(source_image_path).parent,
        width=config.media_width,
        height=config.media_height,
        fps=config.video_fps,
        backend=config.element_animation_backend,
        selected_count=config.element_animation_subject_count,
        candidate_limit=config.element_animation_candidate_limit,
        prompt=config.element_animation_prompt,
        workflow=config.element_animation_workflow,
        intensity=config.element_animation_intensity,
        audio_path=frame.audio_path,
    )
    frame.element_animation_manifest_path = artifact.manifest_path
    frame.element_motion_video_path = artifact.motion_video_path
```

In `FrameProcessor._step_create_video_segment`, add an early branch:

```python
if frame.element_motion_video_path:
    frame.video_segment_path = video_service.merge_audio_video(
        video=frame.element_motion_video_path,
        audio=frame.audio_path,
        output=output_path,
        replace_audio=True,
        audio_volume=1.0,
    )
    return
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
pytest tests/test_element_motion_materializer.py tests/test_element_animation_renderer.py tests/test_standard_pipeline_staged_mode.py -q
```

Expected: PASS for element motion tests and staged pipeline tests.

Commit:

```bash
git add pixelle_video/services/element_motion_materializer.py pixelle_video/models/storyboard.py pixelle_video/pipelines/standard.py pixelle_video/services/frame_processor.py tests/test_element_motion_materializer.py tests/test_standard_pipeline_staged_mode.py
git commit -m "feat: materialize element motion assets in standard pipeline"
git push origin dev
```

---

### Task 6: Carry Clip-Level Element Motion Into HyperFrames

**Files:**
- Modify: `pixelle_video/models/template_render_context.py`
- Modify: `pixelle_video/services/hyperframes_project_service.py`
- Modify: `pixelle_video/services/hyperframes_compiler.py`
- Test: `tests/test_hyperframes_project_service.py`
- Test: `tests/test_hyperframes_compiler.py`

- [ ] **Step 1: Write failing HyperFrames tests**

Add to `tests/test_hyperframes_project_service.py`:

```python
def test_write_project_materializes_clip_level_element_animation_manifest(tmp_path):
    element_manifest = tmp_path / "element_manifest.json"
    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    element_manifest.write_text(
        json.dumps(
            {
                "source_image_path": str(source),
                "canvas": {"width": 1080, "height": 1920},
                "timeline": {"duration": 1.0, "fps": 30},
                "background": {"mode": "source_image_low_motion", "image_path": str(source)},
                "segmentation": {
                    "provider": "test",
                    "workflow": "test.json",
                    "prompt": None,
                    "candidate_limit": 1,
                    "selected_count": 1,
                },
                "elements": [],
                "render": {"backend": "hyperframes_canvas"},
                "audio_path": None,
            }
        ),
        encoding="utf-8",
    )
    manifest = RenderManifest(
        task_id="task-clip-element",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        visual_clips=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0,
                end=1,
                media_path=str(source),
                media_type="image",
                element_animation_manifest_path=str(element_manifest),
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path / "out"))
    paths = service.write_project(manifest, template_params={})
    payload = json.loads(paths.manifest_path.read_text(encoding="utf-8"))

    assert payload["visual_clips"][0]["element_animation_manifest_path"].startswith(
        "data/element_animation/"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_hyperframes_project_service.py::test_write_project_materializes_clip_level_element_animation_manifest -q
```

Expected: FAIL because clip-level manifests are not materialized.

- [ ] **Step 3: Localize clip-level element manifests**

In `HyperFramesProjectService._materialize_project_assets`, update the visual clip loop:

```python
localized_element_path = self._materialize_element_animation_manifest(
    clip.element_animation_manifest_path,
    project_dir,
    manifest_name=f"element_animation_{clip.id}.json",
)
localized_visuals.append(
    replace(
        clip,
        media_path=materialized[target_group][source_name],
        element_animation_manifest_path=localized_element_path,
    )
)
```

Change `_materialize_element_animation_manifest` signature:

```python
def _materialize_element_animation_manifest(
    self,
    manifest_path: str | None,
    project_dir: Path,
    *,
    manifest_name: str = "element_animation_manifest.json",
) -> str | None:
```

Set target directory:

```python
target_manifest_path = data_dir / "element_animation" / manifest_name
target_manifest_path.parent.mkdir(parents=True, exist_ok=True)
return f"data/element_animation/{manifest_name}"
```

- [ ] **Step 4: Expose manifest path to compiled visual HTML**

In `HyperFramesCompiler._render_visuals`, add an escaped data attribute:

```python
element_manifest_attr = ""
if clip.element_animation_manifest_path:
    element_manifest_attr = (
        ' data-element-animation-manifest="'
        f'{escape(clip.element_animation_manifest_path, quote=True)}"'
        '"'
    )
```

Use it on the visual clip container:

```python
f'<div id="{escape(clip.id, quote=True)}" class="clip visual-clip" '
f'data-start="{clip.start}" '
f'data-duration="{duration}" data-track-index="{track_index}"'
f"{element_manifest_attr}>"
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
pytest tests/test_hyperframes_project_service.py tests/test_hyperframes_compiler.py -q
```

Expected: PASS for HyperFrames materialization and compiler tests.

Commit:

```bash
git add pixelle_video/models/template_render_context.py pixelle_video/services/hyperframes_project_service.py pixelle_video/services/hyperframes_compiler.py tests/test_hyperframes_project_service.py tests/test_hyperframes_compiler.py
git commit -m "feat: carry clip element motion into hyperframes projects"
git push origin dev
```

---

### Task 7: Add `FfmpegManifestRenderer`

**Files:**
- Create: `pixelle_video/services/ffmpeg_manifest_renderer.py`
- Test: `tests/test_ffmpeg_manifest_renderer.py`

- [ ] **Step 1: Write failing renderer tests**

Create `tests/test_ffmpeg_manifest_renderer.py`:

```python
from pathlib import Path

from pixelle_video.models.render_execution_plan import RenderExecutionPlan
from pixelle_video.models.render_package import RenderManifest, VisualClip
from pixelle_video.services.ffmpeg_manifest_renderer import FfmpegManifestRenderer


def test_ffmpeg_manifest_renderer_uses_single_image_fast_path(tmp_path):
    calls = []

    class FakeVideoService:
        def create_video_from_image(self, image, audio, output, fps=30):
            calls.append(("image", image, audio, output, fps))
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_bytes(b"video")
            return output

    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        master_audio_path=str(tmp_path / "master.wav"),
        visual_clips=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0,
                end=2,
                media_path=str(tmp_path / "frame.png"),
                media_type="image",
            )
        ],
    )
    Path(manifest.master_audio_path).write_bytes(b"audio")
    Path(manifest.visual_clips[0].media_path).write_bytes(b"png")

    renderer = FfmpegManifestRenderer(video_service=FakeVideoService())
    output = renderer.render(
        manifest=manifest,
        execution_plan=RenderExecutionPlan(
            requested_backend="ffmpeg_manifest",
            effective_backend="ffmpeg_manifest",
        ),
        output_path=str(tmp_path / "final.mp4"),
    )

    assert output == str(tmp_path / "final.mp4")
    assert calls == [
        (
            "image",
            str(tmp_path / "frame.png"),
            str(tmp_path / "master.wav"),
            str(tmp_path / "final.mp4"),
            30,
        )
    ]


def test_ffmpeg_manifest_renderer_extracts_clip_audio_for_multiple_images(tmp_path, monkeypatch):
    calls = []
    commands = []

    class FakeVideoService:
        def create_video_from_image(self, image, audio, output, fps=30):
            calls.append(("image", Path(image).name, Path(audio).name, Path(output).name))
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_bytes(b"segment")
            return output

        def concat_videos(self, videos, output, **kwargs):
            calls.append(("concat", [Path(item).name for item in videos], Path(output).name))
            Path(output).write_bytes(b"final")
            return output

    def fake_run(command, capture_output=None, text=None, check=None):
        commands.append(command)
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_bytes(b"audio")
        return type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr(
        "pixelle_video.services.ffmpeg_manifest_renderer.subprocess.run",
        fake_run,
    )

    master_audio = tmp_path / "master.wav"
    master_audio.write_bytes(b"audio")
    frames = [tmp_path / "frame0.png", tmp_path / "frame1.png"]
    for frame in frames:
        frame.write_bytes(b"png")

    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        master_audio_path=str(master_audio),
        visual_clips=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0,
                end=1.5,
                media_path=str(frames[0]),
                media_type="image",
            ),
            VisualClip(
                id="clip-2",
                frame_index=1,
                start=1.5,
                end=3.0,
                media_path=str(frames[1]),
                media_type="image",
            ),
        ],
    )

    renderer = FfmpegManifestRenderer(video_service=FakeVideoService())
    renderer.render(
        manifest=manifest,
        execution_plan=RenderExecutionPlan(
            requested_backend="ffmpeg_manifest",
            effective_backend="ffmpeg_manifest",
        ),
        output_path=str(tmp_path / "final.mp4"),
    )

    assert [command[command.index("-ss") + 1] for command in commands] == ["0", "1.5"]
    assert [command[command.index("-t") + 1] for command in commands] == ["1.5", "1.5"]
    assert calls[-1] == ("concat", ["segment_000.mp4", "segment_001.mp4"], "final.mp4")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_ffmpeg_manifest_renderer.py -q
```

Expected: FAIL because the renderer module does not exist.

- [ ] **Step 3: Implement renderer**

Create `pixelle_video/services/ffmpeg_manifest_renderer.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

from pixelle_video.models.render_execution_plan import RenderExecutionPlan
from pixelle_video.models.render_package import RenderManifest, VisualClip
from pixelle_video.services.video import VideoService


class FfmpegManifestRenderer:
    def __init__(self, *, video_service: VideoService | None = None):
        self.video_service = video_service or VideoService()

    def render(
        self,
        *,
        manifest: RenderManifest,
        execution_plan: RenderExecutionPlan,
        output_path: str,
        ass_path: str | None = None,
        bgm_path: str | None = None,
        bgm_volume: float = 0.2,
        bgm_mode: str = "loop",
    ) -> str:
        clips = list(manifest.visual_clips)
        if not clips:
            raise ValueError("ffmpeg_manifest requires at least one visual clip")
        if len(clips) == 1:
            rendered = self._render_single_clip(
                clips[0],
                manifest=manifest,
                output_path=output_path,
            )
        else:
            rendered = self._render_multiple_clips(
                clips,
                manifest=manifest,
                output_path=output_path,
                bgm_path=bgm_path,
                bgm_volume=bgm_volume,
                bgm_mode=bgm_mode,
            )
        if ass_path:
            burned_path = str(Path(output_path).with_name("final_text_burned.mp4"))
            return self.video_service.burn_ass_subtitles(rendered, ass_path, burned_path)
        return rendered

    def _render_single_clip(
        self,
        clip: VisualClip,
        *,
        manifest: RenderManifest,
        output_path: str,
    ) -> str:
        if not manifest.master_audio_path:
            raise ValueError("ffmpeg_manifest single clip path requires master audio")
        if clip.media_type == "image":
            return self.video_service.create_video_from_image(
                image=clip.media_path,
                audio=manifest.master_audio_path,
                output=output_path,
                fps=manifest.fps,
            )
        return self.video_service.merge_audio_video(
            video=clip.media_path,
            audio=manifest.master_audio_path,
            output=output_path,
            replace_audio=True,
            audio_volume=1.0,
        )

    def _render_multiple_clips(
        self,
        clips: list[VisualClip],
        *,
        manifest: RenderManifest,
        output_path: str,
        bgm_path: str | None,
        bgm_volume: float,
        bgm_mode: str,
    ) -> str:
        temp_dir = Path(output_path).with_suffix("")
        temp_dir.mkdir(parents=True, exist_ok=True)
        segment_paths: list[str] = []
        for index, clip in enumerate(clips):
            segment_path = str(temp_dir / f"segment_{index:03d}.mp4")
            clip_audio_path = self._extract_clip_audio(
                manifest.master_audio_path,
                temp_dir / f"audio_{index:03d}.wav",
                start=clip.start,
                end=clip.end,
            )
            if clip.media_type == "image":
                self.video_service.create_video_from_image(
                    image=clip.media_path,
                    audio=clip_audio_path,
                    output=segment_path,
                    fps=manifest.fps,
                )
            else:
                self.video_service.merge_audio_video(
                    video=clip.media_path,
                    audio=clip_audio_path,
                    output=segment_path,
                    replace_audio=True,
                    audio_volume=1.0,
                )
            segment_paths.append(segment_path)
        return self.video_service.concat_videos(
            segment_paths,
            output_path,
            bgm_path=bgm_path,
            bgm_volume=bgm_volume,
            bgm_mode=bgm_mode,
        )

    def _extract_clip_audio(
        self,
        master_audio_path: str | None,
        output_path: Path,
        *,
        start: float,
        end: float,
    ) -> str:
        if not master_audio_path:
            raise ValueError("ffmpeg_manifest multiple clip path requires master audio")
        duration = max(float(end) - float(start), 0.001)
        command = [
            "ffmpeg",
            "-y",
            "-ss",
            self._format_time(start),
            "-i",
            master_audio_path,
            "-t",
            self._format_time(duration),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"failed to extract clip audio: {result.stderr}")
        return str(output_path)

    @staticmethod
    def _format_time(value: float) -> str:
        return f"{max(float(value), 0.0):.3f}".rstrip("0").rstrip(".") or "0"
```

- [ ] **Step 4: Run renderer tests**

Run:

```bash
pytest tests/test_ffmpeg_manifest_renderer.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit and push**

```bash
git add pixelle_video/services/ffmpeg_manifest_renderer.py tests/test_ffmpeg_manifest_renderer.py
git commit -m "feat: add ffmpeg manifest renderer"
git push origin dev
```

---

### Task 8: Add Capability Resolver and Standard Pipeline Routing

**Files:**
- Create: `pixelle_video/services/render_capability_resolver.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/test_render_capability_resolver.py`
- Test: `tests/test_standard_pipeline_ffmpeg_manifest_mode.py`

- [ ] **Step 1: Write failing resolver tests**

Create `tests/test_render_capability_resolver.py`:

```python
from pixelle_video.services.render_capability_resolver import (
    RenderCapabilityInput,
    RenderCapabilityResolver,
)


def test_resolver_allows_ffmpeg_manifest_for_prerendered_image_template():
    result = RenderCapabilityResolver().resolve(
        RenderCapabilityInput(
            requested_backend="ffmpeg_manifest",
            template_type="image",
            media_domain="image",
            template_prerendered=True,
            element_motion_backend="python_ffmpeg",
            has_hyperframes_native_template=False,
        )
    )

    assert result.effective_backend == "ffmpeg_manifest"
    assert result.fallback_reason is None


def test_resolver_falls_back_when_ffmpeg_manifest_needs_browser_template():
    result = RenderCapabilityResolver().resolve(
        RenderCapabilityInput(
            requested_backend="ffmpeg_manifest",
            template_type="image",
            media_domain="image",
            template_prerendered=False,
            element_motion_backend="hyperframes_canvas",
            has_hyperframes_native_template=False,
        )
    )

    assert result.effective_backend == "legacy"
    assert "requires prerendered template" in result.fallback_reason
```

- [ ] **Step 2: Run resolver tests to verify they fail**

Run:

```bash
pytest tests/test_render_capability_resolver.py -q
```

Expected: FAIL because the resolver does not exist.

- [ ] **Step 3: Implement resolver**

Create `pixelle_video/services/render_capability_resolver.py`:

```python
from dataclasses import dataclass

from pixelle_video.render_backend import (
    FFMPEG_MANIFEST_RENDER_BACKEND,
    HYPERFRAMES_COMPILED_RENDER_BACKEND,
    LEGACY_RENDER_BACKEND,
)


@dataclass(frozen=True)
class RenderCapabilityInput:
    requested_backend: str
    template_type: str
    media_domain: str
    template_prerendered: bool
    element_motion_backend: str | None
    has_hyperframes_native_template: bool


@dataclass(frozen=True)
class RenderCapabilityResult:
    effective_backend: str
    fallback_reason: str | None = None


class RenderCapabilityResolver:
    def resolve(self, request: RenderCapabilityInput) -> RenderCapabilityResult:
        if request.requested_backend == LEGACY_RENDER_BACKEND:
            return RenderCapabilityResult(effective_backend=LEGACY_RENDER_BACKEND)
        if request.requested_backend == HYPERFRAMES_COMPILED_RENDER_BACKEND:
            if request.has_hyperframes_native_template or request.template_prerendered:
                return RenderCapabilityResult(
                    effective_backend=HYPERFRAMES_COMPILED_RENDER_BACKEND
                )
            return RenderCapabilityResult(
                effective_backend=LEGACY_RENDER_BACKEND,
                fallback_reason="HyperFrames requires native or prerendered template",
            )
        if request.requested_backend == FFMPEG_MANIFEST_RENDER_BACKEND:
            if not request.template_prerendered:
                return RenderCapabilityResult(
                    effective_backend=LEGACY_RENDER_BACKEND,
                    fallback_reason="ffmpeg_manifest requires prerendered template assets",
                )
            if request.element_motion_backend == "hyperframes_canvas":
                return RenderCapabilityResult(
                    effective_backend=HYPERFRAMES_COMPILED_RENDER_BACKEND,
                    fallback_reason="ffmpeg_manifest cannot render hyperframes_canvas element motion",
                )
            return RenderCapabilityResult(effective_backend=FFMPEG_MANIFEST_RENDER_BACKEND)
        return RenderCapabilityResult(
            effective_backend=LEGACY_RENDER_BACKEND,
            fallback_reason=f"unsupported render backend: {request.requested_backend}",
        )
```

- [ ] **Step 4: Route standard pipeline post-production**

In `StandardPipeline`, add:

```python
def _get_render_backend_fallback_reason(self, ctx: PipelineContext) -> str | None:
    return getattr(ctx, "render_backend_fallback_reason", None)
```

Update `_resolve_effective_render_backend` to use `RenderCapabilityResolver`. Preserve current HyperFrames fallback tests by keeping `_get_hyperframes_fallback_reason` as the source for native template availability.

Add in `post_production`:

```python
if self._resolve_effective_render_backend(ctx) == FFMPEG_MANIFEST_RENDER_BACKEND:
    await self._post_production_ffmpeg_manifest(ctx)
    return
```

Implement `_post_production_ffmpeg_manifest`:

```python
async def _post_production_ffmpeg_manifest(self, ctx: PipelineContext) -> None:
    manifest = self._build_render_manifest_for_current_timeline(ctx)
    execution_plan = self._build_render_execution_plan(ctx)
    ass_outputs = self._export_ass_for_manifest_if_needed(ctx, manifest)
    from pixelle_video.services.ffmpeg_manifest_renderer import FfmpegManifestRenderer

    ctx.final_video_path = FfmpegManifestRenderer().render(
        manifest=manifest,
        execution_plan=execution_plan,
        output_path=ctx.final_video_path,
        ass_path=str(ass_outputs.master) if ass_outputs else None,
        bgm_path=ctx.params.get("bgm_path"),
        bgm_volume=ctx.params.get("bgm_volume", 0.2),
        bgm_mode=ctx.params.get("bgm_mode", "loop"),
    )
    ctx.observability["render_execution_plan"] = execution_plan.to_dict()
```

Use helper names exactly as implemented in this task. If existing code already has equivalent private helpers, adapt the call site to those names and update tests to assert behavior, not private method names.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
pytest tests/test_render_capability_resolver.py tests/test_standard_pipeline_ffmpeg_manifest_mode.py tests/test_standard_pipeline_hyperframes_mode.py tests/test_standard_pipeline_staged_mode.py -q
```

Expected: PASS for backend routing tests.

Commit:

```bash
git add pixelle_video/services/render_capability_resolver.py pixelle_video/pipelines/standard.py tests/test_render_capability_resolver.py tests/test_standard_pipeline_ffmpeg_manifest_mode.py
git commit -m "feat: route standard pipeline through render capability resolver"
git push origin dev
```

---

### Task 9: Persist Render Execution Metadata and Update History UI

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `web/utils/render_backend_ui.py`
- Modify: `web/pages/2_📚_History.py`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `web/i18n/locales/zh_CN.json`
- Test: `tests/test_render_backend_ui.py`
- Test: `tests/test_standard_pipeline_hyperframes_mode.py`
- Test: `tests/test_standard_pipeline_ffmpeg_manifest_mode.py`

- [ ] **Step 1: Write failing metadata tests**

Add to `tests/test_render_backend_ui.py`:

```python
def test_get_task_render_backend_fallback_reason_reads_result_payload():
    assert (
        render_backend_ui.get_task_render_backend_fallback_reason(
            {
                "result": {
                    "render_execution_plan": {
                        "fallback_reason": "ffmpeg_manifest requires prerendered template assets"
                    }
                }
            }
        )
        == "ffmpeg_manifest requires prerendered template assets"
    )
    assert render_backend_ui.get_task_render_backend_fallback_reason({}) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_render_backend_ui.py::test_get_task_render_backend_fallback_reason_reads_result_payload -q
```

Expected: FAIL because the helper does not exist.

- [ ] **Step 3: Implement metadata helper and persistence**

Add to `web/utils/render_backend_ui.py`:

```python
def get_task_render_backend_fallback_reason(metadata: Mapping[str, Any]) -> Optional[str]:
    summary = _get_result_summary(metadata, "render_execution_plan")
    if summary is None:
        return None
    reason = summary.get("fallback_reason")
    return str(reason) if reason else None
```

In `StandardPipeline._persist_task_data`, include:

```python
if "render_execution_plan" in ctx.observability:
    result_metadata["render_execution_plan"] = ctx.observability["render_execution_plan"]
```

Use the existing result metadata variable name in the function.

- [ ] **Step 4: Update History UI labels**

Add English:

```json
"history.detail.render_backend_fallback": "Backend fallback",
"history.detail.render_backend_fallback_reason": "Reason: {reason}"
```

Add Chinese:

```json
"history.detail.render_backend_fallback": "渲染后端回退",
"history.detail.render_backend_fallback_reason": "原因：{reason}"
```

In `web/pages/2_📚_History.py`, render the fallback reason next to backend details:

```python
fallback_reason = get_task_render_backend_fallback_reason(metadata)
if fallback_reason:
    st.markdown(f"**{tr('history.detail.render_backend_fallback')}**")
    st.caption(
        tr(
            "history.detail.render_backend_fallback_reason",
            reason=fallback_reason,
        )
    )
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
pytest tests/test_render_backend_ui.py tests/test_standard_pipeline_hyperframes_mode.py tests/test_standard_pipeline_ffmpeg_manifest_mode.py -q
```

Expected: PASS for metadata and backend UI tests.

Commit:

```bash
git add pixelle_video/pipelines/standard.py web/utils/render_backend_ui.py "web/pages/2_📚_History.py" web/i18n/locales/en_US.json web/i18n/locales/zh_CN.json tests/test_render_backend_ui.py tests/test_standard_pipeline_hyperframes_mode.py tests/test_standard_pipeline_ffmpeg_manifest_mode.py
git commit -m "feat: persist render execution backend diagnostics"
git push origin dev
```

---

### Task 10: Final Regression Pass

**Files:**
- No source file changes expected.
- Test: backend, render package, template, element motion, HyperFrames, and FFmpeg manifest test groups.

- [ ] **Step 1: Check status before verification**

Run:

```bash
git status --short
```

Expected: only unrelated pre-existing dirty files, or a clean tree if prior dirty files were resolved outside this plan.

- [ ] **Step 2: Run targeted test group**

Run:

```bash
pytest tests/test_render_backend_ui.py tests/test_render_package_models.py tests/test_render_execution_plan.py tests/test_template_visual_materializer.py tests/test_element_motion_materializer.py tests/test_element_animation_renderer.py tests/test_hyperframes_project_service.py tests/test_hyperframes_compiler.py tests/test_ffmpeg_manifest_renderer.py tests/test_render_capability_resolver.py tests/test_standard_pipeline_ffmpeg_manifest_mode.py tests/test_standard_pipeline_hyperframes_mode.py tests/test_standard_pipeline_staged_mode.py -q
```

Expected: PASS. If a test fails in a file outside this plan's touched files, copy the exact failure name and confirm whether it is caused by pre-existing dirty work.

- [ ] **Step 3: Run focused config and API tests**

Run:

```bash
pytest tests/test_video_api.py tests/test_output_preview.py tests/test_style_config_storyboard_planning_ui.py -q
```

Expected: PASS for render backend selection, request serialization, and UI payload tests.

- [ ] **Step 4: Inspect staged changes**

Run:

```bash
git diff --stat
git diff --cached --stat
```

Expected: no unstaged or staged changes created by verification.

- [ ] **Step 5: Report verification**

Prepare a short report with:

```text
Targeted render tests: PASS
Config/API/UI tests: PASS
Known unrelated dirty files: <count and categories from git status>
Last pushed commit: <sha and message>
```

No commit is needed for this task unless a verification fix was made.

---

## Plan Self-Review

Spec coverage:

- Three backend taxonomy is covered by Tasks 1, 8, and 9.
- Template visual asset layer is covered by Tasks 3 and 4.
- Clip-level element motion integration is covered by Tasks 5 and 6.
- `ffmpeg_manifest` final renderer is covered by Task 7.
- Capability fallback and requested/effective metadata are covered by Tasks 8 and 9.
- Legacy stability and duplicate text prevention are covered by Tasks 3 and 4.
- HyperFrames reuse of pre-rendered assets and element manifests is covered by Task 6.
- Verification is covered by Task 10.

Type consistency:

- Backend id is consistently `ffmpeg_manifest`.
- Element animation backend id remains `python_ffmpeg` or `hyperframes_canvas`.
- Template text policy values are consistently `caption_renderer`, `template_body`, `none`, and `explicit_both`.
- New execution metadata is consistently named `RenderExecutionPlan` and `render_execution_plan`.

Risk controls:

- Each task has its own failing test first.
- Each task ends with one commit and push.
- The plan avoids `git worktree` because repository instructions forbid it.
