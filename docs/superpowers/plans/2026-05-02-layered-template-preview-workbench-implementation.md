# Layered Template Preview Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立统一的分层模板排版源模型，把标题样式、字幕/标题、图片实施预览、模板保存、模板快捷切换和最终生成全部接到同一份 `LayeredTemplateSpec` 契约上。

**Architecture:** 现有仓库已经统一了 `render_backend` 执行路径，但还没有统一“模板排版事实源”。本计划新增 `LayeredTemplateSpec` / `TemplateLayer` / `TemplatePreset` 核心模型，前端 Streamlit 编辑器只负责编辑状态，右侧即时预览工作台、模板库、真实预览帧、HTML screenshot、HyperFrames compiled 和 ffmpeg_manifest 都从同一份 normalized spec 派生。`MediaPlacement` 同步升级为默认中心 + `offset_x` / `offset_y`，旧 `anchor` 只保留兼容输入，不再作为产品能力暴露。

**Tech Stack:** Python 3.11, dataclasses, Pydantic, pytest, Streamlit 1.53.1, FastAPI, Playwright HTML capture, HyperFrames, ffmpeg.

---

## Source Spec

Design: `docs/superpowers/specs/2026-05-02-layered-template-preview-workbench-design.md`

## Key Facts Before Coding

- 当前仓库还没有统一的多图层模板源模型。`render_backend` 统一的是执行路径，不是模板排版契约。
- 当前即时预览仍在 `web/components/text_rendering_config.py`，这会让“文字预览”“模板预览”“保存模板”“最终生成”继续分叉。
- 当前右栏 `web/components/output_preview.py` 里只有 `生成视频` 与 `最近视频`，没有独立的工作台组件。
- 当前 `MediaPlacement` 仍然以 `anchor` 为产品能力；这和新需求“默认居中 + 数值偏移”冲突。
- 当前模板库来自 `pixelle_video/utils/template_util.py` 的系统模板发现，不支持“我的模板”“最近模板”“最近使用 5 个模板快捷切换”。
- 当前后端三条链路 `frame_html.py`、`hyperframes_compiler.py`、`ffmpeg_manifest_renderer.py` 都没有消费统一的多图层排版契约。

## Boundary Rules

- `LayeredTemplateSpec` 是模板排版唯一事实源；`session_state`、`template_params`、`HTML` 字符串都不是事实源。
- 标题和字幕继续以 `text_rendering.title_style` / `text_rendering.caption_style` 作为正式文字样式契约；分层模板中的 `role="title"` / `role="caption"` 只引用这两个契约，不复制它们的样式事实源。
- 普通文字层使用自己的 `style` 字段；标题和字幕层使用 `role` 绑定正式文字样式。
- `template_params` 只保留 legacy HTML 模板的参数，不接收分层模板的布局字段。
- `MediaPlacement` 新输出只允许 `offset_x` / `offset_y`，不允许新 UI 输出 `anchor`。
- 旧 `anchor` 仅作为兼容输入保留；一旦进入标准流程，必须归一化成 offset 语义。
- 即时预览 HTML 只能由系统从 spec 生成，不接受用户自定义 HTML、CSS 或脚本。
- ffmpeg_manifest 不重新解释多图层布局；它只消费同一 spec 预物化后的视觉资产。
- 系统模板、我的模板、最近模板必须走同一份 registry 读取协议，不能保留两套模板卡片数据结构。

## File Structure

- Create `pixelle_video/models/layered_template.py`: `RectSpec`、`LayerSourceSpec`、`TemplateLayer`、`LayeredTemplateSpec`、fingerprint 和 JSON round-trip。
- Create `pixelle_video/models/template_preset.py`: `TemplatePreset`、`TemplatePresetSource`、`TemplatePresetSummary`。
- Modify `pixelle_video/models/media_placement.py`: 升级为 `offset_x` / `offset_y`，保留 legacy `anchor` 兼容输入。
- Modify `pixelle_video/models/storyboard.py`: 让 `StoryboardConfig` 接受 `layered_template_spec` 和 `selected_template_preset_id`。
- Modify `pixelle_video/models/render_package.py`: 让 `RenderManifest` 接受 `layered_template_spec`。
- Modify `pixelle_video/models/template_render_context.py`: 让 HyperFrames 编译上下文接受 `layered_template_spec`。
- Create `pixelle_video/repositories/template_presets.py`: `presets.json`、缩略图、素材资产的本地仓储。
- Create `pixelle_video/services/template_registry.py`: 统一系统模板、我的模板、最近模板视图。
- Create `pixelle_video/services/layered_template_service.py`: spec normalize、校验、fingerprint、标题/字幕 role 解析、真实预览渲染入口。
- Create `pixelle_video/services/layered_template_adapters/html_preview.py`: 即时预览 HTML。
- Create `pixelle_video/services/layered_template_adapters/html_frame.py`: HTML screenshot 渲染适配。
- Create `pixelle_video/services/layered_template_adapters/hyperframes.py`: HyperFrames composition 适配。
- Create `pixelle_video/services/layered_template_adapters/ffmpeg_manifest.py`: ffmpeg 预物化视觉资产适配。
- Modify `pixelle_video/services/frame_html.py`: 增加“渲染任意 HTML 文档到 PNG”的基础能力。
- Modify `pixelle_video/services/template_visual_materializer.py`: 在存在 `layered_template_spec` 时改走新 HTML frame adapter。
- Modify `pixelle_video/services/hyperframes_compiler.py`: 注入分层模板 composition。
- Modify `pixelle_video/services/render_capability_resolver.py`: 补充 layered template 预物化能力判定。
- Create `api/schemas/layered_template_preview.py`: 真实预览帧 API schema。
- Create `api/routers/layered_template_preview.py`: `POST /layered-templates/preview-frame`。
- Modify `api/routers/__init__.py` and `api/app.py`: 注册新 router。
- Modify `api/schemas/video.py` and `api/routers/video.py`: 接受 `layered_template_spec` 和 `selected_template_preset_id`。
- Create `web/components/layered_template_state.py`: Streamlit 编辑状态读写、layer 增删改查和 spec build。
- Create `web/components/layout_preview_workbench.py`: 右栏即时预览工作台。
- Modify `web/components/style_config.py`: 模板库、图层编辑器、媒体位置 offset 控件。
- Modify `web/components/text_rendering_config.py`: 去掉旧即时预览职责，只保留文字契约编辑。
- Modify `web/components/output_preview.py`: 插入右栏工作台，并把生成请求带上 normalized spec。
- Modify `web/pipelines/standard.py`: 继续三栏布局，但右栏渲染新工作台。
- Modify `web/i18n/locales/zh_CN.json` and `web/i18n/locales/en_US.json`: 新文案。
- Add or modify tests:
  - `tests/test_media_placement.py`
  - `tests/test_output_preview.py`
  - `tests/test_style_config_template_gallery.py`
  - `tests/test_text_rendering_preview.py`
  - `tests/test_layered_template_models.py`
  - `tests/test_template_presets_repository.py`
  - `tests/test_template_registry.py`
  - `tests/test_layered_template_preview_service.py`
  - `tests/test_layered_template_preview_api.py`
  - `tests/test_style_config_layered_template_ui.py`
  - `tests/test_layout_preview_workbench.py`
  - `tests/test_template_visual_materializer.py`
  - `tests/test_frame_html.py`
  - `tests/test_hyperframes_compiler.py`
  - `tests/test_ffmpeg_manifest_renderer.py`
  - `tests/test_render_capability_resolver.py`

