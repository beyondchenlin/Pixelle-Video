# Template Media Contract v2 Implementation Plan

> Note (2026-04-29 follow-up): the shipped runtime default `media_placement.scale_percent` is now `100`. References to `80%` below remain as historical implementation context for the earlier iteration.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a platform-level media placement contract so generated image/video media defaults to 80% of the final video canvas, remains aspect-correct, and can be positioned with 9-grid anchors.

**Architecture:** `MediaPlacement` becomes the single fact source for display size and position, independent from `GenerationSizeContract` media generation dimensions. UI, API, storyboard config, render manifests, legacy HTML rendering, HyperFrames rendering, and template linting all consume the same contract. Templates keep background, title, decoration, and layering, but main media size/position is owned by the platform.

**Tech Stack:** Python dataclasses/Pydantic/FastAPI, Streamlit UI, Playwright HTML screenshots, PIL image inspection, HyperFrames HTML templates, pytest.

---

## Source Spec

Design: `docs/superpowers/specs/2026-04-29-template-media-contract-v2-design.md`

Review commits already made:

- `63d121d docs: 设计媒体摆放契约 v2`
- `a150cbc docs: 补充媒体摆放契约复审约束`

## File Structure

- Create `pixelle_video/models/media_placement.py`: `MediaPlacement`, validation, geometry calculation, and template/canvas coordinate projection.
- Modify `pixelle_video/models/template_parameters.py`: reserve system media-layer placeholders.
- Modify `api/schemas/video.py`: add API request model for `media_placement`.
- Modify `api/routers/video.py`: copy API `media_placement` into generation params.
- Modify `pixelle_video/models/storyboard.py`: add `media_placement` to `StoryboardConfig`; keep `media_layout_mode` compatibility only.
- Modify `pixelle_video/models/render_package.py`: persist `media_placement` in `RenderManifest`.
- Modify `pixelle_video/models/template_render_context.py`: add `media_placement` for HyperFrames.
- Modify `pixelle_video/services/persistence.py`: snapshot and restore `media_placement`.
- Modify `pixelle_video/pipelines/standard.py`, `pixelle_video/pipelines/asset_based.py`, and `pixelle_video/services/frame_processor.py`: thread the contract through configs, manifests, and template materialization.
- Modify `pixelle_video/services/template_visual_materializer.py`: pass typed `MediaPlacement`, media type, and source dimensions to `HTMLFrameGenerator`.
- Modify `pixelle_video/services/frame_html.py`: inject standard media CSS/markup and calculate final-canvas placement with template-coordinate projection.
- Modify `pixelle_video/services/hyperframes_compiler.py`: render HyperFrames visual clips through the same standard media layer and CSS variables.
- Create `pixelle_video/services/template_media_lint.py`: fail templates that bypass the standard media layer.
- Modify `pixelle_video/utils/template_util.py`: expose lint helpers for template discovery tests.
- Modify `web/components/style_config.py`: add percent slider, 9-grid anchor control, and result summary.
- Modify `web/i18n/locales/zh_CN.json` and `web/i18n/locales/en_US.json`: add UI labels.
- Modify legacy templates under `templates/1080x1920`, `templates/1920x1080`, and `templates/1080x1080`: replace main media `{{image}}` usage with `{{pixelle_media_layer}}`.
- Modify HyperFrames templates under `resources/hyperframes/templates/*/index.template.html`: replace fixed media shells with standard placement-aware layer hooks.
- Add/modify tests:
  - `tests/test_media_placement.py`
  - `tests/test_video_api.py`
  - `tests/test_storyboard_size_contract.py`
  - `tests/test_render_package_models.py`
  - `tests/test_template_render_context.py`
  - `tests/test_template_visual_materializer.py`
  - `tests/test_frame_html.py`
  - `tests/test_hyperframes_compiler.py`
  - `tests/test_template_media_lint.py`
  - `tests/test_style_config_template_gallery.py`
  - `tests/test_output_preview.py`

## Task 1: Media Placement Model And Geometry

**Files:**
- Create: `pixelle_video/models/media_placement.py`
- Test: `tests/test_media_placement.py`

- [ ] **Step 1: Write failing model and geometry tests**

Create `tests/test_media_placement.py`:

```python
import pytest

from pixelle_video.models.media_placement import (
    MediaPlacement,
    calculate_media_box,
    project_canvas_box_to_template,
    resolve_media_placement,
)


def test_media_placement_defaults_to_canvas_contain_80_center():
    placement = MediaPlacement()

    assert placement.basis == "canvas"
    assert placement.fit == "contain"
    assert placement.scale_percent == 80
    assert placement.anchor == "center"
    assert placement.to_dict() == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 80,
        "anchor": "center",
    }


@pytest.mark.parametrize("scale", [9, 101])
def test_media_placement_rejects_scale_outside_allowed_range(scale):
    with pytest.raises(ValueError, match="scale_percent"):
        MediaPlacement(scale_percent=scale)


@pytest.mark.parametrize("anchor", ["middle", "top-middle", ""])
def test_media_placement_rejects_unknown_anchor(anchor):
    with pytest.raises(ValueError, match="anchor"):
        MediaPlacement(anchor=anchor)


def test_resolve_media_placement_accepts_dict_and_none():
    assert resolve_media_placement(None) == MediaPlacement()
    assert resolve_media_placement({"scale_percent": 100, "anchor": "right"}) == MediaPlacement(
        scale_percent=100,
        anchor="right",
    )


@pytest.mark.parametrize(
    ("source", "scale", "expected"),
    [
        ((1280, 720), 100, (1280, 720, 0, 0)),
        ((1280, 720), 80, (1024, 576, 128, 72)),
        ((1024, 1024), 100, (720, 720, 280, 0)),
        ((1024, 1024), 80, (576, 576, 352, 72)),
        ((720, 1280), 100, (405, 720, 438, 0)),
        ((720, 1280), 80, (324, 576, 478, 72)),
    ],
)
def test_contain_geometry_uses_final_canvas(source, scale, expected):
    box = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=source[0],
        media_source_height=source[1],
        placement=MediaPlacement(scale_percent=scale),
    )

    assert (round(box.width), round(box.height), round(box.left), round(box.top)) == expected


def test_anchor_right_bottom_moves_position_without_changing_size():
    center = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=1024,
        media_source_height=1024,
        placement=MediaPlacement(scale_percent=80, anchor="center"),
    )
    bottom_right = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=1024,
        media_source_height=1024,
        placement=MediaPlacement(scale_percent=80, anchor="bottom_right"),
    )

    assert bottom_right.width == pytest.approx(center.width)
    assert bottom_right.height == pytest.approx(center.height)
    assert bottom_right.left == pytest.approx(704)
    assert bottom_right.top == pytest.approx(144)


def test_canvas_box_projects_into_template_coordinates_for_same_aspect_resize():
    canvas_box = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=1280,
        media_source_height=720,
        placement=MediaPlacement(scale_percent=80),
    )

    template_box = project_canvas_box_to_template(
        canvas_box,
        canvas_width=1280,
        canvas_height=720,
        template_width=1920,
        template_height=1080,
        canvas_fit="contain",
    )

    assert template_box.width == pytest.approx(1536)
    assert template_box.height == pytest.approx(864)
    assert template_box.left == pytest.approx(192)
    assert template_box.top == pytest.approx(108)


def test_projection_rejects_template_canvas_aspect_mismatch():
    canvas_box = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=1280,
        media_source_height=720,
        placement=MediaPlacement(),
    )

    with pytest.raises(ValueError, match="aspect ratio"):
        project_canvas_box_to_template(
            canvas_box,
            canvas_width=1280,
            canvas_height=720,
            template_width=1080,
            template_height=1920,
            canvas_fit="contain",
        )
```

