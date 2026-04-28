# Video Media Size Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an explicit size contract so final video canvas dimensions and generated media dimensions are independently controlled, with image generation defaulting to `768x768` and optional sync to the final canvas.

**Architecture:** Add a domain-level size contract module, then thread it through Web UI request construction, API request construction, `StoryboardConfig`, standard pipeline rendering, template rendering, and element animation. Templates remain layout assets with their own base coordinate system; rendered frames are normalized to the requested output canvas.

**Tech Stack:** Python 3.11, dataclasses, Pydantic v2, Streamlit, FastAPI, pytest, Pillow, Playwright-backed HTML rendering.

---

## File Structure

- Create `pixelle_video/models/size_contract.py`
  - Owns all orientation/preset/default/sync rules.
  - Provides `GenerationSizeContract.from_params()` as the single new size resolution entry point.

- Modify `pixelle_video/models/storyboard.py`
  - Adds `canvas_width` / `canvas_height` to `StoryboardConfig`.
  - Keeps legacy constructor compatibility by resolving missing canvas dimensions from media dimensions.

- Modify `pixelle_video/pipelines/standard.py`
  - Resolves the size contract during storyboard initialization.
  - Uses canvas dimensions for final render manifests, HyperFrames canvas, and element-motion work on composed frames.

- Modify `pixelle_video/services/frame_html.py`
  - Supports target canvas dimensions while rendering templates at their base coordinate system.
  - Normalizes the rendered PNG to the target canvas with Pillow.

- Modify `pixelle_video/services/template_visual_materializer.py`
  - Accepts canvas dimensions and passes them to `HTMLFrameGenerator`.

- Modify `web/components/style_config.py`
  - Renders final video size controls.
  - Computes media size from the shared size contract instead of template meta.
  - Keeps template meta only as recommendation/compatibility information.

- Modify `web/components/output_preview.py`
  - Copies explicit canvas/media size params from `video_params`.
  - Stops using `session_state["template_media_width"]` as the source of generation request dimensions.

- Modify `api/schemas/video.py` and `api/routers/video.py`
  - Adds optional canvas/media fields to the API schema.
  - Stops forcing template-derived media sizes into API requests.

- Modify `pixelle_video/utils/template_util.py`
  - Adds a helper to resolve an orientation-compatible template for a selected template type.

- Modify `web/i18n/locales/zh_CN.json` and `web/i18n/locales/en_US.json`
  - Adds labels for final video size, media size, orientation, resolution, and sync controls.

- Tests:
  - Create `tests/test_size_contract.py`
  - Create or extend `tests/test_storyboard_size_contract.py`
  - Extend `tests/test_output_preview.py`
  - Extend `tests/test_video_api.py`
  - Extend `tests/test_frame_html.py`
  - Extend `tests/test_standard_pipeline_hyperframes_mode.py`
  - Add or extend template utility tests.

## Repo Constraint

`AGENTS.md` forbids using `git worktree` for this repository. Execute this plan in the current workspace and commit only files touched by each task. The workspace already contains unrelated user changes; do not revert them.

## Task 1: Core Size Contract

**Files:**
- Create: `pixelle_video/models/size_contract.py`
- Create: `tests/test_size_contract.py`

- [ ] **Step 1: Write failing tests for default values, presets, sync, and legacy media fallback**

Add `tests/test_size_contract.py`:

```python
import pytest

from pixelle_video.models.size_contract import (
    DEFAULT_MEDIA_SIZE,
    GenerationSizeContract,
    SizeSpec,
    resolve_canvas_size,
)


def test_default_generation_size_contract_keeps_video_and_media_independent():
    contract = GenerationSizeContract.default()

    assert (contract.canvas_width, contract.canvas_height) == (1280, 720)
    assert (contract.media_width, contract.media_height) == (768, 768)
    assert contract.video_orientation == "landscape"
    assert contract.video_resolution_preset == "1k"
    assert contract.sync_media_size_to_canvas is False


@pytest.mark.parametrize(
    ("orientation", "preset", "expected"),
    [
        ("landscape", "1k", SizeSpec(1280, 720)),
        ("landscape", "2k", SizeSpec(1920, 1080)),
        ("landscape", "4k", SizeSpec(3840, 2160)),
        ("portrait", "1k", SizeSpec(720, 1280)),
        ("portrait", "2k", SizeSpec(1080, 1920)),
        ("portrait", "4k", SizeSpec(2160, 3840)),
        ("square", "1k", SizeSpec(1024, 1024)),
        ("square", "2k", SizeSpec(2048, 2048)),
        ("square", "4k", SizeSpec(4096, 4096)),
    ],
)
def test_resolve_canvas_size_for_orientation_presets(orientation, preset, expected):
    assert resolve_canvas_size(orientation, preset) == expected


def test_media_size_defaults_to_768_square_when_sync_is_off():
    contract = GenerationSizeContract.from_params(
        {
            "video_orientation": "portrait",
            "video_resolution_preset": "2k",
            "sync_media_size_to_canvas": False,
        }
    )

    assert (contract.canvas_width, contract.canvas_height) == (1080, 1920)
    assert (contract.media_width, contract.media_height) == DEFAULT_MEDIA_SIZE.as_tuple()


def test_media_size_syncs_to_canvas_when_enabled():
    contract = GenerationSizeContract.from_params(
        {
            "video_orientation": "landscape",
            "video_resolution_preset": "4k",
            "sync_media_size_to_canvas": True,
        }
    )

    assert (contract.canvas_width, contract.canvas_height) == (3840, 2160)
    assert (contract.media_width, contract.media_height) == (3840, 2160)


def test_explicit_canvas_and_media_dimensions_take_precedence():
    contract = GenerationSizeContract.from_params(
        {
            "canvas_width": 1280,
            "canvas_height": 720,
            "media_width": 1024,
            "media_height": 1024,
        }
    )

    assert (contract.canvas_width, contract.canvas_height) == (1280, 720)
    assert (contract.media_width, contract.media_height) == (1024, 1024)


def test_legacy_media_only_request_uses_media_as_canvas():
    contract = GenerationSizeContract.from_params(
        {
            "media_width": 1080,
            "media_height": 1920,
        }
    )

    assert (contract.canvas_width, contract.canvas_height) == (1080, 1920)
    assert (contract.media_width, contract.media_height) == (1080, 1920)


def test_missing_dimensions_uses_new_defaults():
    contract = GenerationSizeContract.from_params({})

    assert (contract.canvas_width, contract.canvas_height) == (1280, 720)
    assert (contract.media_width, contract.media_height) == (768, 768)


@pytest.mark.parametrize(
    "params",
    [
        {"video_orientation": "circle"},
        {"video_resolution_preset": "8k"},
        {"canvas_width": 0, "canvas_height": 720},
        {"media_width": 768, "media_height": -1},
    ],
)
def test_invalid_size_contract_inputs_raise_value_error(params):
    with pytest.raises(ValueError):
        GenerationSizeContract.from_params(params)
```

