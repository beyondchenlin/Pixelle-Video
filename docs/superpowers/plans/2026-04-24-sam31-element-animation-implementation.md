# SAM3.1 Element Animation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an advanced SAM3.1-based element segmentation and micro-animation feature. By default, generated images are segmented into 3 selected foreground subjects; advanced settings let users adjust subject count, candidate count, prompts, backend, and motion intensity. Rendering prefers HyperFrames canvas animation, with Python/FFmpeg available as a first-class lightweight renderer.

**Architecture:** Add a typed element-animation manifest, deterministic animation presets, a ComfyUI SAM3.1 segmentation service, a Python/FFmpeg renderer, HyperFrames manifest materialization, pipeline integration, and Streamlit UI controls. Existing image generation remains the source of truth. The feature is opt-in and only runs for generated image frames.

**Tech Stack:** Python dataclasses, Pillow, FFmpeg, ComfyUI via `comfykit`, HyperFrames HTML assets, Streamlit UI, pytest.

---

## Context

The design spec is already committed at:

- `docs/superpowers/specs/2026-04-24-sam31-element-animation-design.md`

The two review fixes in that spec are requirements for this implementation:

- The background layer must be explicit. `background.mode` is either `inpainted` or `source_image_low_motion`; source-image background is allowed only with subtle motion caps to avoid visible ghosting.
- The manifest must include `canvas` and `timeline`, and it must not duplicate FPS in both timeline and render sections.

Current repository facts that shape the implementation:

- `pixelle_video/services/media.py` can execute ComfyUI workflows and returns first media output through `MediaService.media(...)`.
- Full SAM output parsing needs lower-level access to the Comfy result lists, so the segmentation service will call `core._get_or_create_comfykit().execute(...)` directly instead of using `MediaService.media(...)`.
- `pixelle_video/models/render_package.py` owns HyperFrames render manifests.
- `pixelle_video/services/hyperframes_project_service.py` writes HyperFrames project files.
- `pixelle_video/services/hyperframes_asset_materializer.py` copies media assets into HyperFrames projects.
- `pixelle_video/services/frame_processor.py` generates frame media, composes HTML overlays, and creates video segments.
- `web/components/style_config.py` owns middle-column generation settings.
- `web/components/output_preview.py` maps UI state into request payloads.

## Implementation Rules

- Keep the feature opt-in. Existing generation behavior must be unchanged when `element_animation_enabled=False`.
- Default selection is 3 subjects.
- Advanced options expose the larger candidate pool and backend controls.
- Use SAM3.1 native ComfyUI when available. Keep the workflow contract stable enough that a third-party ComfyUI SAM3 node can be swapped in by changing workflow JSON and parameter names.
- Do not rely on the original full image as a moving background unless `background.mode="source_image_low_motion"` and motion bounds are subtle.
- Preserve user worktree changes. Stage and commit only files touched by this implementation.

## Files To Add

- `pixelle_video/models/element_animation.py`
- `pixelle_video/services/element_animation_presets.py`
- `pixelle_video/services/element_segmentation.py`
- `pixelle_video/services/element_animation_renderer.py`
- `tests/test_element_animation_models.py`
- `tests/test_element_animation_presets.py`
- `tests/test_element_segmentation_service.py`
- `tests/test_element_animation_renderer.py`
- `tests/test_element_animation_ui_mapping.py`
- `workflows/down/image_sam31_segment_依赖与下载说明.md`
- `workflows/selfhost/image_sam31_segment.json`

## Files To Modify

- `pixelle_video/config/schema.py`
- `pixelle_video/models/storyboard.py`
- `pixelle_video/models/render_package.py`
- `pixelle_video/services/frame_processor.py`
- `pixelle_video/services/hyperframes_asset_materializer.py`
- `pixelle_video/services/hyperframes_compiler.py`
- `pixelle_video/services/hyperframes_project_service.py`
- `web/components/style_config.py`
- `web/components/output_preview.py`
- `web/i18n/locales/en_US.json`
- `web/i18n/locales/zh_CN.json`

---

## Task 1: Add Element Animation Manifest Model

**Purpose:** Create the stable data contract shared by segmentation, renderers, HyperFrames, and pipeline state.

- [ ] Add tests first in `tests/test_element_animation_models.py`.

```python
from pathlib import Path

import pytest

from pixelle_video.models.element_animation import (
    ElementAnimation,
    ElementAnimationBackground,
    ElementAnimationCanvas,
    ElementAnimationManifest,
    ElementAnimationRender,
    ElementAnimationSegmentation,
    ElementAnimationTimeline,
    ElementMotionBounds,
    SegmentedElement,
)


def test_manifest_round_trip_preserves_canvas_timeline_and_selection(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    element = tmp_path / "element_001.png"
    mask = tmp_path / "mask_001.png"
    element.write_bytes(b"png")
    mask.write_bytes(b"png")

    manifest = ElementAnimationManifest(
        source_image_path=str(source),
        canvas=ElementAnimationCanvas(width=1024, height=576),
        timeline=ElementAnimationTimeline(duration=3.0, fps=24),
        background=ElementAnimationBackground(
            mode="source_image_low_motion",
            image_path=str(source),
            motion_bounds=ElementMotionBounds(translate_px=4, rotate_deg=0.4, scale_delta=0.01),
        ),
        segmentation=ElementAnimationSegmentation(
            provider="comfyui_sam31",
            workflow="image_sam31_segment.json",
            prompt="main foreground elements",
            candidate_limit=5,
            selected_count=3,
        ),
        elements=[
            SegmentedElement(
                id="element_001",
                label="subject",
                image_path=str(element),
                mask_path=str(mask),
                bbox=[10, 12, 140, 180],
                score=0.92,
                selected=True,
                z_index=1,
                animation=ElementAnimation(
                    preset="float",
                    intensity="medium",
                    seed=7,
                    motion_bounds=ElementMotionBounds(translate_px=18, rotate_deg=2.0, scale_delta=0.04),
                ),
            )
        ],
        render=ElementAnimationRender(backend="hyperframes_canvas"),
    )

    loaded = ElementAnimationManifest.from_dict(manifest.to_dict())

    assert loaded.canvas.width == 1024
    assert loaded.timeline.fps == 24
    assert loaded.render.backend == "hyperframes_canvas"
    assert loaded.selected_elements()[0].id == "element_001"
    assert "fps" not in loaded.render.to_dict()


def test_manifest_rejects_selected_count_above_candidate_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="selected_count"):
        ElementAnimationSegmentation(
            provider="comfyui_sam31",
            workflow="image_sam31_segment.json",
            prompt=None,
            candidate_limit=2,
            selected_count=3,
        )
```

