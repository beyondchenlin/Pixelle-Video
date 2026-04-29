# Template Media Contract v2 设计方案

## 1. 结论

Pixelle 不应该继续让每个模板自行决定图片在画面里的大小、裁切和位置。图片显示规则必须上升为平台级契约，由 UI、API、StoryboardConfig、RenderManifest、HTML 模板渲染和 HyperFrames 渲染共同消费。

采用方案：

- 新增 `MediaPlacement` 作为系统级媒体摆放契约。
- 图片生成尺寸继续由 `media_width` / `media_height` 控制。
- 图片显示尺寸和位置由 `media_placement` 控制。
- `100%` 按最终视频画布 `canvas_width` / `canvas_height` 计算，不按模板内部图片框计算。
- 默认显示占比为 `80%`，默认位置为 `center`。
- 缩放方式使用 `contain`，保持图片原始宽高比，不裁切。
- 位置控件使用 9 宫格锚点。
- 模板继续负责背景、标题、装饰、层级和风格，不再拥有独立图片缩放规则。

这不是最小改动。它是对现有 `media_layout_mode` 的语义升级，目标是从源头拆开“图片生成尺寸”和“图片画面摆放”，避免继续在模板 CSS、`template_params`、session state 或单个渲染后端里打补丁。

## 2. 背景

项目已经完成了视频尺寸和图片生成尺寸的拆分：

- `GenerationSizeContract` 表达最终视频画布和素材生成尺寸。
- `canvas_width` / `canvas_height` 表达最终视频尺寸。
- `media_width` / `media_height` 表达 AI 图片或视频素材生成尺寸。
- `sync_media_size_to_canvas` 可让素材生成尺寸跟随最终画布。

但当前图片在最终视频画面里的显示方式仍然分散：

- HTML 模板里有的使用 `<img src="{{image}}">`。
- 有的模板使用 `background-image: url("{{image}}")`。
- 有的模板使用 `object-fit: cover`，会裁切。
- 有的模板使用 `object-fit: contain`，但位置和可用区域仍由模板自己控制。
- HyperFrames 模板也各自定义 `.visual-clip__media` 的 `object-fit` 和布局。
- 现有 `media_layout_mode` 只有 `template` 和 `canvas` 两个值，无法表达 `80%`、9 宫格位置、是否裁切等关键规则。

这会导致同一个用户意图在不同模板中表现不一致。例如用户选择 `80% + 居中`，模板 A 可能裁切，模板 B 可能铺成背景，模板 C 可能塞进固定 900x900 框。这个问题不能靠继续修改个别模板解决。

## 3. 目标

1. 建立平台级 `MediaPlacement`，作为图片/视频素材在最终画布中显示的唯一事实源。
2. 保持用户心智直观：`100%` 始终按整个最终视频画布计算。
3. 支持横图、竖图、方图在同一视频画布内等比显示。
4. 默认 `80% + 居中`，让模板背景、标题和装饰露出。
5. 支持 9 宫格位置：左上、上中、右上、左中、居中、右中、左下、下中、右下。
6. HTMLFrameGenerator、HyperFrames、FFmpeg manifest 相关链路消费同一份媒体摆放契约。
7. 让模板只表达舞台结构和视觉风格，不再散落自己的图片缩放规则。
8. 为模板增加 lint/校验规则，防止新模板绕过标准媒体层。

## 4. 非目标

- 不改变 AI 图片生成尺寸的含义。`media_width` / `media_height` 仍然只表示生成素材尺寸。
- 不把 `media_placement` 塞进 `template_params`。
- 不让每个模板各自新增 `image_scale`、`image_position` 等私有参数。
- 不把 `100%` 定义为模板图片框大小。
- 不把第一版做成只兼容少数 `<img>` 模板的局部补丁。
- 不强制删除所有老模板的视觉设计；迁移目标是保留风格，统一媒体层。

## 5. 两次 Review 结论