## Task 1: Upgrade Media Placement To Center Offsets

**Files:**
- Modify: `pixelle_video/models/media_placement.py`
- Modify: `web/components/style_config.py`
- Modify: `web/components/output_preview.py`
- Modify: `tests/test_media_placement.py`
- Modify: `tests/test_style_config_template_gallery.py`
- Modify: `tests/test_output_preview.py`
- Modify: `tests/test_text_rendering_preview.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to `tests/test_media_placement.py`:

```python
def test_media_placement_defaults_to_center_offsets():
    placement = MediaPlacement()

    assert placement.basis == "canvas"
    assert placement.fit == "contain"
    assert placement.scale_percent == 100
    assert placement.offset_x == 0
    assert placement.offset_y == 0
    assert placement.to_dict() == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 100,
        "offset_x": 0,
        "offset_y": 0,
    }


def test_calculate_media_box_applies_offsets_from_center():
    box = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=1024,
        media_source_height=1024,
        placement=MediaPlacement(scale_percent=80, offset_x=64, offset_y=-32),
    )

    assert (round(box.width), round(box.height), round(box.left), round(box.top)) == (
        576,
        576,
        416,
        40,
    )


def test_legacy_anchor_payload_still_produces_equivalent_geometry():
    box = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=1024,
        media_source_height=1024,
        placement={"scale_percent": 80, "anchor": "bottom_right"},
    )

    assert (round(box.left), round(box.top)) == (704, 144)
```

Update the existing `test_render_generation_size_controls_sets_default_media_placement` in `tests/test_style_config_template_gallery.py` so its final assertions become:

```python
style_config._render_generation_size_controls()

assert fake_st.session_state["media_placement_scale_percent"] == 100
assert fake_st.session_state["media_placement_offset_x"] == 0
assert fake_st.session_state["media_placement_offset_y"] == 0
assert fake_st.session_state["media_placement"] == {
    "basis": "canvas",
    "fit": "contain",
    "scale_percent": 100,
    "offset_x": 0,
    "offset_y": 0,
}
```

Update `tests/test_output_preview.py`:

```python
def test_build_single_generation_request_uses_media_placement_offset_payload():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "media_placement": {
                "basis": "canvas",
                "fit": "contain",
                "scale_percent": 90,
                "offset_x": 32,
                "offset_y": -18,
            },
        },
        progress_callback=_progress,
        session_state={},
    )

    assert request["media_placement"] == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 90,
        "offset_x": 32,
        "offset_y": -18,
    }
```

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```powershell
python -m pytest tests/test_media_placement.py tests/test_style_config_template_gallery.py::test_render_generation_size_controls_sets_default_media_placement tests/test_output_preview.py::test_build_single_generation_request_uses_media_placement_offset_payload -q
```

Expected: FAIL because `MediaPlacement` still exposes `anchor`, `style_config` still writes `media_placement_anchor`, and request payload still serializes `anchor`.

- [ ] **Step 3: Implement offset-based placement with legacy anchor compatibility**

In `pixelle_video/models/media_placement.py`, update the model:

```python
@dataclass(frozen=True)
class MediaPlacement:
    basis: MediaPlacementBasis = "canvas"
    fit: MediaPlacementFit = "contain"
    scale_percent: int = 100
    offset_x: int = 0
    offset_y: int = 0
    anchor: MediaPlacementAnchor | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MediaPlacement":
        return cls(
            basis=value.get("basis", "canvas"),
            fit=value.get("fit", "contain"),
            scale_percent=value.get("scale_percent", 100),
            offset_x=value.get("offset_x", 0),
            offset_y=value.get("offset_y", 0),
            anchor=value.get("anchor"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "fit": self.fit,
            "scale_percent": self.scale_percent,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
        }
```

Apply offsets inside `calculate_media_box(...)`:

```python
left = (canvas_width - width) / 2
top = (canvas_height - height) / 2

if resolved.anchor is not None:
    left = _anchor_left(resolved.anchor, canvas_width, width)
    top = _anchor_top(resolved.anchor, canvas_height, height)

left += resolved.offset_x
top += resolved.offset_y
```

In `web/components/style_config.py`, replace the 9-grid UI with numeric offsets:

```python
offset_x = int(
    st.number_input(
        tr("media_placement.offset_x"),
        step=1,
        key="media_placement_offset_x",
        **keyed_widget_default_kwargs(
            st.session_state,
            "media_placement_offset_x",
            value=int(st.session_state.get("media_placement_offset_x", 0)),
        ),
    )
)
offset_y = int(
    st.number_input(
        tr("media_placement.offset_y"),
        step=1,
        key="media_placement_offset_y",
        **keyed_widget_default_kwargs(
            st.session_state,
            "media_placement_offset_y",
            value=int(st.session_state.get("media_placement_offset_y", 0)),
        ),
    )
)
placement = MediaPlacement(
    scale_percent=scale_percent,
    offset_x=offset_x,
    offset_y=offset_y,
)
st.session_state["media_placement"] = placement.to_dict()
```

In `web/components/output_preview.py`, keep `_media_placement_payload(...)` unchanged except that it now serializes offsets via `to_dict()`.

- [ ] **Step 4: Run focused tests to verify pass**

Run:

```powershell
python -m pytest tests/test_media_placement.py tests/test_style_config_template_gallery.py::test_render_generation_size_controls_sets_default_media_placement tests/test_output_preview.py::test_build_single_generation_request_uses_media_placement_offset_payload tests/test_text_rendering_preview.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pixelle_video/models/media_placement.py web/components/style_config.py web/components/output_preview.py tests/test_media_placement.py tests/test_style_config_template_gallery.py tests/test_output_preview.py tests/test_text_rendering_preview.py
git commit -m "refactor: 升级媒体摆放偏移契约"
git push origin dev
```

## Task 2: Add Layered Template Core Models

**Files:**
- Create: `pixelle_video/models/layered_template.py`
- Create: `pixelle_video/models/template_preset.py`
- Modify: `tests/test_layered_template_models.py`

- [ ] **Step 1: Write the failing model tests**

Create `tests/test_layered_template_models.py`:

```python
import pytest

from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    LayerSourceSpec,
    RectSpec,
    TemplateLayer,
    layered_template_fingerprint,
)


def test_layered_template_spec_round_trips_to_dict():
    spec = LayeredTemplateSpec(
        version="layered_template.v1",
        template_id="preset-demo",
        template_name="Demo",
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=64, y=64, width=952, height=1792),
        layers=(
            TemplateLayer(
                id="bg-1",
                type="background",
                name="Background",
                rect=RectSpec(x=0, y=0, width=1080, height=1920),
                z_index=0,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=LayerSourceSpec(kind="color", ref="#F6F1E8"),
                style={"background_color": "#F6F1E8"},
                role=None,
            ),
        ),
        metadata={"source": "user"},
    )

    payload = spec.to_dict()

    assert payload["template_id"] == "preset-demo"
    assert payload["layers"][0]["source"]["kind"] == "color"
    assert LayeredTemplateSpec.from_dict(payload) == spec


def test_layered_template_fingerprint_ignores_non_visual_metadata():
    base = LayeredTemplateSpec(
        version="layered_template.v1",
        template_id="preset-demo",
        template_name="Demo",
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=64, y=64, width=952, height=1792),
        layers=(),
        metadata={"updated_at": "2026-05-02T08:00:00Z"},
    )
    changed = LayeredTemplateSpec(
        **{**base.to_dict(), "metadata": {"updated_at": "2026-05-02T09:00:00Z"}}
    )

    assert layered_template_fingerprint(base) == layered_template_fingerprint(changed)