- [ ] **Step 2: Run tests and verify they fail because the module does not exist**

Run:

```powershell
python -m pytest tests/test_media_placement.py -q
```

Expected: `ModuleNotFoundError: No module named 'pixelle_video.models.media_placement'`.

- [ ] **Step 3: Implement the model and pure geometry helpers**

Create `pixelle_video/models/media_placement.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

MediaPlacementBasis = Literal["canvas"]
MediaPlacementFit = Literal["contain"]
MediaPlacementAnchor = Literal[
    "top_left",
    "top",
    "top_right",
    "left",
    "center",
    "right",
    "bottom_left",
    "bottom",
    "bottom_right",
]

VALID_MEDIA_PLACEMENT_BASIS = {"canvas"}
VALID_MEDIA_PLACEMENT_FIT = {"contain"}
VALID_MEDIA_PLACEMENT_ANCHORS = {
    "top_left",
    "top",
    "top_right",
    "left",
    "center",
    "right",
    "bottom_left",
    "bottom",
    "bottom_right",
}


@dataclass(frozen=True)
class MediaPlacement:
    basis: MediaPlacementBasis = "canvas"
    fit: MediaPlacementFit = "contain"
    scale_percent: int = 80
    anchor: MediaPlacementAnchor = "center"

    def __post_init__(self) -> None:
        if self.basis not in VALID_MEDIA_PLACEMENT_BASIS:
            raise ValueError("media_placement.basis must be 'canvas'")
        if self.fit not in VALID_MEDIA_PLACEMENT_FIT:
            raise ValueError("media_placement.fit must be 'contain'")
        scale = int(self.scale_percent)
        if scale < 10 or scale > 100:
            raise ValueError("media_placement.scale_percent must be between 10 and 100")
        if self.anchor not in VALID_MEDIA_PLACEMENT_ANCHORS:
            raise ValueError(
                "media_placement.anchor must be one of "
                f"{sorted(VALID_MEDIA_PLACEMENT_ANCHORS)}"
            )
        object.__setattr__(self, "scale_percent", scale)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "MediaPlacement":
        values = dict(data or {})
        return cls(
            basis=values.get("basis", "canvas"),
            fit=values.get("fit", "contain"),
            scale_percent=int(values.get("scale_percent", 80)),
            anchor=values.get("anchor", "center"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "fit": self.fit,
            "scale_percent": self.scale_percent,
            "anchor": self.anchor,
        }


@dataclass(frozen=True)
class MediaBox:
    width: float
    height: float
    left: float
    top: float


def resolve_media_placement(value: MediaPlacement | Mapping[str, Any] | None) -> MediaPlacement:
    if isinstance(value, MediaPlacement):
        return value
    return MediaPlacement.from_dict(value)


def calculate_media_box(
    *,
    canvas_width: int,
    canvas_height: int,
    media_source_width: int,
    media_source_height: int,
    placement: MediaPlacement | Mapping[str, Any] | None = None,
) -> MediaBox:
    resolved = resolve_media_placement(placement)
    source_width = max(1, int(media_source_width))
    source_height = max(1, int(media_source_height))
    canvas_width = int(canvas_width)
    canvas_height = int(canvas_height)

    base_scale = min(canvas_width / source_width, canvas_height / source_height)
    display_scale = base_scale * (resolved.scale_percent / 100)
    display_width = source_width * display_scale
    display_height = source_height * display_scale

    horizontal = {
        "top_left": "left",
        "left": "left",
        "bottom_left": "left",
        "top": "center",
        "center": "center",
        "bottom": "center",
        "top_right": "right",
        "right": "right",
        "bottom_right": "right",
    }[resolved.anchor]
    vertical = {
        "top_left": "top",
        "top": "top",
        "top_right": "top",
        "left": "center",
        "center": "center",
        "right": "center",
        "bottom_left": "bottom",
        "bottom": "bottom",
        "bottom_right": "bottom",
    }[resolved.anchor]

    if horizontal == "left":
        left = 0.0
    elif horizontal == "right":
        left = canvas_width - display_width
    else:
        left = (canvas_width - display_width) / 2

    if vertical == "top":
        top = 0.0
    elif vertical == "bottom":
        top = canvas_height - display_height
    else:
        top = (canvas_height - display_height) / 2

    return MediaBox(
        width=display_width,
        height=display_height,
        left=left,
        top=top,
    )


def _assert_same_aspect_ratio(
    *,
    canvas_width: int,
    canvas_height: int,
    template_width: int,
    template_height: int,
) -> None:
    left = int(canvas_width) * int(template_height)
    right = int(canvas_height) * int(template_width)
    if abs(left - right) > 1:
        raise ValueError(
            "template and final canvas aspect ratio must match for canvas media placement"
        )


def project_canvas_box_to_template(
    box: MediaBox,
    *,
    canvas_width: int,
    canvas_height: int,
    template_width: int,
    template_height: int,
    canvas_fit: str = "contain",
) -> MediaBox:
    _assert_same_aspect_ratio(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        template_width=template_width,
        template_height=template_height,
    )
    if canvas_fit == "cover":
        scale = max(canvas_width / template_width, canvas_height / template_height)
    else:
        scale = min(canvas_width / template_width, canvas_height / template_height)

    resized_width = template_width * scale
    resized_height = template_height * scale
    offset_left = (canvas_width - resized_width) / 2
    offset_top = (canvas_height - resized_height) / 2

    return MediaBox(
        width=box.width / scale,
        height=box.height / scale,
        left=(box.left - offset_left) / scale,
        top=(box.top - offset_top) / scale,
    )
```

