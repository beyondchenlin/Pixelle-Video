# Layered Template Preview Workbench 设计方案

## 1. 结论

Pixelle 不应把“即时预览区移动到右侧”“图片位置改成数值”“模板库保存参数”“在线添加文字/图片/背景”做成几组独立 UI 补丁。正确方案是新增统一的分层模板源模型，让前端编辑、即时预览、真实预览、保存模板和最终生成全部消费同一份契约。

采用方案：

- 前端维持 Streamlit 为主，不引入高风险自定义 React 应用；使用原生 `st.columns`、`st.container`、`st.segmented_control`、`st.data_editor`、`st.dialog`、`st.popover`、`st.fragment` 和 `st.file_uploader` 组织界面。
- 右侧输出区固定为 `生成视频 -> 即时预览工作台 -> 最近视频`。
- 即时预览工作台顶部新增最近使用的 5 个模板文字快捷列表，点击后回填当前编辑状态。
- 模板制作从单个“添加文字/添加图片/添加背景”升级为可重复添加的图层列表，每个图层都有独立位置、尺寸、层级、透明度、旋转、锁定、素材来源和样式。
- 后端新增 `LayeredTemplateSpec` / `TemplateLayer` 作为模板排版唯一源模型，不继续把模板能力塞进 `template_params`。
- `MediaPlacement` 从 `anchor` 驱动升级为默认中心 + `offset_x` / `offset_y` 数值偏移；旧 `anchor` 只作为兼容输入迁移，不再作为产品能力暴露。
- HTML 截图、HyperFrames compiled、ffmpeg_manifest 都通过 adapter 从同一份 spec 派生，禁止各自维护一套排版逻辑。

这不是最小改动。它的目标是从源头解决“预览和最终生成不一致”“模板库只是静态 HTML 列表”“多图层模板无统一契约”“图片定位规则散落在 UI/模板/CSS/渲染后端”的长期技术债。

## 2. 背景

当前代码已经具备几条相关能力：

- `web/components/output_preview.py` 负责右侧生成视频和最近视频。
- `web/components/text_rendering_config.py` 负责标题/字幕/文字渲染配置，并且当前仍持有即时预览入口。
- `web/components/text_rendering_preview.py` 能构造和渲染标题、字幕、媒体位置的预览 spec。
- `web/components/style_config.py` 负责模板库、输出尺寸、图片显示占比和旧 9 宫格位置选择。
- `pixelle_video/models/media_placement.py` 当前以 `scale_percent + anchor` 表达主媒体位置。
- `render_backend` 已支持 `legacy`、`hyperframes_compiled`、`ffmpeg_manifest`，并通过 `RenderCapabilityResolver` 做后端能力选择和降级。

但当前还缺少一个关键抽象：用户可编辑模板的多图层源模型。现有后端统一的是“视频渲染执行路径”，不是“用户模板排版”。如果直接在 Streamlit 里加控件，再分别改 HTMLFrameGenerator、HyperFrames 和 ffmpeg，就会形成三套布局逻辑，后续必然出现预览正确、导出错误，或某个模板保存后无法复现的问题。

## 3. 目标

1. 把右侧即时预览区移到生成视频和最近视频之间，并让它成为常驻排版工作台。
2. 即时预览必须同步最终视频输出尺寸、素材尺寸、媒体缩放、媒体数值偏移、标题、字幕和模板图层。
3. 模板制作支持多个文字层、多个图片/文件层、多个背景层，而不是每类只能一个。
4. 所有文字、图片、背景图层都能调整位置、尺寸、层级、透明度、旋转和锁定状态。
5. 图片位置默认中心，通过 `offset_x` / `offset_y` 数值调整；移除产品层面的左上、右上、左下、右下等 9 宫格选择。
6. 当前排版参数可保存为“我的模板”，并出现在模板库里供后续选择。
7. 即时预览区展示最近使用的 5 个模板文字列表，便于快速切换。
8. 后端以统一 spec 为源头，避免 HTML screenshot、HyperFrames、ffmpeg_manifest 各自维护排版规则。
9. 兼容旧任务和旧模板数据，但兼容逻辑必须是迁移输入，不是继续扩展旧产品模型。
10. 自动化测试覆盖模型、迁移、预览、模板保存、后端 adapter 和关键 UI payload。

## 4. 非目标

