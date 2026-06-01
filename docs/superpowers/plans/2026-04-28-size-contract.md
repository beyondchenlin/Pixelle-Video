# Size Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ambiguous 1K/2K/4K output sizing with explicit common delivery presets, while keeping media sizing and template design coordinates separate.

**Architecture:** `pixelle_video/models/size_contract.py` remains the single source of truth for generated canvas/media dimensions. Web and API entry points normalize inputs through `GenerationSizeContract`, template helpers expose design-coordinate metadata, and render outputs continue using explicit `canvas_width`/`canvas_height`.

**Tech Stack:** Python dataclasses, Pydantic API schemas, Streamlit UI components, pytest.

---

## File Structure

- Modify `pixelle_video/models/size_contract.py`: standard output preset registry, legacy aliases, media preset registry, label metadata helpers.
- Modify `tests/test_size_contract.py`: TDD coverage for standard video presets, legacy square compatibility, media independence, invalid non-standard outputs.
- Modify `api/schemas/video.py`: API type hints/descriptions for new preset ids and corrected frame-template description.
- Modify `tests/test_video_api.py`: API accepts new output preset ids and rejects non-standard output presets.
- Modify `pixelle_video/utils/template_util.py`: template contract helper that names design dimensions and orientation.
- Modify `tests/test_template_util.py`: template contract tests.
- Modify `web/components/style_config.py`: use standard video preset options, explicit labels, and template design-size copy.
- Modify `tests/test_style_config_template_gallery.py`: UI size-control tests for new labels/options.
- Modify `web/i18n/locales/zh_CN.json` and `web/i18n/locales/en_US.json`: copy updates for final video, media generation, and template design size.
- Modify `tests/test_output_preview.py`: request builder regression for new preset ids and actual canvas summary.
- Modify render pipeline tests only if existing assertions depend on old preset ids.

---

### Task 1: Size Contract Preset Registry

**Files:**
- Modify: `pixelle_video/models/size_contract.py`
- Modify: `tests/test_size_contract.py`

- [ ] **Step 1: Write failing tests for common output presets**

Append to `tests/test_size_contract.py`:

```python
def test_standard_video_presets_exclude_non_common_delivery_sizes():
    from pixelle_video.models.size_contract import STANDARD_VIDEO_SIZE_PRESETS

    all_standard_sizes = {
        spec.as_tuple()
        for presets in STANDARD_VIDEO_SIZE_PRESETS.values()
        for spec in presets.values()
    }

    assert (1280, 720) in all_standard_sizes
    assert (1920, 1080) in all_standard_sizes
    assert (3840, 2160) in all_standard_sizes
    assert (720, 1280) in all_standard_sizes
    assert (1080, 1920) in all_standard_sizes
    assert (2160, 3840) in all_standard_sizes
    assert (1080, 1080) in all_standard_sizes
    assert (1920, 720) not in all_standard_sizes
    assert (1024, 1024) not in all_standard_sizes
    assert (2048, 2048) not in all_standard_sizes
```

- [ ] **Step 2: Write failing tests for new preset ids and legacy aliases**

Replace the existing `test_resolve_canvas_size_for_orientation_presets` parameter list with:

```python
@pytest.mark.parametrize(
    ("orientation", "preset", "expected"),
    [
        ("landscape", "landscape_hd", SizeSpec(1280, 720)),
        ("landscape", "landscape_full_hd", SizeSpec(1920, 1080)),
        ("landscape", "landscape_4k", SizeSpec(3840, 2160)),
        ("portrait", "portrait_hd", SizeSpec(720, 1280)),
        ("portrait", "portrait_full_hd", SizeSpec(1080, 1920)),
        ("portrait", "portrait_4k", SizeSpec(2160, 3840)),
        ("square", "square_standard", SizeSpec(1080, 1080)),
        ("landscape", "1k", SizeSpec(1280, 720)),
        ("landscape", "2k", SizeSpec(1920, 1080)),
        ("portrait", "2k", SizeSpec(1080, 1920)),
        ("square", "1k", SizeSpec(1024, 1024)),
        ("square", "2k", SizeSpec(2048, 2048)),
        ("square", "4k", SizeSpec(4096, 4096)),
    ],
)
def test_resolve_canvas_size_for_orientation_presets(orientation, preset, expected):
    assert resolve_canvas_size(orientation, preset) == expected
```

Add:

```python
def test_default_generation_size_contract_uses_common_landscape_hd_output():
    contract = GenerationSizeContract.default()

    assert (contract.canvas_width, contract.canvas_height) == (1280, 720)
    assert contract.video_orientation == "landscape"
    assert contract.video_resolution_preset == "landscape_hd"


def test_non_standard_output_size_alias_is_rejected():
    with pytest.raises(ValueError, match="unsupported video resolution preset"):
        GenerationSizeContract.from_params(
            {
                "video_orientation": "landscape",
                "video_resolution_preset": "1920x720",
            }
        )
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/test_size_contract.py -q
```

Expected: failures mentioning missing `STANDARD_VIDEO_SIZE_PRESETS` and old `1k` defaults.

- [ ] **Step 4: Implement standard and legacy preset registries**

In `pixelle_video/models/size_contract.py`, replace the top-level preset constants and maps with:

```python
VALID_ORIENTATIONS = ("landscape", "portrait", "square")

STANDARD_VIDEO_SIZE_PRESETS: dict[str, dict[str, SizeSpec]] = {
    "landscape": {
        "landscape_hd": SizeSpec(1280, 720),
        "landscape_full_hd": SizeSpec(1920, 1080),
        "landscape_4k": SizeSpec(3840, 2160),
    },
    "portrait": {
        "portrait_hd": SizeSpec(720, 1280),
        "portrait_full_hd": SizeSpec(1080, 1920),
        "portrait_4k": SizeSpec(2160, 3840),
    },
    "square": {
        "square_standard": SizeSpec(1080, 1080),
    },
}

LEGACY_VIDEO_SIZE_PRESETS: dict[str, dict[str, SizeSpec]] = {
    "landscape": {
        "1k": STANDARD_VIDEO_SIZE_PRESETS["landscape"]["landscape_hd"],
        "2k": STANDARD_VIDEO_SIZE_PRESETS["landscape"]["landscape_full_hd"],
        "4k": STANDARD_VIDEO_SIZE_PRESETS["landscape"]["landscape_4k"],
    },
    "portrait": {
        "1k": STANDARD_VIDEO_SIZE_PRESETS["portrait"]["portrait_hd"],
        "2k": STANDARD_VIDEO_SIZE_PRESETS["portrait"]["portrait_full_hd"],
        "4k": STANDARD_VIDEO_SIZE_PRESETS["portrait"]["portrait_4k"],
    },
    "square": {
        "1k": SizeSpec(1024, 1024),
        "2k": SizeSpec(2048, 2048),
        "4k": SizeSpec(4096, 4096),
    },
}

VIDEO_SIZE_PRESETS: dict[str, dict[str, SizeSpec]] = {
    orientation: {
        **STANDARD_VIDEO_SIZE_PRESETS[orientation],
        **LEGACY_VIDEO_SIZE_PRESETS[orientation],
    }
    for orientation in VALID_ORIENTATIONS
}

VALID_VIDEO_RESOLUTION_PRESETS = tuple(
    preset
    for presets in VIDEO_SIZE_PRESETS.values()
    for preset in presets
)

VALID_MEDIA_RESOLUTION_PRESETS = ("768", "1k", "2k", "4k")

DEFAULT_VIDEO_ORIENTATION = "landscape"
DEFAULT_VIDEO_RESOLUTION_PRESETS_BY_ORIENTATION = {
    "landscape": "landscape_hd",
    "portrait": "portrait_hd",
    "square": "square_standard",
}
DEFAULT_VIDEO_RESOLUTION_PRESET = DEFAULT_VIDEO_RESOLUTION_PRESETS_BY_ORIENTATION[
    DEFAULT_VIDEO_ORIENTATION
]
DEFAULT_MEDIA_ORIENTATION = "landscape"
DEFAULT_MEDIA_RESOLUTION_PRESET = "1k"
```

Replace `_VIDEO_PRESET_ALIASES` with orientation-aware aliases:

```python
_VIDEO_PRESET_ALIASES_BY_ORIENTATION = {
    "landscape": {
        "1280x720": "landscape_hd",
        "1920x1080": "landscape_full_hd",
        "3840x2160": "landscape_4k",
    },
    "portrait": {
        "720x1280": "portrait_hd",
        "1080x1920": "portrait_full_hd",
        "2160x3840": "portrait_4k",
    },
    "square": {
        "1080x1080": "square_standard",
        "1024x1024": "1k",
        "2048x2048": "2k",
        "4096x4096": "4k",
    },
}
```

