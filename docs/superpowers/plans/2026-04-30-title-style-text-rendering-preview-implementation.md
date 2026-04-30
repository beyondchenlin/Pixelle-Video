# Title Style Text Rendering Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立正式的 `text_rendering.title_style` 渲染契约，并在文字渲染配置中增加字幕、标题、图片同屏的实施预览区。

**Architecture:** `title_style` 与 `caption_style`、`overlay_style` 并列，复用同一套 `TextStyleProfileRequest` / `TextStyleProfile`，默认值只来自模板文字 preset。即时预览由前端 `TextRenderingPreviewSpec` 派生，不写入 API payload；真实预览帧通过 HyperFrames 编译链路和 artifact/object storage key 表达，不把本地路径作为正式返回值。

**Tech Stack:** Python 3.11, Pydantic, dataclasses, pytest, Streamlit, HyperFrames HTML/CSS/GSAP, FastAPI, Pixelle platform Artifact/Object Store contracts.

---

## Boundary Rules

- `text_rendering.title_style` 是渲染契约，不属于 Stage 1A `PromptPlan`，不属于 Stage 2 IP `StyleProfile`。
- 模板标题默认值只允许在 `pixelle_video/models/template_text_style_presets.py` 维护；前端、schema、模板 CSS 不再复制默认值。
- `title_style` 不进入 `template_params`，标题仍是模板主标题，不进入 `TextCue` timeline。
- 即时预览只消费正式契约派生出的 `TextRenderingPreviewSpec`，演示标题、演示字幕、占位图不进入生成 payload。
- 真实预览帧必须输出 `storage_key` 和可选 `url`，不能输出 `output/...`、`_runtime/...` 或 Windows/Linux 本地路径。
- 若 Stage 0.5 已在其他分支提供 `ArtifactObjectStore` 适配器，本计划复用现有实现；若当前代码仍只有 Protocol，本计划在 `pixelle_video/storage/artifact_object_store.py` 新增受控 dev adapter，避免 UI 或 API 自己拼本地路径。

## File Structure

- Modify `api/schemas/text_rendering.py`: 给 `TextRenderingRequest` 新增 `title_style: Optional[TextStyleProfileRequest]`。
- Modify `pixelle_video/models/text_style.py`: 新增 `DEFAULT_TITLE_STYLE_ID`，默认 profile 扩展为 caption/title/overlay，并支持模板标题 preset。
- Create `pixelle_video/models/template_text_style_presets.py`: 模板标题样式 preset、标题区域、字幕安全区、模板 ID 归一化。
- Modify `pixelle_video/services/text_rendering_orchestrator.py`: 构建 `title_style`，输出 `TextRenderingBuildResult.title_style`，让 package 包含三类 profile。
- Modify `pixelle_video/services/text_rendering_contract_summary.py`: summary 中纳入标题 profile ID，保持 caption 和 overlay 既有行为。
- Modify `pixelle_video/models/template_render_context.py`: 新增 `title_style_profile`，并把模板文字区域能力从描述扩展到可消费 spec。
- Modify `pixelle_video/services/hyperframes_project_service.py`: 从 `RenderManifest.text_style_profiles` 解析 `title_style_profile`。
- Modify `pixelle_video/services/hyperframes_compiler.py`: 注入 `--title-*` CSS 变量，标题文本按 `max_chars_per_line` 安全换行。
- Modify `resources/hyperframes/templates/*/index.template.html`: 带 `title_region` 的模板标题 CSS 改为消费 `--title-*` 变量。
- Modify `pixelle_video/models/template_text_capabilities.py`: 增加标题 preset 能力校验入口，不影响 overlay text cue 校验。
- Create `pixelle_video/services/text_rendering_preview.py`: 真实预览帧请求、fingerprint、渲染服务、artifact 输出契约。
- Create `api/schemas/text_rendering_preview.py`: 真实预览帧 API 输入输出 schema，只接受资源引用和正式契约。
- Create `api/routers/text_rendering_preview.py`: `POST /text-rendering/preview-frame`，显式生成真实预览帧。
- Modify `api/routers/__init__.py` and app router registration file if present: 注册新 router。
- Create `pixelle_video/storage/artifact_object_store.py`: 当仓库仍缺少通用 artifact object dev adapter 时，提供 `FilesystemDevArtifactObjectStore`。
- Modify `pixelle_video/storage/__init__.py`: 导出新增 artifact object store。
- Create `web/components/text_rendering_preview.py`: `TextRenderingPreviewSpec`、即时预览 HTML、真实预览按钮状态渲染。
- Modify `web/components/text_rendering_config.py`: 字幕/标题样式 tab、`title_style` payload 清洗、预览 spec 构建入口。
- Modify `web/components/style_config.py`: 调整渲染顺序，先解析模板/尺寸/媒体摆放，再渲染文字渲染配置和预览。
- Modify `web/pipelines/standard.py`: 把左侧内容输入透传给 `render_style_config`，供实施预览显示标题和首句字幕。
- Modify `web/i18n/locales/zh_CN.json` and `web/i18n/locales/en_US.json`: 新增标题样式、实施预览、真实预览文案。
- Modify tests listed in each task below.

## Task 1: API Schema Accepts Title Style

**Files:**
- Modify: `api/schemas/text_rendering.py`
- Modify: `tests/test_text_rendering_api_schema.py`
- Modify: `tests/test_style_config_text_rendering_ui.py`

- [ ] **Step 1: Write the failing schema tests**

Add these tests to `tests/test_text_rendering_api_schema.py`:

```python
from pydantic import ValidationError


def test_text_rendering_request_accepts_title_style_with_caption_shape():
    request = TextRenderingRequest.model_validate(
        {
            "title_style": {
                "font_family": "Noto Sans CJK SC",
                "font_size": 88,
                "primary_color": "#112233",
                "stroke_color": "#FFFFFF",
                "stroke_width": 3,
                "background_color": "#000000",
                "background_opacity": 0.75,
                "position": "top_left",
                "margin_y": 72,
                "max_chars_per_line": 9,
            }
        }
    )

    assert request.title_style is not None
    assert request.title_style.font_size == 88
    assert request.title_style.background_opacity == 0.75
    assert request.title_style.position == "top_left"


def test_title_style_forbids_unknown_fields_like_caption_style():
    with pytest.raises(ValidationError):
        TextRenderingRequest.model_validate(
            {
                "title_style": {
                    "font_size": 88,
                    "title_shadow_preset": "private-template-field",
                }
            }
        )
```

Extend `test_text_style_request_serializes_as_partial_override` in `tests/test_text_rendering_api_schema.py`:

```python
request = TextRenderingRequest.model_validate(
    {
        "caption_style": {"font_size": 72, "font_file": "fonts/simhei.ttf"},
        "title_style": {"font_size": 96, "background_opacity": 0.9},
        "overlay_style": {},
    }
)

payload = request.model_dump(exclude_none=True)

assert payload["title_style"] == {
    "background_opacity": 0.9,
    "font_size": 96,
}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_text_rendering_api_schema.py::test_text_rendering_request_accepts_title_style_with_caption_shape tests/test_text_rendering_api_schema.py::test_title_style_forbids_unknown_fields_like_caption_style -q
```

Expected: FAIL because `TextRenderingRequest` has no `title_style`.

- [ ] **Step 3: Add schema field**

In `api/schemas/text_rendering.py`, update `TextRenderingRequest`:

```python
class TextRenderingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overlay: TextOverlayRequest = Field(default_factory=TextOverlayRequest)
    image_text: ImageTextPolicyRequest = Field(default_factory=ImageTextPolicyRequest)
    caption_style: Optional[TextStyleProfileRequest] = None
    title_style: Optional[TextStyleProfileRequest] = None
    overlay_style: Optional[TextStyleProfileRequest] = None
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_text_rendering_api_schema.py tests/test_style_config_text_rendering_ui.py::test_text_rendering_request_accepts_caption_style_and_forbids_unknown_fields -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add api/schemas/text_rendering.py tests/test_text_rendering_api_schema.py tests/test_style_config_text_rendering_ui.py
git commit -m "feat: 接受标题文字渲染样式契约"
git push
```

## Task 2: Template Title Presets Are Source of Truth

**Files:**
- Create: `pixelle_video/models/template_text_style_presets.py`
- Modify: `pixelle_video/models/text_style.py`
- Modify: `pixelle_video/models/template_render_context.py`
- Modify: `tests/test_text_style_models.py`
- Create: `tests/test_template_text_style_presets.py`
- Modify: `tests/test_template_render_context.py`

- [ ] **Step 1: Write failing preset tests**

Create `tests/test_template_text_style_presets.py`:

```python
import pytest

from pixelle_video.models.template_text_style_presets import (
    TEMPLATE_TEXT_STYLE_PRESETS,
    TemplateTextStylePreset,
    normalize_template_id,
    require_template_text_style_preset,
    resolve_template_text_style_preset,
)
from pixelle_video.models.text_style import DEFAULT_TITLE_STYLE_ID


def test_template_text_style_presets_cover_phase1_title_templates():
    assert set(TEMPLATE_TEXT_STYLE_PRESETS) == {
        "image_default",
        "image_life_insights_light",
        "image_landscape_full",
        "image_landscape_minimal",
    }

    for template_id, preset in TEMPLATE_TEXT_STYLE_PRESETS.items():
        assert preset.template_id == template_id
        assert preset.title_style["id"] == DEFAULT_TITLE_STYLE_ID
        assert preset.title_region["x"] >= 0
        assert preset.title_region["y"] >= 0
        assert preset.title_region["width"] > 0
        assert preset.title_region["height"] > 0
        assert preset.caption_safe_area["width"] > 0
        assert preset.caption_safe_area["height"] > 0


def test_normalize_template_id_accepts_frame_template_paths():
    assert normalize_template_id("1080x1920/image_default.html") == "image_default"
    assert normalize_template_id("image_landscape_full") == "image_landscape_full"
    assert normalize_template_id(None) is None


def test_resolve_template_text_style_preset_returns_generic_for_missing_template():
    preset = resolve_template_text_style_preset("static_plain")

    assert isinstance(preset, TemplateTextStylePreset)
    assert preset.template_id == "generic"
    assert preset.title_style["id"] == DEFAULT_TITLE_STYLE_ID


def test_require_template_text_style_preset_fails_for_missing_title_region_preset():
    with pytest.raises(ValueError, match="title preset"):
        require_template_text_style_preset("static_plain")
```