- 不做任意 HTML 在线编辑器。用户编辑结构化图层，不直接写 HTML/CSS。
- 不把多图层模板塞进 `template_params`。
- 不让 Streamlit `session_state` 成为事实源；它只缓存当前编辑会话。
- 不让 ffmpeg_manifest 直接理解复杂模板图层；第一阶段它应消费统一 spec 预渲染后的模板帧或已物化视觉资产。
- 不一次性做完整 Canva 式自由设计器；高级编辑可以作为 `st.dialog` 中的受控图层编辑面板逐步增强。
- 不在每次控件变化时自动触发真实后端渲染；真实预览帧由显式动作触发，并用 fingerprint 缓存。

## 5. 全局设计评审

### Review 1: 前端边界

Streamlit 当前版本为 `1.53.1`，具备足够的原生能力承载这个工作台：

- `st.columns`：维持左/中/右三栏工作流。
- `st.container(border=True)`：组织生成、预览、最近视频、模板卡片和属性面板。
- `st.segmented_control`：用于模板类型、方向和图层类型切换。
- `st.data_editor`：适合做批量图层属性表，但核心交互仍建议用图层列表 + 属性表单，避免用户直接在表格里误改复杂字段。
- `st.dialog`：承载高级编辑，不把中栏撑得过长。
- `st.popover`：承载说明，不污染主工作流。
- `st.fragment`：局部刷新高频组件，例如预览工作台或模板快捷列表。
- `st.file_uploader`：添加图片/文件图层。

因此前端不需要引入新的 SPA。最佳实践是“Streamlit 原生控件管理状态 + 受控 HTML/CSS 只负责预览画布”。HTML 预览不能成为新状态源，也不能让用户注入任意 HTML。

### Review 2: 后端边界

已有 `render_backend` 不能直接承担多图层模板契约。它解决的是“用哪个后端渲染视频”，而不是“模板由哪些层组成、每层位置和样式是什么”。如果继续扩展 `render_backend` 或 `template_params`，会让模板状态、预览状态和生成状态分裂。

正确边界：

```text
LayeredTemplateSpec
  -> Preview HTML adapter
  -> Real preview frame adapter
  -> Template preset storage
  -> HyperFrames adapter
  -> HTMLFrameGenerator adapter
  -> ffmpeg_manifest prerendered visual path
```

`LayeredTemplateSpec` 是源头，adapter 是派生。adapter 可以因后端不同而有实现差异，但不能重新解释用户排版意图。

## 6. 数据模型

### 6.1 LayeredTemplateSpec

新增模块建议：

```text
pixelle_video/models/layered_template.py
```

核心结构：

```python
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
    metadata: Mapping[str, JSONValue]
```

字段规则：

- `version` 第一版为 `layered_template.v1`。
- `template_id` 是稳定 ID，不依赖展示名称。
- `template_type` 继续支持 `static`、`image`、`video`，但图层层面允许 `generated_media` 层表达生成素材。
- `canvas_width` / `canvas_height` 是最终输出画布，不是模板设计坐标。
- `layers` 顺序不作为层级事实源，层级以 `z_index` 为准。
- `metadata` 只放审计和展示信息，不放排版逻辑。

### 6.2 TemplateLayer

```python
LayerType = Literal["text", "image", "background", "generated_media"]

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
    style: Mapping[str, JSONValue]
    role: str | None = None
```

规则：

- `id` 使用稳定 UUID 或 slug，保存模板后不因重命名变化。
- `rect` 使用最终 canvas 坐标，避免模板设计坐标和最终输出坐标混用。
- `opacity` 范围为 `0..1`。
- `rotation` 以度为单位。
- `role` 可选值用于系统识别，如 `title`、`caption`、`main_media`、`brand_badge`、`decorative_background`。
- 标题和字幕也可映射为 `text` layer，但与现有 `text_rendering.title_style` / `caption_style` 的关系必须明确：第一阶段标题/字幕控件继续产生正式文字样式契约，模板 layer 只引用其 role，不复制样式事实源。

### 6.3 RectSpec

```python
@dataclass(frozen=True)
class RectSpec:
    x: float
    y: float
    width: float
    height: float
    unit: Literal["px"] = "px"
```

第一版只开放 `px`，且语义为最终 canvas 像素。百分比可由 UI 层展示换算，但不要进入持久化模型，避免多坐标体系。

### 6.4 MediaPlacement v3

当前 `MediaPlacement` 为 `scale_percent + anchor`。新模型：

```python
@dataclass(frozen=True)
class MediaPlacement:
    basis: Literal["canvas"] = "canvas"
    fit: Literal["contain"] = "contain"
    scale_percent: int = 100
    offset_x: int = 0
    offset_y: int = 0
```