### Review 1: 架构边界

现有 `media_layout_mode` 已经说明项目需要媒体布局概念，但它过于粗糙，并且当前间接依赖 `sync_media_size_to_canvas`。这会把“生成多大图片”和“图片在视频里如何显示”混在一起。

正确边界：

```text
media_width / media_height
  -> 素材生成尺寸

media_placement
  -> 素材在最终视频画布里的显示方式
```

因此 `media_layout_mode` 不应继续承担所有媒体摆放语义。它可以作为兼容字段保留，但新链路应以 `MediaPlacement` 为准。

### Review 2: 技术债风险

拒绝三个看似简单但会留下技术债的做法：

1. 只改几个独立图片层模板。这样 `background-image` 模板和 HyperFrames 模板仍会产生不一致。
2. 把参数放进 `template_params`。这样媒体摆放会变成模板私有能力，平台无法统一测试和验证。
3. 继续让模板 CSS 决定 `object-fit`、宽高和位置。这样每个模板都会成为一个新的规则分支。

最终选择平台级 `MediaPlacement`，并迁移模板到标准媒体层。

## 6. 新增契约

建议新增模块：

```text
pixelle_video/models/media_placement.py
```

核心模型：

```python
from dataclasses import dataclass
from typing import Literal

MediaPlacementBasis = Literal["canvas"]
MediaPlacementFit = Literal["contain", "cover"]
MediaPlacementAnchor = Literal[
    "top_left", "top", "top_right",
    "left", "center", "right",
    "bottom_left", "bottom", "bottom_right",
]

@dataclass(frozen=True)
class MediaPlacement:
    basis: MediaPlacementBasis = "canvas"
    fit: MediaPlacementFit = "contain"
    scale_percent: int = 80
    anchor: MediaPlacementAnchor = "center"
```

第一版只开放 `basis="canvas"` 和 `fit="contain"`。`cover` 可以作为内部兼容值保留，但 UI 不默认暴露，避免用户误以为图片不会被裁切。

校验规则：

- `scale_percent` 建议范围 `10..100`。
- 默认值为 `80`。
- `anchor` 默认 `center`。
- `basis` 第一版只能为 `canvas`。
- 若收到未知值，API 返回清晰错误，不静默回退。

## 7. 几何计算规则

输入：

- 最终画布：`canvas_width` / `canvas_height`
- 原始素材尺寸：从实际图片/视频读取；若不可读，使用 `media_width` / `media_height` 作为 fallback
- `scale_percent`
- `anchor`
- `fit`

对于 `fit="contain"`：

```text
base_scale = min(canvas_width / media_source_width,
                 canvas_height / media_source_height)

display_scale = base_scale * (scale_percent / 100)

display_width = media_source_width * display_scale
display_height = media_source_height * display_scale
```

位置：

```text
left:
  left anchor -> 0
  center anchor -> (canvas_width - display_width) / 2
  right anchor -> canvas_width - display_width

top:
  top anchor -> 0
  center anchor -> (canvas_height - display_height) / 2
  bottom anchor -> canvas_height - display_height
```

例子，最终视频 `1280x720`：

- 横图 `1280x720`，100% 时显示 `1280x720`。
- 方图 `1024x1024`，100% 时显示 `720x720`。
- 竖图 `720x1280`，100% 时显示 `405x720`。
- 默认 80% 时，上述结果再乘以 `0.8`。

## 8. 数据流

### UI

在尺寸/模板配置区域新增媒体摆放控制：

- 占比：滑杆或步进输入，默认 `80%`。
- 位置：9 宫格按钮，默认中间。
- 说明文案：`按最终视频画布计算 100%`。

UI 返回 payload：

```json
{
  "media_placement": {
    "basis": "canvas",
    "fit": "contain",
    "scale_percent": 80,
    "anchor": "center"
  }
}
```

### API

`VideoGenerateRequest` 新增：