@pytest.mark.parametrize("opacity", [-0.1, 1.1])
def test_template_layer_rejects_invalid_opacity(opacity):
    with pytest.raises(ValueError, match="opacity"):
        TemplateLayer(
            id="title-1",
            type="text",
            name="Title",
            rect=RectSpec(x=0, y=0, width=100, height=50),
            z_index=1,
            opacity=opacity,
            rotation=0.0,
            locked=False,
            source=None,
            style={},
            role="title",
        )
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_layered_template_models.py -q
```

Expected: FAIL because `pixelle_video.models.layered_template` does not exist.

- [ ] **Step 3: Implement the source-of-truth dataclasses**

Create `pixelle_video/models/layered_template.py`:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

LayerType = Literal["text", "image", "background", "generated_media"]
LayerSourceKind = Literal["color", "asset", "generated_media", "gradient"]


@dataclass(frozen=True)
class RectSpec:
    x: float
    y: float
    width: float
    height: float
    unit: Literal["px"] = "px"


@dataclass(frozen=True)
class LayerSourceSpec:
    kind: LayerSourceKind
    ref: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TemplateLayer:
    id: str
    type: LayerType
    name: str
    rect: RectSpec
    z_index: int
    opacity: float
    rotation: float
    locked: bool
    source: LayerSourceSpec | None
    style: Mapping[str, Any]
    role: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.opacity) <= 1.0:
            raise ValueError("opacity must be between 0 and 1")
```

Continue with `LayeredTemplateSpec` and fingerprint:

```python
def _rect_to_dict(rect: RectSpec) -> dict[str, Any]:
    return {
        "x": rect.x,
        "y": rect.y,
        "width": rect.width,
        "height": rect.height,
        "unit": rect.unit,
    }


def _source_to_dict(source: LayerSourceSpec | None) -> dict[str, Any] | None:
    if source is None:
        return None
    return {
        "kind": source.kind,
        "ref": source.ref,
        "metadata": dict(source.metadata),
    }


def _layer_to_dict(layer: TemplateLayer) -> dict[str, Any]:
    return {
        "id": layer.id,
        "type": layer.type,
        "name": layer.name,
        "rect": _rect_to_dict(layer.rect),
        "z_index": layer.z_index,
        "opacity": layer.opacity,
        "rotation": layer.rotation,
        "locked": layer.locked,
        "source": _source_to_dict(layer.source),
        "style": dict(layer.style),
        "role": layer.role,
    }


@dataclass(frozen=True)
class LayeredTemplateSpec:
    version: str
    template_id: str
    template_name: str
    template_type: str
    canvas_width: int
    canvas_height: int
    media_width: int
    media_height: int
    safe_area: RectSpec
    layers: tuple[TemplateLayer, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "template_id": self.template_id,
            "template_name": self.template_name,
            "template_type": self.template_type,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "media_width": self.media_width,
            "media_height": self.media_height,
            "safe_area": _rect_to_dict(self.safe_area),
            "layers": [_layer_to_dict(layer) for layer in self.layers],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LayeredTemplateSpec":
        def rect(payload: Mapping[str, Any]) -> RectSpec:
            return RectSpec(
                x=float(payload["x"]),
                y=float(payload["y"]),
                width=float(payload["width"]),
                height=float(payload["height"]),
                unit=str(payload.get("unit", "px")),
            )

        def source(payload: Mapping[str, Any] | None) -> LayerSourceSpec | None:
            if payload is None:
                return None
            return LayerSourceSpec(
                kind=str(payload["kind"]),
                ref=str(payload["ref"]),
                metadata=dict(payload.get("metadata", {})),
            )

        return cls(
            version=str(data["version"]),
            template_id=str(data["template_id"]),
            template_name=str(data["template_name"]),
            template_type=str(data["template_type"]),
            canvas_width=int(data["canvas_width"]),
            canvas_height=int(data["canvas_height"]),
            media_width=int(data["media_width"]),
            media_height=int(data["media_height"]),
            safe_area=rect(data["safe_area"]),
            layers=tuple(
                TemplateLayer(
                    id=str(item["id"]),
                    type=str(item["type"]),
                    name=str(item["name"]),
                    rect=rect(item["rect"]),
                    z_index=int(item["z_index"]),
                    opacity=float(item["opacity"]),
                    rotation=float(item["rotation"]),
                    locked=bool(item["locked"]),
                    source=source(item.get("source")),
                    style=dict(item.get("style", {})),
                    role=item.get("role"),
                )
                for item in data.get("layers", ())
            ),
            metadata=dict(data.get("metadata", {})),
        )


def layered_template_fingerprint(spec: LayeredTemplateSpec | Mapping[str, Any]) -> str:
    payload = spec.to_dict() if isinstance(spec, LayeredTemplateSpec) else dict(spec)
    visual_payload = {key: value for key, value in payload.items() if key != "metadata"}
    encoded = json.dumps(
        visual_payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
```

Create `pixelle_video/models/template_preset.py`:

```python
from dataclasses import dataclass
from typing import Literal

from pixelle_video.models.layered_template import LayeredTemplateSpec

TemplatePresetSource = Literal["system", "user", "recent"]


@dataclass(frozen=True)
class TemplatePreset:
    preset_id: str
    name: str
    source: TemplatePresetSource
    orientation: str
    template_type: str
    spec: LayeredTemplateSpec
    thumbnail_ref: str | None = None
    editable: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    last_used_at: str | None = None
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_layered_template_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pixelle_video/models/layered_template.py pixelle_video/models/template_preset.py tests/test_layered_template_models.py
git commit -m "feat: 建立分层模板核心模型"
git push origin dev
```

## Task 3: Add Template Preset Repository And Unified Registry

**Files:**
- Create: `pixelle_video/repositories/template_presets.py`
- Create: `pixelle_video/services/template_registry.py`
- Modify: `pixelle_video/utils/template_util.py`
- Create: `tests/test_template_presets_repository.py`
- Create: `tests/test_template_registry.py`

- [ ] **Step 1: Write the failing repository and registry tests**

Create `tests/test_template_presets_repository.py`:

```python
from pathlib import Path

from pixelle_video.models.layered_template import LayeredTemplateSpec, RectSpec
from pixelle_video.models.template_preset import TemplatePreset
from pixelle_video.repositories.template_presets import TemplatePresetRepository


def _demo_spec() -> LayeredTemplateSpec:
    return LayeredTemplateSpec(
        version="layered_template.v1",
        template_id="preset-demo",
        template_name="Demo",
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=64, y=64, width=952, height=1792),
        layers=(),
        metadata={},
    )


def test_repository_saves_loads_and_touches_last_used(tmp_path: Path):
    repo = TemplatePresetRepository(root=tmp_path)
    preset = TemplatePreset(
        preset_id="user-demo",
        name="My Demo",
        source="user",
        orientation="portrait",
        template_type="image",
        spec=_demo_spec(),
    )

    repo.save(preset)
    loaded = repo.get("user-demo")
    repo.touch_last_used("user-demo", "2026-05-02T09:30:00Z")

    assert loaded is not None
    assert loaded.name == "My Demo"
    assert repo.get("user-demo").last_used_at == "2026-05-02T09:30:00Z"
    assert (tmp_path / "presets.json").exists()
```