Update `tests/test_text_style_models.py`:

```python
from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
    DEFAULT_TITLE_STYLE_ID,
    TextStyleProfile,
    build_default_text_style_profiles,
    normalize_hex_color,
)


def test_default_text_style_profiles_include_caption_title_and_overlay_defaults():
    profiles = build_default_text_style_profiles(template_id="image_landscape_minimal")

    assert [profile.id for profile in profiles] == [
        DEFAULT_CAPTION_STYLE_ID,
        DEFAULT_TITLE_STYLE_ID,
        DEFAULT_OVERLAY_STYLE_ID,
    ]
    title = profiles[1]
    assert title.name == "Title Default"
    assert title.position == "top_left"
    assert title.font_size == 76
    assert title.background_color == "#FFFFFF"
    assert title.background_opacity == 0.88
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_template_text_style_presets.py tests/test_text_style_models.py::test_default_text_style_profiles_include_caption_title_and_overlay_defaults -q
```

Expected: FAIL because preset module and `DEFAULT_TITLE_STYLE_ID` do not exist.

- [ ] **Step 3: Create preset registry**

Create `pixelle_video/models/template_text_style_presets.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from pixelle_video.models.text_style import DEFAULT_TITLE_STYLE_ID


@dataclass(frozen=True)
class TemplateTextStylePreset:
    template_id: str
    has_title_region: bool
    title_style: Mapping[str, Any]
    title_region: Mapping[str, float]
    caption_safe_area: Mapping[str, float]

    def title_style_dict(self) -> dict[str, Any]:
        return dict(self.title_style)

    def title_region_dict(self) -> dict[str, float]:
        return dict(self.title_region)

    def caption_safe_area_dict(self) -> dict[str, float]:
        return dict(self.caption_safe_area)


GENERIC_TEMPLATE_TEXT_STYLE_PRESET = TemplateTextStylePreset(
    template_id="generic",
    has_title_region=False,
    title_style={
        "id": DEFAULT_TITLE_STYLE_ID,
        "name": "Title Default",
        "font_family": "Noto Sans CJK SC",
        "font_size": 72,
        "font_weight": 700,
        "primary_color": "#FFFFFF",
        "stroke_color": "#000000",
        "stroke_width": 2,
        "background_color": None,
        "background_opacity": 0.0,
        "position": "top",
        "alignment": "center",
        "margin_x": 80,
        "margin_y": 96,
        "max_width_ratio": 0.84,
        "line_height": 1.16,
        "max_chars_per_line": 14,
        "punctuation_mode": "preserve",
    },
    title_region={"x": 0.08, "y": 0.04, "width": 0.84, "height": 0.16},
    caption_safe_area={"x": 0.08, "y": 0.76, "width": 0.84, "height": 0.16},
)


TEMPLATE_TEXT_STYLE_PRESETS: dict[str, TemplateTextStylePreset] = {
    "image_default": TemplateTextStylePreset(
        template_id="image_default",
        has_title_region=True,
        title_style={
            **GENERIC_TEMPLATE_TEXT_STYLE_PRESET.title_style,
            "font_size": 84,
            "font_weight": 800,
            "primary_color": "#2C3E50",
            "stroke_width": 0,
            "background_color": "#FFFFFF",
            "background_opacity": 0.92,
            "position": "top",
            "margin_y": 84,
            "max_chars_per_line": 10,
        },
        title_region={"x": 0.09, "y": 0.045, "width": 0.82, "height": 0.16},
        caption_safe_area={"x": 0.10, "y": 0.73, "width": 0.80, "height": 0.16},
    ),
    "image_life_insights_light": TemplateTextStylePreset(
        template_id="image_life_insights_light",
        has_title_region=True,
        title_style={
            **GENERIC_TEMPLATE_TEXT_STYLE_PRESET.title_style,
            "font_size": 78,
            "font_weight": 800,
            "primary_color": "#5B4631",
            "stroke_color": "#F8EDDC",
            "stroke_width": 1,
            "background_color": "#FFF6E8",
            "background_opacity": 0.82,
            "position": "top",
            "margin_y": 92,
            "max_chars_per_line": 11,
        },
        title_region={"x": 0.10, "y": 0.05, "width": 0.80, "height": 0.15},
        caption_safe_area={"x": 0.12, "y": 0.74, "width": 0.76, "height": 0.15},
    ),
    "image_landscape_full": TemplateTextStylePreset(
        template_id="image_landscape_full",
        has_title_region=True,
        title_style={
            **GENERIC_TEMPLATE_TEXT_STYLE_PRESET.title_style,
            "font_size": 80,
            "font_weight": 700,
            "font_family": "Ma Shan Zheng",
            "primary_color": "#FFFFFF",
            "stroke_color": "#000000",
            "stroke_width": 2,
            "background_color": "#000000",
            "background_opacity": 0.24,
            "position": "top",
            "margin_y": 84,
            "max_chars_per_line": 16,
        },
        title_region={"x": 0.06, "y": 0.075, "width": 0.88, "height": 0.18},
        caption_safe_area={"x": 0.16, "y": 0.68, "width": 0.68, "height": 0.18},
    ),
    "image_landscape_minimal": TemplateTextStylePreset(
        template_id="image_landscape_minimal",
        has_title_region=True,
        title_style={
            **GENERIC_TEMPLATE_TEXT_STYLE_PRESET.title_style,
            "font_size": 76,
            "font_weight": 900,
            "primary_color": "#171410",
            "stroke_width": 0,
            "background_color": "#FFFFFF",
            "background_opacity": 0.88,
            "position": "top_left",
            "alignment": "left",
            "margin_x": 110,
            "margin_y": 92,
            "max_width_ratio": 0.44,
            "max_chars_per_line": 12,
        },
        title_region={"x": 0.055, "y": 0.085, "width": 0.44, "height": 0.20},
        caption_safe_area={"x": 0.18, "y": 0.69, "width": 0.64, "height": 0.17},
    ),
}


def normalize_template_id(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip().replace("\\", "/")
    if not cleaned:
        return None
    stem = Path(cleaned).stem if "/" in cleaned or "." in cleaned else cleaned
    return stem or None


def resolve_template_text_style_preset(template_id: str | None) -> TemplateTextStylePreset:
    normalized = normalize_template_id(template_id)
    if normalized and normalized in TEMPLATE_TEXT_STYLE_PRESETS:
        return TEMPLATE_TEXT_STYLE_PRESETS[normalized]
    return GENERIC_TEMPLATE_TEXT_STYLE_PRESET


def require_template_text_style_preset(template_id: str | None) -> TemplateTextStylePreset:
    normalized = normalize_template_id(template_id)
    if normalized and normalized in TEMPLATE_TEXT_STYLE_PRESETS:
        return TEMPLATE_TEXT_STYLE_PRESETS[normalized]
    raise ValueError(f"template {template_id!r} has no title preset")
```

- [ ] **Step 4: Extend default profile builder**

In `pixelle_video/models/text_style.py`, add constant and optional `template_id`:

```python
DEFAULT_TITLE_STYLE_ID = "title-default"
```

Update function signature:

```python
def build_default_text_style_profiles(
    *,
    config: Any | None = None,
    canvas_width: Any = None,
    canvas_height: Any = None,
    template_id: str | None = None,
) -> list[TextStyleProfile]:
```

Inside the function, import the preset lazily to avoid a module cycle:

```python
from pixelle_video.models.template_text_style_presets import (
    resolve_template_text_style_preset,
)
```

Build title payload before the return:

```python
title_payload = resolve_template_text_style_preset(template_id).title_style_dict()
title_payload.update(scale_basis_kwargs)
title_payload["id"] = DEFAULT_TITLE_STYLE_ID
```

Return caption, title, overlay:

```python
return [
    TextStyleProfile(
        id=DEFAULT_CAPTION_STYLE_ID,
        name="Caption Default",
        **scale_basis_kwargs,
    ),
    TextStyleProfile.from_dict(title_payload),
    TextStyleProfile(
        id=DEFAULT_OVERLAY_STYLE_ID,
        name="Overlay Default",
        font_size=DEFAULT_OVERLAY_FONT_SIZE,
        font_weight=700,
        primary_color=DEFAULT_OVERLAY_PRIMARY_COLOR,
        stroke_width=DEFAULT_OVERLAY_STROKE_WIDTH,
        position="center",
        margin_y=80,
        **scale_basis_kwargs,
    ),
]
```

- [ ] **Step 5: Add template render context fields**

In `pixelle_video/models/template_render_context.py`, add:

```python
from pixelle_video.models.template_text_style_presets import (
    resolve_template_text_style_preset,
)
```

Add fields to `TemplateRenderContext`:

```python
title_style_profile: TextStyleProfile | None = None
template_title_region: Dict[str, float] = field(default_factory=dict)
template_caption_safe_area: Dict[str, float] = field(default_factory=dict)
```

At the end of `__post_init__`:

```python
preset = resolve_template_text_style_preset(self.template_id)
if not self.template_title_region:
    self.template_title_region = preset.title_region_dict()
if not self.template_caption_safe_area:
    self.template_caption_safe_area = preset.caption_safe_area_dict()
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m pytest tests/test_template_text_style_presets.py tests/test_text_style_models.py tests/test_template_render_context.py -q
```

Expected: PASS after updating existing expectations from caption/overlay to caption/title/overlay.

- [ ] **Step 7: Commit**

```powershell
git add pixelle_video/models/template_text_style_presets.py pixelle_video/models/text_style.py pixelle_video/models/template_render_context.py tests/test_template_text_style_presets.py tests/test_text_style_models.py tests/test_template_render_context.py
git commit -m "feat: 建立模板标题样式预设源"
git push
```

## Task 3: Orchestrator Builds Title Style Contract