- [ ] **Step 2: Run the new tests and verify they fail because the module does not exist**

Run:

```bash
pytest tests/test_size_contract.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'pixelle_video.models.size_contract'`.

- [ ] **Step 3: Implement the size contract module**

Create `pixelle_video/models/size_contract.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


VALID_ORIENTATIONS = ("landscape", "portrait", "square")
VALID_RESOLUTION_PRESETS = ("1k", "2k", "4k")


@dataclass(frozen=True)
class SizeSpec:
    width: int
    height: int

    def __post_init__(self) -> None:
        if int(self.width) <= 0 or int(self.height) <= 0:
            raise ValueError("size dimensions must be positive")

    def as_tuple(self) -> tuple[int, int]:
        return int(self.width), int(self.height)


DEFAULT_VIDEO_ORIENTATION = "landscape"
DEFAULT_VIDEO_RESOLUTION_PRESET = "1k"
DEFAULT_MEDIA_SIZE = SizeSpec(768, 768)

VIDEO_SIZE_PRESETS: dict[str, dict[str, SizeSpec]] = {
    "landscape": {
        "1k": SizeSpec(1280, 720),
        "2k": SizeSpec(1920, 1080),
        "4k": SizeSpec(3840, 2160),
    },
    "portrait": {
        "1k": SizeSpec(720, 1280),
        "2k": SizeSpec(1080, 1920),
        "4k": SizeSpec(2160, 3840),
    },
    "square": {
        "1k": SizeSpec(1024, 1024),
        "2k": SizeSpec(2048, 2048),
        "4k": SizeSpec(4096, 4096),
    },
}


def _normalize_optional_string(value: Any, default: str) -> str:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    return normalized or default


def normalize_video_orientation(value: Any = None) -> str:
    orientation = _normalize_optional_string(value, DEFAULT_VIDEO_ORIENTATION)
    if orientation not in VIDEO_SIZE_PRESETS:
        raise ValueError(f"unsupported video orientation: {orientation}")
    return orientation


def normalize_video_resolution_preset(value: Any = None) -> str:
    preset = _normalize_optional_string(value, DEFAULT_VIDEO_RESOLUTION_PRESET)
    aliases = {
        "1280x720": "1k",
        "720x1280": "1k",
        "1024x1024": "1k",
        "1920x1080": "2k",
        "1080x1920": "2k",
        "2048x2048": "2k",
        "3840x2160": "4k",
        "2160x3840": "4k",
        "4096x4096": "4k",
    }
    preset = aliases.get(preset, preset)
    if preset not in VALID_RESOLUTION_PRESETS:
        raise ValueError(f"unsupported video resolution preset: {preset}")
    return preset


def resolve_canvas_size(orientation: Any = None, preset: Any = None) -> SizeSpec:
    normalized_orientation = normalize_video_orientation(orientation)
    normalized_preset = normalize_video_resolution_preset(preset)
    return VIDEO_SIZE_PRESETS[normalized_orientation][normalized_preset]


def _optional_int_pair(params: Mapping[str, Any], width_key: str, height_key: str) -> SizeSpec | None:
    width = params.get(width_key)
    height = params.get(height_key)
    if width is None and height is None:
        return None
    if width is None or height is None:
        raise ValueError(f"{width_key} and {height_key} must be provided together")
    return SizeSpec(int(width), int(height))


def _has_new_canvas_intent(params: Mapping[str, Any]) -> bool:
    return any(
        key in params and params.get(key) is not None
        for key in (
            "canvas_width",
            "canvas_height",
            "video_orientation",
            "video_resolution_preset",
            "sync_media_size_to_canvas",
        )
    )


@dataclass(frozen=True)
class GenerationSizeContract:
    canvas_width: int
    canvas_height: int
    media_width: int
    media_height: int
    video_orientation: str = DEFAULT_VIDEO_ORIENTATION
    video_resolution_preset: str = DEFAULT_VIDEO_RESOLUTION_PRESET
    sync_media_size_to_canvas: bool = False

    @classmethod
    def default(cls) -> "GenerationSizeContract":
        return cls.from_params({})

    @classmethod
    def from_params(cls, params: Mapping[str, Any] | None) -> "GenerationSizeContract":
        source = dict(params or {})
        orientation = normalize_video_orientation(source.get("video_orientation"))
        preset = normalize_video_resolution_preset(source.get("video_resolution_preset"))
        sync = bool(source.get("sync_media_size_to_canvas", False))

        explicit_canvas = _optional_int_pair(source, "canvas_width", "canvas_height")
        explicit_media = _optional_int_pair(source, "media_width", "media_height")

        if explicit_canvas is not None:
            canvas = explicit_canvas
        elif explicit_media is not None and not _has_new_canvas_intent(source):
            canvas = explicit_media
        else:
            canvas = resolve_canvas_size(orientation, preset)

        if sync:
            media = canvas
        elif explicit_media is not None:
            media = explicit_media
        else:
            media = DEFAULT_MEDIA_SIZE

        return cls(
            canvas_width=canvas.width,
            canvas_height=canvas.height,
            media_width=media.width,
            media_height=media.height,
            video_orientation=orientation,
            video_resolution_preset=preset,
            sync_media_size_to_canvas=sync,
        )

    def to_params(self) -> dict[str, Any]:
        return {
            "canvas_width": int(self.canvas_width),
            "canvas_height": int(self.canvas_height),
            "media_width": int(self.media_width),
            "media_height": int(self.media_height),
            "video_orientation": self.video_orientation,
            "video_resolution_preset": self.video_resolution_preset,
            "sync_media_size_to_canvas": bool(self.sync_media_size_to_canvas),
        }
```