- [ ] **Step 4: Run model tests**

Run:

```powershell
python -m pytest tests/test_media_placement.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add pixelle_video/models/media_placement.py tests/test_media_placement.py
git commit -m "feat: add media placement geometry contract"
```

## Task 2: API Contract

**Files:**
- Modify: `api/schemas/video.py`
- Modify: `api/routers/video.py`
- Test: `tests/test_video_api.py`

- [ ] **Step 1: Write failing API schema tests**

Append to `tests/test_video_api.py` near the size-contract tests:

```python
def test_video_generate_request_defaults_media_placement():
    request = VideoGenerateRequest(text="demo")

    assert request.media_placement.to_dict() == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 80,
        "anchor": "center",
    }


def test_video_generate_request_accepts_media_placement():
    request = VideoGenerateRequest(
        text="demo",
        media_placement={"scale_percent": 100, "anchor": "right"},
    )

    assert request.media_placement.scale_percent == 100
    assert request.media_placement.anchor == "right"


def test_video_generate_request_rejects_invalid_media_placement_scale():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            media_placement={"scale_percent": 101},
        )


def test_build_video_generation_params_includes_media_placement():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            media_placement={"scale_percent": 90, "anchor": "bottom"},
        ),
        request_id="req_test",
    )

    assert params["media_placement"] == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 90,
        "anchor": "bottom",
    }
```

- [ ] **Step 2: Run API tests and verify failure**

Run:

```powershell
python -m pytest tests/test_video_api.py::test_video_generate_request_defaults_media_placement tests/test_video_api.py::test_build_video_generation_params_includes_media_placement -q
```

Expected: fails because `VideoGenerateRequest` has no `media_placement`.

- [ ] **Step 3: Add Pydantic schema fields**

Modify `api/schemas/video.py`:

```python
from pixelle_video.models.media_placement import MediaPlacement
```

Add after `MediaResolutionPreset`:

```python
class MediaPlacementRequest(BaseModel):
    basis: Literal["canvas"] = Field("canvas", description="Placement basis. First version supports final canvas only.")
    fit: Literal["contain"] = Field("contain", description="Preserve aspect ratio and do not crop.")
    scale_percent: int = Field(80, ge=10, le=100, description="Display size as percent of final video canvas contain-fit size.")
    anchor: Literal[
        "top_left",
        "top",
        "top_right",
        "left",
        "center",
        "right",
        "bottom_left",
        "bottom",
        "bottom_right",
    ] = Field("center", description="9-grid anchor for the displayed media.")

    def to_model(self) -> MediaPlacement:
        return MediaPlacement.from_dict(self.model_dump())
```

Add to `VideoGenerateRequest` after `sync_media_size_to_canvas`:

```python
    media_placement: MediaPlacementRequest = Field(
        default_factory=MediaPlacementRequest,
        description="Generated image/video display size and position inside the final video canvas.",
    )
```

- [ ] **Step 4: Copy API field into generation params**

Modify `api/routers/video.py` inside `build_video_generation_params()`:

```python
        "media_placement": request_body.media_placement.to_model().to_dict(),
```

Place it immediately after `**size_contract.to_params(),` so size and placement remain adjacent.

- [ ] **Step 5: Run API tests**

Run:

```powershell
python -m pytest tests/test_video_api.py::test_video_generate_request_defaults_media_placement tests/test_video_api.py::test_video_generate_request_accepts_media_placement tests/test_video_api.py::test_video_generate_request_rejects_invalid_media_placement_scale tests/test_video_api.py::test_build_video_generation_params_includes_media_placement -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add api/schemas/video.py api/routers/video.py tests/test_video_api.py
git commit -m "feat: expose media placement in video API"
```

## Task 3: Storyboard, Manifest, Persistence Data Flow

**Files:**
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/models/render_package.py`
- Modify: `pixelle_video/models/template_render_context.py`
- Modify: `pixelle_video/services/persistence.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/pipelines/asset_based.py`
- Test: `tests/test_storyboard_size_contract.py`
- Test: `tests/test_render_package_models.py`
- Test: `tests/test_template_render_context.py`
- Test: `tests/test_storyboard_snapshot_persistence.py`

- [ ] **Step 1: Write failing data-flow tests**

Add to `tests/test_storyboard_size_contract.py`:

```python
from pixelle_video.models.media_placement import MediaPlacement


def test_storyboard_config_defaults_media_placement_independently_from_sync_flag():
    config = StoryboardConfig(
        media_width=768,
        media_height=768,
        canvas_width=1280,
        canvas_height=720,
        sync_media_size_to_canvas=True,
    )

    assert config.media_placement == MediaPlacement()
    assert config.media_placement.scale_percent == 80
```

Add to `tests/test_render_package_models.py`:

```python
def test_render_manifest_round_trips_media_placement():
    manifest = RenderManifest(
        task_id="task-media-placement",
        title="demo",
        canvas_width=1280,
        canvas_height=720,
        media_width=768,
        media_height=768,
        fps=30,
        template_id="image_landscape_minimal",
        media_placement={"scale_percent": 90, "anchor": "bottom_right"},
    )

    restored = RenderManifest.from_dict(manifest.to_dict())

    assert restored.media_placement.to_dict() == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 90,
        "anchor": "bottom_right",
    }
```

Add to `tests/test_template_render_context.py`:

```python
def test_template_render_context_defaults_media_placement():
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=2.0,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
    )

    assert context.media_placement.to_dict()["scale_percent"] == 80
```

- [ ] **Step 2: Run selected tests and verify failure**

Run:

```powershell
python -m pytest tests/test_storyboard_size_contract.py::test_storyboard_config_defaults_media_placement_independently_from_sync_flag tests/test_render_package_models.py::test_render_manifest_round_trips_media_placement tests/test_template_render_context.py::test_template_render_context_defaults_media_placement -q
```

Expected: fails because dataclasses do not expose `media_placement`.

- [ ] **Step 3: Add `media_placement` to dataclasses and manifests**

In `pixelle_video/models/storyboard.py`, import and add a field:

```python
from pixelle_video.models.media_placement import MediaPlacement, resolve_media_placement
```

```python
    media_placement: MediaPlacement | dict[str, Any] | None = None