**Files:**
- Modify: `pixelle_video/services/text_rendering_orchestrator.py`
- Modify: `pixelle_video/services/text_rendering_contract_summary.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/pipelines/asset_based.py`
- Modify: `tests/test_text_rendering_orchestrator.py`
- Modify: `tests/test_pipeline_text_rendering_contract.py`
- Modify: `tests/test_standard_pipeline_text_rendering_summary.py`

- [ ] **Step 1: Write failing orchestrator tests**

Add to `tests/test_text_rendering_orchestrator.py`:

```python
from pixelle_video.models.text_style import DEFAULT_TITLE_STYLE_ID


def test_orchestrator_builds_title_style_from_template_preset_and_user_override():
    result = TextRenderingOrchestrator().build(
        text_rendering={
            "title_style": {
                "font_size": 92,
                "background_color": "#123456",
                "background_opacity": 0.5,
            }
        },
        template_id="image_landscape_minimal",
        canvas_width=1920,
        canvas_height=1080,
    )

    assert result.title_style.id == DEFAULT_TITLE_STYLE_ID
    assert result.title_style.position == "top_left"
    assert result.title_style.font_size == 92
    assert result.title_style.background_color == "#123456"
    assert result.title_style.background_opacity == 0.5
    assert result.title_style.scale_basis_width == 1920
    assert result.title_style.scale_basis_height == 1080
    assert [profile.id for profile in result.text_style_profiles] == [
        DEFAULT_CAPTION_STYLE_ID,
        DEFAULT_TITLE_STYLE_ID,
        DEFAULT_OVERLAY_STYLE_ID,
    ]


def test_orchestrator_uses_generic_title_default_for_templates_without_title_region():
    result = TextRenderingOrchestrator().build(
        text_rendering={},
        template_id="static_plain",
    )

    assert result.title_style.id == DEFAULT_TITLE_STYLE_ID
    assert result.title_style.name == "Title Default"
```

Update package test expectation:

```python
assert [profile.id for profile in package.text_style_profiles] == [
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_TITLE_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_text_rendering_orchestrator.py -q
```

Expected: FAIL because `TextRenderingOrchestrator.build()` has no `template_id` parameter and result has no `title_style`.

- [ ] **Step 3: Extend orchestrator result and build signature**

In `pixelle_video/services/text_rendering_orchestrator.py`, import `DEFAULT_TITLE_STYLE_ID`:

```python
from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
    DEFAULT_TITLE_STYLE_ID,
    TextStyleProfile,
    build_default_text_style_profiles,
)
```

Update dataclass:

```python
@dataclass(frozen=True)
class TextRenderingBuildResult:
    settings: TextRenderingSettings
    text_render_package: TextRenderPackage
    caption_settings: CaptionRenderingSettings
    overlay_policy: TextRenderingPolicy
    overlay_plan: TextOverlayPlan
    text_style_profiles: tuple[TextStyleProfile, ...]
    caption_style: TextStyleProfile
    title_style: TextStyleProfile
    overlay_style: TextStyleProfile
    image_text_policy: ImageTextPromptPolicy
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
```

Update `build()` signature:

```python
def build(
    self,
    *,
    text_rendering: Mapping[str, Any] | None,
    narrations: Sequence[str] = (),
    render_backend: str | None = None,
    frame_count: int | None = None,
    task_id: str | None = None,
    config: Any | None = None,
    canvas_width: int | None = None,
    canvas_height: int | None = None,
    template_id: str | None = None,
) -> TextRenderingBuildResult:
```

Build title style between caption and overlay:

```python
title_style = _profile_from_request(
    style_id=DEFAULT_TITLE_STYLE_ID,
    data=_mapping_or_none(request.get("title_style")),
    config=config,
    canvas_width=canvas_width,
    canvas_height=canvas_height,
    template_id=template_id,
)
```

Use all three profiles:

```python
text_style_profiles = (caption_style, title_style, overlay_style)
```

Return `title_style=title_style`.

- [ ] **Step 4: Make `_profile_from_request` template-aware**

Update helper signature:

```python
def _profile_from_request(
    *,
    style_id: str,
    data: Mapping[str, Any] | None,
    config: Any | None = None,
    canvas_width: int | None = None,
    canvas_height: int | None = None,
    template_id: str | None = None,
) -> TextStyleProfile:
```

Pass template ID:

```python
for profile in build_default_text_style_profiles(
    config=config,
    canvas_width=canvas_width,
    canvas_height=canvas_height,
    template_id=template_id,
)
```

- [ ] **Step 5: Pass template ID from pipelines**

In `pixelle_video/pipelines/standard.py`, update `_get_text_rendering_result`:

```python
template_id = None
if config is not None:
    try:
        template_id = self._resolve_hyperframes_template_id(config)
    except Exception:
        template_id = getattr(config, "frame_template", None)

result = TextRenderingOrchestrator().build(
    text_rendering=self._text_rendering_request_for_contract(ctx),
    narrations=frame_texts,
    render_backend=self._resolve_text_rendering_backend_label(ctx),
    frame_count=len(frame_texts),
    task_id=getattr(ctx, "task_id", None),
    config=config,
    template_id=template_id,
)
```

In `pixelle_video/services/text_rendering_contract_summary.py`, pass `template_id` from `target.config.frame_template` when available:

```python
config = getattr(target, "config", None)
result = TextRenderingOrchestrator().build(
    text_rendering=text_rendering,
    narrations=narrations,
    render_backend=render_backend,
    frame_count=frame_count if frame_count is not None else len(narrations),
    task_id=task_id,
    config=config,
    template_id=getattr(config, "frame_template", None),
)
```

- [ ] **Step 6: Add title style to summaries without changing PromptPlan ownership**

In `_build_text_layer_summary`, include title profile ID in a separate field:

```python
summary = {
    "enabled": text_layer_enabled,
    "renderer": "disabled",
    "track_count": 0,
    "cue_count": 0,
    "native_prompt_hint_count": 0,
    "style_profile_ids": [result.overlay_style.id],
    "title_style_profile_id": result.title_style.id,
    "artifacts": {},
    "fallbacks": [],
    "targets": (
        sorted(result.overlay_policy.enabled_targets) if overlay_enabled else []
    ),
}
```

Do not add title style defaults to `creation_package.prompt_plan`.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
python -m pytest tests/test_text_rendering_orchestrator.py tests/test_pipeline_text_rendering_contract.py tests/test_standard_pipeline_text_rendering_summary.py -q
```

Expected: PASS after updating profile ID lists to include `title-default`.

- [ ] **Step 8: Commit**

```powershell
git add pixelle_video/services/text_rendering_orchestrator.py pixelle_video/services/text_rendering_contract_summary.py pixelle_video/pipelines/standard.py pixelle_video/pipelines/asset_based.py tests/test_text_rendering_orchestrator.py tests/test_pipeline_text_rendering_contract.py tests/test_standard_pipeline_text_rendering_summary.py
git commit -m "feat: 构建标题样式渲染结果"
git push
```

## Task 4: HyperFrames Consumes Title Style Variables

**Files:**
- Modify: `pixelle_video/services/hyperframes_project_service.py`
- Modify: `pixelle_video/services/hyperframes_compiler.py`
- Modify: `resources/hyperframes/templates/image_default/index.template.html`
- Modify: `resources/hyperframes/templates/image_life_insights_light/index.template.html`
- Modify: `resources/hyperframes/templates/image_landscape_full/index.template.html`
- Modify: `resources/hyperframes/templates/image_landscape_minimal/index.template.html`
- Modify: `tests/test_hyperframes_compiler.py`
- Modify: `tests/test_template_render_context.py`

- [ ] **Step 1: Write failing compiler tests**

Add to `tests/test_hyperframes_compiler.py`:

```python
from pixelle_video.models.text_style import DEFAULT_TITLE_STYLE_ID


def test_hyperframes_compiler_emits_title_style_variables(tmp_path: Path):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "image_default"
    (template_dir / "compositions").mkdir(parents=True)
    (template_dir / "index.template.html").write_text(
        '<h1 class="video-title" style="__TITLE_STYLE_CSS__">__TITLE__</h1>',
        encoding="utf-8",
    )
    (template_dir / "compositions" / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )

    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="标题ABCDEFG",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        title_style_profile=TextStyleProfile(
            id=DEFAULT_TITLE_STYLE_ID,
            name="Title Default",
            font_size=96,
            primary_color="#112233",
            background_color="#FFFFFF",
            background_opacity=0.8,
            max_chars_per_line=4,
        ),
    )

    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=tmp_path / "project",
        context=context,
    )

    html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    assert "--title-fill: #112233" in html
    assert "--title-background: rgba(255, 255, 255, 0.8)" in html
    assert "--title-font-size: 96px" in html
    assert "标题AB<br/>CDEF<br/>G" in html
```

Add template lint expectation:

```python
def test_phase1_main_templates_consume_title_style_variables():
    template_ids = [
        "image_default",
        "image_life_insights_light",
        "image_landscape_full",
        "image_landscape_minimal",
    ]

    for template_id in template_ids:
        content = Path(
            f"resources/hyperframes/templates/{template_id}/index.template.html"
        ).read_text(encoding="utf-8")
        assert "__TITLE_STYLE_CSS__" in content
        assert "var(--title-fill)" in content
        assert "var(--title-font-size)" in content
        assert "var(--title-background)" in content
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_hyperframes_compiler.py::test_hyperframes_compiler_emits_title_style_variables tests/test_hyperframes_compiler.py::test_phase1_main_templates_consume_title_style_variables -q
```

Expected: FAIL because `__TITLE_STYLE_CSS__` is not replaced and templates still hardcode title CSS.

- [ ] **Step 3: Resolve title style in project service**

In `pixelle_video/services/hyperframes_project_service.py`, import:

```python
from pixelle_video.models.text_style import DEFAULT_CAPTION_STYLE_ID, DEFAULT_TITLE_STYLE_ID
```

Add helper:

```python
def _resolve_title_style_profile(manifest: RenderManifest):
    return next(
        (
            profile
            for profile in manifest.text_style_profiles
            if profile.id == DEFAULT_TITLE_STYLE_ID
        ),
        None,
    )