- [ ] **Step 4: Run the size contract tests and verify they pass**

Run:

```bash
pytest tests/test_size_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add pixelle_video/models/size_contract.py tests/test_size_contract.py
git commit -m "feat: 增加视频与素材尺寸合同"
```

## Task 2: StoryboardConfig And Pipeline Size Initialization

**Files:**
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Create: `tests/test_storyboard_size_contract.py`
- Modify: `tests/test_tts_comfyui_defaults.py`

- [ ] **Step 1: Write failing StoryboardConfig tests**

Create `tests/test_storyboard_size_contract.py`:

```python
from pixelle_video.models.storyboard import StoryboardConfig


def test_storyboard_config_defaults_canvas_to_media_for_legacy_constructor():
    config = StoryboardConfig(media_width=1080, media_height=1920)

    assert (config.canvas_width, config.canvas_height) == (1080, 1920)
    assert (config.media_width, config.media_height) == (1080, 1920)


def test_storyboard_config_preserves_distinct_canvas_and_media_sizes():
    config = StoryboardConfig(
        canvas_width=1280,
        canvas_height=720,
        media_width=768,
        media_height=768,
        video_orientation="landscape",
        video_resolution_preset="1k",
        sync_media_size_to_canvas=False,
    )

    assert (config.canvas_width, config.canvas_height) == (1280, 720)
    assert (config.media_width, config.media_height) == (768, 768)
    assert config.video_orientation == "landscape"
    assert config.video_resolution_preset == "1k"
    assert config.sync_media_size_to_canvas is False
```

- [ ] **Step 2: Write failing pipeline initialization test**

Append to `tests/test_tts_comfyui_defaults.py`:

```python

@pytest.mark.asyncio
async def test_standard_pipeline_initializes_distinct_canvas_and_media_sizes():
    pipeline = StandardPipeline(_FakeCore())
    ctx = PipelineContext(
        input_text="测试文本。",
        params={
            "canvas_width": 1280,
            "canvas_height": 720,
            "media_width": 768,
            "media_height": 768,
            "video_orientation": "landscape",
            "video_resolution_preset": "1k",
            "sync_media_size_to_canvas": False,
        },
    )
    ctx.task_id = "task-size-contract"
    ctx.title = "Size Contract"
    ctx.storyboard_plan = _single_frame_plan()
    ctx.image_prompts = ["prompt"]

    await pipeline.initialize_storyboard(ctx)

    assert (ctx.config.canvas_width, ctx.config.canvas_height) == (1280, 720)
    assert (ctx.config.media_width, ctx.config.media_height) == (768, 768)
    assert ctx.config.video_orientation == "landscape"
    assert ctx.config.video_resolution_preset == "1k"
```

- [ ] **Step 3: Run tests and verify they fail on missing canvas fields**

Run:

```bash
pytest tests/test_storyboard_size_contract.py tests/test_tts_comfyui_defaults.py::test_standard_pipeline_initializes_distinct_canvas_and_media_sizes -q
```

Expected: FAIL because `StoryboardConfig` has no `canvas_width` / `canvas_height`.

- [ ] **Step 4: Add canvas fields to StoryboardConfig**

Modify `pixelle_video/models/storyboard.py`:

```python
    media_width: int
    media_height: int
    canvas_width: Optional[int] = None
    canvas_height: Optional[int] = None
```

Add near other generation fields:

```python
    video_orientation: str = "landscape"
    video_resolution_preset: str = "1k"
    sync_media_size_to_canvas: bool = False
```

Add this block at the beginning of `__post_init__`:

```python
        self.media_width = int(self.media_width)
        self.media_height = int(self.media_height)
        if self.canvas_width is None:
            self.canvas_width = self.media_width
        if self.canvas_height is None:
            self.canvas_height = self.media_height
        self.canvas_width = int(self.canvas_width)
        self.canvas_height = int(self.canvas_height)
        if self.canvas_width <= 0 or self.canvas_height <= 0:
            raise ValueError("canvas dimensions must be positive")
        if self.media_width <= 0 or self.media_height <= 0:
            raise ValueError("media dimensions must be positive")
        self.sync_media_size_to_canvas = bool(self.sync_media_size_to_canvas)
```

- [ ] **Step 5: Resolve the size contract in StandardPipeline.initialize_storyboard**

Modify `pixelle_video/pipelines/standard.py` imports:

```python
from pixelle_video.models.size_contract import GenerationSizeContract
```

In `initialize_storyboard`, before constructing `StoryboardConfig`, add:

```python
        size_contract = GenerationSizeContract.from_params(ctx.params)
```

Replace the existing `media_width` / `media_height` arguments with:

```python
            canvas_width=size_contract.canvas_width,
            canvas_height=size_contract.canvas_height,
            media_width=size_contract.media_width,
            media_height=size_contract.media_height,
            video_orientation=size_contract.video_orientation,
            video_resolution_preset=size_contract.video_resolution_preset,
            sync_media_size_to_canvas=size_contract.sync_media_size_to_canvas,
```

- [ ] **Step 6: Run the task tests and verify they pass**

Run:

```bash
pytest tests/test_storyboard_size_contract.py tests/test_tts_comfyui_defaults.py::test_standard_pipeline_initializes_distinct_canvas_and_media_sizes -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add pixelle_video/models/storyboard.py pixelle_video/pipelines/standard.py tests/test_storyboard_size_contract.py tests/test_tts_comfyui_defaults.py
git commit -m "feat: 在故事板配置中拆分画布和素材尺寸"
```

## Task 3: Web Request Size Copying

**Files:**
- Modify: `web/components/output_preview.py`
- Modify: `tests/test_output_preview.py`
- Modify: `tests/test_element_animation_ui_mapping.py`

- [ ] **Step 1: Write failing tests for single and batch request builders**

Append to `tests/test_output_preview.py`:

```python

def test_build_single_generation_request_uses_video_params_size_contract_not_template_session():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "canvas_width": 1280,
            "canvas_height": 720,
            "media_width": 768,
            "media_height": 768,
            "video_orientation": "landscape",
            "video_resolution_preset": "1k",
            "sync_media_size_to_canvas": False,
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["canvas_width"] == 1280
    assert request["canvas_height"] == 720
    assert request["media_width"] == 768
    assert request["media_height"] == 768
    assert request["video_orientation"] == "landscape"
    assert request["video_resolution_preset"] == "1k"
    assert request["sync_media_size_to_canvas"] is False


def test_build_single_generation_request_defaults_to_size_contract_when_missing_sizes():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {"text": "demo", "mode": "generate", "tts_inference_mode": "local"},
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["canvas_width"] == 1280
    assert request["canvas_height"] == 720
    assert request["media_width"] == 768
    assert request["media_height"] == 768


def test_build_batch_shared_config_copies_size_contract():
    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "canvas_width": 1080,
            "canvas_height": 1920,
            "media_width": 1080,
            "media_height": 1920,
            "video_orientation": "portrait",
            "video_resolution_preset": "2k",
            "sync_media_size_to_canvas": True,
        }
    )

    assert shared_config["canvas_width"] == 1080
    assert shared_config["canvas_height"] == 1920
    assert shared_config["media_width"] == 1080
    assert shared_config["media_height"] == 1920
    assert shared_config["sync_media_size_to_canvas"] is True
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
pytest tests/test_output_preview.py::test_build_single_generation_request_uses_video_params_size_contract_not_template_session tests/test_output_preview.py::test_build_single_generation_request_defaults_to_size_contract_when_missing_sizes tests/test_output_preview.py::test_build_batch_shared_config_copies_size_contract -q
```

Expected: FAIL because `canvas_width` is not copied and single generation still reads template media session state.

- [ ] **Step 3: Implement a shared request-copy helper**

Modify `web/components/output_preview.py` imports:

```python
from pixelle_video.models.size_contract import GenerationSizeContract
```

Add:

```python
SIZE_CONTRACT_OPTION_KEYS = (
    "canvas_width",
    "canvas_height",
    "media_width",
    "media_height",
    "video_orientation",
    "video_resolution_preset",
    "sync_media_size_to_canvas",
)


def copy_generation_size_params(source, target):
    contract = GenerationSizeContract.from_params(source)
    target.update(contract.to_params())
```

In `build_single_generation_request`, replace:

```python
        "media_width": session_state.get("template_media_width"),
        "media_height": session_state.get("template_media_height"),
```

with no inline size fields, then call after the request dict is created:

```python
    copy_generation_size_params(video_params, request)
```

In `build_batch_shared_config`, remove inline `media_width` / `media_height` and call:

```python
    copy_generation_size_params(video_params, shared_config)
```

- [ ] **Step 4: Update element animation request tests that only asserted options**

If `tests/test_element_animation_ui_mapping.py` expected template session state to set media dimensions indirectly, update those tests to assert animation options only and let the new output-preview size contract tests own size behavior. Do not remove animation option assertions.

- [ ] **Step 5: Run output preview and element animation request tests**

Run:

```bash
pytest tests/test_output_preview.py tests/test_element_animation_ui_mapping.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add web/components/output_preview.py tests/test_output_preview.py tests/test_element_animation_ui_mapping.py
git commit -m "feat: Web 请求使用显式尺寸合同"
```

## Task 4: API Schema And Router Size Contract

**Files:**
- Modify: `api/schemas/video.py`
- Modify: `api/routers/video.py`
- Modify: `tests/test_video_api.py`

- [ ] **Step 1: Write failing API parameter tests**

Append to `tests/test_video_api.py`:

```python

def test_video_generate_request_accepts_explicit_canvas_and_media_sizes():
    request = VideoGenerateRequest(
        text="demo",
        canvas_width=1280,
        canvas_height=720,
        media_width=768,
        media_height=768,
        video_orientation="landscape",
        video_resolution_preset="1k",
        sync_media_size_to_canvas=False,
    )

    assert request.canvas_width == 1280
    assert request.canvas_height == 720
    assert request.media_width == 768
    assert request.media_height == 768
    assert request.video_orientation == "landscape"
    assert request.video_resolution_preset == "1k"


def test_build_video_generation_params_uses_request_size_contract():
    request = VideoGenerateRequest(
        text="demo",
        canvas_width=1280,
        canvas_height=720,
        media_width=768,
        media_height=768,
        video_orientation="landscape",
        video_resolution_preset="1k",
    )

    params = build_video_generation_params(request, request_id="req_size")

    assert params["canvas_width"] == 1280
    assert params["canvas_height"] == 720
    assert params["media_width"] == 768
    assert params["media_height"] == 768
    assert params["video_orientation"] == "landscape"
    assert params["video_resolution_preset"] == "1k"


def test_build_video_generation_params_defaults_when_request_has_no_sizes():
    request = VideoGenerateRequest(text="demo")

    params = build_video_generation_params(request, request_id="req_default")

    assert params["canvas_width"] == 1280
    assert params["canvas_height"] == 720
    assert params["media_width"] == 768
    assert params["media_height"] == 768
```

Ensure imports include:

```python
from api.routers.video import build_video_generation_params
from api.schemas.video import VideoGenerateRequest
```

- [ ] **Step 2: Run the new API tests and verify they fail**

Run:

```bash
pytest tests/test_video_api.py::test_video_generate_request_accepts_explicit_canvas_and_media_sizes tests/test_video_api.py::test_build_video_generation_params_uses_request_size_contract tests/test_video_api.py::test_build_video_generation_params_defaults_when_request_has_no_sizes -q
```

Expected: FAIL because `VideoGenerateRequest` forbids the new fields and `build_video_generation_params` requires template-derived media dimensions.

- [ ] **Step 3: Add API schema fields**

Modify `api/schemas/video.py` imports:

```python
from pixelle_video.models.size_contract import (
    DEFAULT_MEDIA_SIZE,
    DEFAULT_VIDEO_ORIENTATION,
    DEFAULT_VIDEO_RESOLUTION_PRESET,
)
```