Create `tests/test_template_registry.py`:

```python
from pixelle_video.models.template_preset import TemplatePreset
from pixelle_video.services.template_registry import TemplateRegistry


def test_registry_merges_system_and_user_presets(monkeypatch):
    monkeypatch.setattr(
        "pixelle_video.services.template_registry.build_system_template_presets",
        lambda: [
            TemplatePreset(
                preset_id="system:image_default",
                name="image_default",
                source="system",
                orientation="portrait",
                template_type="image",
                spec=None,  # type: ignore[arg-type]
                editable=False,
            )
        ],
    )

    class FakeRepo:
        def list_all(self):
            return [
                TemplatePreset(
                    preset_id="user:demo",
                    name="My Demo",
                    source="user",
                    orientation="portrait",
                    template_type="image",
                    spec=None,  # type: ignore[arg-type]
                )
            ]

        def list_recent(self, limit=5):
            return self.list_all()[:limit]

    presets = TemplateRegistry(repository=FakeRepo()).list_presets(source="all")

    assert [preset.preset_id for preset in presets] == ["system:image_default", "user:demo"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_template_presets_repository.py tests/test_template_registry.py -q
```

Expected: FAIL because repository and registry modules do not exist.

- [ ] **Step 3: Implement JSON-backed repository and one-source registry**

Create `pixelle_video/repositories/template_presets.py`:

```python
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from pixelle_video.models.layered_template import LayeredTemplateSpec
from pixelle_video.models.template_preset import TemplatePreset


class TemplatePresetRepository:
    def __init__(self, root: str | Path = "data/template_presets") -> None:
        self.root = Path(root)
        self.index_path = self.root / "presets.json"
        self.assets_dir = self.root / "assets"
        self.thumbnails_dir = self.root / "thumbnails"
```

Implement atomic persistence and query helpers:

```python
    def save(self, preset: TemplatePreset) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        records = {item.preset_id: item for item in self.list_all()}
        records[preset.preset_id] = preset
        payload = [self._to_record(item) for item in records.values()]
        temp_path = self.index_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.index_path)
```

Create `pixelle_video/services/template_registry.py`:

```python
from __future__ import annotations

from pixelle_video.models.template_preset import TemplatePreset
from pixelle_video.repositories.template_presets import TemplatePresetRepository
from pixelle_video.utils.template_util import get_all_templates_with_info


def build_system_template_presets() -> list[TemplatePreset]:
    presets: list[TemplatePreset] = []
    for item in get_all_templates_with_info():
        presets.append(
            TemplatePreset(
                preset_id=f"system:{item.template_path}",
                name=item.display_info.name,
                source="system",
                orientation=item.display_info.orientation,
                template_type=item.display_info.name.split("_", 1)[0],
                spec=None,  # type: ignore[arg-type]
                editable=False,
            )
        )
    return presets
```

And the registry itself:

```python
class TemplateRegistry:
    def __init__(self, repository: TemplatePresetRepository | None = None) -> None:
        self.repository = repository or TemplatePresetRepository()

    def list_presets(self, *, source: str = "all") -> list[TemplatePreset]:
        system_presets = build_system_template_presets()
        user_presets = self.repository.list_all()
        if source == "system":
            return system_presets
        if source == "user":
            return user_presets
        if source == "recent":
            return self.repository.list_recent(limit=5)
        return system_presets + user_presets
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_template_presets_repository.py tests/test_template_registry.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pixelle_video/repositories/template_presets.py pixelle_video/services/template_registry.py pixelle_video/utils/template_util.py tests/test_template_presets_repository.py tests/test_template_registry.py
git commit -m "feat: 增加模板预设仓储与统一注册表"
git push origin dev
```

## Task 4: Add Layered Preview Service And Preview Frame API

**Files:**
- Create: `pixelle_video/services/layered_template_service.py`
- Create: `pixelle_video/services/layered_template_adapters/html_preview.py`
- Modify: `pixelle_video/services/frame_html.py`
- Create: `api/schemas/layered_template_preview.py`
- Create: `api/routers/layered_template_preview.py`
- Modify: `api/routers/__init__.py`
- Modify: `api/app.py`
- Create: `tests/test_layered_template_preview_service.py`
- Create: `tests/test_layered_template_preview_api.py`

- [ ] **Step 1: Write the failing preview tests**

Create `tests/test_layered_template_preview_service.py`:

```python
from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    LayerSourceSpec,
    RectSpec,
    TemplateLayer,
)
from pixelle_video.services.layered_template_service import LayeredTemplateService


def _preview_spec() -> LayeredTemplateSpec:
    return LayeredTemplateSpec(
        version="layered_template.v1",
        template_id="demo",
        template_name="Demo",
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=64, y=64, width=952, height=1792),
        layers=(
            TemplateLayer(
                id="bg",
                type="background",
                name="Background",
                rect=RectSpec(x=0, y=0, width=1080, height=1920),
                z_index=0,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=LayerSourceSpec(kind="color", ref="#F6F1E8"),
                style={"background_color": "#F6F1E8"},
            ),
            TemplateLayer(
                id="title",
                type="text",
                name="Title",
                rect=RectSpec(x=96, y=120, width=888, height=220),
                z_index=20,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=None,
                style={},
                role="title",
            ),
        ),
        metadata={},
    )


def test_render_preview_html_orders_layers_and_escapes_text():
    html = LayeredTemplateService().render_preview_html(
        spec=_preview_spec(),
        title_text="<b>Title</b>",
        caption_text="Caption",
        text_rendering={"title_style": {"font_size": 88, "primary_color": "#2C3E50"}},
    )

    assert html.index('data-layer-id="bg"') < html.index('data-layer-id="title"')
    assert "&lt;b&gt;Title&lt;/b&gt;" in html
    assert "<script" not in html
    assert "position:absolute" in html
```

Create `tests/test_layered_template_preview_api.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.layered_template_preview import router


def test_preview_frame_api_returns_storage_key(monkeypatch):
    class FakeService:
        async def render_preview_frame(self, request):
            return {"storage_key": "artifacts/ws/preview.png", "url": "/api/files/artifacts/ws/preview.png"}

    monkeypatch.setattr(
        "api.routers.layered_template_preview.LayeredTemplateService",
        lambda *args, **kwargs: FakeService(),
    )

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/layered-templates/preview-frame",
        json={
            "workspace_id": "ws",
            "title_text": "Title",
            "caption_text": "Caption",
            "text_rendering": {"title_style": {"font_size": 88}},
            "spec": {
                "version": "layered_template.v1",
                "template_id": "demo",
                "template_name": "Demo",
                "template_type": "image",
                "canvas_width": 1080,
                "canvas_height": 1920,
                "media_width": 1080,
                "media_height": 1920,
                "safe_area": {"x": 64, "y": 64, "width": 952, "height": 1792, "unit": "px"},
                "layers": [],
                "metadata": {},
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["storage_key"] == "artifacts/ws/preview.png"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_layered_template_preview_service.py tests/test_layered_template_preview_api.py -q
```

Expected: FAIL because the service, schema, and router do not exist.

- [ ] **Step 3: Implement preview HTML adapter and preview-frame API**

Create `pixelle_video/services/layered_template_service.py`:

```python
from pixelle_video.models.layered_template import LayeredTemplateSpec, layered_template_fingerprint
from pixelle_video.services.layered_template_adapters.html_preview import render_layered_template_preview_html


class LayeredTemplateService:
    def render_preview_html(
        self,
        *,
        spec: LayeredTemplateSpec,
        title_text: str,
        caption_text: str,
        text_rendering: dict,
    ) -> str:
        return render_layered_template_preview_html(
            spec=spec,
            title_text=title_text,
            caption_text=caption_text,
            text_rendering=text_rendering,
            fingerprint=layered_template_fingerprint(spec),
        )
```

In `pixelle_video/services/frame_html.py`, add a raw-HTML render helper that later tasks can reuse:

```python
    async def render_html_document(
        self,
        *,
        html: str,
        output_path: str,
        width: int,
        height: int,
    ) -> str:
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        prepared_html = self._prepare_html_for_render(html)
        browser = await self._ensure_browser()
        page = await browser.new_page(
            viewport={"width": int(width), "height": int(height)},
            device_scale_factor=1,
        )
        tmp_html_path = None
        try:
            fd, tmp_html_path = tempfile.mkstemp(
                suffix=".html",
                prefix="pv_raw_html_",
                dir=get_temp_path(),
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(prepared_html)
            await page.goto(
                Path(tmp_html_path).as_uri(),
                wait_until=self.render_readiness.navigation_wait_until,
                timeout=self.render_readiness.navigation_timeout_ms,
            )
            await self.render_readiness.wait(page)
            await page.screenshot(
                path=output_path,
                type="png",
                omit_background=True,
            )
            return output_path
        finally:
            try:
                await page.close()
            finally:
                if tmp_html_path and os.path.exists(tmp_html_path):
                    self._remove_temp_html(tmp_html_path)
```

Create API schema `api/schemas/layered_template_preview.py`:

```python
class LayeredTemplatePreviewFrameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=1, pattern=WORKSPACE_ID_PATTERN.pattern)
    title_text: str = ""
    caption_text: str = ""
    text_rendering: TextRenderingRequest = Field(default_factory=TextRenderingRequest)
    spec: dict
```

Create router `api/routers/layered_template_preview.py`:

```python
router = APIRouter(prefix="/layered-templates", tags=["Layered Templates"])


@router.post("/preview-frame", response_model=LayeredTemplatePreviewFrameResponse)
async def render_layered_template_preview_frame(http_request: Request, request: LayeredTemplatePreviewFrameRequest):
    object_store = _get_artifact_object_store(http_request)
    service = LayeredTemplateService(object_store=object_store)
    result = await service.render_preview_frame(request)
    return LayeredTemplatePreviewFrameResponse(storage_key=result["storage_key"], url=result.get("url"))
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_layered_template_preview_service.py tests/test_layered_template_preview_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pixelle_video/services/layered_template_service.py pixelle_video/services/layered_template_adapters/html_preview.py pixelle_video/services/frame_html.py api/schemas/layered_template_preview.py api/routers/layered_template_preview.py api/routers/__init__.py api/app.py tests/test_layered_template_preview_service.py tests/test_layered_template_preview_api.py
git commit -m "feat: 增加分层模板预览服务与接口"
git push origin dev
```

## Task 5: Refactor Middle Column Into A Real Multi-Layer Editor

**Files:**
- Create: `web/components/layered_template_state.py`
- Modify: `web/components/style_config.py`
- Modify: `web/components/text_rendering_config.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Create: `tests/test_style_config_layered_template_ui.py`

- [ ] **Step 1: Write the failing Streamlit state tests**

Create `tests/test_style_config_layered_template_ui.py`:

```python
from web.components.layered_template_state import LayeredTemplateEditorState


def test_editor_state_can_append_multiple_layers():
    state = LayeredTemplateEditorState.empty(
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
    )

    state = state.append_text_layer("标题一")
    state = state.append_text_layer("标题二")
    state = state.append_image_layer("图片一")
    state = state.append_background_layer("背景一")

    assert [layer.type for layer in state.layers] == ["text", "text", "image", "background"]
    assert len({layer.id for layer in state.layers}) == 4


def test_editor_state_builds_layered_template_spec():
    state = LayeredTemplateEditorState.empty(
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
    ).append_text_layer("标题")

    spec = state.build_spec(template_id="demo", template_name="Demo", template_type="image")

    assert spec.template_id == "demo"
    assert spec.canvas_width == 1080
    assert spec.layers[0].type == "text"