规则：

- 默认中心。
- `offset_x > 0` 向右，`offset_y > 0` 向下。
- `scale_percent` 范围仍为 `10..100`。
- 旧 `anchor` 输入通过迁移函数转换为等价 `offset_x` / `offset_y`。例如旧 `top_left` 在当前 canvas 和媒体显示盒下可迁移为对应负偏移，但 UI 不再显示 anchor。
- 运行时仍接受旧 mapping，立即 normalize 为新 dict 后向下游传递。

## 7. 前端设计

### 7.1 三栏布局

左栏保持导航/素材入口，中栏负责编辑，右栏负责输出和预览。

右栏固定顺序：

```text
生成视频
即时预览工作台
最近视频
```

`render_output_preview(...)` 不应直接内联所有预览逻辑，而应调用新组件：

```text
web/components/layout_preview_workbench.py
```

该组件只消费 `LayeredTemplateSpec` 和必要的 preview state，不直接读取散落的 `session_state` key。

### 7.2 中栏模板库

模板库顶部：

- 搜索框。
- `保存当前为模板`。
- `导入模板`。
- 模板方向 segmented control：竖屏、横屏、方形。
- 模板来源 segmented control：系统模板、我的模板、最近。

模板卡片继续使用 Streamlit grid，但卡片数据来自模板 registry，而不是扫描 HTML 后临时拼 UI。

新增 registry 模块建议：

```text
pixelle_video/services/template_registry.py
pixelle_video/models/template_preset.py
```

### 7.3 在线模板制作

中栏模板制作区：

- `+ 添加文字`
- `+ 添加图片/文件`
- `+ 添加背景`

每次点击都新增一个 layer，而不是覆盖单一字段。

图层管理：

- 左侧图层列表显示名称、类型、role、z_index。
- 右侧属性面板编辑当前 layer。
- 高级编辑放入 `st.dialog`，避免主页面过长。

图层属性：

- `x`
- `y`
- `width`
- `height`
- `z_index`
- `opacity`
- `rotation`
- `locked`
- `source`
- `style`

图片/文件层使用 `st.file_uploader` 或素材库引用，保存模板时持久化为 artifact/storage key，不保存临时上传对象。

### 7.4 即时预览工作台

位置：右栏生成视频下方、最近视频上方。

内容：

- 最近 5 个模板文字快捷列表。
- 当前画布尺寸、素材尺寸、图层数量、渲染模式摘要。
- 受控 HTML/CSS 缩放预览画布。
- `刷新真实帧` 按钮。
- `保存为我的模板` 按钮。

最近 5 个模板：

- 来源为本地 template preset usage history。
- 展示模板名称、方向、最近使用时间。
- 点击后用 preset 回填当前 `LayeredTemplateSpec`。
- 当前模板高亮。

即时预览渲染规则：

- HTML 只由系统从 spec 生成。
- 不能执行用户自定义脚本。
- 不持久化 preview-only 文本、占位图、缩放 CSS。
- 画布按最终 canvas aspect ratio 缩放显示。

## 8. 后端设计

### 8.1 LayeredTemplateService

新增服务：

```text
pixelle_video/services/layered_template_service.py
```

职责：

- validate `LayeredTemplateSpec`。
- normalize legacy media placement。
- build preview HTML。
- build real preview frame request。
- materialize template preset thumbnail。
- compile spec into backend-specific render input。

### 8.2 TemplatePresetRepository

新增 repository：

```text
pixelle_video/repositories/template_presets.py
```

存储位置第一版建议：

```text
data/template_presets/
  presets.json
  thumbnails/
  assets/
```

`presets.json` 保存：

- preset id
- name
- template type
- orientation
- spec
- thumbnail path/storage key
- created_at
- updated_at
- last_used_at
- source: `system` 或 `user`

系统模板仍可来自仓库模板，但进入 UI 时统一包装成 `TemplatePreset`，避免系统模板和用户模板走两套 UI 数据结构。

### 8.3 渲染 adapter

新增 adapter 边界：

```text
pixelle_video/services/layered_template_adapters/
  html_preview.py
  html_frame.py
  hyperframes.py
  ffmpeg_manifest.py
```

职责：

- `html_preview.py`：生成 Streamlit 即时预览 HTML。
- `html_frame.py`：生成 HTMLFrameGenerator 可消费的标准 HTML 或上下文。
- `hyperframes.py`：把 spec 编译为 HyperFrames template/context。
- `ffmpeg_manifest.py`：消费已物化的模板帧或视觉资产，不直接解释复杂图层。