Add fields in the media/video parameter area:

```python
    canvas_width: Optional[int] = Field(
        None,
        ge=1,
        le=4096,
        description="Final video canvas width. Defaults to the selected orientation/preset.",
    )
    canvas_height: Optional[int] = Field(
        None,
        ge=1,
        le=4096,
        description="Final video canvas height. Defaults to the selected orientation/preset.",
    )
    media_width: Optional[int] = Field(
        None,
        ge=1,
        le=4096,
        description=f"Generated media width. Defaults to {DEFAULT_MEDIA_SIZE.width}.",
    )
    media_height: Optional[int] = Field(
        None,
        ge=1,
        le=4096,
        description=f"Generated media height. Defaults to {DEFAULT_MEDIA_SIZE.height}.",
    )
    video_orientation: Optional[Literal["landscape", "portrait", "square"]] = Field(
        DEFAULT_VIDEO_ORIENTATION,
        description="Final video orientation preset group.",
    )
    video_resolution_preset: Optional[Literal["1k", "2k", "4k"]] = Field(
        DEFAULT_VIDEO_RESOLUTION_PRESET,
        description="Final video resolution preset within the selected orientation.",
    )
    sync_media_size_to_canvas: bool = Field(
        False,
        description="When true, generated media dimensions follow the final canvas size.",
    )
```

- [ ] **Step 4: Refactor router request building to use GenerationSizeContract**

Modify `api/routers/video.py` imports:

```python
from pixelle_video.models.size_contract import GenerationSizeContract
```

Change signature:

```python
def build_video_generation_params(
    request_body: VideoGenerateRequest,
    *,
    request_id: str,
    api_task_id: str | None = None,
) -> dict:
```

At the top of the function:

```python
    size_contract = GenerationSizeContract.from_params(
        request_body.model_dump(exclude_none=True)
    )
```

Replace inline media fields with:

```python
        **size_contract.to_params(),
```

Remove `media_width` / `media_height` arguments from `generate_video_sync()` and `execute_video_generation()`. Keep `resolve_video_media_size()` only if other endpoints still use it; do not call it from standard video generation.

- [ ] **Step 5: Update existing API tests that expected template-derived dimensions**

In `tests/test_video_api.py`, update existing expected calls so default API requests now contain:

```python
"canvas_width": 1280,
"canvas_height": 720,
"media_width": 768,
"media_height": 768,
"video_orientation": "landscape",
"video_resolution_preset": "1k",
"sync_media_size_to_canvas": False,
```

Replace old expectations of `"media_width": 1080, "media_height": 1920` for default API requests.

- [ ] **Step 6: Run API tests**

Run:

```bash
pytest tests/test_video_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add api/schemas/video.py api/routers/video.py tests/test_video_api.py
git commit -m "feat: API 使用显式视频尺寸合同"
```

## Task 5: Template Rendering Canvas Normalization

**Files:**
- Modify: `pixelle_video/services/frame_html.py`
- Modify: `pixelle_video/services/template_visual_materializer.py`
- Modify: `tests/test_frame_html.py`
- Modify: `tests/test_template_visual_materializer.py`

- [ ] **Step 1: Write failing HTMLFrameGenerator canvas normalization test**

Append to `tests/test_frame_html.py`:

```python

def test_html_frame_generator_normalizes_rendered_frame_to_requested_canvas(monkeypatch, tmp_path):
    from PIL import Image

    captured = {}

    class FakePage:
        async def goto(self, url, wait_until):
            captured["goto"] = (url, wait_until)

        async def screenshot(self, path, type, omit_background):
            Image.new("RGBA", (1920, 1080), (255, 0, 0, 255)).save(path)

        async def close(self):
            captured["closed"] = True

    class FakeBrowser:
        async def new_page(self, viewport, device_scale_factor):
            captured["viewport"] = viewport
            captured["device_scale_factor"] = device_scale_factor
            return FakePage()

    async def fake_ensure_browser():
        return FakeBrowser()

    monkeypatch.setattr(HTMLFrameGenerator, "_ensure_browser", staticmethod(fake_ensure_browser))

    generator = HTMLFrameGenerator(
        "templates/1920x1080/image_landscape_full.html",
        canvas_width=1280,
        canvas_height=720,
    )
    output_path = tmp_path / "normalized.png"

    run_async(
        generator.generate_frame(
            title="Demo",
            text="Body",
            image="",
            ext={"index": 1},
            output_path=str(output_path),
        )
    )

    with Image.open(output_path) as image:
        assert image.size == (1280, 720)

    assert captured["viewport"] == {"width": 1920, "height": 1080}
```

- [ ] **Step 2: Write failing materializer canvas forwarding test**

Append to `tests/test_template_visual_materializer.py`:

```python

def test_template_visual_materializer_forwards_canvas_size_to_html_generator(monkeypatch, tmp_path):
    from pixelle_video.services import template_visual_materializer as module

    captured = {}

    class FakeGenerator:
        def __init__(self, template_path, canvas_width=None, canvas_height=None):
            captured["init"] = (template_path, canvas_width, canvas_height)
            self.width = canvas_width
            self.height = canvas_height

        async def generate_frame(self, title, text, image, ext, output_path):
            captured["generate"] = (title, text, image, ext, output_path)
            Path(output_path).write_bytes(b"png")
            return output_path

    monkeypatch.setattr(module, "HTMLFrameGenerator", FakeGenerator)

    materializer = module.TemplateVisualMaterializer()
    result = run_async(
        materializer.materialize_frame(
            title="Demo",
            template_body_text="Body",
            media_path=None,
            frame_index=0,
            template_path="templates/1920x1080/image_landscape_full.html",
            template_id="image_landscape_full",
            output_path=tmp_path / "frame.png",
            text_policy="template_body",
            template_params=None,
            canvas_width=1280,
            canvas_height=720,
        )
    )

    assert captured["init"] == (
        "templates/1920x1080/image_landscape_full.html",
        1280,
        720,
    )
    assert (result.width, result.height) == (1280, 720)
```

Ensure test imports include `Path` and `run_async` if not present.