Update `normalize_video_resolution_preset`:

```python
def normalize_video_resolution_preset(
    value: Any = None,
    *,
    orientation: str | None = None,
) -> str:
    normalized_orientation = normalize_video_orientation(orientation)
    default = DEFAULT_VIDEO_RESOLUTION_PRESETS_BY_ORIENTATION[normalized_orientation]
    preset = _normalize_optional_string(value, default)
    preset = _VIDEO_PRESET_ALIASES_BY_ORIENTATION[normalized_orientation].get(
        preset,
        preset,
    )
    if preset not in VIDEO_SIZE_PRESETS[normalized_orientation]:
        raise ValueError(f"unsupported video resolution preset: {preset}")
    return preset
```

Update calls:

```python
normalized_preset = normalize_video_resolution_preset(
    preset,
    orientation=normalized_orientation,
)
```

and:

```python
video_preset = normalize_video_resolution_preset(
    source.get("video_resolution_preset"),
    orientation=video_orientation,
)
```

- [ ] **Step 5: Update media preset aliases**

Keep media model aliases permissive, but avoid depending on video alias internals:

```python
_MEDIA_PRESET_ALIASES = {
    "768x768": "768",
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
```

- [ ] **Step 6: Run size contract tests**

Run:

```bash
pytest tests/test_size_contract.py -q
```

Expected: all tests in `tests/test_size_contract.py` pass.

- [ ] **Step 7: Commit**

```bash
git add pixelle_video/models/size_contract.py tests/test_size_contract.py
git commit -m "refactor: 统一标准输出尺寸合同"
```

---

### Task 2: API Contract Alignment

**Files:**
- Modify: `api/schemas/video.py`
- Modify: `api/routers/video.py` only if import or validation behavior needs a local adjustment
- Modify: `tests/test_video_api.py`

- [ ] **Step 1: Write failing API schema tests**

In `tests/test_video_api.py`, replace old preset assertions in `test_video_generate_request_accepts_size_contract_controls` with:

```python
request = VideoGenerateRequest(
    text="demo",
    canvas_width=1280,
    canvas_height=720,
    media_width=768,
    media_height=768,
    video_orientation="landscape",
    video_resolution_preset="landscape_hd",
    media_orientation="square",
    media_resolution_preset="768",
    sync_media_size_to_canvas=False,
)

assert request.video_resolution_preset == "landscape_hd"
```

Add:

```python
def test_video_generate_request_accepts_new_full_hd_preset():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            video_orientation="landscape",
            video_resolution_preset="landscape_full_hd",
            media_orientation="square",
            media_resolution_preset="768",
        ),
        request_id="req_full_hd",
    )

    assert (params["canvas_width"], params["canvas_height"]) == (1920, 1080)
    assert params["video_resolution_preset"] == "landscape_full_hd"


def test_video_generate_request_rejects_non_standard_1920x720_output():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            video_orientation="landscape",
            video_resolution_preset="1920x720",
        )
```

- [ ] **Step 2: Run API tests to verify failure**

Run:

```bash
pytest tests/test_video_api.py::test_video_generate_request_accepts_new_full_hd_preset tests/test_video_api.py::test_video_generate_request_rejects_non_standard_1920x720_output -q
```

Expected: first test fails until schema type accepts new ids; second may fail if schema still accepts arbitrary strings.

- [ ] **Step 3: Update API preset type definitions**

In `api/schemas/video.py`, update the type aliases near `VideoGenerateRequest`:

```python
VideoResolutionPreset = Literal[
    "landscape_hd",
    "landscape_full_hd",
    "landscape_4k",
    "portrait_hd",
    "portrait_full_hd",
    "portrait_4k",
    "square_standard",
    "1k",
    "2k",
    "4k",
]
MediaResolutionPreset = Literal["768", "1k", "2k", "4k"]
```

Update the frame template description:

```python
frame_template: Optional[str] = Field(
    None,
    description=(
        "HTML template path with design coordinate size, e.g. "
        "'1920x1080/image_landscape_minimal.html'. Final video size is controlled "
        "by canvas_width/canvas_height or video_resolution_preset."
    ),
)
```

- [ ] **Step 4: Run API tests**

Run:

```bash
pytest tests/test_video_api.py -q
```

Expected: all API tests pass.

- [ ] **Step 5: Commit**

```bash
git add api/schemas/video.py tests/test_video_api.py
git commit -m "fix: 对齐视频接口尺寸预设合同"
```