adapter 禁止直接读取 Streamlit session。所有输入必须来自 spec。

### 8.4 真实预览帧

真实预览帧继续使用显式触发：

```text
LayeredTemplateSpec
  -> fingerprint
  -> LayeredTemplateService.render_preview_frame(...)
  -> object store / local artifact
```

缓存规则：

- 相同 fingerprint 复用。
- spec 变化后旧真实帧标记为过期。
- 真实帧失败时保留即时预览，并展示错误原因。

### 8.5 与 text_rendering 的关系

标题和字幕属性已经进入 `text_rendering` 体系。分层模板不能复制这套事实源。

第一阶段规则：

- 标题 layer 可用 `role="title"` 引用当前 `title_style`。
- 字幕 layer 可用 `role="caption"` 引用当前 `caption_style`。
- layer 的 rect 决定排版区域，文字样式仍来自 `text_rendering`。
- 如果用户添加普通文字层，才使用该 layer 自己的 text style。

这样可以避免“标题样式在 text_rendering 一份、模板 layer 又一份”的双事实源。

## 9. 数据流

```text
Streamlit controls
  -> EditorSessionState
  -> LayeredTemplateSpecBuilder
  -> LayeredTemplateSpec
  -> LayoutPreviewWorkbench
  -> Save TemplatePreset
  -> Build generation request
  -> Render backend adapters
```

关键规则：

- `session_state` 只是编辑缓存。
- `LayeredTemplateSpecBuilder` 负责把 UI 控件状态归一化。
- `LayeredTemplateSpec` 是预览、保存、生成的共同输入。
- 生成请求中携带 normalized spec 或引用 preset id + resolved spec snapshot。
- 历史任务保存 spec snapshot，保证未来模板被修改后仍可复现旧任务。

## 10. 兼容和迁移

### 10.1 旧 MediaPlacement

旧 payload：

```json
{
  "scale_percent": 80,
  "anchor": "top_right"
}
```

迁移为：

```json
{
  "scale_percent": 80,
  "offset_x": 0,
  "offset_y": 0
}
```

具体 offset 按 canvas、source media 和 scale 计算。迁移函数必须可测试，并且只在输入 normalize 阶段使用。UI 不再展示旧 anchor。

### 10.2 旧模板

旧 HTML 模板继续可选，但进入新模板库时需要包装成系统 preset。无法表达图层的模板第一阶段可标记为 `legacy_html` source，并限制在线编辑能力：

- 可预览。
- 可选择。
- 可保存当前排版参数为新的 layered preset。
- 不允许直接编辑旧模板内部 HTML。

### 10.3 旧任务

旧任务没有 `LayeredTemplateSpec` 时：

- 使用旧 `frame_template`、`template_params`、`media_placement` 构造兼容 spec。
- 如果无法完整还原图层，历史详情标注为 legacy snapshot。
- 不因缺少新 spec 阻断历史播放或下载。

## 11. 错误处理

- layer id 重复：validate 失败。
- layer rect 非法：validate 失败，明确指出 layer id 和字段。
- opacity 越界：validate 失败。
- z_index 重复：允许，但渲染按 `z_index` 后再按 layer 顺序稳定排序。
- 上传素材丢失：预览显示缺失状态，保存模板失败并提示重新选择素材。
- preset thumbnail 生成失败：保存模板失败，不产生半成品 preset。
- backend adapter 不支持某 layer 类型：返回明确能力错误，不能静默忽略 layer。
- ffmpeg_manifest 无法直接消费多图层：必须走预渲染视觉资产路径。

## 12. 测试方案

### 12.1 模型测试

- `LayeredTemplateSpec` 能序列化和反序列化。
- `TemplateLayer` 校验 layer type、rect、opacity、z_index。
- `MediaPlacement` 默认中心 + offset 为 0。
- 旧 anchor mapping 可迁移为新 offset。
- spec fingerprint 对影响视觉的字段敏感，对非视觉 metadata 不敏感。

### 12.2 前端构建测试

- Streamlit 控件状态能构建出完整 `LayeredTemplateSpec`。
- 多次添加文字/图片/背景会新增不同 layer id。
- 删除 layer 后不会留下孤立 selected layer。
- 保存模板只持久化 spec，不持久化 preview-only 字段。
- 最近 5 个模板按 last_used_at 排序。

### 12.3 预览测试