- [ ] **Step 3: Run focused tests and verify they fail**

Run:

```bash
pytest tests/test_frame_html.py::test_html_frame_generator_normalizes_rendered_frame_to_requested_canvas tests/test_template_visual_materializer.py::test_template_visual_materializer_forwards_canvas_size_to_html_generator -q
```

Expected: FAIL because constructor args and materializer args are unsupported.

- [ ] **Step 4: Implement HTMLFrameGenerator canvas normalization**

Modify `pixelle_video/services/frame_html.py` imports:

```python
from PIL import Image
```

Change constructor:

```python
    def __init__(
        self,
        template_path: str,
        *,
        canvas_width: int | None = None,
        canvas_height: int | None = None,
        canvas_fit: str = "contain",
    ):
```

After parsing template size:

```python
        self.template_width, self.template_height = parse_template_size(template_path)
        self.width = int(canvas_width) if canvas_width is not None else self.template_width
        self.height = int(canvas_height) if canvas_height is not None else self.template_height
        self.canvas_fit = canvas_fit
```

In `generate_frame`, keep Playwright viewport at template size:

```python
                viewport={"width": self.template_width, "height": self.template_height},
```

After `page.screenshot(...)`, call:

```python
                self._normalize_output_canvas(output_path)
```

Add helper:

```python
    def _normalize_output_canvas(self, output_path: str) -> None:
        target_size = (int(self.width), int(self.height))
        template_size = (int(self.template_width), int(self.template_height))
        if target_size == template_size:
            return

        with Image.open(output_path) as image:
            frame = image.convert("RGBA")
            if self.canvas_fit == "cover":
                scale = max(target_size[0] / frame.width, target_size[1] / frame.height)
            else:
                scale = min(target_size[0] / frame.width, target_size[1] / frame.height)
            resized_size = (
                max(1, int(round(frame.width * scale))),
                max(1, int(round(frame.height * scale))),
            )
            resized = frame.resize(resized_size, Image.Resampling.LANCZOS)
            if self.canvas_fit == "cover":
                left = max(0, (resized.width - target_size[0]) // 2)
                top = max(0, (resized.height - target_size[1]) // 2)
                normalized = resized.crop(
                    (left, top, left + target_size[0], top + target_size[1])
                )
            else:
                normalized = Image.new("RGBA", target_size, (0, 0, 0, 0))
                left = (target_size[0] - resized.width) // 2
                top = (target_size[1] - resized.height) // 2
                normalized.alpha_composite(resized, (left, top))
            normalized.save(output_path)
```

- [ ] **Step 5: Forward canvas dimensions through TemplateVisualMaterializer**

Modify `pixelle_video/services/template_visual_materializer.py` `materialize_frame()` signature:

```python
        canvas_width: int | None = None,
        canvas_height: int | None = None,
```

Construct generator:

```python
        generator = HTMLFrameGenerator(
            str(template_path),
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )
```

- [ ] **Step 6: Run frame and materializer tests**

Run:

```bash
pytest tests/test_frame_html.py tests/test_template_visual_materializer.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add pixelle_video/services/frame_html.py pixelle_video/services/template_visual_materializer.py tests/test_frame_html.py tests/test_template_visual_materializer.py
git commit -m "feat: 模板渲染归一化到目标画布"
```

## Task 6: Template Orientation Resolution And UI Controls

**Files:**
- Modify: `pixelle_video/utils/template_util.py`
- Modify: `web/components/style_config.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Create or modify: `tests/test_template_util.py`
- Extend: `tests/test_style_config_template_gallery.py`

- [ ] **Step 1: Write failing template orientation resolver tests**

Create `tests/test_template_util.py`:

```python
from pixelle_video.utils.template_util import (
    get_template_orientation,
    resolve_compatible_template_for_orientation,
)


def test_get_template_orientation_from_size_directory():
    assert get_template_orientation("1920x1080/image_full.html") == "landscape"
    assert get_template_orientation("1080x1920/image_default.html") == "portrait"
    assert get_template_orientation("1080x1080/image_minimal_framed.html") == "square"


def test_resolve_compatible_template_switches_to_matching_orientation():
    selected = resolve_compatible_template_for_orientation(
        current_template="1080x1920/image_default.html",
        template_type="image",
        orientation="landscape",
    )

    assert selected.startswith("1920x1080/")
    assert selected.split("/")[-1].startswith("image_")
```

- [ ] **Step 2: Run the template utility tests and verify they fail**

Run:

```bash
pytest tests/test_template_util.py -q
```

Expected: FAIL because the resolver functions do not exist.

- [ ] **Step 3: Implement template orientation helpers**

Modify `pixelle_video/utils/template_util.py`:

```python
def get_template_orientation(template_path: str) -> str:
    width, height = parse_template_size(template_path)
    if width > height:
        return "landscape"
    if height > width:
        return "portrait"
    return "square"


def resolve_compatible_template_for_orientation(
    *,
    current_template: str,
    template_type: Literal["static", "image", "video"],
    orientation: str,
) -> str:
    if get_template_orientation(current_template) == orientation:
        return current_template

    grouped = get_templates_grouped_by_size_and_type(template_type)
    candidates = [
        template
        for templates in grouped.values()
        for template in templates
        if template.display_info.orientation == orientation
    ]
    if not candidates:
        return current_template

    current_name = Path(current_template).name
    same_name = [template for template in candidates if Path(template.template_path).name == current_name]
    if same_name:
        return same_name[0].template_path
    return sorted(candidates, key=lambda template: template.display_info.name)[0].template_path