```python
media_placement: Optional[MediaPlacementRequest]
```

如果未传，使用默认 `MediaPlacement()`。这保证旧 API 调用也获得新默认行为，而不是继续走模板私有规则。

### StoryboardConfig

`StoryboardConfig` 新增：

```python
media_placement: MediaPlacement
```

保留 `media_layout_mode` 作为兼容属性，但新渲染路径优先使用 `media_placement`。

### RenderManifest

`RenderManifest` 新增：

```python
media_placement: MediaPlacement
```

`to_dict()` / `from_dict()` 必须持久化该字段，保证 FFmpeg manifest、HyperFrames project、历史任务和诊断文件可复盘同一布局事实。

### TemplateRenderContext

`TemplateRenderContext` 新增：

```python
media_placement: MediaPlacement
```

HyperFramesCompiler 将其投影为 CSS 变量和 data attributes。

### HTMLFrameGenerator

`generate_frame()` 增加可选参数或通过 `ext` 注入标准保留字段：

```text
media_placement_scale
media_placement_anchor
media_placement_fit
media_placement_basis
```

更推荐由 `HTMLFrameGenerator` 直接注入一个标准 CSS 片段，而不是让每个模板重复实现布局计算。

## 9. 标准媒体层

所有图片/视频模板应迁移到统一结构：

```html
<div class="pixelle-media-layer">
  <div class="pixelle-media-box" data-pixelle-media-box>
    <img class="pixelle-media" src="{{image}}" alt="">
  </div>
</div>
```

标准 CSS 由系统注入或由共享片段提供：

```css
.pixelle-media-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.pixelle-media-box {
  position: absolute;
  width: var(--pixelle-media-display-width);
  height: var(--pixelle-media-display-height);
  left: var(--pixelle-media-left);
  top: var(--pixelle-media-top);
}

.pixelle-media {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
```

模板可以继续添加视觉外观，例如阴影、圆角、边框，但不能覆盖：

- `position`
- `left`
- `top`
- `width`
- `height`
- `object-fit`

这些属性归平台媒体摆放契约所有。

## 10. 模板迁移策略

现有模板分三类迁移：

1. 独立 `<img>` 模板：把图片节点迁移到 `.pixelle-media-layer`，保留原模板的背景、标题、装饰。
2. `background-image` 模板：拆成两层，背景装饰仍由模板负责，主图片改为标准媒体层。
3. 全图背景类模板：如果视觉上确实需要全图铺底，声明为模板装饰背景；主图片仍走标准媒体层。若该模板没有主图片概念，则标记为 static 或 decorative-only，不显示媒体摆放控件。

迁移要求：

- 新模板禁止直接使用裸 `{{image}}` 作为背景图或随意 `<img>`。
- 新模板必须使用标准媒体层。
- 模板预览也必须消费同一 `MediaPlacement` 默认值。

## 11. 渲染后端要求

### HTML / Legacy

`TemplateVisualMaterializer` 将 `media_placement` 传给 `HTMLFrameGenerator`。

`HTMLFrameGenerator` 负责：

- 获取最终画布尺寸。
- 获取实际素材尺寸。
- 计算媒体显示盒子的宽高和坐标。
- 注入 CSS 变量。
- 渲染模板。

### HyperFrames

`HyperFramesCompiler` 负责：

- 把 `media_placement` 写入 `index.html`。
- 将 `.visual-clip` 或 `.visual-frame` 映射到标准媒体层规则。
- 确保 HyperFrames 预览和最终 render 与 legacy HTML 结果一致。

### FFmpeg Manifest

如果 FFmpeg manifest 后续直接消费原始 media clip，而不是已经合成好的 template visual，也必须消费 `media_placement`。第一版如果 FFmpeg 路径仍使用已合成帧，可以先只持久化字段，避免产生第二套几何计算。

## 12. UI 细节

控件采用方案 A：