- 即时预览 HTML 消费 spec，不直接读取散落 session key。
- 画布 aspect ratio 与 canvas 一致。
- 多图层按 z_index 渲染。
- `role="title"` 使用 `title_style`。
- `role="caption"` 使用 `caption_style`。
- 图片层使用 rect 和 object-fit 规则。
- 真实预览 fingerprint 一致时复用缓存。
- spec 变化后真实预览状态标记为过期。

### 12.4 后端 adapter 测试

- HTML preview adapter 输出安全 HTML，不包含用户脚本。
- HTMLFrameGenerator adapter 能消费同一 spec。
- HyperFrames adapter 生成的 context 包含相同 layer 几何信息。
- ffmpeg_manifest adapter 对多图层 spec 选择预渲染视觉资产路径。
- 不支持的 layer type 明确失败。

### 12.5 集成测试

- `build_single_generation_request(...)` 包含 normalized layered template payload 或 preset snapshot。
- 保存“我的模板”后模板库能列出并回填。
- 最近 5 个模板在切换模板后更新。
- 预览和生成请求使用同一份 normalized spec。
- 旧 `anchor` payload 仍可生成，但 UI 返回新 offset payload。

## 13. 实施顺序

1. 新增 `MediaPlacement` offset 模型和 legacy anchor normalize 测试。
2. 新增 `LayeredTemplateSpec`、`TemplateLayer`、`RectSpec` 和 fingerprint。
3. 新增 `LayeredTemplateSpecBuilder`，从现有模板、尺寸、文字样式和媒体设置构建 spec。
4. 抽出 `LayoutPreviewWorkbench`，放入右侧生成视频和最近视频之间。
5. 把现有即时预览从 `text_rendering_config` 中解耦，改为右侧 workbench 消费 spec。
6. 新增最近 5 个模板 usage history 和快捷切换。
7. 新增模板 preset repository，支持保存当前为“我的模板”和缩略图。
8. 新增多图层编辑 UI：图层列表、添加文字、添加图片/文件、添加背景、属性面板。
9. 新增后端 adapter，先覆盖即时 HTML preview 和真实预览帧。
10. 接入生成请求，确保生成路径使用同一份 spec snapshot。
11. 扩展 HyperFrames 和 ffmpeg_manifest adapter，并补齐能力降级错误。
12. 做模板库和旧模板兼容迁移。

## 14. 风险和缓解

### 风险 1：Streamlit 页面变得过长

缓解：主页面只保留常用属性；高级编辑放入 `st.dialog`；说明放入 `st.popover`；预览区放右侧常驻。

### 风险 2：预览和导出再次分叉

缓解：所有预览和导出都从 `LayeredTemplateSpec` 派生；禁止 adapter 读取 session；测试覆盖同一 spec 到不同 adapter 的几何一致性。

### 风险 3：`template_params` 继续膨胀

缓解：模板排版字段不进入 `template_params`；`template_params` 只保留旧模板自定义参数或非布局参数。

### 风险 4：ffmpeg_manifest 无法表达复杂图层

缓解：第一阶段让 ffmpeg_manifest 消费预渲染视觉资产；不强迫 ffmpeg 直接实现复杂图层布局。

### 风险 5：旧模板无法完整在线编辑

缓解：旧模板先包装为 legacy preset，可选择和预览；用户保存当前排版时生成新的 layered preset，而不是修改旧 HTML。

## 15. 验收标准

1. 右侧输出区顺序为 `生成视频 -> 即时预览工作台 -> 最近视频`。
2. 即时预览工作台展示当前画布、素材、标题、字幕、媒体位置和多图层排版。
3. 即时预览工作台顶部展示最近使用的 5 个模板文字快捷列表。
4. 图片位置 UI 不再显示 9 宫格，默认中心，通过 X/Y 数值偏移调整。
5. 用户可以多次添加文字、图片/文件和背景层。
6. 每个图层都能编辑位置、尺寸、层级、透明度、旋转和锁定。
7. 当前配置可以保存为“我的模板”，并在模板库中出现。
8. 点击“我的模板”能回填完整排版 spec。
9. 预览、保存模板和生成请求使用同一份 normalized `LayeredTemplateSpec`。
10. 旧 anchor payload 可被兼容迁移，但新 UI 和新 payload 使用 offset。
11. HTML preview、真实预览帧、HyperFrames 和 ffmpeg_manifest 路径不各自维护独立排版事实源。
12. 自动化测试覆盖模型、迁移、前端 spec builder、预览、模板保存、最近模板和渲染 adapter。