```

- [ ] **Step 4: Add i18n labels**

Add to `web/i18n/locales/zh_CN.json`:

```json
"size.final_video_title": "最终视频尺寸",
"size.orientation": "画幅",
"size.resolution": "分辨率",
"size.sync_media_to_canvas": "同步到图片生成尺寸",
"size.sync_media_to_canvas_help": "开启后，图片/素材生成尺寸会跟随最终视频尺寸；关闭时默认使用 768x768。",
"size.final_video_info": "最终视频尺寸：{width} × {height}",
"size.media_generation_info": "图片生成尺寸：{width} × {height}",
"size.template_orientation_mismatch": "当前模板画幅与最终视频画幅不一致，系统会按最终视频尺寸归一化输出。"
```

Add to `web/i18n/locales/en_US.json`:

```json
"size.final_video_title": "Final Video Size",
"size.orientation": "Aspect",
"size.resolution": "Resolution",
"size.sync_media_to_canvas": "Sync to image generation size",
"size.sync_media_to_canvas_help": "When enabled, generated image/media dimensions follow the final video size. When disabled, image generation defaults to 768x768.",
"size.final_video_info": "Final video size: {width} × {height}",
"size.media_generation_info": "Image generation size: {width} × {height}",
"size.template_orientation_mismatch": "The selected template aspect differs from the final video aspect, so output will be normalized to the final video size."
```

Ensure commas are valid in both JSON files.

- [ ] **Step 5: Render size controls in style_config**

Modify `web/components/style_config.py` imports:

```python
from pixelle_video.models.size_contract import (
    GenerationSizeContract,
    VIDEO_SIZE_PRESETS,
)
from pixelle_video.utils.template_util import (
    get_template_orientation,
    resolve_compatible_template_for_orientation,
)
```

Add a small helper near other UI helpers:

```python
def _render_generation_size_controls() -> GenerationSizeContract:
    orientation_labels = {
        "landscape": tr("orientation.landscape"),
        "portrait": tr("orientation.portrait"),
        "square": tr("orientation.square"),
    }
    orientation_options = list(VIDEO_SIZE_PRESETS.keys())
    orientation = st.segmented_control(
        tr("size.orientation"),
        orientation_options,
        format_func=lambda key: orientation_labels.get(key, key),
        default=st.session_state.get("video_orientation", "landscape"),
        key="video_orientation",
    )
    if orientation is None:
        orientation = "landscape"

    preset_options = list(VIDEO_SIZE_PRESETS[orientation].keys())
    preset = st.segmented_control(
        tr("size.resolution"),
        preset_options,
        format_func=lambda key: f"{key.upper()} ({VIDEO_SIZE_PRESETS[orientation][key].width}×{VIDEO_SIZE_PRESETS[orientation][key].height})",
        default=st.session_state.get("video_resolution_preset", "1k")
        if st.session_state.get("video_resolution_preset", "1k") in preset_options
        else "1k",
        key="video_resolution_preset",
    )
    if preset is None:
        preset = "1k"

    sync = st.toggle(
        tr("size.sync_media_to_canvas"),
        value=bool(st.session_state.get("sync_media_size_to_canvas", False)),
        help=tr("size.sync_media_to_canvas_help"),
        key="sync_media_size_to_canvas",
    )
    contract = GenerationSizeContract.from_params(
        {
            "video_orientation": orientation,
            "video_resolution_preset": preset,
            "sync_media_size_to_canvas": sync,
        }
    )
    st.info(
        tr(
            "size.final_video_info",
            width=contract.canvas_width,
            height=contract.canvas_height,
        )
    )
    return contract
```

Call this helper inside the template/style section before media workflow controls:

```python
        with render_middle_column_detail_section(tr("size.final_video_title")):
            size_contract = _render_generation_size_controls()
```

When template type or orientation changes, call `resolve_compatible_template_for_orientation()` before rendering the selected template details:

```python
        resolved_template = resolve_compatible_template_for_orientation(
            current_template=st.session_state["selected_template"],
            template_type=selected_template_type,
            orientation=size_contract.video_orientation,
        )
        if resolved_template != st.session_state["selected_template"]:
            st.session_state["selected_template"] = resolved_template
            st.rerun()
```

Replace media size reads from `template_media_width` / `template_media_height` with:

```python
            media_width = size_contract.media_width
            media_height = size_contract.media_height
```

Return the size fields:

```python
        **size_contract.to_params(),
```

Keep `template_media_width` / `template_media_height` session state only for template recommendation/compatibility display.

- [ ] **Step 6: Run JSON validation and template utility tests**

Run:

```bash
python -m json.tool web/i18n/locales/zh_CN.json > $null
python -m json.tool web/i18n/locales/en_US.json > $null
pytest tests/test_template_util.py tests/test_style_config_template_gallery.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

```bash
git add pixelle_video/utils/template_util.py web/components/style_config.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_template_util.py tests/test_style_config_template_gallery.py
git commit -m "feat: 增加最终视频尺寸 UI 合同"
```

## Task 7: Render Consumers Use Canvas Dimensions

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/services/frame_processor.py`
- Modify: `tests/test_standard_pipeline_hyperframes_mode.py`

- [ ] **Step 1: Write failing manifest test for explicit canvas over template size**

Append to `tests/test_standard_pipeline_hyperframes_mode.py` near existing canvas tests:

```python

@pytest.mark.asyncio
async def test_post_production_uses_explicit_canvas_size_over_template_size(monkeypatch, tmp_path):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(
        tmp_path,
        frame_template="1080x1920/image_default.html",
    )
    ctx.config.canvas_width = 1280
    ctx.config.canvas_height = 720
    ctx.config.media_width = 768
    ctx.config.media_height = 768
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")

    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        Path(frame.image_path).write_text("raw", encoding="utf-8")

    def fake_normalize_audio(input_path, output_path):
        Path(output_path).write_bytes(b"wav")
        return output_path

    def fake_concat_audio_files(audio_paths, output_path, **kwargs):
        Path(output_path).write_bytes(b"master-audio")

    def fake_get_audio_duration(audio_path):
        return 4.0

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)
    monkeypatch.setattr(pipeline, "_get_audio_duration", fake_get_audio_duration)

    await pipeline.post_production(ctx)

    manifest = core.hyperframes_project_service.manifest
    assert (manifest.canvas_width, manifest.canvas_height) == (1280, 720)
    assert (manifest.media_width, manifest.media_height) == (768, 768)
    assert core.hyperframes_renderer.calls[0]["width"] == 1280
    assert core.hyperframes_renderer.calls[0]["height"] == 720
```

- [ ] **Step 2: Write failing element motion canvas-dimension test**

Append to `tests/test_standard_pipeline_hyperframes_mode.py`:

```python