```

In `StoryboardConfig.__post_init__()` after `sync_media_size_to_canvas`:

```python
        self.media_placement = resolve_media_placement(self.media_placement)
```

In `pixelle_video/models/render_package.py`, import and add constructor/to/from support:

```python
from pixelle_video.models.media_placement import MediaPlacement, resolve_media_placement
```

Add field and `__init__` parameter:

```python
    media_placement: MediaPlacement = field(default_factory=MediaPlacement)
```

```python
        media_placement: MediaPlacement | Mapping[str, Any] | None = None,
```

Set in `__init__()`:

```python
        self.media_placement = resolve_media_placement(media_placement)
```

Persist in `to_dict()`:

```python
            "media_placement": self.media_placement.to_dict(),
```

Restore in `from_dict()`:

```python
            media_placement=data.get("media_placement"),
```

In `pixelle_video/models/template_render_context.py`, import and add:

```python
from pixelle_video.models.media_placement import MediaPlacement, resolve_media_placement
```

```python
    media_placement: MediaPlacement | dict[str, Any] | None = None
```

Set in `__post_init__()`:

```python
        self.media_placement = resolve_media_placement(self.media_placement)
```

- [ ] **Step 4: Thread params into pipeline config and manifests**

In every `StoryboardConfig(...)` construction in `pixelle_video/pipelines/standard.py` and `pixelle_video/pipelines/asset_based.py`, add:

```python
            media_placement=ctx.params.get("media_placement"),
```

In every `RenderManifest(...)` construction in `pixelle_video/pipelines/standard.py`, add:

```python
            media_placement=config.media_placement,
```

For the legacy manifest built from `storyboard.config`, add:

```python
                media_placement=storyboard.config.media_placement,
```

In `pixelle_video/services/hyperframes_project_service.py`, pass manifest placement into context:

```python
        media_placement=manifest.media_placement,
```

- [ ] **Step 5: Persist snapshots**

In `pixelle_video/services/persistence.py`, include the field in snapshot config dictionaries:

```python
            "media_placement": config.media_placement.to_dict(),
```

When loading `StoryboardConfig`, pass:

```python
            media_placement=data.get("media_placement"),
```

- [ ] **Step 6: Run data-flow tests**

Run:

```powershell
python -m pytest tests/test_storyboard_size_contract.py tests/test_render_package_models.py tests/test_template_render_context.py tests/test_storyboard_snapshot_persistence.py -q
```

Expected: all selected suites pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add pixelle_video/models/storyboard.py pixelle_video/models/render_package.py pixelle_video/models/template_render_context.py pixelle_video/services/persistence.py pixelle_video/pipelines/standard.py pixelle_video/pipelines/asset_based.py pixelle_video/services/hyperframes_project_service.py tests/test_storyboard_size_contract.py tests/test_render_package_models.py tests/test_template_render_context.py tests/test_storyboard_snapshot_persistence.py
git commit -m "feat: persist media placement through render contracts"
```

## Task 4: Legacy HTML Renderer Standard Media Layer

**Files:**
- Modify: `pixelle_video/models/template_parameters.py`
- Modify: `pixelle_video/services/template_visual_materializer.py`
- Modify: `pixelle_video/services/frame_html.py`
- Modify: `pixelle_video/services/frame_processor.py`
- Test: `tests/test_template_visual_materializer.py`
- Test: `tests/test_frame_html.py`

- [ ] **Step 1: Write failing renderer tests**

Add to `tests/test_template_visual_materializer.py`:

```python
@pytest.mark.asyncio
async def test_template_visual_materializer_forwards_typed_media_placement(tmp_path, monkeypatch):
    calls = {}

    class FakeGenerator:
        width = 1280
        height = 720

        def __init__(self, template_path, canvas_width=None, canvas_height=None):
            calls["canvas"] = (canvas_width, canvas_height)

        async def generate_frame(
            self,
            *,
            title,
            text,
            image,
            ext,
            output_path,
            media_placement,
            media_type,
            media_width,
            media_height,
        ):
            calls["media_placement"] = media_placement.to_dict()
            calls["media_type"] = media_type
            calls["media_size"] = (media_width, media_height)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"png")
            return output_path

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        FakeGenerator,
    )

    await TemplateVisualMaterializer().materialize_frame(
        title="Demo",
        template_body_text="Template body",
        media_path="raw.png",
        media_type="image",
        frame_index=0,
        template_path="templates/1920x1080/image_landscape_minimal.html",
        template_id="image_landscape_minimal",
        output_path=tmp_path / "frame.png",
        text_policy="caption_renderer",
        canvas_width=1280,
        canvas_height=720,
        media_width=768,
        media_height=768,
        media_placement={"scale_percent": 90, "anchor": "right"},
    )

    assert calls["media_placement"]["scale_percent"] == 90
    assert calls["media_type"] == "image"
    assert calls["media_size"] == (768, 768)
```

Add to `tests/test_frame_html.py`:

```python
def test_html_frame_generator_injects_standard_media_layer_css(tmp_path):
    template_dir = tmp_path / "templates" / "1920x1080"
    template_dir.mkdir(parents=True)
    template = template_dir / "image_standard.html"
    template.write_text(
        "<html><head></head><body>{{pixelle_media_layer}}</body></html>",
        encoding="utf-8",
    )

    generator = HTMLFrameGenerator(str(template), canvas_width=1280, canvas_height=720)
    html = generator._build_render_html(
        title="Demo",
        text="",
        image="file:///tmp/source.png",
        ext={"index": 1},
        media_placement={"scale_percent": 80, "anchor": "center"},
        media_type="image",
        media_width=1280,
        media_height=720,
    )

    assert "pixelle-media-layer" in html
    assert "--pixelle-media-display-width: 1536px" in html
    assert "--pixelle-media-display-height: 864px" in html
    assert "--pixelle-media-left: 192px" in html
    assert "--pixelle-media-top: 108px" in html
    assert '<img class="pixelle-media"' in html


def test_html_frame_generator_injects_video_media_element(tmp_path):
    template_dir = tmp_path / "templates" / "1280x720"
    template_dir.mkdir(parents=True)
    template = template_dir / "video_standard.html"
    template.write_text(
        "<html><head></head><body>{{pixelle_media_layer}}</body></html>",
        encoding="utf-8",
    )

    generator = HTMLFrameGenerator(str(template), canvas_width=1280, canvas_height=720)
    html = generator._build_render_html(
        title="Demo",
        text="",
        image="file:///tmp/source.mp4",
        ext={"index": 1},
        media_placement={"scale_percent": 80},
        media_type="video",
        media_width=1280,
        media_height=720,
    )

    assert '<video class="pixelle-media"' in html
    assert "muted playsinline" in html
```