---

### Task 3: Template Design Contract Helper

**Files:**
- Modify: `pixelle_video/utils/template_util.py`
- Modify: `tests/test_template_util.py`

- [ ] **Step 1: Write failing template contract tests**

Append to `tests/test_template_util.py`:

```python
from pixelle_video.utils.template_util import parse_template_contract


def test_parse_template_contract_exposes_design_size_and_orientation():
    contract = parse_template_contract("1920x1080/image_landscape_minimal.html")

    assert contract.template_design_width == 1920
    assert contract.template_design_height == 1080
    assert contract.template_orientation == "landscape"
    assert contract.template_path == "1920x1080/image_landscape_minimal.html"


def test_template_contract_does_not_claim_final_output_size():
    contract = parse_template_contract("1080x1920/image_default.html")

    assert not hasattr(contract, "canvas_width")
    assert not hasattr(contract, "canvas_height")
```

- [ ] **Step 2: Run template tests to verify failure**

Run:

```bash
pytest tests/test_template_util.py -q
```

Expected: import failure for `parse_template_contract`.

- [ ] **Step 3: Implement template contract helper**

In `pixelle_video/utils/template_util.py`, add after `TemplateInfo`:

```python
class TemplateContract(BaseModel):
    """Template design-coordinate metadata. This never defines final output size."""

    template_path: str = Field(..., description="Template path relative to templates root")
    template_design_width: int = Field(..., description="Template design coordinate width")
    template_design_height: int = Field(..., description="Template design coordinate height")
    template_orientation: Literal["portrait", "landscape", "square"] = Field(
        ...,
        description="Template layout orientation",
    )
```

Add after `get_template_orientation`:

```python
def parse_template_contract(template_path: str) -> TemplateContract:
    width, height = parse_template_size(template_path)
    if width > height:
        orientation: Literal["portrait", "landscape", "square"] = "landscape"
    elif height > width:
        orientation = "portrait"
    else:
        orientation = "square"
    return TemplateContract(
        template_path=template_path,
        template_design_width=width,
        template_design_height=height,
        template_orientation=orientation,
    )
```

- [ ] **Step 4: Run template tests**

Run:

```bash
pytest tests/test_template_util.py -q
```

Expected: all template util tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/utils/template_util.py tests/test_template_util.py
git commit -m "feat: 增加模板设计尺寸合同"
```

---

### Task 4: Web UI Size Controls and Copy

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `tests/test_style_config_template_gallery.py`

- [ ] **Step 1: Write failing UI tests for standard video options**

In `tests/test_style_config_template_gallery.py`, update `FakeStreamlit` in `test_render_generation_size_controls_returns_independent_image_size`:

```python
self.session_state = {
    "video_orientation": "portrait",
    "video_resolution_preset": "portrait_full_hd",
    "media_orientation": "landscape",
    "media_resolution_preset": "4k",
    "sync_media_size_to_canvas": False,
}
```

Append:

```python
def test_render_generation_size_controls_uses_standard_video_presets(monkeypatch):
    captured_video_options = []
    captured_video_labels = []

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "video_orientation": "landscape",
                "video_resolution_preset": "landscape_full_hd",
                "media_orientation": "square",
                "media_resolution_preset": "768",
                "sync_media_size_to_canvas": False,
            }

        def segmented_control(self, label, options, *, format_func, default, key):
            if key == "video_resolution_preset":
                captured_video_options.extend(options)
                captured_video_labels.extend(format_func(option) for option in options)
            return self.session_state[key]

        def toggle(self, _label, *, value, help, key):
            return self.session_state[key]

        def info(self, _message):
            return None

    monkeypatch.setattr(style_config, "st", FakeStreamlit())
    monkeypatch.setattr(
        style_config,
        "tr",
        lambda key, **kwargs: key.format(**kwargs) if kwargs else key,
    )

    contract = style_config._render_generation_size_controls()

    assert (contract.canvas_width, contract.canvas_height) == (1920, 1080)
    assert "1920x720" not in "".join(captured_video_labels)
    assert "1K" not in "".join(captured_video_labels)
    assert captured_video_options == [
        "landscape_hd",
        "landscape_full_hd",
        "landscape_4k",
    ]