```

Pass into `TemplateRenderContext`:

```python
title_style_profile=_resolve_title_style_profile(manifest),
```

- [ ] **Step 4: Add title variable rendering to compiler**

In `pixelle_video/services/hyperframes_compiler.py`, add replacement:

```python
"__TITLE__": self._render_title_html(context),
"__TITLE_STYLE_CSS__": self._render_title_style_css(context),
```

Replace the existing `"__TITLE__": escape(context.title),` entry.

Add methods:

```python
def _render_title_style_css(self, context: TemplateRenderContext) -> str:
    profile = context.title_style_profile
    if profile is None:
        return ""
    return self._style_profile_css_variables(profile, context, prefix="title")


def _render_title_html(self, context: TemplateRenderContext) -> str:
    text = self._safe_display_text(context.title)
    profile = context.title_style_profile
    max_chars = profile.max_chars_per_line if profile is not None else None
    lines = self._wrap_display_text(text, max_chars)
    return "<br/>".join(escape(line) for line in lines)


@staticmethod
def _wrap_display_text(text: str, max_chars: int | None) -> list[str]:
    if max_chars is None or max_chars <= 0:
        return [text]
    compact = text.strip()
    if not compact:
        return [""]
    return [
        compact[index : index + max_chars]
        for index in range(0, len(compact), max_chars)
    ]