```

Add a UI regression test to the same file:

```python
def test_text_rendering_controls_no_longer_render_instant_preview(monkeypatch):
    captured = {"markdown": []}

    class FakeUI:
        session_state = {}

        def expander(self, *_args, **_kwargs):
            class _Ctx:
                def __enter__(self_inner):
                    return self
                def __exit__(self_inner, exc_type, exc, tb):
                    return False
            return _Ctx()

        def container(self, **_kwargs):
            return self.expander("")

        def markdown(self, value, **_kwargs):
            captured["markdown"].append(value)

        def tabs(self, _labels):
            return [self, self]

        def checkbox(self, *_args, **_kwargs):
            return False

        def text_area(self, *_args, **_kwargs):
            return ""

        def selectbox(self, _label, options, **_kwargs):
            return options[0]

        def number_input(self, _label, **kwargs):
            return kwargs.get("value", 0)

        def color_picker(self, _label, **kwargs):
            return kwargs.get("value", "#FFFFFF")

        def radio(self, _label, options, **_kwargs):
            return options[0]

    payload = text_rendering_config.render_text_rendering_controls(
        "hyperframes_compiled",
        ui=FakeUI(),
        translate=lambda key, **kwargs: key,
        template_id="image_default",
    )

    assert isinstance(payload, dict)
    assert "text_rendering_preview.title" not in captured["markdown"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_style_config_layered_template_ui.py -q
```

Expected: FAIL because editor state module does not exist and `render_text_rendering_controls(...)` still renders preview markup.

- [ ] **Step 3: Implement editor state and move preview ownership out of text rendering**

Create `web/components/layered_template_state.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import uuid4

from pixelle_video.models.layered_template import LayeredTemplateSpec, RectSpec, TemplateLayer


@dataclass(frozen=True)
class LayeredTemplateEditorState:
    canvas_width: int
    canvas_height: int
    media_width: int
    media_height: int
    layers: tuple[TemplateLayer, ...] = ()
    selected_layer_id: str | None = None
```

Add append/build helpers:

```python
    def append_text_layer(self, name: str) -> "LayeredTemplateEditorState":
        layer = TemplateLayer(
            id=f"layer_{uuid4().hex[:8]}",
            type="text",
            name=name,
            rect=RectSpec(x=96, y=120, width=self.canvas_width - 192, height=180),
            z_index=len(self.layers) + 10,
            opacity=1.0,
            rotation=0.0,
            locked=False,
            source=None,
            style={},
        )
        return replace(self, layers=(*self.layers, layer), selected_layer_id=layer.id)
```

In `web/components/text_rendering_config.py`, remove the block that calls `build_text_rendering_preview_spec(...)`, `render_text_rendering_preview(...)`, `request_real_preview_frame(...)`, and `render_real_preview_status(...)`. The function should now stop after building `text_rendering_payload` and return it.

In `web/components/style_config.py`, replace the current template parameter-only editing flow with:

```python
editor_state = ensure_layered_template_editor_state(
    session_state=st.session_state,
    canvas_width=size_contract.canvas_width,
    canvas_height=size_contract.canvas_height,
    media_width=size_contract.media_width,
    media_height=size_contract.media_height,
)

col_add_text, col_add_image, col_add_background = st.columns(3)
if col_add_text.button(tr("template_editor.add_text"), width="stretch"):
    editor_state = editor_state.append_text_layer(tr("template_editor.default_text"))
if col_add_image.button(tr("template_editor.add_image"), width="stretch"):
    editor_state = editor_state.append_image_layer(tr("template_editor.default_image"))
if col_add_background.button(tr("template_editor.add_background"), width="stretch"):
    editor_state = editor_state.append_background_layer(tr("template_editor.default_background"))
```

Return the normalized spec from `render_style_config(...)`:

```python
layered_template_spec = editor_state.build_spec(
    template_id=selected_preset_id or Path(frame_template).stem,
    template_name=selected_template_name or Path(frame_template).stem,
    template_type=selected_template_type,
)
result["layered_template_spec"] = layered_template_spec.to_dict()
result["selected_template_preset_id"] = selected_preset_id
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_style_config_layered_template_ui.py tests/test_style_config_template_gallery.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add web/components/layered_template_state.py web/components/style_config.py web/components/text_rendering_config.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_style_config_layered_template_ui.py
git commit -m "refactor: 重构中栏分层模板编辑器"
git push origin dev
```

## Task 6: Add The Right-Column Instant Preview Workbench

**Files:**
- Create: `web/components/layout_preview_workbench.py`
- Modify: `web/components/output_preview.py`
- Create: `tests/test_layout_preview_workbench.py`
- Modify: `tests/test_output_preview.py`

- [ ] **Step 1: Write the failing right-column tests**

Create `tests/test_layout_preview_workbench.py`:

```python
from web.components import layout_preview_workbench


def test_recent_template_shortcuts_are_sorted_by_last_used_desc():
    items = [
        {"preset_id": "a", "name": "A", "last_used_at": "2026-05-02T08:00:00Z"},
        {"preset_id": "b", "name": "B", "last_used_at": "2026-05-02T10:00:00Z"},
        {"preset_id": "c", "name": "C", "last_used_at": "2026-05-02T09:00:00Z"},
    ]

    ordered = layout_preview_workbench.sort_recent_template_shortcuts(items, limit=2)

    assert [item["preset_id"] for item in ordered] == ["b", "c"]
```

Add this regression test to `tests/test_output_preview.py`:

```python
def test_render_single_output_renders_workbench_between_generation_and_recent(monkeypatch):
    sections = []

    monkeypatch.setattr(
        output_preview,
        "_render_layout_preview_workbench_section",
        lambda *args, **kwargs: sections.append("workbench"),
        raising=False,
    )
    monkeypatch.setattr(
        output_preview,
        "render_recent_video_gallery",
        lambda *args, **kwargs: sections.append("recent"),
    )
    monkeypatch.setattr(
        output_preview,
        "_render_generation_section",
        lambda *args, **kwargs: sections.append("generation"),
        raising=False,
    )

    output_preview._render_single_output_sections(object(), {"text": "demo"})

    assert sections == ["generation", "workbench", "recent"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_layout_preview_workbench.py tests/test_output_preview.py::test_render_single_output_renders_workbench_between_generation_and_recent -q
```

Expected: FAIL because the workbench component and section splitter do not exist.

- [ ] **Step 3: Implement the workbench component and right-column split**

Create `web/components/layout_preview_workbench.py`:

```python
from __future__ import annotations

import streamlit as st

from pixelle_video.services.layered_template_adapters.html_preview import render_layered_template_preview_html


def sort_recent_template_shortcuts(items: list[dict], limit: int = 5) -> list[dict]:
    return sorted(
        items,
        key=lambda item: item.get("last_used_at") or "",
        reverse=True,
    )[:limit]
```

Render the workbench:

```python
def render_layout_preview_workbench(*, spec, title_text, caption_text, text_rendering, recent_templates, real_preview_state):
    with st.container(border=True):
        st.markdown("**即时预览工作台**")
        for item in sort_recent_template_shortcuts(recent_templates, limit=5):
            st.button(item["name"], key=f"recent_template_{item['preset_id']}", width="stretch")
        st.caption(f"{spec.canvas_width}x{spec.canvas_height} · {len(spec.layers)} layers")
        st.markdown(
            render_layered_template_preview_html(
                spec=spec,
                title_text=title_text,
                caption_text=caption_text,
                text_rendering=text_rendering,
            ),
            unsafe_allow_html=True,
        )
```

In `web/components/output_preview.py`, split `render_single_output(...)` into explicit sections:

```python
def _render_single_output_sections(pixelle_video, video_params):
    _render_generation_section(pixelle_video, video_params)
    _render_layout_preview_workbench_section(pixelle_video, video_params)
    render_recent_video_gallery(pixelle_video)
```

And wire the request payload:

```python
if video_params.get("layered_template_spec") is not None:
    request["layered_template_spec"] = video_params["layered_template_spec"]
if video_params.get("selected_template_preset_id"):
    request["selected_template_preset_id"] = video_params["selected_template_preset_id"]
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_layout_preview_workbench.py tests/test_output_preview.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add web/components/layout_preview_workbench.py web/components/output_preview.py tests/test_layout_preview_workbench.py tests/test_output_preview.py
git commit -m "feat: 新增右栏即时预览工作台"
git push origin dev
```

## Task 7: Thread Layered Template Snapshot Through Requests And Pipeline Models

**Files:**
- Modify: `api/schemas/video.py`
- Modify: `api/routers/video.py`
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/models/render_package.py`
- Modify: `pixelle_video/models/template_render_context.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `tests/test_output_preview.py`
- Modify: `tests/test_template_render_context.py`
- Create: `tests/test_standard_pipeline_layered_template.py`

- [ ] **Step 1: Write the failing pipeline contract tests**

Add to `tests/test_output_preview.py`:

```python
def test_build_single_generation_request_includes_layered_template_snapshot():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "layered_template_spec": {"template_id": "demo", "layers": []},
            "selected_template_preset_id": "user:demo",
        },
        progress_callback=_progress,
        session_state={},
    )

    assert request["layered_template_spec"] == {"template_id": "demo", "layers": []}
    assert request["selected_template_preset_id"] == "user:demo"
```

Create `tests/test_standard_pipeline_layered_template.py`:

```python
from pixelle_video.models.storyboard import StoryboardConfig


def test_storyboard_config_accepts_layered_template_snapshot():
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        layered_template_spec={"template_id": "demo", "layers": []},
        selected_template_preset_id="user:demo",
    )

    assert config.layered_template_spec == {"template_id": "demo", "layers": []}
    assert config.selected_template_preset_id == "user:demo"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_output_preview.py::test_build_single_generation_request_includes_layered_template_snapshot tests/test_standard_pipeline_layered_template.py -q