```

- [ ] **Step 2: Run UI tests to verify failure**

Run:

```bash
pytest tests/test_style_config_template_gallery.py -q
```

Expected: failures because UI still uses old `VIDEO_SIZE_PRESETS` options and labels.

- [ ] **Step 3: Update UI imports and labels**

In `web/components/style_config.py`, import `STANDARD_VIDEO_SIZE_PRESETS`:

```python
from pixelle_video.models.size_contract import (
    DEFAULT_MEDIA_ORIENTATION,
    DEFAULT_MEDIA_RESOLUTION_PRESET,
    DEFAULT_VIDEO_ORIENTATION,
    DEFAULT_VIDEO_RESOLUTION_PRESETS_BY_ORIENTATION,
    GenerationSizeContract,
    MEDIA_SIZE_PRESETS,
    STANDARD_VIDEO_SIZE_PRESETS,
)
```

Add helper functions near `_render_size_segmented_control`:

```python
def _format_size_label(name: str, spec) -> str:
    return f"{name} ({spec.width}×{spec.height})"


def _build_video_preset_labels(orientation: str) -> dict[str, str]:
    names = {
        "landscape_hd": tr("size.preset.landscape_hd"),
        "landscape_full_hd": tr("size.preset.landscape_full_hd"),
        "landscape_4k": tr("size.preset.landscape_4k"),
        "portrait_hd": tr("size.preset.portrait_hd"),
        "portrait_full_hd": tr("size.preset.portrait_full_hd"),
        "portrait_4k": tr("size.preset.portrait_4k"),
        "square_standard": tr("size.preset.square_standard"),
    }
    return {
        preset: _format_size_label(names[preset], spec)
        for preset, spec in STANDARD_VIDEO_SIZE_PRESETS[orientation].items()
    }
```

In `_render_generation_size_controls`, change video options/default:

```python
video_preset_labels = _build_video_preset_labels(video_orientation)
video_resolution_preset = _render_size_segmented_control(
    label=tr("size.video_resolution"),
    options=list(STANDARD_VIDEO_SIZE_PRESETS[video_orientation].keys()),
    labels=video_preset_labels,
    key="video_resolution_preset",
    default=DEFAULT_VIDEO_RESOLUTION_PRESETS_BY_ORIENTATION[video_orientation],
)
```

Keep media options from `MEDIA_SIZE_PRESETS`, but make labels dimension-first:

```python
media_preset_labels = {
    preset: f"{spec.width}×{spec.height}"
    for preset, spec in MEDIA_SIZE_PRESETS[media_orientation].items()
}
```

- [ ] **Step 4: Update i18n strings**

Add keys to `web/i18n/locales/zh_CN.json`:

```json
"size.preset.landscape_hd": "HD 横屏",
"size.preset.landscape_full_hd": "Full HD 横屏",
"size.preset.landscape_4k": "4K 横屏",
"size.preset.portrait_hd": "HD 竖屏",
"size.preset.portrait_full_hd": "Full HD 竖屏",
"size.preset.portrait_4k": "4K 竖屏",
"size.preset.square_standard": "标准方屏",
"size.template_base_info": "模板坐标尺寸：{width} × {height}，仅用于布局缩放"
```

Add keys to `web/i18n/locales/en_US.json`:

```json
"size.preset.landscape_hd": "HD landscape",
"size.preset.landscape_full_hd": "Full HD landscape",
"size.preset.landscape_4k": "4K landscape",
"size.preset.portrait_hd": "HD portrait",
"size.preset.portrait_full_hd": "Full HD portrait",
"size.preset.portrait_4k": "4K portrait",
"size.preset.square_standard": "Standard square",
"size.template_base_info": "Template coordinate size: {width} × {height}, used only for layout scaling"
```

If a key already exists, replace only its value and keep JSON ordering near the current `size.*` keys.

- [ ] **Step 5: Run UI tests**

Run:

```bash
pytest tests/test_style_config_template_gallery.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add web/components/style_config.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_style_config_template_gallery.py
git commit -m "fix: 明确输出尺寸与模板坐标展示"
```

---

### Task 5: Request Builders and Render Manifest Regression

**Files:**
- Modify: `tests/test_output_preview.py`
- Modify: `tests/test_render_package_models.py`
- Modify: existing render pipeline tests only if they assert old preset ids

- [ ] **Step 1: Add request builder tests for new ids**

Append to `tests/test_output_preview.py`:

```python
def test_build_single_generation_request_uses_full_hd_standard_preset():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "video_orientation": "landscape",
            "video_resolution_preset": "landscape_full_hd",
            "media_orientation": "square",
            "media_resolution_preset": "768",
            "sync_media_size_to_canvas": False,
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1920, "template_media_height": 1080},
    )

    assert (request["canvas_width"], request["canvas_height"]) == (1920, 1080)
    assert (request["media_width"], request["media_height"]) == (768, 768)
    assert request["video_resolution_preset"] == "landscape_full_hd"