- [ ] **Step 2: Run selected tests and verify failure**

Run:

```powershell
python -m pytest tests/test_template_visual_materializer.py::test_template_visual_materializer_forwards_typed_media_placement tests/test_frame_html.py::test_html_frame_generator_injects_standard_media_layer_css tests/test_frame_html.py::test_html_frame_generator_injects_video_media_element -q
```

Expected: fails because materializer and frame generator do not accept these parameters.

- [ ] **Step 3: Reserve system media placeholders**

Modify `pixelle_video/models/template_parameters.py`:

```python
        "pixelle_media_layer",
        "pixelle_media_display_width",
        "pixelle_media_display_height",
        "pixelle_media_left",
        "pixelle_media_top",
```

- [ ] **Step 4: Add `HTMLFrameGenerator._build_render_html()` and standard layer helpers**

In `pixelle_video/services/frame_html.py`, import:

```python
from pixelle_video.models.media_placement import (
    MediaPlacement,
    calculate_media_box,
    project_canvas_box_to_template,
    resolve_media_placement,
)
```

Add helper methods before `generate_frame()`:

```python
    def _resolve_media_source_size(
        self,
        image: str,
        *,
        media_width: int | None,
        media_height: int | None,
    ) -> tuple[int, int]:
        if image and not image.startswith(("http://", "https://", "data:", "file://")):
            path = Path(image)
            if not path.is_absolute():
                path = Path.cwd() / path
            if path.exists():
                try:
                    with Image.open(path) as source:
                        return source.width, source.height
                except Exception:
                    logger.debug(f"Could not inspect media dimensions with PIL: {path}")
        return max(1, int(media_width or self.width)), max(1, int(media_height or self.height))

    def _build_standard_media_layer(
        self,
        *,
        media_url: str,
        media_type: str,
        media_placement: MediaPlacement,
        media_width: int | None,
        media_height: int | None,
    ) -> tuple[str, dict[str, str]]:
        source_width, source_height = self._resolve_media_source_size(
            media_url,
            media_width=media_width,
            media_height=media_height,
        )
        canvas_box = calculate_media_box(
            canvas_width=self.width,
            canvas_height=self.height,
            media_source_width=source_width,
            media_source_height=source_height,
            placement=media_placement,
        )
        template_box = project_canvas_box_to_template(
            canvas_box,
            canvas_width=self.width,
            canvas_height=self.height,
            template_width=self.template_width,
            template_height=self.template_height,
            canvas_fit=self.canvas_fit,
        )
        media_tag = (
            f'<video class="pixelle-media" src="{media_url}" muted playsinline></video>'
            if media_type == "video"
            else f'<img class="pixelle-media" src="{media_url}" alt="">'
        )
        layer = (
            '<div class="pixelle-media-layer">'
            '<div class="pixelle-media-box" data-pixelle-media-box>'
            f"{media_tag}"
            "</div>"
            "</div>"
        )
        variables = {
            "pixelle_media_display_width": f"{round(template_box.width)}px",
            "pixelle_media_display_height": f"{round(template_box.height)}px",
            "pixelle_media_left": f"{round(template_box.left)}px",
            "pixelle_media_top": f"{round(template_box.top)}px",
        }
        return layer, variables

    def _inject_standard_media_css(self, html: str, variables: dict[str, str]) -> str:
        css = f"""
<style data-pixelle-media-placement>
:root {{
  --pixelle-media-display-width: {variables["pixelle_media_display_width"]};
  --pixelle-media-display-height: {variables["pixelle_media_display_height"]};
  --pixelle-media-left: {variables["pixelle_media_left"]};
  --pixelle-media-top: {variables["pixelle_media_top"]};
}}
.pixelle-media-layer {{
  position: absolute;
  inset: 0;
  pointer-events: none;
}}
.pixelle-media-box {{
  position: absolute;
  box-sizing: border-box;
  width: var(--pixelle-media-display-width);
  height: var(--pixelle-media-display-height);
  left: var(--pixelle-media-left);
  top: var(--pixelle-media-top);
}}
.pixelle-media {{
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}}
</style>"""
        head_match = re.search(r"</head>", html, flags=re.IGNORECASE)
        if head_match:
            return f"{html[:head_match.start()]}{css}{html[head_match.start():]}"
        return f"{css}{html}"

    def _build_render_html(
        self,
        *,
        title: str,
        text: str,
        image: str,
        ext: Optional[Dict[str, Any]],
        media_placement: MediaPlacement | dict[str, Any] | None,
        media_type: str,
        media_width: int | None,
        media_height: int | None,
    ) -> str:
        layer, media_variables = self._build_standard_media_layer(
            media_url=image,
            media_type=media_type,
            media_placement=resolve_media_placement(media_placement),
            media_width=media_width,
            media_height=media_height,
        )
        context = {
            "title": title,
            "text": text,
            "image": image,
            "pixelle_media_layer": layer,
            **media_variables,
        }
        if ext:
            context.update(ext)
        html = self._replace_parameters(self.template, context)
        return self._inject_standard_media_css(html, media_variables)
```

- [ ] **Step 5: Extend `generate_frame()` signature and call the builder**

Change `generate_frame()` signature in `pixelle_video/services/frame_html.py`:

```python
        output_path: Optional[str] = None,
        media_placement: MediaPlacement | dict[str, Any] | None = None,
        media_type: str = "image",
        media_width: int | None = None,
        media_height: int | None = None,
```

Replace context/html construction with:

```python
        html = self._build_render_html(
            title=title,
            text=text,
            image=image,
            ext=ext,
            media_placement=media_placement,
            media_type=media_type,
            media_width=media_width,
            media_height=media_height,
        )
        html = self._prepare_html_for_render(html)
```

- [ ] **Step 6: Thread fields through materializer and frame processor**

Modify `TemplateVisualMaterializer.materialize_frame()` signature:

```python
        media_type: str = "image",
        media_width: int | None = None,
        media_height: int | None = None,
        media_placement: Any = None,
```

Pass into `generate_frame()`:

```python
            media_placement=resolve_media_placement(media_placement),
            media_type=media_type,
            media_width=media_width,
            media_height=media_height,
```

In `pixelle_video/services/frame_processor.py`, pass:

```python
            media_type=frame.media_type or "image",
            media_width=config.media_width,
            media_height=config.media_height,
            media_placement=config.media_placement,
```

- [ ] **Step 7: Run renderer tests**

Run:

```powershell
python -m pytest tests/test_template_visual_materializer.py tests/test_frame_html.py -q
```

Expected: all selected suites pass.

- [ ] **Step 8: Commit**

Run:

```powershell
git add pixelle_video/models/template_parameters.py pixelle_video/services/template_visual_materializer.py pixelle_video/services/frame_html.py pixelle_video/services/frame_processor.py tests/test_template_visual_materializer.py tests/test_frame_html.py
git commit -m "feat: render standard media placement in legacy templates"
```

## Task 5: Template Lint And Legacy Template Migration

**Files:**
- Create: `pixelle_video/services/template_media_lint.py`
- Modify: `pixelle_video/utils/template_util.py`
- Modify: all image/video templates under `templates/1080x1920`, `templates/1920x1080`, `templates/1080x1080`
- Test: `tests/test_template_media_lint.py`
- Test: `tests/test_template_util.py`

- [ ] **Step 1: Write failing lint tests**

Create `tests/test_template_media_lint.py`:

```python
from pathlib import Path

from pixelle_video.services.template_media_lint import lint_media_template


def test_lint_accepts_standard_media_layer_placeholder(tmp_path):
    template = tmp_path / "image_standard.html"
    template.write_text(
        "<html><body><div class='stage'>{{pixelle_media_layer}}</div></body></html>",
        encoding="utf-8",
    )

    result = lint_media_template(template)

    assert result.errors == []


def test_lint_rejects_bare_image_tag(tmp_path):
    template = tmp_path / "image_bad.html"
    template.write_text('<html><body><img src="{{image}}"></body></html>', encoding="utf-8")

    result = lint_media_template(template)

    assert any("bare {{image}}" in error for error in result.errors)


def test_lint_rejects_background_image_main_media(tmp_path):
    template = tmp_path / "image_bad_background.html"
    template.write_text(
        '<html><style>.hero{background-image:url("{{image}}")}</style></html>',
        encoding="utf-8",
    )

    result = lint_media_template(template)

    assert any("background-image" in error for error in result.errors)


def test_all_repository_image_and_video_templates_use_standard_layer():
    failures = {}
    for path in sorted(Path("templates").rglob("*.html")):
        if not path.name.startswith(("image_", "video_", "asset_")):
            continue
        result = lint_media_template(path)
        if result.errors:
            failures[str(path)] = result.errors

    assert failures == {}
```

- [ ] **Step 2: Run lint tests and verify failure**

Run:

```powershell
python -m pytest tests/test_template_media_lint.py -q
```

Expected: fails because linter does not exist and templates still use direct `{{image}}`.

- [ ] **Step 3: Implement linter**

Create `pixelle_video/services/template_media_lint.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass(frozen=True)
class TemplateMediaLintResult:
    path: Path
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def lint_media_template(path: str | Path) -> TemplateMediaLintResult:
    template_path = Path(path)
    html = template_path.read_text(encoding="utf-8")
    errors: list[str] = []

    if "{{pixelle_media_layer}}" not in html:
        errors.append("missing {{pixelle_media_layer}} standard media placeholder")

    if re.search(r"<(?:img|image|video)\b[^>]*(?:src|href)\s*=\s*['\"]?\{\{image\}\}", html, re.IGNORECASE):
        errors.append("bare {{image}} media element bypasses standard media layer")

    if re.search(r"background(?:-image)?\s*:[^;{}]*\{\{image\}\}", html, re.IGNORECASE):
        errors.append("background-image using {{image}} bypasses standard media layer")

    return TemplateMediaLintResult(path=template_path, errors=errors)
```

- [ ] **Step 4: Migrate templates**

For each `image_*.html`, `video_*.html`, and `asset_*.html` template, replace the main media element with:

```html
{{pixelle_media_layer}}
```

Keep template-specific visual decoration by styling the standard classes without overriding protected geometry:

```css
.pixelle-media-box {
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 15px 50px rgba(0, 0, 0, 0.08);
}
```

For templates that previously used `background-image: url("{{image}}")` as the main media, split it into background decoration plus the standard layer:

```html
<div class="template-background-decoration"></div>
{{pixelle_media_layer}}
```

Do not leave any main-media `{{image}}` reference in migrated templates. Static templates may keep `{{background=...}}` because `background` is a distinct template parameter.

- [ ] **Step 5: Run lint tests**

Run:

```powershell
python -m pytest tests/test_template_media_lint.py tests/test_template_util.py -q
```

Expected: lint passes for all repository image/video templates.

- [ ] **Step 6: Commit**

Run:

```powershell
git add pixelle_video/services/template_media_lint.py pixelle_video/utils/template_util.py templates tests/test_template_media_lint.py tests/test_template_util.py
git commit -m "feat: enforce standard media layer in templates"
```

## Task 6: HyperFrames Contract

**Files:**
- Modify: `pixelle_video/services/hyperframes_compiler.py`
- Modify: `pixelle_video/services/hyperframes_project_service.py`
- Modify: `resources/hyperframes/templates/image_default/index.template.html`
- Modify: `resources/hyperframes/templates/image_landscape_full/index.template.html`
- Modify: `resources/hyperframes/templates/image_landscape_minimal/index.template.html`
- Modify: `resources/hyperframes/templates/image_life_insights_light/index.template.html`
- Test: `tests/test_hyperframes_compiler.py`
- Test: `tests/test_hyperframes_project_service.py`

- [ ] **Step 1: Write failing HyperFrames tests**

Add to `tests/test_hyperframes_compiler.py`:

```python
def test_hyperframes_compiler_emits_media_placement_variables(tmp_path: Path):
    compiler = HyperFramesCompiler()
    context = TemplateRenderContext(
        template_id="image_landscape_minimal",
        canvas_width=1280,
        canvas_height=720,
        media_width=1280,
        media_height=720,
        media_placement={"scale_percent": 80, "anchor": "center"},
        duration=6.0,
        fps=30,
        title="Landscape",
        author="LanRen.AI",
        footer="LanRen",
        theme=None,
        style_profile="image_landscape_minimal",
        visuals=[
            VisualClip(
                id="v1",
                frame_index=0,
                start=0.0,
                end=6.0,
                media_path="assets/images/01.png",
                media_type="image",
            )
        ],
    )

    compiler.compile(project_dir=tmp_path / "project", context=context)

    index_html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    assert "--pixelle-media-display-width: 1024px" in index_html
    assert "--pixelle-media-display-height: 576px" in index_html
    assert "--pixelle-media-left: 128px" in index_html
    assert "--pixelle-media-top: 72px" in index_html
    assert "pixelle-media-layer" in index_html
    assert "visual-clip__media" not in index_html
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests/test_hyperframes_compiler.py::test_hyperframes_compiler_emits_media_placement_variables -q
```

Expected: fails because compiler still emits `.visual-frame` and template-local media layout.

- [ ] **Step 3: Add compiler media placement CSS variables**

In `pixelle_video/services/hyperframes_compiler.py`, import:

```python
from pixelle_video.models.media_placement import calculate_media_box
```

Add a helper:

```python
    def _render_media_placement_css(self, context: TemplateRenderContext) -> str:
        source_width = int(context.media_width or context.canvas_width)
        source_height = int(context.media_height or context.canvas_height)
        box = calculate_media_box(
            canvas_width=context.canvas_width,
            canvas_height=context.canvas_height,
            media_source_width=source_width,
            media_source_height=source_height,
            placement=context.media_placement,
        )
        return (
            "<style data-pixelle-media-placement>"
            ":root {"
            f"--pixelle-media-display-width: {round(box.width)}px;"
            f"--pixelle-media-display-height: {round(box.height)}px;"
            f"--pixelle-media-left: {round(box.left)}px;"
            f"--pixelle-media-top: {round(box.top)}px;"
            "}"
            ".pixelle-media-layer{position:absolute;inset:0;pointer-events:none;}"
            ".pixelle-media-clip{position:absolute;left:var(--pixelle-media-left);top:var(--pixelle-media-top);width:var(--pixelle-media-display-width);height:var(--pixelle-media-display-height);}"
            ".pixelle-media{width:100%;height:100%;object-fit:contain;display:block;}"
            "</style>"
        )
```

Add replacement:

```python
            "__MEDIA_PLACEMENT_CSS__": self._render_media_placement_css(context),
```

- [ ] **Step 4: Render standard media layer in `_render_visuals()`**

Replace the clip wrapper construction with:

```python
            rendered.append(
                (
                    f'<div id="{escape(clip.id, quote=True)}" class="clip pixelle-media-clip" '
                    f'data-start="{clip.start}" '
                    f'data-duration="{duration}" data-track-index="{track_index}"'
                    f"{element_manifest_attr}>"
                    f"{media_tag}"
                    "</div>"
                )
            )
```

Change `_build_media_tag()` to standard media class:

```python
        if media_type == "video":
            return (
                '<video class="pixelle-media" '
                f'src="{escaped_path}" muted playsinline></video>'
            )
        return f'<img class="pixelle-media" src="{escaped_path}" alt="" />'
```

- [ ] **Step 5: Update HyperFrames templates**

In each HyperFrames `index.template.html`, place the CSS hook inside `<head>`:

```html
__MEDIA_PLACEMENT_CSS__
```

Replace template-specific media shells around `__VISUALS__` with:

```html
<div class="pixelle-media-layer">__VISUALS__</div>
```

Keep title, background decoration, signatures, captions, text layer, and audio unchanged.

- [ ] **Step 6: Run HyperFrames tests**

Run:

```powershell
python -m pytest tests/test_hyperframes_compiler.py tests/test_hyperframes_project_service.py -q
```

Expected: all selected suites pass after updating older assertions that expected `data-media-layout-mode="canvas"` to now assert media placement CSS variables.

- [ ] **Step 7: Commit**

Run:

```powershell
git add pixelle_video/services/hyperframes_compiler.py pixelle_video/services/hyperframes_project_service.py resources/hyperframes/templates tests/test_hyperframes_compiler.py tests/test_hyperframes_project_service.py
git commit -m "feat: apply media placement in hyperframes templates"
```

## Task 7: Streamlit UI Controls

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Test: `tests/test_style_config_template_gallery.py`
- Test: `tests/test_output_preview.py`

- [ ] **Step 1: Write failing UI param tests**

Add to `tests/test_style_config_template_gallery.py`:

```python
def test_generation_size_controls_include_default_media_placement(fake_st):
    fake_st.session_state.update(
        {
            "video_orientation": "landscape",
            "video_resolution_preset": "landscape_hd",
            "media_orientation": "landscape",
            "media_resolution_preset": "768",
            "sync_media_size_to_canvas": False,
        }
    )

    contract = style_config._render_generation_size_controls()

    assert contract.canvas_width == 1280
    assert fake_st.session_state["media_placement_scale_percent"] == 80
    assert fake_st.session_state["media_placement_anchor"] == "center"
```

Add to `tests/test_output_preview.py` where the generated request payload is asserted:

```python
    assert request["media_placement"] == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 80,
        "anchor": "center",
    }
```

- [ ] **Step 2: Run UI tests and verify failure**

Run:

```powershell
python -m pytest tests/test_style_config_template_gallery.py::test_generation_size_controls_include_default_media_placement tests/test_output_preview.py -q
```

Expected: fails because UI state and request payload do not include `media_placement`.

- [ ] **Step 3: Add UI control helper**

In `web/components/style_config.py`, import:

```python
from pixelle_video.models.media_placement import MediaPlacement
```

Add helper near `_render_generation_size_controls()`:

```python
MEDIA_PLACEMENT_ANCHOR_GRID = [
    ("top_left", "↖"),
    ("top", "↑"),
    ("top_right", "↗"),
    ("left", "←"),
    ("center", "●"),
    ("right", "→"),
    ("bottom_left", "↙"),
    ("bottom", "↓"),
    ("bottom_right", "↘"),
]


def _render_media_placement_controls() -> MediaPlacement:
    scale = st.slider(
        tr("media_placement.scale"),
        min_value=10,
        max_value=100,
        value=int(st.session_state.get("media_placement_scale_percent", 80)),
        step=5,
        key="media_placement_scale_percent",
        help=tr("media_placement.scale_help"),
    )
    current_anchor = st.session_state.get("media_placement_anchor", "center")
    if current_anchor not in {anchor for anchor, _ in MEDIA_PLACEMENT_ANCHOR_GRID}:
        current_anchor = "center"
        st.session_state["media_placement_anchor"] = current_anchor

    st.caption(tr("media_placement.anchor"))
    for row_start in range(0, 9, 3):
        columns = st.columns(3)
        for column, (anchor, label) in zip(columns, MEDIA_PLACEMENT_ANCHOR_GRID[row_start:row_start + 3]):
            button_type = "primary" if anchor == current_anchor else "secondary"
            if column.button(label, key=f"media_placement_anchor_{anchor}", type=button_type):
                st.session_state["media_placement_anchor"] = anchor
                current_anchor = anchor

    placement = MediaPlacement(scale_percent=scale, anchor=current_anchor)
    st.info(
        tr(
            "media_placement.summary",
            scale=placement.scale_percent,
            anchor=tr(f"media_placement.anchor.{placement.anchor}"),
        )
    )
    return placement
```

Call it inside `_render_generation_size_controls()` after the media sync toggle and before the info boxes:

```python
    media_placement = _render_media_placement_controls()
    st.session_state["media_placement"] = media_placement.to_dict()
```

- [ ] **Step 4: Add locale strings**

Add to `web/i18n/locales/zh_CN.json` inside `"t"`:

```json
"media_placement.scale": "图片显示占比",
"media_placement.scale_help": "100% 按最终视频画布计算；80% 会在保持比例的前提下露出背景。",
"media_placement.anchor": "图片位置",
"media_placement.summary": "图片显示：按视频画布 {scale}%，{anchor}",
"media_placement.anchor.top_left": "左上",
"media_placement.anchor.top": "靠上",
"media_placement.anchor.top_right": "右上",
"media_placement.anchor.left": "靠左",
"media_placement.anchor.center": "居中",
"media_placement.anchor.right": "靠右",
"media_placement.anchor.bottom_left": "左下",
"media_placement.anchor.bottom": "靠下",
"media_placement.anchor.bottom_right": "右下"
```

Add matching English strings to `web/i18n/locales/en_US.json`.

- [ ] **Step 5: Include placement in outgoing request payload**

Where the Streamlit pipeline builds the video request, add:

```python
"media_placement": dict(st.session_state.get("media_placement") or MediaPlacement().to_dict()),
```

Keep `sync_media_size_to_canvas` separate and unchanged.

- [ ] **Step 6: Run UI tests**

Run:

```powershell
python -m pytest tests/test_style_config_template_gallery.py tests/test_output_preview.py -q
```

Expected: selected UI/payload tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add web/components/style_config.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_style_config_template_gallery.py tests/test_output_preview.py
git commit -m "feat: add media placement controls"
```

## Task 8: End-To-End Verification

**Files:**
- Modify tests only when assertions need updated names from this plan.

- [ ] **Step 1: Run focused contract suites**

Run:

```powershell
python -m pytest tests/test_media_placement.py tests/test_video_api.py tests/test_storyboard_size_contract.py tests/test_render_package_models.py tests/test_template_render_context.py tests/test_template_visual_materializer.py tests/test_frame_html.py tests/test_hyperframes_compiler.py tests/test_template_media_lint.py tests/test_style_config_template_gallery.py tests/test_output_preview.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run broader render-related suites**

Run:

```powershell
python -m pytest tests/test_standard_pipeline_hyperframes_mode.py tests/test_hyperframes_project_service.py tests/test_hyperframes_runtime_contract.py tests/test_template_util.py tests/test_storyboard_snapshot_persistence.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Generate one legacy visual smoke output**

Run:

```powershell
python - <<'PY'
from pathlib import Path
from PIL import Image
from pixelle_video.services.frame_html import HTMLFrameGenerator
from web.utils.async_helpers import run_async

source = Path("_runtime/media-placement-smoke-source.png")
source.parent.mkdir(parents=True, exist_ok=True)
Image.new("RGB", (1280, 720), (255, 255, 255)).save(source)

output = Path("_runtime/media-placement-smoke-frame.png")
generator = HTMLFrameGenerator(
    "templates/1920x1080/image_landscape_minimal.html",
    canvas_width=1280,
    canvas_height=720,
)
run_async(
    generator.generate_frame(
        title="Smoke",
        text="",
        image=str(source),
        ext={"index": 1},
        output_path=str(output),
        media_placement={"scale_percent": 80, "anchor": "center"},
        media_type="image",
        media_width=1280,
        media_height=720,
    )
)
with Image.open(output) as image:
    print(image.size)
PY
```

Expected output includes `(1280, 720)` and `_runtime/media-placement-smoke-frame.png` visually shows the image centered with background visible.

- [ ] **Step 4: Verify app browser manually**

Open the existing local app at `http://localhost:50915/`, use the current in-app browser, and confirm:

- Default image display summary reads `80%` and `居中`.
- The 9-grid buttons change selected position without changing image generation size.
- `图片尺寸同步到视频` still only changes generated media dimensions.
- A generated 1280x720 video with a horizontal image shows the media at 80% center by default.

- [ ] **Step 5: Commit final test adjustments**

Run:

```powershell
git status --short
git add tests pixelle_video api web resources templates
git commit -m "test: verify media placement contract end to end"
```

Expected: this commit exists only when Task 8 required test assertion edits. If `git status --short` is clean after verification, skip the commit command.

## Self-Review

Spec coverage:

- Platform fact source: Task 1.
- API and request payload: Task 2.
- Storyboard, manifest, persistence: Task 3.
- Legacy HTML rendering and coordinate projection: Task 4.
- Template lint and migration: Task 5.
- HyperFrames parity: Task 6.
- UI default 80%, 9-grid, summary: Task 7.
- Verification across tests, smoke output, and app browser: Task 8.

Placeholder scan:

- The plan contains no placeholder markers and no unspecified error handling step.
- Template migration is expressed as a concrete repository-wide lint-gated action because exact template visual CSS must preserve each template's existing design.

Type consistency:

- `MediaPlacement.to_dict()`, `MediaPlacement.from_dict()`, and `resolve_media_placement()` are used consistently across API, dataclasses, manifests, and renderers.
- `media_placement` remains separate from `media_layout_mode` and `sync_media_size_to_canvas`.
- Legacy rendering projects final-canvas boxes into template coordinates; HyperFrames consumes final-canvas boxes directly.