```

Expected: FAIL because request builder and `StoryboardConfig` do not accept these fields.

- [ ] **Step 3: Implement request, config, and manifest plumbing**

In `api/schemas/video.py`, add fields:

```python
layered_template_spec: dict | None = None
selected_template_preset_id: str | None = None
```

In `pixelle_video/models/storyboard.py`, extend `StoryboardConfig`:

```python
layered_template_spec: Optional[Dict[str, Any]] = None
selected_template_preset_id: Optional[str] = None
```

In `pixelle_video/models/render_package.py`, extend `RenderManifest`:

```python
layered_template_spec: Mapping[str, Any] | None = None
```

In `pixelle_video/models/template_render_context.py`, extend the compiler context:

```python
layered_template_spec: Mapping[str, Any] | None = None
```

In `pixelle_video/pipelines/standard.py`, add the new fields at the existing config and manifest construction points.

```python
ctx.config = StoryboardConfig(
    task_id=ctx.task_id,
    n_storyboard=frame_count,
    min_narration_words=ctx.params.get("min_narration_words", 5),
    max_narration_words=ctx.params.get("max_narration_words", 20),
    min_image_prompt_words=ctx.params.get("min_image_prompt_words", 30),
    max_image_prompt_words=ctx.params.get("max_image_prompt_words", 60),
    video_fps=ctx.params.get("video_fps", 30),
    tts_inference_mode=resolved_tts_inference_mode,
    voice_id=final_voice_id,
    tts_workflow=final_tts_workflow,
    tts_speed=ctx.params.get("tts_speed", 1.2),
    ref_audio=ctx.params.get("ref_audio"),
    ref_audio_text=ctx.params.get("ref_audio_text") or ctx.params.get("prompt_text"),
    **resolve_storyboard_render_kwargs(self.core.config, ctx.params),
    canvas_width=size_contract.canvas_width,
    canvas_height=size_contract.canvas_height,
    media_width=size_contract.media_width,
    media_height=size_contract.media_height,
    video_orientation=size_contract.video_orientation,
    video_resolution_preset=size_contract.video_resolution_preset,
    media_orientation=size_contract.media_orientation,
    media_resolution_preset=size_contract.media_resolution_preset,
    sync_media_size_to_canvas=size_contract.sync_media_size_to_canvas,
    media_placement=ctx.params.get("media_placement"),
    media_workflow=ctx.params.get("media_workflow"),
    media_negative_prompt=ctx.media_negative_prompt,
    frame_template=frame_template,
    template_params=ctx.params.get("template_params"),
    layered_template_spec=ctx.params.get("layered_template_spec"),
    selected_template_preset_id=ctx.params.get("selected_template_preset_id"),
    **build_storyboard_config_planning_kwargs(ctx.planning_snapshot, planning_params),
)
```

Add `layered_template_spec=config.layered_template_spec` to every `RenderManifest(...)` construction immediately after `media_placement=...`:

```python
manifest = RenderManifest(
    task_id=ctx.task_id or config.task_id or "",
    title=storyboard.title,
    canvas_width=canvas_width,
    canvas_height=canvas_height,
    media_width=config.media_width,
    media_height=config.media_height,
    sync_media_size_to_canvas=config.sync_media_size_to_canvas,
    media_layout_mode=config.media_layout_mode,
    media_placement=config.media_placement,
    layered_template_spec=config.layered_template_spec,
    fps=config.video_fps,
    template_id=Path(config.frame_template).stem,
)
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_output_preview.py::test_build_single_generation_request_includes_layered_template_snapshot tests/test_standard_pipeline_layered_template.py tests/test_template_render_context.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add api/schemas/video.py api/routers/video.py pixelle_video/models/storyboard.py pixelle_video/models/render_package.py pixelle_video/models/template_render_context.py pixelle_video/pipelines/standard.py tests/test_output_preview.py tests/test_template_render_context.py tests/test_standard_pipeline_layered_template.py
git commit -m "refactor: 贯通分层模板生成快照契约"
git push origin dev
```

## Task 8: Integrate Layered Template HTML Screenshot Rendering

**Files:**
- Create: `pixelle_video/services/layered_template_adapters/html_frame.py`
- Modify: `pixelle_video/services/template_visual_materializer.py`
- Modify: `pixelle_video/services/frame_html.py`
- Modify: `tests/test_template_visual_materializer.py`
- Modify: `tests/test_frame_html.py`

- [ ] **Step 1: Write the failing HTML screenshot tests**

Add to `tests/test_template_visual_materializer.py`:

```python
@pytest.mark.asyncio
async def test_template_visual_materializer_uses_layered_adapter_when_spec_present(tmp_path, monkeypatch):
    captured = {}

    class FakeLayeredAdapter:
        async def materialize(self, **kwargs):
            captured.update(kwargs)
            output_path = Path(kwargs["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"png")
            return str(output_path)

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.LayeredTemplateHTMLFrameAdapter",
        lambda: FakeLayeredAdapter(),
    )

    asset = await TemplateVisualMaterializer().materialize_frame(
        title="Demo",
        template_body_text="Template body",
        media_path="raw.png",
        frame_index=0,
        template_path="templates/1080x1920/image_default.html",
        template_id="image_default",
        output_path=tmp_path / "frame.png",
        text_policy="caption_renderer",
        layered_template_spec={"template_id": "demo", "layers": []},
    )

    assert asset.path == str(tmp_path / "frame.png")
    assert captured["layered_template_spec"]["template_id"] == "demo"
```

Add to `tests/test_frame_html.py`:

```python
@pytest.mark.asyncio
async def test_render_html_document_captures_raw_html(tmp_path):
    generator = HTMLFrameGenerator("templates/1080x1920/image_default.html")

    output = tmp_path / "preview.png"
    result = await generator.render_html_document(
        html="<html><body><div id='demo'>hello</div></body></html>",
        output_path=str(output),
        width=320,
        height=240,
    )

    assert result == str(output)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_template_visual_materializer.py tests/test_frame_html.py -q
```

Expected: FAIL because the layered adapter entry point and `render_html_document(...)` helper are missing.

- [ ] **Step 3: Implement HTML frame adapter and materializer switch**

Create `pixelle_video/services/layered_template_adapters/html_frame.py`:

```python
from __future__ import annotations

from pixelle_video.models.layered_template import LayeredTemplateSpec
from pixelle_video.services.frame_html import HTMLFrameGenerator
from pixelle_video.services.layered_template_service import LayeredTemplateService


class LayeredTemplateHTMLFrameAdapter:
    def __init__(self, service: LayeredTemplateService | None = None) -> None:
        self.service = service or LayeredTemplateService()

    async def materialize(self, *, layered_template_spec: dict, title: str, caption_text: str, text_rendering: dict, output_path: str) -> str:
        spec = LayeredTemplateSpec.from_dict(layered_template_spec)
        html = self.service.render_preview_html(
            spec=spec,
            title_text=title,
            caption_text=caption_text,
            text_rendering=text_rendering,
        )
        generator = HTMLFrameGenerator("templates/1080x1920/image_default.html")
        return await generator.render_html_document(
            html=html,
            output_path=output_path,
            width=spec.canvas_width,
            height=spec.canvas_height,
        )
```

In `pixelle_video/services/template_visual_materializer.py`, switch on the new snapshot:

```python
        layered_template_spec: Mapping[str, Any] | None = None,
```

Add the parameter above to `TemplateVisualMaterializer.materialize_frame(...)`, then branch before constructing the legacy `HTMLFrameGenerator`:

```python
if layered_template_spec:
    generated_path = await LayeredTemplateHTMLFrameAdapter().materialize(
        layered_template_spec=dict(layered_template_spec),
        title=title,
        caption_text=body_text,
        text_rendering={},
        output_path=str(output_path),
    )
    spec = LayeredTemplateSpec.from_dict(layered_template_spec)
    return TemplateVisualAsset(
        path=str(generated_path),
        frame_index=int(frame_index),
        template_id=template_id,
        template_path=str(template_path),
        width=int(spec.canvas_width),
        height=int(spec.canvas_height),
        media_path=media_path,
        text_policy=text_policy,
        diagnostics={
            "template_params_count": 0,
            "layered_template_id": spec.template_id,
        },
    )
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_template_visual_materializer.py tests/test_frame_html.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pixelle_video/services/layered_template_adapters/html_frame.py pixelle_video/services/template_visual_materializer.py pixelle_video/services/frame_html.py tests/test_template_visual_materializer.py tests/test_frame_html.py
git commit -m "feat: 接入分层模板 HTML 截图渲染"
git push origin dev
```

## Task 9: Integrate HyperFrames And ffmpeg Manifest Adapters

**Files:**
- Create: `pixelle_video/services/layered_template_adapters/hyperframes.py`
- Create: `pixelle_video/services/layered_template_adapters/ffmpeg_manifest.py`
- Modify: `pixelle_video/services/hyperframes_compiler.py`
- Modify: `pixelle_video/services/ffmpeg_manifest_renderer.py`
- Modify: `pixelle_video/services/render_capability_resolver.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `tests/test_hyperframes_compiler.py`
- Modify: `tests/test_ffmpeg_manifest_renderer.py`
- Modify: `tests/test_render_capability_resolver.py`

- [ ] **Step 1: Write the failing backend adapter tests**

Add to `tests/test_hyperframes_compiler.py`:

```python
def test_hyperframes_compiler_injects_layered_template_composition(tmp_path):
    compiler = HyperFramesCompiler()
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1.0,
        fps=30,
        title="Demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        layered_template_spec={"template_id": "demo", "layers": []},
    )

    compiler.compile(project_dir=tmp_path / "project", context=context)

    assert (tmp_path / "project" / "compositions" / "layered_template.html").exists()
```

Add to `tests/test_render_capability_resolver.py`:

```python
def test_ffmpeg_manifest_accepts_layered_template_when_prerender_available():
    result = RenderCapabilityResolver().resolve(
        RenderCapabilityInput(
            requested_backend="ffmpeg_manifest",
            template_type="image",
            media_domain="image",
            template_prerendered=True,
            element_motion_backend=None,
            has_hyperframes_native_template=True,
        )
    )

    assert result.effective_backend == "ffmpeg_manifest"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_hyperframes_compiler.py tests/test_ffmpeg_manifest_renderer.py tests/test_render_capability_resolver.py -q
```

Expected: FAIL because compiler does not emit `layered_template.html`, ffmpeg path has no layered adapter, and capability diagnostics are incomplete.

- [ ] **Step 3: Implement HyperFrames composition adapter and ffmpeg prerender adapter**

Create `pixelle_video/services/layered_template_adapters/hyperframes.py`:

```python
from pixelle_video.models.layered_template import LayeredTemplateSpec
from pixelle_video.services.layered_template_service import LayeredTemplateService


class LayeredTemplateHyperFramesAdapter:
    def __init__(self, service: LayeredTemplateService | None = None) -> None:
        self.service = service or LayeredTemplateService()

    def build_composition_html(self, *, spec: dict, title_text: str, caption_text: str, text_rendering: dict) -> str:
        return self.service.render_preview_html(
            spec=LayeredTemplateSpec.from_dict(spec),
            title_text=title_text,
            caption_text=caption_text,
            text_rendering=text_rendering,
        )
```

Modify `pixelle_video/services/hyperframes_compiler.py`:

```python
layered_template_html = ""
if context.layered_template_spec:
    layered_template_html = LayeredTemplateHyperFramesAdapter().build_composition_html(
        spec=dict(context.layered_template_spec),
        title_text=context.title,
        caption_text="",
        text_rendering={},
    )
    (project_dir / "compositions" / "layered_template.html").write_text(
        layered_template_html,
        encoding="utf-8",
    )
```

Create `pixelle_video/services/layered_template_adapters/ffmpeg_manifest.py`:

```python
class LayeredTemplateFfmpegAdapter:
    async def prerender_visual_asset(self, *, layered_template_spec: dict, output_path: str, title_text: str, caption_text: str) -> str:
        return await LayeredTemplateHTMLFrameAdapter().materialize(
            layered_template_spec=layered_template_spec,
            title=title_text,
            caption_text=caption_text,
            text_rendering={},
            output_path=output_path,
        )
```

In `pixelle_video/pipelines/standard.py`, before ffmpeg manifest render:

```python
if config.layered_template_spec:
    prerendered_template_asset = await LayeredTemplateFfmpegAdapter().prerender_visual_asset(
        layered_template_spec=config.layered_template_spec,
        output_path=str(Path(ctx.task_dir) / "layered_template.png"),
        title_text=storyboard.title,
        caption_text="",
    )
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_hyperframes_compiler.py tests/test_ffmpeg_manifest_renderer.py tests/test_render_capability_resolver.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pixelle_video/services/layered_template_adapters/hyperframes.py pixelle_video/services/layered_template_adapters/ffmpeg_manifest.py pixelle_video/services/hyperframes_compiler.py pixelle_video/services/ffmpeg_manifest_renderer.py pixelle_video/services/render_capability_resolver.py pixelle_video/pipelines/standard.py tests/test_hyperframes_compiler.py tests/test_ffmpeg_manifest_renderer.py tests/test_render_capability_resolver.py
git commit -m "feat: 打通分层模板多后端渲染适配"
git push origin dev
```

## Final Verification

- [ ] **Step 1: Run the full focused regression suite**

Run:

```powershell
python -m pytest tests/test_media_placement.py tests/test_output_preview.py tests/test_style_config_template_gallery.py tests/test_style_config_layered_template_ui.py tests/test_layered_template_models.py tests/test_template_presets_repository.py tests/test_template_registry.py tests/test_layered_template_preview_service.py tests/test_layered_template_preview_api.py tests/test_template_visual_materializer.py tests/test_frame_html.py tests/test_hyperframes_compiler.py tests/test_ffmpeg_manifest_renderer.py tests/test_render_capability_resolver.py tests/test_standard_pipeline_layered_template.py -q
```

Expected: PASS.

- [ ] **Step 2: Run one end-to-end local smoke test**

Run:

```powershell
python -m pytest tests/test_output_preview.py::test_render_single_output_renders_workbench_between_generation_and_recent tests/test_style_config_layered_template_ui.py::test_editor_state_builds_layered_template_spec tests/test_template_visual_materializer.py::test_template_visual_materializer_uses_layered_adapter_when_spec_present -q
```

Expected: PASS.

- [ ] **Step 3: Review for contract leaks**

Manually verify these invariants in the diff:

```text
1. 新 UI payload 不再输出 media_placement.anchor
2. text_rendering_config.py 不再渲染即时预览
3. output_preview.py 请求里包含 layered_template_spec
4. template_params 没有新增任何图层布局字段
5. HyperFrames / ffmpeg / HTML screenshot 都从 layered_template_spec 派生
```

- [ ] **Step 4: Commit any final cleanup**

```powershell
git add .
git commit -m "test: 收敛分层模板预览工作台回归验证"
git push origin dev
```

- [ ] **Step 5: Handoff**

确认这些验收项全部满足后再汇报完成：

```text
1. 右栏顺序固定为 生成视频 -> 即时预览工作台 -> 最近视频
2. 即时预览工作台显示最近 5 个模板快捷切换
3. 图片位置控件只有 scale + offset_x + offset_y
4. 中栏支持多文字层、多图片层、多背景层
5. 当前排版可以保存为我的模板并在模板库回填
6. 生成请求和最终渲染都消费同一份 layered_template_spec
```