- [ ] Add `pixelle_video/models/element_animation.py`.

Use dataclasses with explicit `to_dict()` / `from_dict()` methods. Keep path values as strings to match existing manifest models.

Required public API:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AnimationIntensity = Literal["low", "medium", "high"]
AnimationPreset = Literal["float", "pulse", "drift", "pop", "parallax"]
BackgroundMode = Literal["inpainted", "source_image_low_motion"]
ElementRenderBackend = Literal["hyperframes_canvas", "python_ffmpeg"]


@dataclass
class ElementMotionBounds:
    translate_px: float = 12.0
    rotate_deg: float = 1.5
    scale_delta: float = 0.03

    def to_dict(self) -> dict[str, float]:
        return {
            "translate_px": self.translate_px,
            "rotate_deg": self.rotate_deg,
            "scale_delta": self.scale_delta,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ElementMotionBounds":
        data = data or {}
        return cls(
            translate_px=float(data.get("translate_px", 12.0)),
            rotate_deg=float(data.get("rotate_deg", 1.5)),
            scale_delta=float(data.get("scale_delta", 0.03)),
        )
```

Add the remaining classes with the same pattern:

- `ElementAnimationCanvas(width: int, height: int)`
- `ElementAnimationTimeline(duration: float, fps: int)`
- `ElementAnimationBackground(mode, image_path, motion_bounds)`
- `ElementAnimationSegmentation(provider, workflow, prompt, candidate_limit, selected_count)`
- `ElementAnimation(preset, intensity, seed, motion_bounds)`
- `SegmentedElement(id, label, image_path, mask_path, bbox, score, selected, z_index, animation)`
- `ElementAnimationRender(backend)`
- `ElementAnimationManifest(source_image_path, canvas, timeline, background, segmentation, elements, render, audio_path=None)`

Validation rules:

```python
def __post_init__(self) -> None:
    if self.candidate_limit < 1:
        raise ValueError("candidate_limit must be at least 1")
    if self.selected_count < 1:
        raise ValueError("selected_count must be at least 1")
    if self.selected_count > self.candidate_limit:
        raise ValueError("selected_count cannot exceed candidate_limit")
```

For `ElementAnimationManifest.selected_elements()`:

```python
def selected_elements(self) -> list[SegmentedElement]:
    return sorted(
        [element for element in self.elements if element.selected],
        key=lambda element: element.z_index,
    )
```

- [ ] Run the focused tests.

```powershell
python -m pytest tests/test_element_animation_models.py -q
```

Expected result:

```text
2 passed
```

- [ ] Commit this task.

```powershell
git status --short
git add pixelle_video/models/element_animation.py tests/test_element_animation_models.py
git commit -m "Add element animation manifest model"
```

---

## Task 2: Add Deterministic Animation Presets

**Purpose:** Keep animation tasteful for simple drawings and make rendering deterministic across HyperFrames and Python.

- [ ] Add tests in `tests/test_element_animation_presets.py`.

```python
from pixelle_video.models.element_animation import ElementMotionBounds
from pixelle_video.services.element_animation_presets import (
    ElementTransform,
    resolve_background_bounds,
    resolve_element_bounds,
    sample_transform,
)


def test_source_image_background_bounds_are_subtle() -> None:
    bounds = resolve_background_bounds("source_image_low_motion", "high")

    assert bounds.translate_px <= 6
    assert bounds.rotate_deg <= 0.5
    assert bounds.scale_delta <= 0.015


def test_sample_transform_is_deterministic() -> None:
    bounds = ElementMotionBounds(translate_px=20, rotate_deg=2, scale_delta=0.05)

    first = sample_transform("float", time=0.75, duration=3.0, seed=11, bounds=bounds)
    second = sample_transform("float", time=0.75, duration=3.0, seed=11, bounds=bounds)

    assert first == second
    assert isinstance(first, ElementTransform)
    assert abs(first.x) <= 20
    assert abs(first.rotate) <= 2
    assert 0.95 <= first.scale <= 1.05


def test_element_bounds_scale_by_intensity() -> None:
    low = resolve_element_bounds("low")
    high = resolve_element_bounds("high")

    assert low.translate_px < high.translate_px
    assert low.rotate_deg < high.rotate_deg
    assert low.scale_delta < high.scale_delta
```

- [ ] Add `pixelle_video/services/element_animation_presets.py`.

Required public API:

```python
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from pixelle_video.models.element_animation import (
    AnimationIntensity,
    AnimationPreset,
    BackgroundMode,
    ElementMotionBounds,
)


@dataclass(frozen=True)
class ElementTransform:
    x: float
    y: float
    rotate: float
    scale: float
    opacity: float = 1.0


def resolve_element_bounds(intensity: AnimationIntensity) -> ElementMotionBounds:
    if intensity == "low":
        return ElementMotionBounds(translate_px=8, rotate_deg=0.8, scale_delta=0.015)
    if intensity == "high":
        return ElementMotionBounds(translate_px=28, rotate_deg=3.0, scale_delta=0.06)
    return ElementMotionBounds(translate_px=16, rotate_deg=1.8, scale_delta=0.035)


def resolve_background_bounds(mode: BackgroundMode, intensity: AnimationIntensity) -> ElementMotionBounds:
    if mode == "source_image_low_motion":
        return ElementMotionBounds(translate_px=4 if intensity != "high" else 6, rotate_deg=0.4, scale_delta=0.012)
    return resolve_element_bounds("low")
```

`sample_transform(...)` must use only deterministic math plus a seeded random phase:

```python
def _phase(seed: int, channel: int) -> float:
    rng = random.Random(seed * 1009 + channel * 9176)
    return rng.random() * math.tau


def sample_transform(
    preset: AnimationPreset,
    *,
    time: float,
    duration: float,
    seed: int,
    bounds: ElementMotionBounds,
) -> ElementTransform:
    progress = 0 if duration <= 0 else max(0.0, min(1.0, time / duration))
    wave = math.sin(progress * math.tau + _phase(seed, 1))
    wave_b = math.cos(progress * math.tau + _phase(seed, 2))

    if preset == "pulse":
        return ElementTransform(
            x=wave_b * bounds.translate_px * 0.25,
            y=wave * bounds.translate_px * 0.25,
            rotate=wave_b * bounds.rotate_deg * 0.25,
            scale=1 + abs(wave) * bounds.scale_delta,
        )
    if preset == "drift":
        return ElementTransform(
            x=(progress - 0.5) * bounds.translate_px,
            y=wave * bounds.translate_px * 0.35,
            rotate=wave_b * bounds.rotate_deg,
            scale=1 + wave * bounds.scale_delta * 0.5,
        )
    if preset == "pop":
        pop = math.sin(min(1.0, progress * 2.5) * math.pi)
        return ElementTransform(
            x=wave_b * bounds.translate_px * 0.2,
            y=-pop * bounds.translate_px * 0.35,
            rotate=wave * bounds.rotate_deg * 0.4,
            scale=1 + pop * bounds.scale_delta,
        )
    if preset == "parallax":
        return ElementTransform(
            x=wave * bounds.translate_px,
            y=wave_b * bounds.translate_px * 0.25,
            rotate=wave * bounds.rotate_deg * 0.35,
            scale=1 + wave_b * bounds.scale_delta * 0.35,
        )
    return ElementTransform(
        x=wave * bounds.translate_px * 0.6,
        y=wave_b * bounds.translate_px,
        rotate=wave * bounds.rotate_deg,
        scale=1 + wave_b * bounds.scale_delta,
    )
```

- [ ] Run tests.

```powershell
python -m pytest tests/test_element_animation_presets.py -q
```

Expected result:

```text
3 passed
```

- [ ] Commit this task.

```powershell
git status --short
git add pixelle_video/services/element_animation_presets.py tests/test_element_animation_presets.py
git commit -m "Add element animation presets"
```

---

## Task 3: Add SAM3.1 Segmentation Service

**Purpose:** Turn a generated image into an element-animation manifest by calling a ComfyUI SAM3.1 workflow and normalizing outputs.

- [ ] Add tests in `tests/test_element_segmentation_service.py`.

```python
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from pixelle_video.services.element_segmentation import ElementSegmentationService


@dataclass
class FakeComfyImage:
    path: str


@dataclass
class FakeComfyResult:
    images: list[FakeComfyImage]


class FakeKit:
    def __init__(self, result: FakeComfyResult) -> None:
        self.result = result
        self.calls: list[tuple[object, dict[str, object]]] = []

    def execute(self, workflow_input: object, workflow_params: dict[str, object]) -> FakeComfyResult:
        self.calls.append((workflow_input, workflow_params))
        return self.result


class FakeCore:
    def __init__(self, kit: FakeKit) -> None:
        self.kit = kit

    def _get_or_create_comfykit(self) -> FakeKit:
        return self.kit


def _png(path: Path, color: tuple[int, int, int, int]) -> None:
    Image.new("RGBA", (32, 32), color).save(path)


def test_segment_image_builds_manifest_from_comfy_outputs(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    background = tmp_path / "background.png"
    element_a = tmp_path / "element_a.png"
    mask_a = tmp_path / "mask_a.png"
    element_b = tmp_path / "element_b.png"
    mask_b = tmp_path / "mask_b.png"
    for path, color in [
        (source, (255, 255, 255, 255)),
        (background, (250, 250, 250, 255)),
        (element_a, (255, 0, 0, 255)),
        (mask_a, (255, 255, 255, 255)),
        (element_b, (0, 0, 255, 255)),
        (mask_b, (255, 255, 255, 255)),
    ]:
        _png(path, color)

    kit = FakeKit(
        FakeComfyResult(
            images=[
                FakeComfyImage(str(background)),
                FakeComfyImage(str(element_a)),
                FakeComfyImage(str(mask_a)),
                FakeComfyImage(str(element_b)),
                FakeComfyImage(str(mask_b)),
            ]
        )
    )
    service = ElementSegmentationService(FakeCore(kit))

    manifest = service.segment_image(
        image_path=str(source),
        task_id="task-1",
        frame_index=0,
        output_dir=str(tmp_path / "out"),
        width=32,
        height=32,
        duration=2.5,
        fps=24,
        selected_count=1,
        candidate_limit=2,
        prompt="main simple drawing subjects",
        workflow="image_sam31_segment.json",
        backend="hyperframes_canvas",
        intensity="medium",
    )

    assert kit.calls
    assert kit.calls[0][1]["image"] == str(source)
    assert kit.calls[0][1]["candidate_limit"] == 2
    assert manifest.background.mode == "inpainted"
    assert manifest.segmentation.selected_count == 1
    assert len(manifest.elements) == 2
    assert [element.selected for element in manifest.elements] == [True, False]
    assert Path(manifest.elements[0].image_path).exists()
    assert Path(manifest.elements[0].mask_path).exists()


def test_segment_image_falls_back_to_source_low_motion_when_background_missing(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    element = tmp_path / "element.png"
    mask = tmp_path / "mask.png"
    _png(source, (255, 255, 255, 255))
    _png(element, (255, 0, 0, 255))
    _png(mask, (255, 255, 255, 255))

    kit = FakeKit(FakeComfyResult(images=[FakeComfyImage(str(element)), FakeComfyImage(str(mask))]))
    service = ElementSegmentationService(FakeCore(kit))

    manifest = service.segment_image(
        image_path=str(source),
        task_id="task-1",
        frame_index=0,
        output_dir=str(tmp_path / "out"),
        width=32,
        height=32,
        duration=1.0,
        fps=12,
        selected_count=1,
        candidate_limit=1,
        prompt=None,
        workflow="image_sam31_segment.json",
        backend="python_ffmpeg",
        intensity="high",
    )

    assert manifest.background.mode == "source_image_low_motion"
    assert manifest.background.motion_bounds.translate_px <= 6
    assert manifest.render.backend == "python_ffmpeg"
```

- [ ] Add `pixelle_video/services/element_segmentation.py`.

Required method signature:

```python
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from PIL import Image

from pixelle_video.models.element_animation import (
    AnimationIntensity,
    ElementAnimation,
    ElementAnimationBackground,
    ElementAnimationCanvas,
    ElementAnimationManifest,
    ElementAnimationRender,
    ElementAnimationSegmentation,
    ElementAnimationTimeline,
    ElementRenderBackend,
    SegmentedElement,
)
from pixelle_video.services.element_animation_presets import (
    resolve_background_bounds,
    resolve_element_bounds,
)


class ElementSegmentationService:
    def __init__(self, core: Any) -> None:
        self.core = core

    def segment_image(
        self,
        *,
        image_path: str,
        task_id: str,
        frame_index: int,
        output_dir: str,
        width: int,
        height: int,
        duration: float,
        fps: int,
        selected_count: int,
        candidate_limit: int,
        prompt: str | None,
        workflow: str,
        backend: ElementRenderBackend,
        intensity: AnimationIntensity,
        audio_path: str | None = None,
    ) -> ElementAnimationManifest:
        ...
```

Implementation rules:

- Output directory: `Path(output_dir) / "element_animation" / f"frame_{frame_index:03d}"`.
- Call ComfyUI:

```python
kit = self.core._get_or_create_comfykit()
workflow_params = {
    "image": image_path,
    "prompt": prompt or "main foreground subjects, separated simple drawing elements",
    "candidate_limit": candidate_limit,
    "selected_count": selected_count,
    "width": width,
    "height": height,
}
result = kit.execute(workflow, workflow_params)
```

- Interpret outputs:
  - If there are at least `1 + candidate_limit * 2` images, the first image is the inpainted background.
  - Remaining images are element/mask pairs.
  - If the background is missing, copy the source image as background and set `background.mode="source_image_low_motion"`.
- Copy each output to stable paths:
  - `background.png`
  - `element_001.png`, `mask_001.png`
  - `element_002.png`, `mask_002.png`
- Mark only the first `selected_count` elements selected.
- Use preset cycle: `["float", "pulse", "drift", "parallax", "pop"]`.
- Use `resolve_element_bounds(intensity)` for element motion and `resolve_background_bounds(background_mode, intensity)` for background motion.
- Estimate bounding boxes from mask alpha using Pillow:

```python
def _mask_bbox(mask_path: Path) -> list[int]:
    image = Image.open(mask_path).convert("RGBA")
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return [0, 0, image.width, image.height]
    left, top, right, bottom = bbox
    return [left, top, right, bottom]
```

- [ ] Run tests.

```powershell
python -m pytest tests/test_element_segmentation_service.py -q
```

Expected result:

```text
2 passed
```

- [ ] Commit this task.

```powershell
git status --short
git add pixelle_video/services/element_segmentation.py tests/test_element_segmentation_service.py
git commit -m "Add SAM3.1 element segmentation service"
```

---

## Task 4: Add Python/FFmpeg Element Animation Renderer

**Purpose:** Provide a local renderer that creates simple, attractive motion without relying on HyperFrames.

- [ ] Add tests in `tests/test_element_animation_renderer.py`.

```python
from pathlib import Path

from PIL import Image

from pixelle_video.models.element_animation import (
    ElementAnimation,
    ElementAnimationBackground,
    ElementAnimationCanvas,
    ElementAnimationManifest,
    ElementAnimationRender,
    ElementAnimationSegmentation,
    ElementAnimationTimeline,
    ElementMotionBounds,
    SegmentedElement,
)
from pixelle_video.services.element_animation_renderer import PythonElementAnimationRenderer


def _png(path: Path, size: tuple[int, int], color: tuple[int, int, int, int]) -> None:
    Image.new("RGBA", size, color).save(path)


def test_render_frame_composites_selected_element(tmp_path: Path) -> None:
    background = tmp_path / "background.png"
    element = tmp_path / "element.png"
    mask = tmp_path / "mask.png"
    _png(background, (64, 64), (255, 255, 255, 255))
    _png(element, (64, 64), (255, 0, 0, 255))
    _png(mask, (64, 64), (255, 255, 255, 255))

    manifest = ElementAnimationManifest(
        source_image_path=str(background),
        canvas=ElementAnimationCanvas(width=64, height=64),
        timeline=ElementAnimationTimeline(duration=1.0, fps=12),
        background=ElementAnimationBackground(
            mode="inpainted",
            image_path=str(background),
            motion_bounds=ElementMotionBounds(translate_px=0, rotate_deg=0, scale_delta=0),
        ),
        segmentation=ElementAnimationSegmentation(
            provider="comfyui_sam31",
            workflow="image_sam31_segment.json",
            prompt=None,
            candidate_limit=1,
            selected_count=1,
        ),
        elements=[
            SegmentedElement(
                id="element_001",
                label="subject",
                image_path=str(element),
                mask_path=str(mask),
                bbox=[0, 0, 64, 64],
                score=1.0,
                selected=True,
                z_index=1,
                animation=ElementAnimation(
                    preset="pulse",
                    intensity="low",
                    seed=1,
                    motion_bounds=ElementMotionBounds(translate_px=0, rotate_deg=0, scale_delta=0),
                ),
            )
        ],
        render=ElementAnimationRender(backend="python_ffmpeg"),
    )

    renderer = PythonElementAnimationRenderer()
    frame = renderer.render_frame(manifest, time=0)

    assert frame.size == (64, 64)
    assert frame.getpixel((32, 32))[0] > 200
```

- [ ] Add `pixelle_video/services/element_animation_renderer.py`.

Required public API:

```python
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from pixelle_video.models.element_animation import ElementAnimationManifest
from pixelle_video.services.element_animation_presets import sample_transform


class PythonElementAnimationRenderer:
    def render_frame(self, manifest: ElementAnimationManifest, *, time: float) -> Image.Image:
        ...

    def render_video(self, manifest: ElementAnimationManifest, output_path: str) -> str:
        ...
```

Frame rendering algorithm:

```python
canvas_size = (manifest.canvas.width, manifest.canvas.height)
base = Image.open(manifest.background.image_path).convert("RGBA").resize(canvas_size)
for element in manifest.selected_elements():
    layer = Image.open(element.image_path).convert("RGBA").resize(canvas_size)
    mask = Image.open(element.mask_path).convert("L").resize(canvas_size)
    transform = sample_transform(
        element.animation.preset,
        time=time,
        duration=manifest.timeline.duration,
        seed=element.animation.seed,
        bounds=element.animation.motion_bounds,
    )
    transformed = layer.rotate(transform.rotate, resample=Image.Resampling.BICUBIC, center=(canvas_size[0] / 2, canvas_size[1] / 2))
    transformed_mask = mask.rotate(transform.rotate, resample=Image.Resampling.BICUBIC, center=(canvas_size[0] / 2, canvas_size[1] / 2))
    if transform.scale != 1:
        # resize around center, then paste back into a transparent canvas
        ...
    offset = (round(transform.x), round(transform.y))
    base.alpha_composite(transformed, dest=offset, source=(0, 0, canvas_size[0], canvas_size[1]))
return base.convert("RGB")
```

For `render_video(...)`:

- Create `frame_%05d.png` files in `tempfile.TemporaryDirectory()`.
- Frame count: `max(1, round(manifest.timeline.duration * manifest.timeline.fps))`.
- Encode with FFmpeg:

```powershell
ffmpeg -y -framerate <fps> -i frame_%05d.png -pix_fmt yuv420p -c:v libx264 output.mp4
```

- If `manifest.audio_path` exists, add audio:

```powershell
ffmpeg -y -i silent_video.mp4 -i audio.mp3 -c:v copy -c:a aac -shortest output.mp4
```

- Use `subprocess.run(..., check=True)`.

- [ ] Run tests.

```powershell
python -m pytest tests/test_element_animation_renderer.py -q
```

Expected result:

```text
1 passed
```

- [ ] Commit this task.

```powershell
git status --short
git add pixelle_video/services/element_animation_renderer.py tests/test_element_animation_renderer.py
git commit -m "Add Python element animation renderer"
```

---

## Task 5: Extend Render Package For Element Animation

**Purpose:** Let HyperFrames projects receive element-animation metadata without changing existing visual clip behavior.

- [ ] Extend `pixelle_video/models/render_package.py`.

Add an optional field to `RenderManifest`:

```python
element_animation_manifest_path: str | None = None
```

Update `to_dict()`:

```python
if self.element_animation_manifest_path:
    data["element_animation_manifest_path"] = self.element_animation_manifest_path
```

Update `from_dict()`:

```python
element_animation_manifest_path=data.get("element_animation_manifest_path"),
```

- [ ] Update `tests/test_render_package_models.py`.

Add an assertion to the existing round-trip test or add a small dedicated test:

```python
def test_render_manifest_round_trip_preserves_element_animation_manifest_path() -> None:
    manifest = RenderManifest(
        canvas_width=1280,
        canvas_height=720,
        media_width=1280,
        media_height=720,
        fps=24,
        master_audio_path="audio.mp3",
        duration=3.0,
        visual_clips=[],
        element_animation_manifest_path="data/element_animation_manifest.json",
    )

    loaded = RenderManifest.from_dict(manifest.to_dict())

    assert loaded.element_animation_manifest_path == "data/element_animation_manifest.json"
```

- [ ] Run tests.

```powershell
python -m pytest tests/test_render_package_models.py -q
```

Expected result includes the new test passing.

- [ ] Commit this task.

```powershell
git status --short
git add pixelle_video/models/render_package.py tests/test_render_package_models.py
git commit -m "Allow render manifests to reference element animation"
```

---

## Task 6: Materialize Element Animation Assets For HyperFrames

**Purpose:** Copy the JSON manifest and its image assets into the HyperFrames project so canvas templates can animate them.

- [ ] Modify `pixelle_video/services/hyperframes_project_service.py`.

Add helper:

```python
def _copy_element_animation_manifest(self, render_manifest: RenderManifest, project_dir: Path) -> str | None:
    if not render_manifest.element_animation_manifest_path:
        return None
    source_manifest_path = Path(render_manifest.element_animation_manifest_path)
    if not source_manifest_path.exists():
        return None

    data_dir = project_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    target_manifest_path = data_dir / "element_animation_manifest.json"

    manifest_data = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    asset_dir = project_dir / "assets" / "element_animation"
    asset_dir.mkdir(parents=True, exist_ok=True)

    def copy_asset(value: str) -> str:
        source = Path(value)
        target = asset_dir / source.name
        shutil.copy2(source, target)
        return f"assets/element_animation/{target.name}"

    manifest_data["source_image_path"] = copy_asset(manifest_data["source_image_path"])
    manifest_data["background"]["image_path"] = copy_asset(manifest_data["background"]["image_path"])
    for element in manifest_data["elements"]:
        element["image_path"] = copy_asset(element["image_path"])
        element["mask_path"] = copy_asset(element["mask_path"])

    target_manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return "data/element_animation_manifest.json"
```

Call this during project writing before template compilation and pass the returned relative path into compiler context.

- [ ] Modify `pixelle_video/services/hyperframes_compiler.py`.

Add `element_animation_manifest_path: str | None = None` to the template context and replacement mapping:

```python
"__ELEMENT_ANIMATION_MANIFEST__": context.element_animation_manifest_path or "",
```

- [ ] Update `tests/test_hyperframes_project_service.py`.

Add a fixture manifest with a background, source, element, and mask PNG. Verify:

```python
assert (project_dir / "data" / "element_animation_manifest.json").exists()
assert (project_dir / "assets" / "element_animation" / "background.png").exists()
assert "assets/element_animation/" in copied_manifest["background"]["image_path"]
```

- [ ] Run tests.

```powershell
python -m pytest tests/test_hyperframes_project_service.py -q
```

Expected result: existing tests plus the new asset materialization test pass.

- [ ] Commit this task.

```powershell
git status --short
git add pixelle_video/services/hyperframes_project_service.py pixelle_video/services/hyperframes_compiler.py tests/test_hyperframes_project_service.py
git commit -m "Materialize element animation assets for HyperFrames"
```

---

## Task 7: Add Config Fields And Request Mapping

**Purpose:** Expose the feature through configuration and UI payloads without changing defaults.

- [ ] Modify `pixelle_video/config/schema.py` and `pixelle_video/models/storyboard.py`.

Add fields with these defaults:

```python
element_animation_enabled: bool = False
element_animation_backend: str = "hyperframes_canvas"
element_animation_subject_count: int = 3
element_animation_candidate_limit: int = 3
element_animation_prompt: str | None = None
element_animation_intensity: str = "medium"
element_animation_workflow: str = "image_sam31_segment.json"
```

Validation in the config model:

```python
if self.element_animation_subject_count < 1:
    raise ValueError("element_animation_subject_count must be at least 1")
if self.element_animation_candidate_limit < self.element_animation_subject_count:
    raise ValueError("element_animation_candidate_limit must be >= element_animation_subject_count")
if self.element_animation_backend not in {"hyperframes_canvas", "python_ffmpeg"}:
    raise ValueError("unsupported element_animation_backend")
```

- [ ] Add UI request mapping tests in `tests/test_element_animation_ui_mapping.py`.

Focus on pure request-building helpers in `web/components/output_preview.py`; do not render Streamlit in this test.

```python
from web.components.output_preview import build_single_generation_request


def test_single_generation_request_includes_element_animation_options() -> None:
    request = build_single_generation_request(
        prompt="a simple flower and sun",
        style="简笔画",
        duration=3,
        media_type="image",
        render_backend="hyperframes",
        element_animation_enabled=True,
        element_animation_backend="hyperframes_canvas",
        element_animation_subject_count=3,
        element_animation_candidate_limit=5,
        element_animation_prompt="flower, sun, cloud",
        element_animation_intensity="medium",
        element_animation_workflow="image_sam31_segment.json",
    )

    assert request["element_animation_enabled"] is True
    assert request["element_animation_subject_count"] == 3
    assert request["element_animation_candidate_limit"] == 5
    assert request["element_animation_backend"] == "hyperframes_canvas"
```

If `build_single_generation_request` currently has a different signature, extend it with keyword-only optional fields using the defaults above.

- [ ] Modify `web/components/style_config.py`.

Add a collapsible section under media/render settings:

```python
with render_middle_column_collapsible_section("element_animation", tr("element_animation.title")):
    element_animation_enabled = st.toggle(
        tr("element_animation.enabled"),
        value=False,
        help=tr("element_animation.enabled_help"),
    )
    subject_count = st.slider(
        tr("element_animation.subject_count"),
        min_value=1,
        max_value=8,
        value=3,
        disabled=not element_animation_enabled,
    )
    with st.expander(tr("element_animation.advanced"), expanded=False):
        candidate_limit = st.slider(
            tr("element_animation.candidate_limit"),
            min_value=subject_count,
            max_value=12,
            value=max(3, subject_count),
            disabled=not element_animation_enabled,
        )
        backend = st.selectbox(
            tr("element_animation.backend"),
            options=["hyperframes_canvas", "python_ffmpeg"],
            index=0,
            disabled=not element_animation_enabled,
        )
        intensity = st.selectbox(
            tr("element_animation.intensity"),
            options=["low", "medium", "high"],
            index=1,
            disabled=not element_animation_enabled,
        )
        prompt = st.text_input(
            tr("element_animation.prompt"),
            value="",
            disabled=not element_animation_enabled,
        )
```

Persist the values in the same settings object/session-state pattern already used by this file.

- [ ] Add i18n keys.

`web/i18n/locales/zh_CN.json`:

```json
{
  "element_animation.title": "元素微动增强",
  "element_animation.enabled": "启用元素分割微动",
  "element_animation.enabled_help": "生成图片后分割主体元素，并为选中的元素添加轻量动画。",
  "element_animation.subject_count": "默认选中主体数",
  "element_animation.advanced": "高级选项",
  "element_animation.candidate_limit": "候选分割数量",
  "element_animation.backend": "动画渲染方式",
  "element_animation.intensity": "动效强度",
  "element_animation.prompt": "分割提示词"
}
```

`web/i18n/locales/en_US.json`:

```json
{
  "element_animation.title": "Element motion",
  "element_animation.enabled": "Enable element segmentation motion",
  "element_animation.enabled_help": "Segment generated images into foreground elements and add lightweight motion.",
  "element_animation.subject_count": "Selected subjects",
  "element_animation.advanced": "Advanced options",
  "element_animation.candidate_limit": "Segmentation candidates",
  "element_animation.backend": "Animation renderer",
  "element_animation.intensity": "Motion intensity",
  "element_animation.prompt": "Segmentation prompt"
}
```

- [ ] Run tests.

```powershell
python -m pytest tests/test_element_animation_ui_mapping.py -q
```

Expected result:

```text
1 passed
```

- [ ] Commit this task.

```powershell
git status --short
git add pixelle_video/config/schema.py pixelle_video/models/storyboard.py web/components/style_config.py web/components/output_preview.py web/i18n/locales/en_US.json web/i18n/locales/zh_CN.json tests/test_element_animation_ui_mapping.py
git commit -m "Add element animation configuration and UI mapping"
```

---

## Task 8: Integrate Python Renderer In FrameProcessor

**Purpose:** Make `python_ffmpeg` backend produce animated frame videos through the existing frame pipeline.

- [ ] Modify `pixelle_video/services/frame_processor.py`.

After image media is generated and downloaded, before HTML composition, add:

```python
if (
    getattr(config, "element_animation_enabled", False)
    and frame.media_type == "image"
    and frame.image_path
    and getattr(config, "element_animation_backend", "hyperframes_canvas") == "python_ffmpeg"
):
    output_dir = str(Path(frame.image_path).parent.parent)
    segmentation_service = ElementSegmentationService(core)
    manifest = segmentation_service.segment_image(
        image_path=frame.image_path,
        task_id=config.task_id,
        frame_index=frame.index,
        output_dir=output_dir,
        width=config.media_width,
        height=config.media_height,
        duration=frame.duration,
        fps=config.fps,
        selected_count=config.element_animation_subject_count,
        candidate_limit=config.element_animation_candidate_limit,
        prompt=config.element_animation_prompt,
        workflow=config.element_animation_workflow,
        backend="python_ffmpeg",
        intensity=config.element_animation_intensity,
        audio_path=frame.audio_path,
    )
    animated_path = get_task_frame_path(config.task_id, frame.index, "video")
    PythonElementAnimationRenderer().render_video(manifest, animated_path)
    frame.video_path = animated_path
    frame.media_type = "video"
```

Then the existing compose/video segment branch overlays HTML subtitles onto the animated video and keeps audio handling consistent.

- [ ] Add a focused processor test if the existing test harness can instantiate `FrameProcessor` with fake `core`.

Test expectation:

```python
assert frame.media_type == "video"
assert frame.video_path.endswith("_video.mp4")
```

Use monkeypatching to replace `ElementSegmentationService.segment_image` and `PythonElementAnimationRenderer.render_video` so the test does not call ComfyUI or FFmpeg.

- [ ] Run the focused frame processor tests.

```powershell
python -m pytest tests -q -k "frame_processor or element_animation"
```

Expected result: no failures in the selected tests.

- [ ] Commit this task.

```powershell
git status --short
git add pixelle_video/services/frame_processor.py tests
git commit -m "Render element animations through Python frame backend"
```

---

## Task 9: Integrate HyperFrames Backend Manifest Flow

**Purpose:** Make the preferred HyperFrames backend receive the element-animation manifest while preserving existing static clip generation.

- [ ] Identify where `RenderManifest` is assembled for HyperFrames generation.

Use:

```powershell
rg "RenderManifest\(" pixelle_video tests
rg "hyperframes" pixelle_video/services pixelle_video/pipelines tests
```

- [ ] In the HyperFrames render-manifest assembly path, when:

```python
config.element_animation_enabled is True
config.element_animation_backend == "hyperframes_canvas"
frame.media_type == "image"
frame.image_path is not None
```

call `ElementSegmentationService.segment_image(...)` with `backend="hyperframes_canvas"` and write the manifest JSON next to the task output:

```python
manifest_path = Path(task_output_dir) / "element_animation_manifest.json"
manifest_path.write_text(
    json.dumps(element_manifest.to_dict(), ensure_ascii=False, indent=2),
    encoding="utf-8",
)
render_manifest.element_animation_manifest_path = str(manifest_path)
```

- [ ] If multiple frames are included in one HyperFrames package, use:

```text
element_animation_manifest_frame_000.json
element_animation_manifest_frame_001.json
```

and add only the first manifest to `RenderManifest.element_animation_manifest_path` for the initial vertical slice. The later multi-frame carousel behavior is outside this task; the existing visual clips still render all frames.

- [ ] Add a render-manifest assembly test.

Expected assertion:

```python
assert render_manifest.element_animation_manifest_path.endswith("element_animation_manifest_frame_000.json")
```

Use monkeypatching to avoid ComfyUI execution.

- [ ] Run focused tests.

```powershell
python -m pytest tests -q -k "hyperframes or render_manifest or element_animation"
```

Expected result: no failures in selected tests.

- [ ] Commit this task.

```powershell
git status --short
git add pixelle_video pixelle_video/services tests
git commit -m "Pass element animation manifests to HyperFrames"
```

---

## Task 10: Add HyperFrames Canvas Template Support

**Purpose:** Animate selected segmented elements inside the existing HyperFrames rendering path.

- [ ] Locate the default HyperFrames HTML template.

Use:

```powershell
rg "__ELEMENT_ANIMATION_MANIFEST__|visual_clips|caption" templates pixelle_video -g "*.html" -g "*.js" -g "*.ts"
```

- [ ] Add a canvas animation module in the relevant template asset path.

The runtime script must:

```javascript
const manifestUrl = "__ELEMENT_ANIMATION_MANIFEST__";

async function loadElementAnimationManifest() {
  if (!manifestUrl) return null;
  const response = await fetch(manifestUrl);
  if (!response.ok) return null;
  return response.json();
}

function sampleTransform(animation, t, duration) {
  const bounds = animation.motion_bounds;
  const progress = duration <= 0 ? 0 : Math.max(0, Math.min(1, t / duration));
  const phase = ((animation.seed * 1009) % 6283) / 1000;
  const wave = Math.sin(progress * Math.PI * 2 + phase);
  const waveB = Math.cos(progress * Math.PI * 2 + phase * 1.7);
  return {
    x: wave * bounds.translate_px * 0.6,
    y: waveB * bounds.translate_px,
    rotate: wave * bounds.rotate_deg,
    scale: 1 + waveB * bounds.scale_delta,
  };
}

function drawLayer(ctx, image, transform, width, height) {
  ctx.save();
  ctx.translate(width / 2 + transform.x, height / 2 + transform.y);
  ctx.rotate((transform.rotate * Math.PI) / 180);
  ctx.scale(transform.scale, transform.scale);
  ctx.drawImage(image, -width / 2, -height / 2, width, height);
  ctx.restore();
}
```

- [ ] Ensure the canvas is full composition size and does not create cards or extra visible instructions.

CSS constraints:

```css
.element-animation-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
```

- [ ] Add a template unit test if the project has template snapshot tests. If no template test exists, add a compiler test that verifies `__ELEMENT_ANIMATION_MANIFEST__` is replaced.

- [ ] Run focused tests.

```powershell
python -m pytest tests -q -k "hyperframes or compiler or element_animation"
```

Expected result: no failures in selected tests.

- [ ] Commit this task.

```powershell
git status --short
git add templates pixelle_video/services/hyperframes_compiler.py tests
git commit -m "Animate segmented elements in HyperFrames"
```

---

## Task 11: Add SAM3.1 Workflow Contract And Dependency Docs

**Purpose:** Provide an explicit ComfyUI workflow contract and installation notes for native SAM3.1 support.

- [ ] Add `workflows/down/image_sam31_segment_依赖与下载说明.md`.

Content:

```markdown
# SAM3.1 元素分割工作流依赖

Pixelle 的元素微动增强功能优先使用 ComfyUI 原生 SAM3.1 节点。

## 推荐版本

- ComfyUI: 包含 `SAM3 Detect` / `SAM3 Track to Mask` 节点的版本
- 模型来源: `Comfy-Org/sam3.1`
- 官方参考: `facebookresearch/sam3`

## 工作流契约

`image_sam31_segment.json` 接收这些参数：

- `image`: 生成后的图片路径
- `prompt`: 主体分割提示词
- `candidate_limit`: 候选元素数量
- `selected_count`: 默认选中数量
- `width`: 输出宽度
- `height`: 输出高度

输出图片顺序：

1. `background.png`: 优先为移除主体后的背景
2. `element_001.png`
3. `mask_001.png`
4. `element_002.png`
5. `mask_002.png`

当工作流无法输出背景时，Pixelle 会使用 `source_image_low_motion` 背景模式，并自动降低背景运动幅度。
```

- [ ] Add `workflows/selfhost/image_sam31_segment.json`.

The JSON must be valid and must document the expected parameter names. Use the repository's existing workflow JSON structure if present. If existing workflow files are plain ComfyUI graphs, add a graph with a top-level `_pixelle_contract` object:

```json
{
  "_pixelle_contract": {
    "name": "image_sam31_segment",
    "description": "SAM3.1 segmentation workflow contract for element animation.",
    "inputs": ["image", "prompt", "candidate_limit", "selected_count", "width", "height"],
    "outputs": ["background", "element_mask_pairs"],
    "preferred_nodes": ["SAM3 Detect", "SAM3 Track to Mask"]
  }
}
```

- [ ] Add a JSON validity test if workflow tests already exist. Otherwise run:

```powershell
python -m json.tool workflows/selfhost/image_sam31_segment.json > $null
```

Expected result: command exits successfully.

- [ ] Commit this task.

```powershell
git status --short
git add workflows/down/image_sam31_segment_依赖与下载说明.md workflows/selfhost/image_sam31_segment.json
git commit -m "Document SAM3.1 ComfyUI segmentation workflow"
```

---

## Task 12: Final Verification

**Purpose:** Confirm the vertical slice is stable before handing it back.

- [ ] Run focused test suite.

```powershell
python -m pytest `
  tests/test_element_animation_models.py `
  tests/test_element_animation_presets.py `
  tests/test_element_segmentation_service.py `
  tests/test_element_animation_renderer.py `
  tests/test_render_package_models.py `
  tests/test_hyperframes_project_service.py `
  tests/test_element_animation_ui_mapping.py `
  -q
```

Expected result: all selected tests pass.

- [ ] Run broader smoke tests.

```powershell
python -m pytest tests -q -k "element_animation or hyperframes or render_package or frame_processor"
```

Expected result: no selected test failures.

- [ ] Check worktree and commit history.

```powershell
git status --short
git log --oneline -8
```

Expected result:

- Only intentional implementation files are modified or committed.
- Pre-existing unrelated dirty files remain untouched.

- [ ] Push branch.

```powershell
git push
```

Expected result:

```text
To ...
   <old>..<new>  dev -> dev
```

---

## Rollout Notes

- Default UI behavior remains unchanged until the user enables element micro-motion.
- The default generated video behavior uses 3 selected subjects.
- HyperFrames is the preferred renderer for rich canvas animation.
- Python/FFmpeg is a selectable renderer and is useful for local lightweight rendering.
- For simple line-art or prominent-subject images, `candidate_limit=3` and `selected_count=3` should usually be enough.
- If SAM3.1 workflow output lacks a clean background, source-image background mode must stay visually subtle.

## Manual QA Checklist

- [ ] Generate a simple drawing image with 3 clear foreground elements.
- [ ] Enable element micro-motion with default settings.
- [ ] Confirm 3 subjects are selected and animated.
- [ ] Increase candidate limit to 5 and selected subjects to 4 from advanced options.
- [ ] Render once with `hyperframes_canvas`.
- [ ] Render once with `python_ffmpeg`.
- [ ] Confirm captions/HTML overlays still appear on the final video.
- [ ] Confirm background does not visibly double the moving subjects when `source_image_low_motion` is used.