```

Update `_style_profile_css_variables` signature:

```python
def _style_profile_css_variables(
    self,
    profile: TextStyleProfile,
    context: TemplateRenderContext,
    *,
    prefix: str = "text",
) -> str:
```

Use prefix in variable names:

```python
return "; ".join(
    [
        f"--{prefix}-fill: {profile.primary_color}",
        f"--{prefix}-stroke-color: {profile.stroke_color}",
        f"--{prefix}-stroke-width: {stroke_width}px",
        f"--{prefix}-background: {background}",
        f"--{prefix}-font-family: {self._css_font_family_value(profile.font_family)}",
        f"--{prefix}-font-size: {font_size}px",
        f"--{prefix}-font-weight: {int(profile.font_weight)}",
        f"--{prefix}-line-height: {float(profile.line_height)}",
        f"--{prefix}-max-width: {max_width}px",
        f"--{prefix}-margin-x: {margin_x}px",
        f"--{prefix}-margin-y: {margin_y}px",
    ]
) + ";"
```

Existing calls continue using default `prefix="text"`.

- [ ] **Step 5: Update templates to consume variables**

For each `resources/hyperframes/templates/*/index.template.html`, put `style="__TITLE_STYLE_CSS__"` on the title element or wrapper and replace hardcoded title style values with CSS variables.

For `image_landscape_minimal`, the title CSS must become:

```css
.title {
  display: inline-block;
  max-width: var(--title-max-width);
  padding: 0.12em 0.2em;
  font-size: var(--title-font-size);
  line-height: var(--title-line-height);
  font-weight: var(--title-font-weight);
  color: var(--title-fill);
  font-family: var(--title-font-family);
  -webkit-text-stroke: var(--title-stroke-width) var(--title-stroke-color);
  background: var(--title-background);
  border-radius: 18px;
}
```

And the title element:

```html
<div class="header"><div class="title" style="__TITLE_STYLE_CSS__">__TITLE__</div></div>
```

Apply the same variable meanings to the other three templates, preserving their layout wrappers, ornaments, z-index, and animation timing.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m pytest tests/test_hyperframes_compiler.py tests/test_template_render_context.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add pixelle_video/services/hyperframes_project_service.py pixelle_video/services/hyperframes_compiler.py resources/hyperframes/templates/image_default/index.template.html resources/hyperframes/templates/image_life_insights_light/index.template.html resources/hyperframes/templates/image_landscape_full/index.template.html resources/hyperframes/templates/image_landscape_minimal/index.template.html tests/test_hyperframes_compiler.py tests/test_template_render_context.py
git commit -m "feat: 让 HyperFrames 标题消费样式变量"
git push
```

## Task 5: Frontend Payload Adds Caption/Title Tabs

**Files:**
- Modify: `web/components/text_rendering_config.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `tests/test_style_config_text_rendering_ui.py`

- [ ] **Step 1: Write failing frontend payload tests**

Add to `tests/test_style_config_text_rendering_ui.py`:

```python
def test_build_text_rendering_payload_keeps_title_style_and_drops_preview_demo_fields():
    from web.components.text_rendering_config import build_text_rendering_payload

    payload = build_text_rendering_payload(
        caption_style=None,
        title_style={
            "font_size": 96,
            "background_color": "#FFFFFF",
            "background_opacity": 0.85,
            "max_chars_per_line": 0,
            "preview_title_text": "只用于预览",
        },
        overlay_policy=None,
        suppress_embedded_text=False,
        positive_prompt="",
    )

    assert payload["title_style"] == {
        "font_size": 96,
        "background_color": "#FFFFFF",
        "background_opacity": 0.85,
    }
    assert "preview_title_text" not in str(payload)


def test_text_rendering_controls_render_caption_and_title_tabs(monkeypatch):
    from web.components import text_rendering_config
    from web.components.text_rendering_config import render_text_rendering_controls

    class _TabsUI(_WidgetDefaultRecordingUI):
        def __init__(self):
            super().__init__()
            self.tabs_labels = []

        def tabs(self, labels):
            self.tabs_labels.append(list(labels))
            return [_NoopContext(), _NoopContext()]

    fake_ui = _TabsUI()
    monkeypatch.setattr(text_rendering_config, "discover_font_options", lambda *_args: [])

    render_text_rendering_controls(
        "hyperframes_compiled",
        ui=fake_ui,
        translate=lambda key: key,
        template_id="image_landscape_minimal",
        canvas_width=1920,
        canvas_height=1080,
        media_width=768,
        media_height=768,
        media_placement={"scale_percent": 80, "anchor": "center"},
        title_text="当前标题",
        caption_text="当前字幕",
        preview_media_ref=None,
    )

    assert fake_ui.tabs_labels == [["caption_style.tab", "title_style.tab"]]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_style_config_text_rendering_ui.py::test_build_text_rendering_payload_keeps_title_style_and_drops_preview_demo_fields tests/test_style_config_text_rendering_ui.py::test_text_rendering_controls_render_caption_and_title_tabs -q
```

Expected: FAIL because payload has no `title_style` argument and controls have no tabs.

- [ ] **Step 3: Add title defaults and payload cleaning**

In `web/components/text_rendering_config.py`, import:

```python
from pixelle_video.models.template_text_style_presets import (
    resolve_template_text_style_preset,
)
```

Add:

```python
TITLE_STYLE_PREVIEW_ONLY_KEYS = {
    "preview_title_text",
    "preview_caption_text",
    "preview_media_ref",
}


def _title_style_defaults_for_template(template_id: str | None) -> dict[str, Any]:
    preset = resolve_template_text_style_preset(template_id)
    style = preset.title_style_dict()
    return {
        "font_family": style.get("font_family", CAPTION_STYLE_DEFAULTS["font_family"]),
        "font_size": style.get("font_size", 72),
        "primary_color": style.get("primary_color", "#FFFFFF"),
        "stroke_color": style.get("stroke_color", "#000000"),
        "stroke_width": style.get("stroke_width", 2),
        "background_color": style.get("background_color") or "#000000",
        "background_opacity": style.get("background_opacity", 0.0),
        "position": style.get("position", "top"),
        "margin_y": style.get("margin_y", 96),
        "max_chars_per_line": style.get("max_chars_per_line"),
    }
```

Update `_clean_text_style_payload`:

```python
for key, value in style.items():
    if key in TITLE_STYLE_PREVIEW_ONLY_KEYS:
        continue
```

Update `build_text_rendering_payload` signature and body:

```python
def build_text_rendering_payload(
    *,
    overlay_policy: dict | None,
    suppress_embedded_text: bool,
    positive_prompt: str,
    caption_style: dict | None = None,
    title_style: dict | None = None,
    overlay_style: dict | None = None,
) -> dict:
```

```python
title_style_payload = _clean_text_style_payload(title_style)
if title_style_payload is not None:
    payload["title_style"] = title_style_payload
```

- [ ] **Step 4: Render tabs**

Update `render_text_rendering_controls` signature:

```python
def render_text_rendering_controls(
    render_backend: str,
    *,
    ui: Any | None = None,
    translate=None,
    template_id: str | None = None,
    canvas_width: int | None = None,
    canvas_height: int | None = None,
    media_width: int | None = None,
    media_height: int | None = None,
    media_placement: Mapping[str, Any] | None = None,
    title_text: str | None = None,
    caption_text: str | None = None,
    preview_media_ref: str | None = None,
) -> dict:
```

Replace the caption-only detail section with:

```python
with _render_middle_column_detail_section(ui, translate("text_style.tabs_title")):
    caption_tab, title_tab = ui.tabs(
        [translate("caption_style.tab"), translate("title_style.tab")]
    )
    with caption_tab:
        caption_style = _render_text_style_controls(
            "caption_style",
            CAPTION_STYLE_DEFAULTS,
            ui=ui,
            translate=translate,
        )
    with title_tab:
        title_style = _render_text_style_controls(
            "title_style",
            _title_style_defaults_for_template(template_id),
            ui=ui,
            translate=translate,
        )
```

Pass `title_style=title_style` to `build_text_rendering_payload`.

- [ ] **Step 5: Add i18n keys**

In `web/i18n/locales/zh_CN.json` under `"t"`:

```json
"text_style.tabs_title": "文字样式",
"caption_style.tab": "字幕样式",
"title_style.tab": "标题样式",
"title_style.font_family": "标题字体",
"title_style.font_family_help": "标题样式复用文字渲染字体契约。将字体文件放到项目根目录 fonts/，也兼容 font/ 和 resource/fonts/。",
"title_style.font_size": "标题字号",
"title_style.primary_color": "标题文字颜色",
"title_style.stroke_color": "标题描边颜色",
"title_style.stroke_width": "标题描边宽度",
"title_style.background_color": "标题背景颜色",
"title_style.background_opacity": "标题背景不透明度",
"title_style.position": "标题位置",
"title_style.margin_y": "标题垂直边距",
"title_style.max_chars_per_line": "标题每行最多字符数（0 = 自动）"
```

Add matching English keys in `web/i18n/locales/en_US.json`.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m pytest tests/test_style_config_text_rendering_ui.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add web/components/text_rendering_config.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_style_config_text_rendering_ui.py
git commit -m "feat: 增加标题样式配置入口"
git push
```

## Task 6: Immediate Text Rendering Preview Area

**Files:**
- Create: `web/components/text_rendering_preview.py`
- Modify: `web/components/text_rendering_config.py`
- Modify: `web/components/style_config.py`
- Modify: `web/pipelines/standard.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Create: `tests/test_text_rendering_preview.py`
- Modify: `tests/test_style_config_text_rendering_ui.py`

- [ ] **Step 1: Write failing preview spec tests**

Create `tests/test_text_rendering_preview.py`:

```python
from web.components.text_rendering_preview import (
    TextRenderingPreviewSpec,
    build_text_rendering_preview_spec,
    preview_spec_fingerprint,
    render_preview_html,
)


def test_build_text_rendering_preview_spec_derives_from_contracts_only():
    spec = build_text_rendering_preview_spec(
        template_id="image_landscape_minimal",
        render_backend="hyperframes_compiled",
        canvas_width=1920,
        canvas_height=1080,
        media_width=768,
        media_height=768,
        media_placement={"scale_percent": 80, "anchor": "center"},
        preview_media_ref=None,
        title_text="正式标题",
        caption_text="首句字幕",
        title_style={"font_size": 88, "background_opacity": 0.7},
        caption_style={"font_size": 42, "primary_color": "#2C3E50"},
    )

    assert isinstance(spec, TextRenderingPreviewSpec)
    assert spec.template_id == "image_landscape_minimal"
    assert spec.title_text == "正式标题"
    assert spec.caption_text == "首句字幕"
    assert spec.placeholder_media is True
    assert spec.template_title_region["width"] > 0
    assert spec.template_caption_safe_area["height"] > 0
    assert spec.fingerprint == preview_spec_fingerprint(spec)


def test_render_preview_html_contains_image_title_and_caption_layers():
    spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes_compiled",
        canvas_width=1080,
        canvas_height=1920,
        media_width=768,
        media_height=768,
        media_placement={"scale_percent": 100, "anchor": "center"},
        preview_media_ref=None,
        title_text="预览标题",
        caption_text="预览字幕",
        title_style={"font_size": 80, "background_color": "#FFFFFF"},
        caption_style={"font_size": 42, "background_color": "#000000"},
    )

    html = render_preview_html(spec)

    assert "text-rendering-preview__media" in html
    assert "text-rendering-preview__title" in html
    assert "text-rendering-preview__caption" in html
    assert "预览标题" in html
    assert "预览字幕" in html
    assert "text_rendering" not in html
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_text_rendering_preview.py -q
```

Expected: FAIL because preview component does not exist.

- [ ] **Step 3: Create preview component**

Create `web/components/text_rendering_preview.py`:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from html import escape
from typing import Any, Mapping

from pixelle_video.models.media_placement import calculate_media_box, resolve_media_placement
from pixelle_video.models.template_text_style_presets import resolve_template_text_style_preset


@dataclass(frozen=True)
class TextRenderingPreviewSpec:
    template_id: str
    render_backend: str | None
    canvas_width: int
    canvas_height: int
    media_width: int
    media_height: int
    media_placement: dict[str, Any]
    preview_media_ref: str | None
    placeholder_media: bool
    title_text: str
    caption_text: str
    title_style: dict[str, Any]
    caption_style: dict[str, Any]
    template_title_region: dict[str, float]
    template_caption_safe_area: dict[str, float]
    fingerprint: str


def build_text_rendering_preview_spec(
    *,
    template_id: str,
    render_backend: str | None,
    canvas_width: int,
    canvas_height: int,
    media_width: int,
    media_height: int,
    media_placement: Mapping[str, Any] | None,
    preview_media_ref: str | None,
    title_text: str | None,
    caption_text: str | None,
    title_style: Mapping[str, Any] | None,
    caption_style: Mapping[str, Any] | None,
) -> TextRenderingPreviewSpec:
    preset = resolve_template_text_style_preset(template_id)
    normalized_media_placement = resolve_media_placement(media_placement).to_dict()
    spec_without_fingerprint = {
        "template_id": str(template_id),
        "render_backend": render_backend,
        "canvas_width": int(canvas_width),
        "canvas_height": int(canvas_height),
        "media_width": int(media_width),
        "media_height": int(media_height),
        "media_placement": normalized_media_placement,
        "preview_media_ref": str(preview_media_ref).strip() if preview_media_ref else None,
        "placeholder_media": not bool(preview_media_ref),
        "title_text": str(title_text or "标题预览"),
        "caption_text": str(caption_text or "字幕预览用于检查排版安全区"),
        "title_style": dict(title_style or {}),
        "caption_style": dict(caption_style or {}),
        "template_title_region": preset.title_region_dict(),
        "template_caption_safe_area": preset.caption_safe_area_dict(),
    }
    fingerprint = _fingerprint_payload(spec_without_fingerprint)
    return TextRenderingPreviewSpec(
        **spec_without_fingerprint,
        fingerprint=fingerprint,
    )


def preview_spec_fingerprint(spec: TextRenderingPreviewSpec) -> str:
    payload = asdict(spec)
    payload.pop("fingerprint", None)
    return _fingerprint_payload(payload)


def _fingerprint_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def render_preview_html(spec: TextRenderingPreviewSpec) -> str:
    media_box = calculate_media_box(
        canvas_width=spec.canvas_width,
        canvas_height=spec.canvas_height,
        media_source_width=spec.media_width,
        media_source_height=spec.media_height,
        placement=resolve_media_placement(spec.media_placement),
    )
    title_region = _region_css(spec.template_title_region, spec.canvas_width, spec.canvas_height)
    caption_region = _region_css(spec.template_caption_safe_area, spec.canvas_width, spec.canvas_height)
    title_style = _text_style_css(spec.title_style, role="title")
    caption_style = _text_style_css(spec.caption_style, role="caption")
    media = _media_html(spec)
    return f"""
<div class="text-rendering-preview" data-fingerprint="{escape(spec.fingerprint)}">
  <style>
    .text-rendering-preview {{
      position: relative;
      width: 100%;
      aspect-ratio: {spec.canvas_width} / {spec.canvas_height};
      overflow: hidden;
      border-radius: 18px;
      background: #f4efe6;
      box-shadow: inset 0 0 0 1px rgba(40, 35, 28, 0.12);
    }}
    .text-rendering-preview__media {{
      position: absolute;
      left: {round(media_box.left / spec.canvas_width * 100, 4)}%;
      top: {round(media_box.top / spec.canvas_height * 100, 4)}%;
      width: {round(media_box.width / spec.canvas_width * 100, 4)}%;
      height: {round(media_box.height / spec.canvas_height * 100, 4)}%;
      display: grid;
      place-items: center;
      overflow: hidden;
      border-radius: 14px;
      background: linear-gradient(135deg, #d6e2d7, #f1d6b8);
    }}
    .text-rendering-preview__media img {{ width: 100%; height: 100%; object-fit: contain; }}
    .text-rendering-preview__title {{ position: absolute; {title_region} {title_style} }}
    .text-rendering-preview__caption {{ position: absolute; {caption_region} {caption_style} }}
  </style>
  <div class="text-rendering-preview__media">{media}</div>
  <div class="text-rendering-preview__title">{escape(spec.title_text)}</div>
  <div class="text-rendering-preview__caption">{escape(spec.caption_text)}</div>
</div>
"""


def render_text_rendering_preview(spec: TextRenderingPreviewSpec, *, ui, translate) -> None:
    ui.markdown(render_preview_html(spec), unsafe_allow_html=True)
    ui.caption(translate("text_rendering_preview.instant_notice"))


def _media_html(spec: TextRenderingPreviewSpec) -> str:
    if spec.preview_media_ref:
        return f'<img src="{escape(spec.preview_media_ref, quote=True)}" alt="" />'
    return '<span style="color:#665c50;font-weight:700;">Placeholder Preview</span>'


def _region_css(region: Mapping[str, float], canvas_width: int, canvas_height: int) -> str:
    return (
        f"left:{float(region['x']) * 100:.4f}%;"
        f"top:{float(region['y']) * 100:.4f}%;"
        f"width:{float(region['width']) * 100:.4f}%;"
        f"height:{float(region['height']) * 100:.4f}%;"
    )


def _text_style_css(style: Mapping[str, Any], *, role: str) -> str:
    font_size = int(style.get("font_size") or (72 if role == "title" else 42))
    color = str(style.get("primary_color") or "#FFFFFF")
    background_color = str(style.get("background_color") or "#000000")
    opacity = float(style.get("background_opacity") or 0.0)
    stroke_color = str(style.get("stroke_color") or "#000000")
    stroke_width = int(style.get("stroke_width") or 0)
    return (
        "display:flex;align-items:center;justify-content:center;"
        "box-sizing:border-box;text-align:center;padding:0.2em 0.35em;"
        f"font-size:clamp(12px,{font_size / 19.2:.3f}vw,{font_size}px);"
        f"color:{color};background:{_rgba(background_color, opacity)};"
        f"-webkit-text-stroke:{stroke_width}px {stroke_color};"
        "font-weight:800;line-height:1.16;"
    )


def _rgba(hex_color: str, opacity: float) -> str:
    color = hex_color if hex_color.startswith("#") and len(hex_color) == 7 else "#000000"
    return (
        f"rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, "
        f"{int(color[5:7], 16)}, {max(0.0, min(opacity, 1.0)):g})"
    )
```

- [ ] **Step 4: Render preview inside text rendering controls**

In `web/components/text_rendering_config.py`, import:

```python
from web.components.text_rendering_preview import (
    build_text_rendering_preview_spec,
    render_text_rendering_preview,
)
```

After title and caption styles are rendered, build and render spec when dimensions are present:

```python
if all(value is not None for value in (template_id, canvas_width, canvas_height, media_width, media_height)):
    preview_spec = build_text_rendering_preview_spec(
        template_id=str(template_id),
        render_backend=render_backend,
        canvas_width=int(canvas_width),
        canvas_height=int(canvas_height),
        media_width=int(media_width),
        media_height=int(media_height),
        media_placement=media_placement,
        preview_media_ref=preview_media_ref,
        title_text=title_text,
        caption_text=caption_text,
        title_style=title_style,
        caption_style=caption_style,
    )
    with _render_middle_column_detail_section(ui, translate("text_rendering_preview.title")):
        render_text_rendering_preview(preview_spec, ui=ui, translate=translate)
```

- [ ] **Step 5: Reorder style config and pass preview context**

In `web/components/style_config.py`, remove the early call:

```python
text_rendering = render_text_rendering_controls(
    render_backend,
    ui=st,
    translate=tr,
)
```

After `frame_template`, `size_contract`, `media_width`, `media_height`, and `template_media_type` are resolved, call:

```python
text_rendering = render_text_rendering_controls(
    render_backend,
    ui=st,
    translate=tr,
    template_id=Path(frame_template).stem,
    canvas_width=size_contract.canvas_width,
    canvas_height=size_contract.canvas_height,
    media_width=media_width,
    media_height=media_height,
    media_placement=st.session_state.get("media_placement"),
    title_text=(content_context or {}).get("title"),
    caption_text=_preview_caption_text((content_context or {}).get("text")),
    preview_media_ref=st.session_state.get("text_rendering_preview_media_ref"),
)
```

Update `render_style_config` signature:

```python
def render_style_config(
    pixelle_video,
    storyboard_default_enabled: bool = False,
    storyboard_prompt_language: str = CHINESE_PROMPT_LANGUAGE,
    content_context: dict | None = None,
):
```

Add helper:

```python
def _preview_caption_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return tr("text_rendering_preview.default_caption")
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), text)
    return first_line[:80]
```

In `web/pipelines/standard.py`, pass content:

```python
style_params = render_style_config(
    pixelle_video,
    storyboard_default_enabled=False,
    storyboard_prompt_language=content_params.get(
        "storyboard_prompt_language",
        CHINESE_PROMPT_LANGUAGE,
    ),
    content_context=content_params,
)
```

- [ ] **Step 6: Add i18n keys**

In `web/i18n/locales/zh_CN.json`:

```json
"text_rendering_preview.title": "实施预览区（实时排版预览）",
"text_rendering_preview.instant_notice": "即时预览用于排版反馈；真实预览帧请使用显式生成按钮校准最终渲染。",
"text_rendering_preview.default_caption": "字幕预览用于检查排版安全区"
```

Add equivalent English keys.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
python -m pytest tests/test_text_rendering_preview.py tests/test_style_config_text_rendering_ui.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add web/components/text_rendering_preview.py web/components/text_rendering_config.py web/components/style_config.py web/pipelines/standard.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_text_rendering_preview.py tests/test_style_config_text_rendering_ui.py
git commit -m "feat: 增加文字渲染实施预览区"
git push
```

## Task 7: Real Preview Frame Contract Uses Artifact Keys

**Files:**
- Create: `pixelle_video/storage/artifact_object_store.py`
- Modify: `pixelle_video/storage/__init__.py`
- Create: `pixelle_video/services/text_rendering_preview.py`
- Create: `api/schemas/text_rendering_preview.py`
- Create: `api/routers/text_rendering_preview.py`
- Modify: `api/routers/__init__.py`
- Modify: API application router registration file that includes routers from `api/routers/__init__.py`
- Create: `tests/test_text_rendering_preview_service.py`
- Create: `tests/test_text_rendering_preview_api.py`
- Modify: `tests/test_platform_repository_contracts.py`

- [ ] **Step 1: Write failing service contract tests**

Create `tests/test_text_rendering_preview_service.py`:

```python
from pathlib import Path

import pytest

from pixelle_video.repositories.artifacts import StoredArtifactFile
from pixelle_video.services.text_rendering_preview import (
    TextRenderingPreviewFrameRequest,
    TextRenderingPreviewFrameService,
)


class _FakeObjectStore:
    def __init__(self):
        self.uploads = []

    async def put_file(self, workspace_id, source_path, metadata=None):
        self.uploads.append((workspace_id, Path(source_path), dict(metadata or {})))
        return StoredArtifactFile(
            storage_key=f"artifacts/{workspace_id}/preview.png",
            url=f"/api/files/{workspace_id}/preview.png",
        )

    async def get_file_url(self, storage_key, options=None):
        return f"/api/files/{storage_key}"

    async def exists(self, storage_key):
        return storage_key == "artifacts/ws/preview.png"


class _FakeRenderer:
    def render_preview_frame(self, request, output_path):
        output_path.write_bytes(b"png")
        return output_path


@pytest.mark.asyncio
async def test_preview_frame_service_returns_storage_key_not_local_path(tmp_path):
    object_store = _FakeObjectStore()
    service = TextRenderingPreviewFrameService(
        object_store=object_store,
        renderer=_FakeRenderer(),
        staging_root=tmp_path,
    )

    result = await service.render_preview_frame(
        TextRenderingPreviewFrameRequest(
            workspace_id="ws",
            template_id="image_default",
            render_backend="hyperframes_compiled",
            canvas_width=1080,
            canvas_height=1920,
            media_width=768,
            media_height=768,
            media_placement={"scale_percent": 100, "anchor": "center"},
            preview_media_storage_key="artifacts/ws/source.png",
            title_text="标题",
            caption_text="字幕",
            text_rendering={"title_style": {"font_size": 88}},
        )
    )

    assert result.storage_key == "artifacts/ws/preview.png"
    assert result.url == "/api/files/ws/preview.png"
    assert result.local_path is None
    assert object_store.uploads[0][2]["kind"] == "text_rendering_preview_frame"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_text_rendering_preview_service.py -q
```

Expected: FAIL because service does not exist.

- [ ] **Step 3: Add artifact object dev adapter if missing**

Create `pixelle_video/storage/artifact_object_store.py`:

```python
from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath
from uuid import uuid4

from pixelle_video.repositories.artifacts import StoredArtifactFile
from pixelle_video.storage.object_store import WORKSPACE_ID_PATTERN


class FilesystemDevArtifactObjectStore:
    def __init__(self, root: str | Path = "output", base_url: str = "/api/files") -> None:
        self.root = Path(root).expanduser().resolve()
        self.base_url = base_url.rstrip("/")

    async def put_file(self, workspace_id: str, source_path, metadata=None) -> StoredArtifactFile:
        if not WORKSPACE_ID_PATTERN.fullmatch(str(workspace_id)):
            raise ValueError("workspace_id must not contain path syntax")
        source = Path(source_path).resolve()
        suffix = source.suffix.lower() or ".bin"
        storage_key = f"artifacts/{workspace_id}/{uuid4().hex}{suffix}"
        target = self._path_for_storage_key(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return StoredArtifactFile(
            storage_key=storage_key,
            url=f"{self.base_url}/{storage_key}",
        )

    async def get_file_url(self, storage_key: str, options=None) -> str:
        self._path_for_storage_key(storage_key)
        return f"{self.base_url}/{storage_key}"

    async def exists(self, storage_key: str) -> bool:
        try:
            return self._path_for_storage_key(storage_key).is_file()
        except ValueError:
            return False

    def _path_for_storage_key(self, storage_key: str) -> Path:
        key = PurePosixPath(storage_key)
        parts = key.parts
        if (
            not storage_key
            or key.as_posix() != storage_key
            or storage_key.startswith("/")
            or "\\" in storage_key
            or ":" in storage_key
            or any(part in {"", ".", ".."} for part in parts)
            or len(parts) != 3
            or parts[0] != "artifacts"
            or not WORKSPACE_ID_PATTERN.fullmatch(parts[1])
        ):
            raise ValueError("invalid artifact storage key")
        target = self.root.joinpath(*parts).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("artifact storage key escapes root")
        return target
```

Export in `pixelle_video/storage/__init__.py`:

```python
from pixelle_video.storage.artifact_object_store import FilesystemDevArtifactObjectStore
```

- [ ] **Step 4: Create preview service**

Create `pixelle_video/services/text_rendering_preview.py`:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from pixelle_video.repositories.artifacts import ArtifactObjectStore
from pixelle_video.services.text_rendering_orchestrator import TextRenderingOrchestrator


@dataclass(frozen=True)
class TextRenderingPreviewFrameRequest:
    workspace_id: str
    template_id: str
    render_backend: str | None
    canvas_width: int
    canvas_height: int
    media_width: int
    media_height: int
    media_placement: Mapping[str, Any]
    preview_media_storage_key: str | None
    title_text: str
    caption_text: str
    text_rendering: Mapping[str, Any]
    preview_media_url: str | None = None


@dataclass(frozen=True)
class TextRenderingPreviewFrameResult:
    storage_key: str
    url: str | None
    fingerprint: str
    local_path: None = None


class HyperFramesCompiledPreviewFrameRenderer:
    async def render_preview_frame(
        self,
        request: TextRenderingPreviewFrameRequest,
        output_path: Path,
    ) -> Path:
        from playwright.async_api import async_playwright

        from pixelle_video.models.render_package import CaptionCue, VisualClip
        from pixelle_video.models.template_render_context import TemplateRenderContext
        from pixelle_video.models.text_style import DEFAULT_CAPTION_STYLE_ID
        from pixelle_video.services.hyperframes_compiler import HyperFramesCompiler

        build_result = TextRenderingOrchestrator().build(
            text_rendering=request.text_rendering,
            render_backend=request.render_backend,
            frame_count=1,
            task_id=f"preview-{preview_frame_fingerprint(request)}",
            canvas_width=request.canvas_width,
            canvas_height=request.canvas_height,
            template_id=request.template_id,
        )
        media_ref = request.preview_media_url or _placeholder_svg_data_uri()
        context = TemplateRenderContext(
            template_id=request.template_id,
            canvas_width=request.canvas_width,
            canvas_height=request.canvas_height,
            media_width=request.media_width,
            media_height=request.media_height,
            media_placement=dict(request.media_placement),
            duration=1.0,
            fps=30,
            title=request.title_text,
            author=None,
            footer=None,
            theme=None,
            style_profile=request.template_id,
            visuals=[
                VisualClip(
                    id="preview-media",
                    frame_index=0,
                    start=0.0,
                    end=1.0,
                    media_path=media_ref,
                    media_type="image",
                )
            ],
            captions=[
                CaptionCue(
                    id="preview-caption",
                    text=request.caption_text,
                    start=0.0,
                    end=1.0,
                    frame_indices=[0],
                    style_profile=DEFAULT_CAPTION_STYLE_ID,
                )
            ],
            text_style_profiles=list(build_result.text_style_profiles),
            title_style_profile=build_result.title_style,
        )
        project_dir = output_path.parent / "hyperframes"
        HyperFramesCompiler().compile(project_dir=project_dir, context=context)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": request.canvas_width, "height": request.canvas_height},
                device_scale_factor=1,
            )
            try:
                await page.goto((project_dir / "index.html").resolve().as_uri())
                await page.screenshot(path=str(output_path), type="png", full_page=False)
            finally:
                await browser.close()
        return output_path


class TextRenderingPreviewFrameService:
    def __init__(
        self,
        *,
        object_store: ArtifactObjectStore,
        renderer: TextRenderingPreviewFrameRenderer,
        staging_root: str | Path,
    ) -> None:
        self.object_store = object_store
        self.renderer = renderer
        self.staging_root = Path(staging_root)

    async def render_preview_frame(
        self,
        request: TextRenderingPreviewFrameRequest,
    ) -> TextRenderingPreviewFrameResult:
        fingerprint = preview_frame_fingerprint(request)
        staging_dir = self.staging_root / "text-rendering-preview" / fingerprint
        staging_dir.mkdir(parents=True, exist_ok=True)
        output_path = staging_dir / "preview.png"

        TextRenderingOrchestrator().build(
            text_rendering=request.text_rendering,
            render_backend=request.render_backend,
            frame_count=1,
            task_id=f"preview-{fingerprint}",
            canvas_width=request.canvas_width,
            canvas_height=request.canvas_height,
            template_id=request.template_id,
        )
        render_request = request
        if request.preview_media_storage_key:
            media_url = await self.object_store.get_file_url(
                request.preview_media_storage_key
            )
            render_request = replace(request, preview_media_url=media_url)
        rendered_path = await self.renderer.render_preview_frame(render_request, output_path)
        stored = await self.object_store.put_file(
            request.workspace_id,
            rendered_path,
            metadata={
                "kind": "text_rendering_preview_frame",
                "fingerprint": fingerprint,
                "template_id": request.template_id,
            },
        )
        return TextRenderingPreviewFrameResult(
            storage_key=stored.storage_key,
            url=stored.url,
            fingerprint=fingerprint,
        )


def preview_frame_fingerprint(request: TextRenderingPreviewFrameRequest) -> str:
    payload = {
        "template_id": request.template_id,
        "render_backend": request.render_backend,
        "canvas_width": request.canvas_width,
        "canvas_height": request.canvas_height,
        "media_width": request.media_width,
        "media_height": request.media_height,
        "media_placement": dict(request.media_placement),
        "preview_media_storage_key": request.preview_media_storage_key,
        "title_text": request.title_text,
        "caption_text": request.caption_text,
        "text_rendering": dict(request.text_rendering),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _placeholder_svg_data_uri() -> str:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop stop-color="#d6e2d7"/><stop offset="1" stop-color="#f1d6b8"/>'
        '</linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/>'
        '<text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" '
        'font-size="42" font-family="sans-serif" fill="#665c50">Preview Media</text>'
        '</svg>'
    )
    return "data:image/svg+xml;charset=utf-8," + quote(svg)
```

The renderer compiles the same HyperFrames template path used by final generation and captures a representative frame from `index.html`. It never reads `template_params["title_style"]`.

- [ ] **Step 5: Add API schema and router**

Create `api/schemas/text_rendering_preview.py`:

```python
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.text_rendering import TextRenderingRequest


class TextRenderingPreviewFrameRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    template_id: str = Field(min_length=1, max_length=128)
    render_backend: Optional[str] = None
    canvas_width: int = Field(gt=0)
    canvas_height: int = Field(gt=0)
    media_width: int = Field(gt=0)
    media_height: int = Field(gt=0)
    media_placement: dict[str, Any] = Field(default_factory=dict)
    preview_media_storage_key: Optional[str] = None
    title_text: str = ""
    caption_text: str = ""
    text_rendering: TextRenderingRequest = Field(default_factory=TextRenderingRequest)


class TextRenderingPreviewFrameResponseSchema(BaseModel):
    storage_key: str
    url: Optional[str] = None
    fingerprint: str
```

Create `api/routers/text_rendering_preview.py`:

```python
from pathlib import Path

from fastapi import APIRouter

from api.config import get_api_config
from api.schemas.text_rendering_preview import (
    TextRenderingPreviewFrameRequestSchema,
    TextRenderingPreviewFrameResponseSchema,
)
from pixelle_video.services.text_rendering_preview import (
    HyperFramesCompiledPreviewFrameRenderer,
    TextRenderingPreviewFrameRequest,
    TextRenderingPreviewFrameService,
)
from pixelle_video.storage.artifact_object_store import FilesystemDevArtifactObjectStore

router = APIRouter(prefix="/text-rendering", tags=["Text Rendering"])


@router.post("/preview-frame", response_model=TextRenderingPreviewFrameResponseSchema)
async def render_text_rendering_preview_frame(request: TextRenderingPreviewFrameRequestSchema):
    config = get_api_config()
    service = TextRenderingPreviewFrameService(
        object_store=FilesystemDevArtifactObjectStore(
            root=config.artifact_base_path,
            base_url=config.artifact_base_url,
        ),
        renderer=HyperFramesCompiledPreviewFrameRenderer(),
        staging_root=Path(config.artifact_base_path) / "preview-staging",
    )
    result = await service.render_preview_frame(
        TextRenderingPreviewFrameRequest(
            workspace_id=request.workspace_id,
            template_id=request.template_id,
            render_backend=request.render_backend,
            canvas_width=request.canvas_width,
            canvas_height=request.canvas_height,
            media_width=request.media_width,
            media_height=request.media_height,
            media_placement=request.media_placement,
            preview_media_storage_key=request.preview_media_storage_key,
            title_text=request.title_text,
            caption_text=request.caption_text,
            text_rendering=request.text_rendering.model_dump(exclude_none=True),
        )
    )
    return TextRenderingPreviewFrameResponseSchema(
        storage_key=result.storage_key,
        url=result.url,
        fingerprint=result.fingerprint,
    )
```

Wire the router to the same application registration pattern used by existing routers. The route returns only `storage_key`, optional `url`, and `fingerprint`.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m pytest tests/test_text_rendering_preview_service.py tests/test_text_rendering_preview_api.py tests/test_platform_repository_contracts.py -q
```

Expected: PASS after tests account for the configured route behavior.

- [ ] **Step 7: Commit**

```powershell
git add pixelle_video/storage/artifact_object_store.py pixelle_video/storage/__init__.py pixelle_video/services/text_rendering_preview.py api/schemas/text_rendering_preview.py api/routers/text_rendering_preview.py api/routers/__init__.py tests/test_text_rendering_preview_service.py tests/test_text_rendering_preview_api.py tests/test_platform_repository_contracts.py
git commit -m "feat: 建立真实文字预览帧存储契约"
git push
```

## Task 8: UI Real Preview Action and Cache State

**Files:**
- Modify: `web/components/text_rendering_preview.py`
- Modify: `web/components/text_rendering_config.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `tests/test_text_rendering_preview.py`
- Modify: `tests/test_style_config_text_rendering_ui.py`

- [ ] **Step 1: Write failing UI cache tests**

Add to `tests/test_text_rendering_preview.py`:

```python
def test_preview_cache_marks_real_frame_stale_when_fingerprint_changes():
    from web.components.text_rendering_preview import (
        build_real_preview_state,
        is_real_preview_stale,
    )

    state = build_real_preview_state(
        storage_key="artifacts/ws/preview.png",
        url="/api/files/artifacts/ws/preview.png",
        fingerprint="old",
        error=None,
    )

    assert is_real_preview_stale(state, "old") is False
    assert is_real_preview_stale(state, "new") is True
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_text_rendering_preview.py::test_preview_cache_marks_real_frame_stale_when_fingerprint_changes -q
```

Expected: FAIL because cache helpers do not exist.

- [ ] **Step 3: Add real preview state helpers**

In `web/components/text_rendering_preview.py`, add:

```python
def build_real_preview_state(
    *,
    storage_key: str | None,
    url: str | None,
    fingerprint: str | None,
    error: str | None,
) -> dict[str, Any]:
    return {
        "storage_key": storage_key,
        "url": url,
        "fingerprint": fingerprint,
        "error": error,
    }


def is_real_preview_stale(state: Mapping[str, Any] | None, fingerprint: str) -> bool:
    if not state:
        return True
    return state.get("fingerprint") != fingerprint
```

Add rendering helper:

```python
def render_real_preview_status(
    *,
    spec: TextRenderingPreviewSpec,
    state: Mapping[str, Any] | None,
    ui,
    translate,
) -> None:
    if state and state.get("url") and not is_real_preview_stale(state, spec.fingerprint):
        ui.image(state["url"], caption=translate("text_rendering_preview.real_current"))
        return
    if state and state.get("url"):
        ui.caption(translate("text_rendering_preview.real_stale"))
    if state and state.get("error"):
        ui.error(translate("text_rendering_preview.real_failed", error=state["error"]))


def request_real_preview_frame(
    *,
    spec: TextRenderingPreviewSpec,
    text_rendering_payload: Mapping[str, Any],
    api_base_url: str,
    workspace_id: str,
) -> dict[str, Any]:
    import httpx

    endpoint = f"{api_base_url.rstrip('/')}/text-rendering/preview-frame"
    payload = {
        "workspace_id": workspace_id,
        "template_id": spec.template_id,
        "render_backend": spec.render_backend,
        "canvas_width": spec.canvas_width,
        "canvas_height": spec.canvas_height,
        "media_width": spec.media_width,
        "media_height": spec.media_height,
        "media_placement": spec.media_placement,
        "preview_media_storage_key": (
            spec.preview_media_ref
            if str(spec.preview_media_ref or "").startswith("artifacts/")
            else None
        ),
        "title_text": spec.title_text,
        "caption_text": spec.caption_text,
        "text_rendering": text_rendering_payload,
    }
    try:
        response = httpx.post(endpoint, json=payload, timeout=60.0)
        response.raise_for_status()
        data = response.json()
        return build_real_preview_state(
            storage_key=data.get("storage_key"),
            url=data.get("url"),
            fingerprint=data.get("fingerprint"),
            error=None,
        )
    except Exception as exc:
        return build_real_preview_state(
            storage_key=None,
            url=None,
            fingerprint=spec.fingerprint,
            error=str(exc),
        )
```

- [ ] **Step 4: Add explicit button in controls**

In `web/components/text_rendering_config.py`, after instantaneous preview:

```python
preview_state_key = "text_rendering_real_preview_frame"
render_real_preview_status(
    spec=preview_spec,
    state=_session_value(ui, preview_state_key, None),
    ui=ui,
    translate=translate,
)
if _call_control(
    ui,
    "button",
    False,
    translate("text_rendering_preview.generate_real"),
    key="text_rendering_generate_real_preview",
    width="stretch",
):
    result = request_real_preview_frame(
        spec=preview_spec,
        text_rendering_payload=build_text_rendering_payload(
            caption_style=caption_style,
            title_style=title_style,
            overlay_policy=overlay_policy,
            overlay_style=overlay_style,
            suppress_embedded_text=suppress_embedded_text,
            positive_prompt=positive_prompt,
        ),
        api_base_url=_session_value(ui, "api_base_url", "http://localhost:8000/api"),
        workspace_id=_session_value(ui, "workspace_id", "default"),
    )
    _set_session_value(ui, preview_state_key, result)
```

This UI state is not part of `build_text_rendering_payload`.

- [ ] **Step 5: Add i18n keys**

In `web/i18n/locales/zh_CN.json`:

```json
"text_rendering_preview.generate_real": "生成真实预览帧",
"text_rendering_preview.real_current": "真实预览帧",
"text_rendering_preview.real_stale": "真实预览帧已过期，请重新生成。",
"text_rendering_preview.real_failed": "真实预览帧生成失败：{error}"
```

Add equivalent English keys.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m pytest tests/test_text_rendering_preview.py tests/test_style_config_text_rendering_ui.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add web/components/text_rendering_preview.py web/components/text_rendering_config.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_text_rendering_preview.py tests/test_style_config_text_rendering_ui.py
git commit -m "feat: 增加真实预览帧交互状态"
git push
```

## Task 9: Golden Fixtures and Regression Coverage

**Files:**
- Modify: `tests/fixtures/text_rendering/text_render_package_legacy_caption.json`
- Modify: `tests/fixtures/text_rendering/text_render_package_overlay_hybrid.json`
- Modify: `tests/fixtures/text_rendering/render_manifest_with_text_styles.json`
- Modify: `tests/test_text_rendering_golden_artifacts.py`
- Modify: `tests/test_output_preview.py`
- Modify: `tests/test_hyperframes_runtime_contract.py`

- [ ] **Step 1: Update golden expectations**

In `tests/test_text_rendering_golden_artifacts.py`, update explicit profile ID assertions:

```python
assert [profile["id"] for profile in payload["text_style_profiles"]] == [
    "caption-default",
    "title-default",
    "overlay-default",
]
```

For legacy fixture with one caption and no overlay, assert title profile is present:

```python
assert [profile["id"] for profile in payload["text_style_profiles"]] == [
    "caption-default",
    "title-default",
]
```

- [ ] **Step 2: Update fixture JSON**

Add this profile object after `caption-default` in fixtures that include current text style profiles:

```json
{
  "version": "text_style_profile.v1",
  "id": "title-default",
  "name": "Title Default",
  "font_family": "Noto Sans CJK SC",
  "font_file": null,
  "font_size": 84,
  "font_weight": 800,
  "primary_color": "#2C3E50",
  "background_color": "#FFFFFF",
  "background_opacity": 0.92,
  "stroke_color": "#000000",
  "stroke_width": 0,
  "shadow_color": null,
  "shadow_blur": 0,
  "position": "top",
  "alignment": "center",
  "margin_x": 80,
  "margin_y": 84,
  "max_width_ratio": 0.84,
  "line_height": 1.16,
  "max_chars_per_line": 10,
  "punctuation_mode": "preserve",
  "scale_basis_width": null,
  "scale_basis_height": null
}
```

- [ ] **Step 3: Add request passthrough regression**

In `tests/test_output_preview.py`, extend `test_build_single_generation_request_includes_text_rendering_policy`:

```python
text_rendering = {
    "overlay": {"enabled": False},
    "title_style": {"font_size": 96, "background_opacity": 0.8},
    "image_text": {
        "suppress_embedded_text": True,
        "positive_prompt": "avoid generated lettering",
    },
}
```

Assert:

```python
assert request["text_rendering"]["title_style"] == {
    "font_size": 96,
    "background_opacity": 0.8,
}
```

- [ ] **Step 4: Run regression suite**

Run:

```powershell
python -m pytest tests/test_text_rendering_golden_artifacts.py tests/test_output_preview.py tests/test_hyperframes_runtime_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/fixtures/text_rendering/text_render_package_legacy_caption.json tests/fixtures/text_rendering/text_render_package_overlay_hybrid.json tests/fixtures/text_rendering/render_manifest_with_text_styles.json tests/test_text_rendering_golden_artifacts.py tests/test_output_preview.py tests/test_hyperframes_runtime_contract.py
git commit -m "test: 更新标题样式渲染回归用例"
git push
```

## Task 10: Final Verification and Documentation Notes

**Files:**
- Modify: `docs/superpowers/specs/2026-04-29-title-style-text-rendering-design.md` only if implementation uncovers a contract correction.
- Modify: `docs/pixelle_video_full_planning_md/23_STAGE1_STAGE2_PARALLEL_DEVELOPMENT_STRATEGY.md` only if implementation changes the boundary wording.
- Modify: `docs/pixelle_video_full_planning_md/24_PLATFORM_FOUNDATION_ZERO_TECH_DEBT_SUBPLAN.md` only if object-store integration details changed.

- [ ] **Step 1: Run full targeted test suite**

Run:

```powershell
python -m pytest tests/test_text_rendering_api_schema.py tests/test_text_style_models.py tests/test_template_text_style_presets.py tests/test_text_rendering_orchestrator.py tests/test_template_render_context.py tests/test_hyperframes_compiler.py tests/test_style_config_text_rendering_ui.py tests/test_text_rendering_preview.py tests/test_text_rendering_preview_service.py tests/test_text_rendering_preview_api.py tests/test_text_rendering_golden_artifacts.py tests/test_output_preview.py tests/test_pipeline_text_rendering_contract.py tests/test_standard_pipeline_text_rendering_summary.py -q
```

Expected: PASS.

- [ ] **Step 2: Run static conflict scan**

Run:

```powershell
rg "title_style|caption_style|TextStyleProfile|TextRenderingPreviewSpec|preview-frame|_runtime|template_params" pixelle_video api web docs -n
```

Verify:

- `title_style` only appears under `text_rendering`, template text presets, render context, compiler, preview derivation, tests, and docs.
- No new `title_style` default appears in Stage 1A `PromptPlan`, Stage 2 `StyleProfile`, `AssetBible`, or `PromptComposer`.
- No real preview response returns `_runtime`, `output/...`, `Path`, `local_path`, or Windows/Linux absolute paths.
- No `title_style` is passed through `template_params`.

- [ ] **Step 3: Run route/schema smoke test**

Run:

```powershell
python -m pytest tests/test_text_rendering_preview_api.py tests/test_resource_resolver_contract.py tests/test_platform_repository_contracts.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit documentation corrections if needed**

Only if docs changed:

```powershell
git add docs/superpowers/specs/2026-04-29-title-style-text-rendering-design.md docs/pixelle_video_full_planning_md/23_STAGE1_STAGE2_PARALLEL_DEVELOPMENT_STRATEGY.md docs/pixelle_video_full_planning_md/24_PLATFORM_FOUNDATION_ZERO_TECH_DEBT_SUBPLAN.md
git commit -m "docs: 对齐标题样式预览实施边界"
git push
```

If docs did not change, do not create an empty commit.

## Self-Review

- Spec coverage: Tasks 1 to 3 cover API/schema/default merge/orchestrator/package summary. Tasks 4 and 9 cover HyperFrames compiler and template consumption. Tasks 5, 6, and 8 cover UI tabs, payload cleaning, immediate preview, and real preview state. Task 7 covers real preview frame storage boundary. Task 10 covers Stage1/Stage2 conflict verification.
- Placeholder scan: The plan contains concrete file paths, exact test names, concrete code snippets, commands, expected outcomes, and Chinese commit messages. No `TBD` marker is used.
- Type consistency: `DEFAULT_TITLE_STYLE_ID` is consistently `"title-default"`. API field is `title_style`. Runtime result field is `title_style`. Preview struct is `TextRenderingPreviewSpec`. Real preview route is `/text-rendering/preview-frame`.
- Stage boundary: The plan never stores title/caption style in Stage1A `PromptPlan` or Stage2 `StyleProfile`; preview derives from rendering contracts and storage keys.
- Technical debt check: The plan removes hardcoded title CSS as a source of truth, avoids `template_params` for styles, avoids local path response contracts, and adds tests for the important boundaries.