def test_build_batch_shared_config_uses_standard_video_preset():
    shared_config = output_preview.build_batch_shared_config(
        {
            "title_prefix": "Series",
            "video_orientation": "portrait",
            "video_resolution_preset": "portrait_full_hd",
            "media_orientation": "square",
            "media_resolution_preset": "768",
        }
    )

    assert (shared_config["canvas_width"], shared_config["canvas_height"]) == (
        1080,
        1920,
    )
    assert shared_config["video_resolution_preset"] == "portrait_full_hd"
```

- [ ] **Step 2: Add manifest regression for canvas fields**

In `tests/test_render_package_models.py`, add near existing manifest tests:

```python
def test_render_manifest_serializes_canvas_size_from_size_contract():
    manifest = RenderManifest(
        task_id="task-size",
        title="Size Demo",
        fps=30,
        template_id="image_landscape_minimal",
        canvas_width=1920,
        canvas_height=1080,
        media_width=768,
        media_height=768,
    )

    data = manifest.to_dict()

    assert data["canvas_width"] == 1920
    assert data["canvas_height"] == 1080
    assert data["width"] == 1920
    assert data["height"] == 1080
    assert data["media_width"] == 768
    assert data["media_height"] == 768
```

- [ ] **Step 3: Run targeted tests**

Run:

```bash
pytest tests/test_output_preview.py tests/test_render_package_models.py -q
```

Expected: any failures are old preset-id assumptions that need updating.

- [ ] **Step 4: Update old preset assertions**

Search:

```bash
Select-String -Path tests\*.py -Pattern '"video_resolution_preset": "1k"','video_resolution_preset"] == "1k"'
```

For tests that model new UI/API behavior, replace `"1k"` with `"landscape_hd"` or the orientation-specific id. Keep `"1k"` only in tests explicitly named legacy compatibility.

- [ ] **Step 5: Run targeted tests again**

Run:

```bash
pytest tests/test_output_preview.py tests/test_render_package_models.py tests/test_video_api.py tests/test_size_contract.py -q
```

Expected: all targeted tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_output_preview.py tests/test_render_package_models.py
git commit -m "test: 覆盖标准尺寸请求与渲染清单"
```

---

### Task 6: Full Verification and Cleanup

**Files:**
- Modify only files required by failures surfaced in this task.

- [ ] **Step 1: Run complete size-related test set**

Run:

```bash
pytest tests/test_size_contract.py tests/test_video_api.py tests/test_output_preview.py tests/test_style_config_template_gallery.py tests/test_template_util.py tests/test_render_package_models.py tests/test_storyboard_size_contract.py tests/test_storyboard_snapshot_persistence.py tests/test_tts_comfyui_defaults.py -q
```

Expected: all listed tests pass.

- [ ] **Step 2: Search for old misleading output labels**

Run:

```bash
Select-String -Path pixelle_video\**\*.py,web\**\*.py,tests\**\*.py -Pattern '1K \\(','2K \\(','1920x720','Frame Template \\(determines video size\\)','Video size is auto-determined from template'
```

Expected: no production UI/API strings imply template determines final video size. Remaining `1k`/`2k` hits should be legacy compatibility data or media-size presets, not user-facing output labels.

- [ ] **Step 3: Run formatting or lint command if the repo exposes one**

Check `pyproject.toml`. If it defines a pytest-only workflow and no formatter, skip formatting. If a formatter target exists, run it and commit formatting separately only if files change.

- [ ] **Step 4: Final status check**

Run:

```bash
git status --short
```

Expected: only unrelated pre-existing worktree changes remain, or the tree is clean for files touched by this plan.

- [ ] **Step 5: Commit verification fixes if needed**

If Step 1 or Step 2 required any code changes:

```bash
git add pixelle_video/models/size_contract.py api/schemas/video.py pixelle_video/utils/template_util.py web/components/style_config.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_size_contract.py tests/test_video_api.py tests/test_template_util.py tests/test_style_config_template_gallery.py tests/test_output_preview.py tests/test_render_package_models.py
git commit -m "fix: 清理尺寸合同遗留引用"
```

If no code changed, do not create an empty commit.