- 一个占比滑杆，默认 `80`。
- 一个 3x3 位置按钮组，默认 center。
- 位置按钮使用图标或紧凑符号，不做大段说明。
- 与“图片尺寸同步到视频”分开显示，避免用户混淆：
  - 同步开关：控制生成图片多大。
  - 占比/位置：控制图片在视频里显示多大、在哪。

建议显示结果摘要：

```text
图片显示：按视频画布 80%，居中
```

## 13. 兼容性

- 旧请求没有 `media_placement`：默认 `80% + center + contain + canvas`。
- 旧模板未迁移：模板 lint 应报告风险；开发阶段可以临时允许 legacy 模板运行，但不应作为验收完成状态。
- `media_layout_mode` 保留读取，但不再作为新能力的事实源。
- `sync_media_size_to_canvas` 继续只影响 `media_width` / `media_height`，不自动改变 `media_placement.scale_percent`。
- 历史任务显示时，如果没有 `media_placement` 字段，使用默认值展示。

## 14. 错误处理

- `scale_percent` 越界时报错，并提示允许范围。
- `anchor` 非法时报错，并列出支持值。
- 读取素材尺寸失败时，使用 `media_width` / `media_height` 作为 fallback，并记录诊断。
- 模板缺少标准媒体层时，模板 lint 报错；运行时至少记录 warning。
- 模板覆盖受保护媒体布局属性时，lint 报错。

## 15. 测试策略

先写失败测试，再实现。

单元测试：

- `MediaPlacement` 默认值为 `canvas/contain/80/center`。
- `scale_percent` 范围校验。
- 9 个 anchor 坐标计算正确。
- 横图、竖图、方图在 `1280x720` 画布下的 100% 和 80% 显示尺寸正确。

集成测试：

- Web 请求 payload 包含 `media_placement`。
- API schema 接受合法 `media_placement` 并拒绝非法值。
- `StoryboardConfig`、`RenderManifest`、`TemplateRenderContext` 都持久化同一份 `media_placement`。
- HTMLFrameGenerator 渲染出的 debug HTML 包含媒体摆放变量。
- HyperFrames 编译产物包含同一媒体摆放变量。
- 模板 lint 能发现裸 `{{image}}`、`background-image: url("{{image}}")`、覆盖标准媒体尺寸/位置等问题。

视觉验证：

- 1280x720 视频，横图 80% center 居中显示，四周露出背景。
- 1280x720 视频，方图 80% center 显示为居中正方形。
- 1280x720 视频，竖图 80% right 显示在右侧且不裁切。
- 切换 9 宫格时，只改变位置，不改变图片显示尺寸。

## 16. 验收标准

- 新任务默认图片显示为按最终视频画布计算的 `80% + 居中`。
- 用户可通过 UI 调整占比和 9 宫格位置。
- 横图、竖图、方图都保持原比例，不裁切。
- `sync_media_size_to_canvas` 只影响生成素材尺寸，不影响显示占比。
- HTML 模板和 HyperFrames 模板消费同一 `MediaPlacement`。
- 所有迁移后的图片模板不再拥有私有图片缩放/定位规则。
- 模板 lint 阻止新模板绕过标准媒体层。
- 自动化测试覆盖几何计算、API/manifest 数据流、模板 lint 和关键渲染产物。

## 17. 实施顺序建议

1. 新增 `MediaPlacement` 模型和几何计算测试。
2. 扩展 API、StoryboardConfig、RenderManifest、TemplateRenderContext 数据通路。
3. 增加 UI 控件和请求构建。
4. 改造 HTMLFrameGenerator 注入标准媒体层变量。
5. 改造 HyperFramesCompiler 使用同一契约。
6. 建立模板 lint。
7. 迁移现有 image/video 模板到标准媒体层。
8. 做视觉回归验证。

这个顺序优先建立事实源和测试，再迁移模板，避免一开始就在大量模板 CSS 里手工改动而失去架构控制。