@pytest.mark.asyncio
async def test_element_motion_for_composed_frame_uses_canvas_dimensions(monkeypatch, tmp_path):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path)
    ctx.config.element_animation_enabled = True
    ctx.config.canvas_width = 1280
    ctx.config.canvas_height = 720
    ctx.config.media_width = 768
    ctx.config.media_height = 768
    frame = ctx.storyboard.frames[0]
    frame.composed_image_path = str(tmp_path / "composed.png")
    Path(frame.composed_image_path).write_bytes(b"png")

    captured = {}

    class FakeMaterializer:
        def __init__(self, segmentation_service):
            captured["segmentation_service"] = segmentation_service

        async def materialize_frame(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                manifest_path="manifest.json",
                motion_video_path="motion.mp4",
            )

    monkeypatch.setattr(
        "pixelle_video.services.element_motion_materializer.ElementMotionMaterializer",
        FakeMaterializer,
    )

    await pipeline._materialize_element_motion_for_frame(ctx, frame)

    assert captured["width"] == 1280
    assert captured["height"] == 720
    assert frame.element_animation_manifest_path == "manifest.json"
    assert frame.element_motion_video_path == "motion.mp4"
```

- [ ] **Step 3: Run the focused render tests and verify they fail**

Run:

```bash
pytest tests/test_standard_pipeline_hyperframes_mode.py::test_post_production_uses_explicit_canvas_size_over_template_size tests/test_standard_pipeline_hyperframes_mode.py::test_element_motion_for_composed_frame_uses_canvas_dimensions -q
```

Expected: FAIL because render paths still prefer template/media dimensions.

- [ ] **Step 4: Update StandardPipeline canvas resolution**

Modify `_resolve_hyperframes_canvas_size()` in `pixelle_video/pipelines/standard.py`:

```python
    def _resolve_hyperframes_canvas_size(self, config: StoryboardConfig) -> tuple[int, int]:
        canvas_width = getattr(config, "canvas_width", None)
        canvas_height = getattr(config, "canvas_height", None)
        if canvas_width and canvas_height:
            return int(canvas_width), int(canvas_height)
        try:
            return parse_template_size(config.frame_template)
        except ValueError as exc:
            logger.warning(
                "Failed to parse HyperFrames canvas size from template "
                f"{config.frame_template!r}: {exc}. Falling back to media size."
            )
            return int(config.media_width), int(config.media_height)
```

Update `_build_render_manifest_for_current_timeline()`:

```python
        canvas_width, canvas_height = (
            int(config.canvas_width),
            int(config.canvas_height),
        )
```

Use those values for `RenderManifest(canvas_width=..., canvas_height=...)`.

Update `_materialize_element_motion_for_frame()`:

```python
            width=int(config.canvas_width),
            height=int(config.canvas_height),
```

- [ ] **Step 5: Pass canvas dimensions to TemplateVisualMaterializer**

Modify `pixelle_video/services/frame_processor.py` in `_compose_frame_html()`:

```python
            canvas_width=getattr(config, "canvas_width", None),
            canvas_height=getattr(config, "canvas_height", None),
```

when calling `TemplateVisualMaterializer().materialize_frame(...)`.

- [ ] **Step 6: Run render path tests**

Run:

```bash
pytest tests/test_standard_pipeline_hyperframes_mode.py tests/test_frame_processor_negative_prompt.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```bash
git add pixelle_video/pipelines/standard.py pixelle_video/services/frame_processor.py tests/test_standard_pipeline_hyperframes_mode.py
git commit -m "feat: 渲染链路消费最终画布尺寸"
```

## Task 8: Full Verification

**Files:**
- No new production files unless previous tasks reveal a missed import or test fixture update.

- [ ] **Step 1: Run focused size contract suite**

Run:

```bash
pytest tests/test_size_contract.py tests/test_storyboard_size_contract.py tests/test_output_preview.py tests/test_video_api.py tests/test_frame_html.py tests/test_template_visual_materializer.py tests/test_standard_pipeline_hyperframes_mode.py -q
```

Expected: PASS.

- [ ] **Step 2: Run broad project tests likely affected by request and render changes**

Run:

```bash
pytest tests/test_element_animation_ui_mapping.py tests/test_render_package_models.py tests/test_standard_pipeline_prompt_prefix.py tests/test_standard_pipeline_text_rendering_summary.py tests/test_pipeline_text_rendering_contract.py tests/test_storyboard_snapshot_persistence.py -q
```

Expected: PASS.

- [ ] **Step 3: Run lint on changed Python files**

Run:

```bash
ruff check pixelle_video/models/size_contract.py pixelle_video/models/storyboard.py pixelle_video/pipelines/standard.py pixelle_video/services/frame_html.py pixelle_video/services/template_visual_materializer.py pixelle_video/services/frame_processor.py web/components/output_preview.py web/components/style_config.py api/schemas/video.py api/routers/video.py
```

Expected: PASS.

- [ ] **Step 4: Run final git diff review**

Run:

```bash
git diff --check
git status --short
```

Expected:

- `git diff --check` exits successfully.
- `git status --short` shows only intended files from this feature plus unrelated pre-existing user changes.

- [ ] **Step 5: Handle verification-only fixes if any**

If Step 1 through Step 4 reveal import-only or assertion-alignment fixes, return to the task that owns the failing file, make a focused fix, rerun that task's verification command, and commit with that task's explicit `git add` command. If no fixes were needed, do not create an empty commit.

## Plan Self-Review

- Spec coverage:
  - Default final canvas and default media size: Task 1.
  - Orientation/preset table: Task 1.
  - Sync option: Task 1 and Task 6.
  - Web request construction: Task 3.
  - API request construction: Task 4.
  - `StoryboardConfig` compatibility: Task 2.
  - Template rendering normalization: Task 5.
  - Render manifest and element animation consumers: Task 7.
  - Verification: Task 8.

- Placeholder scan:
  - The plan contains no `TBD`, `TODO`, or unassigned implementation sections.

- Type consistency:
  - The contract fields are consistently named `canvas_width`, `canvas_height`, `media_width`, `media_height`, `video_orientation`, `video_resolution_preset`, and `sync_media_size_to_canvas`.
