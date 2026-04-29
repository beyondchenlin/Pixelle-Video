# Title Style Text Rendering 设计方案

## 1. 结论

Pixelle 不应该只在前端表单里临时增加一组“标题样式”字段，也不应该把标题样式塞进模板私有参数。标题样式必须上升为 `text_rendering` 体系中的正式契约，与现有 `caption_style`、`overlay_style` 并列，由 UI、API schema、orchestrator、render package、模板编译器和模板默认值共同消费。

采用方案：

- 在 `text_rendering` 下新增正式字段 `title_style`。
- `title_style` 直接复用现有 `TextStyleProfileRequest` / `TextStyleProfile` 结构，不再复制一套标题专用 schema。
- 前端在 `文字渲染` 折叠区内新增 `字幕样式` / `标题样式` 双 tab，但 tab 只切换样式表单，不影响文字层和图中文字策略等全局区块。
- 标题继续作为模板主标题渲染，不改造成 text cue，不参加时间轴切换。
- 带 `title_region` 的模板为 `title_style` 提供默认 preset，模板视觉默认值成为标题样式的 source of truth。
- `title_style` 的字段集与字幕样式保持一致，包含背景颜色和背景不透明度。
- 无标题区的模板允许安全忽略 `title_style`，旧请求不传 `title_style` 时稳定回落到模板默认。

这不是最小改动。它的目标是从源头建立“标题文字样式”这条正式链路，避免继续在模板 CSS、前端 session state 或单个 pipeline 里打补丁。

## 2. 背景

当前项目的文字渲染已经有两套正式样式能力：

- `caption_style`：控制字幕样式。
- `overlay_style`：控制关键词/叠加文字样式。

现状问题在于主标题仍然游离在体系之外：

- 模板里的标题通过 `__TITLE__` 或 `manifest.title` 注入纯文本。
- 标题的字体、字号、颜色、背景和位置主要写死在模板 CSS 中。
- 前端 `文字渲染` 面板只有 `字幕样式`，用户无法直接控制主标题。
- 如果只在前端增加标题字段而不进入正式契约，标题样式会变成“看起来可配、实际上没有统一落点”的半成品功能。

同时，这次需求已经明确了一个重要产品原则：

- 标题样式字段要和字幕样式尽量一致。
- 标题样式必须支持背景颜色和背景不透明度。
- UI 上希望在 `文字渲染` 下通过双 tab 切换 `字幕样式` 与 `标题样式`。

因此，本次设计的关键不只是“前端多一个 tab”，而是让标题文字进入现有文字样式体系，成为长期可维护的正式能力。

## 3. 目标

1. 为主标题建立正式的 `title_style` 契约，而不是模板私有参数。
2. 让 `title_style` 与 `caption_style` 使用同一套字段结构和清洗逻辑。
3. 在前端 `文字渲染` 区域提供 `字幕样式` / `标题样式` 双 tab 操作体验。
4. 支持标题背景颜色和背景不透明度，并与字幕字段口径一致。
5. 保持标题仍然是模板主标题，不引入不必要的 cue/timeline 复杂度。
6. 让模板默认标题样式集中在模板能力层，避免前端、schema、模板 CSS 各自维护一份默认值。
7. 让 `standard`、`asset_based`、历史任务复盘和 HyperFrames 编译链路消费同一份标题样式事实源。
8. 保证旧请求、无标题模板和未传 `title_style` 的场景都能稳定兼容。

## 4. 非目标

- 不把主标题改造成 `TextCue` 或加入 text timeline。
- 不新增一套 `TitleStyleRequest` / `TitleStyleProfile` 专用模型。
- 不把 `title_style` 放进 `template_params`。
- 不让每个模板自行定义私有标题参数，例如 `title_font_size`、`headline_box_color`。
- 不把前端 `演示` 文本持久化到 API 请求或渲染产物。
- 不要求第一版把所有模板的标题表现完全视觉统一；模板仍可保留各自的标题区域结构和装饰。

## 5. 两次设计评审结论

### Review 1: 契约边界

前端 UI 只是入口，不是事实源。如果只做双 tab 表单而不建立 `title_style` 契约，那么标题样式就会退化成模板局部参数或 UI 假配置。

正确边界：

```text
text_rendering.caption_style
  -> 字幕文字样式

text_rendering.title_style
  -> 模板主标题样式

text_rendering.overlay_style
  -> 叠加文字样式
```

### Review 2: 技术债风险

拒绝三个看似简单但会留下技术债的方案：

1. 只在前端复制一套标题字段，但后端不接正式契约。这样 UI 与实际渲染会分叉。
2. 把标题样式塞进 `template_params`。这样标题能力会变成模板私有能力，平台无法统一验证。
3. 把标题也改造成 cue。这样会把“常驻主标题”错误地拉进时间轴和 track 系统，复杂度明显过高。

最终选择：标题继续是模板主标题，但其样式进入统一文字样式契约，作为正式的 `title_style` 长期维护。

## 6. 新增契约

### 6.1 API schema

文件：

```text
api/schemas/text_rendering.py
```

在 `TextRenderingRequest` 中新增：

```python
title_style: Optional[TextStyleProfileRequest] = None
```

`title_style` 复用 `TextStyleProfileRequest`，与 `caption_style` 共用字段：

- `font_family`
- `font_file`
- `font_size`
- `primary_color`
- `stroke_color`
- `stroke_width`
- `background_color`
- `background_opacity`
- `position`
- `margin_y`
- `max_chars_per_line`

第一版不新增标题专属字段，避免在 schema 层复制结构并造成长期漂移。

### 6.2 样式 profile

文件：

```text
pixelle_video/models/text_style.py
```

新增默认 style id：

```python
DEFAULT_TITLE_STYLE_ID = "title-default"
```

`build_default_text_style_profiles(...)` 从返回两套 profile 扩展为三套：

- `caption-default`
- `title-default`
- `overlay-default`

`title-default` 的字段结构仍然是 `TextStyleProfile`，但默认值不再写死为通用字幕风格，而是由模板 preset 决定。

## 7. 模板默认值与 Source of Truth

### 7.1 原则

标题默认值不能同时散落在三个地方：

- 前端常量
- API/schema 默认值
- 模板 CSS

正确的 source of truth 是：

```text
模板能力层 preset
  -> orchestrator 构造默认 title_style
  -> 前端读取并展示
  -> 编译器将 profile 投影成模板 CSS 变量
```

### 7.2 模板能力声明

为每个带 `title_region` 的模板声明标题默认样式 preset，并把它们集中放在新的 Python 注册表模块中：

```text
pixelle_video/models/template_text_style_presets.py
```

该模块作为标题视觉默认值的唯一事实源，负责按 `template_id` 返回标题 preset。前端、orchestrator 和编译器都只从这里读取，不允许再分别维护副本。

每个模板至少声明：

- 是否存在 `title_region`
- 标题默认 `font_family`
- 标题默认 `font_size`
- 标题默认 `primary_color`
- 标题默认 `stroke_color`
- 标题默认 `stroke_width`
- 标题默认 `background_color`
- 标题默认 `background_opacity`
- 标题默认 `position`
- 标题默认 `margin_y`
- 标题默认 `max_chars_per_line`

示例原则：

- `image_landscape_minimal`：左上小标题块，默认有白色半透明背景。
- `image_default`：居中标题卡片，保留卡片视觉语言。
- `image_landscape_full`：上方大标题带，允许保留描边/阴影风格。
- `image_life_insights_light`：居中大标题，沿用暖色纸感模板的标题基调。

### 7.3 前端默认值读取

前端 `title_style` 默认值不自己发明，而是从当前模板 preset seed 到 session state。

行为规则：

- 第一次进入或切换模板时，如果用户未改过标题字段，则按模板 preset 初始化。
- 一旦用户手动修改过 `title_style_*` session key，就不再因模板重绘被覆盖。
- `caption_style` 继续沿用现有默认值逻辑，不被 `title_style` 影响。

## 8. 前端交互设计

文件：

```text
web/components/text_rendering_config.py
```

### 8.1 区块结构

`文字渲染` 折叠区内调整为：

1. 样式 tab 区
   - `字幕样式`
   - `标题样式`
2. 固定全局区块
   - `文字层` / 关键词叠加设置
   - `图中文字策略`

tab 只负责切换样式编辑区，不复制全局设置区块。

### 8.2 样式表单

`标题样式` 复用现有 `_render_text_style_controls(...)`，新增前缀：

```python
"title_style"
```

并新增标题默认值来源，而不是复制一份新的标题表单组件。

字段集与字幕一致：

- 字体
- 字号
- 文字颜色
- 描边颜色
- 描边宽度
- 背景颜色
- 背景不透明度
- 位置
- 垂直边距
- 每行最多字符数

额外增加前端本地预览字段：

- `演示`

该字段只用于前端预览，不写入 payload。

### 8.3 Payload 规则

`build_text_rendering_payload(...)` 新增可选参数：

```python
title_style: dict | None = None
```

清洗规则与 `caption_style` 一致：

- 去掉 `None`
- 清理空字符串字体字段
- `max_chars_per_line <= 0` 视为未设置
- `background_opacity` 转为 float

输出示例：

```json
{
  "overlay": {"enabled": false},
  "image_text": {
    "suppress_embedded_text": false,
    "positive_prompt": "..."
  },
  "caption_style": {
    "font_size": 42
  },
  "title_style": {
    "font_size": 76,
    "background_color": "#FFFFFF",
    "background_opacity": 0.92,
    "position": "top_left",
    "max_chars_per_line": 8
  }
}
```

## 9. Orchestrator 与共享契约链路

文件：

```text
pixelle_video/services/text_rendering_orchestrator.py
pixelle_video/services/text_rendering_contract_summary.py
pixelle_video/pipelines/standard.py
pixelle_video/pipelines/asset_based.py
```

### 9.1 构造规则

`TextRenderingOrchestrator.build(...)` 新增标题 profile 构造：

```python
title_style = _profile_from_request(
    style_id=DEFAULT_TITLE_STYLE_ID,
    data=_mapping_or_none(request.get("title_style")),
    config=config,
    template_id=template_id,
)
```

其中 `template_id` 成为显式输入，不能再依赖调用方在外部偷偷拼默认标题样式。`title_style` 与现有字号修复后的 `caption_style` 一样，`scale_basis_width` / `scale_basis_height` 都必须来自当前任务画布，而不是写死值。

合并顺序必须明确为：

```text
模板 title preset
  -> 平台级默认补足
  -> 用户 title_style 覆盖
```

### 9.2 package 输出

`text_style_profiles` 由两套扩展为三套：

- `caption_style`
- `title_style`
- `overlay_style`

`TextRenderingBuildResult` 也新增：

```python
title_style: TextStyleProfile
```

### 9.3 共享路径一致性

`standard` 和 `asset_based` 都必须通过同一个 orchestrator 构建 `title_style`，禁止某条路径自己拼默认标题样式。

这和之前字幕字号修复的经验一致：任何“只在某个 pipeline 手动补字段”的方案都会再次形成分叉。

## 10. 模板编译与渲染

文件：

```text
pixelle_video/services/hyperframes_compiler.py
pixelle_video/models/template_render_context.py
resources/hyperframes/templates/*/index.template.html
```

### 10.1 TemplateRenderContext

`TemplateRenderContext` 新增一个显式字段，用于主标题样式：

```python
title_style_profile: TextStyleProfile | None = None
```

这样模板编译器不需要从 `text_style_profiles` 全量列表里猜哪个是标题 profile。

### 10.2 编译器职责

`HyperFramesCompiler` 为模板主标题生成一组独立 CSS 变量，例如：

- `--title-fill`
- `--title-stroke-color`
- `--title-stroke-width`
- `--title-background`
- `--title-font-family`
- `--title-font-size`
- `--title-font-weight`
- `--title-line-height`
- `--title-max-width`
- `--title-margin-y`

这些变量来自 `title_style_profile`，并按最终 `canvas_width` / `canvas_height` 做一致缩放。

`position` 的语义也要明确：`title_style.position` 仍然接受和字幕一致的枚举值，但它作用于模板声明的 `title_region`，不是直接把标题移动到整张画布任意位置。实现上应由模板能力层把这些值映射到标题区域内的锚点布局，避免标题跑到字幕区或页脚区。

### 10.3 模板消费方式

带 `title_region` 的模板统一改为通过 CSS 变量消费主标题样式，而不是继续把关键值写死在模板 CSS 中。

例如模板中的标题元素不再只写：

```html
<div class="title">__TITLE__</div>
```

还需要通过编译器注入的变量消费样式，例如：

```css
.title {
  color: var(--title-fill);
  font-family: var(--title-font-family);
  font-size: var(--title-font-size);
  -webkit-text-stroke: var(--title-stroke-width) var(--title-stroke-color);
  background: var(--title-background);
}
```

### 10.4 换行规则

标题不进入 cue 系统，但 `max_chars_per_line` 仍然生效，用于主标题排版。第一版采用和字幕一致的简单文本折行策略即可，不引入额外标题专用排版引擎。

### 10.5 无标题模板

若模板没有 `title_region`：

- 可以不消费 `title_style_profile`
- 编译器不得报错
- `title_style` 仍可在 contract 中存在，但会被安全忽略

## 11. HTMLFrameGenerator 与旧模板兼容

文件：

```text
pixelle_video/services/frame_html.py
```

如果某些旧 HTML 模板仍使用 `HTMLFrameGenerator` 直接通过 `{{ title }}` 注入主标题，而不是 HyperFrames compiled 模板，则第一版兼容策略如下：

- 允许 `ext` 中新增内部保留字段，例如 `pixelle_title_style`
- 由渲染器内部把 `title_style_profile` 投影成旧模板可消费的结构
- 外部调用方不得直接通过 `template_params` 传标题样式

这是一条兼容桥，不是新的长期事实源。长期目标仍然是统一迁移到标准模板能力层和编译器注入。

## 12. 兼容性与错误处理

### 12.1 旧请求

旧请求未传 `title_style` 时：

- 请求继续合法
- 系统使用当前模板的标题默认 preset

### 12.2 未知字段

`title_style` 与 `caption_style` 一样，继续依赖 `TextStyleProfileRequest(extra="forbid")`：

- 未知字段直接返回清晰错误
- 不静默吞掉

### 12.3 非法值

- 颜色值不合法：直接校验失败
- `font_size` 超范围：直接校验失败
- `background_opacity` 不在 `0..1`：直接校验失败
- `max_chars_per_line <= 0`：前端 payload 清洗时视为未设置

### 12.4 模板缺少标题能力

若模板声明有 `title_region` 但未提供标题 preset：

- 视为模板能力缺失
- 在测试和 lint 层失败
- 不允许上线后靠运行时静默回退掩盖问题

## 13. 测试方案

### 13.1 API / schema

新增测试覆盖：

- `TextRenderingRequest` 接受 `title_style`
- `title_style` 字段集与 `caption_style` 同构
- 未知 `title_style` 字段被拒绝

### 13.2 前端 UI

新增测试覆盖：

- `文字渲染` 中存在双 tab
- `title_style` 使用同一个 shared control renderer
- `标题样式` 包含背景颜色和背景不透明度
- `build_text_rendering_payload(...)` 会保留 `title_style`
- `演示` 字段不进入 payload
- 标题 session key 与字幕 session key 不串台

### 13.3 Orchestrator / contract

新增测试覆盖：

- 未传 `title_style` 时，返回模板 preset 默认值
- 传入 `title_style` 后能正确覆盖默认值
- `standard` 路径与 `asset_based` 路径都能拿到同样的 `title_style`
- `text_style_profiles` 中稳定包含 `title-default`

### 13.4 模板编译

新增测试覆盖：

- 至少一个带标题背景块的模板能把 `title_style` 写入生成 HTML
- 至少一个无标题模板传入 `title_style` 时不会报错
- `max_chars_per_line` 对标题折行生效

### 13.5 模板能力 lint

新增测试/校验规则：

- 带 `title_region` 的模板必须声明标题 preset
- 模板标题 CSS 不允许再把核心标题属性完全写死而绕开变量注入

## 14. 实施顺序

1. 扩展 `TextRenderingRequest`、`TextStyleProfile` 默认 profile 和 orchestrator，建立 `title_style` 契约。
2. 为模板能力层增加 `title_region` 对应的标题默认 preset。
3. 扩展前端 `文字渲染` 组件，新增双 tab 和 `title_style` payload。
4. 扩展 `TemplateRenderContext` 与 `HyperFramesCompiler`，让模板主标题消费 `title_style_profile`。
5. 调整带标题的模板，把主标题改为消费 CSS 变量。
6. 补齐 API、UI、orchestrator、模板编译与模板能力 lint 测试。

## 15. 风险与缓解

### 风险 1：标题默认值仍然出现多份副本

缓解：

- 明确模板 preset 为视觉默认值 source of truth
- 前端只读取 preset，不自己发明标题默认值

### 风险 2：某些模板继续绕过变量注入

缓解：

- 为带 `title_region` 的模板增加 lint/测试要求
- 把“标题关键样式必须消费变量”写成显式验收标准

### 风险 3：`title_style` 和 `caption_style` 后续字段漂移

缓解：

- 复用同一套 `TextStyleProfileRequest` / `TextStyleProfile`
- 复用同一个前端 shared control renderer

### 风险 4：旧请求或无标题模板回归

缓解：

- 明确旧请求可回退模板默认
- 明确无标题模板允许安全忽略 `title_style`

## 16. 验收标准

满足以下条件时视为本设计完成：

1. API 可接受 `text_rendering.title_style`，并与字幕样式共享字段结构。
2. 前端 `文字渲染` 中可以通过双 tab 分别配置字幕样式和标题样式。
3. 标题样式支持背景颜色和背景不透明度。
4. 标题样式默认值来自模板 preset，而不是前端或模板 CSS 的重复副本。
5. 标题仍作为模板主标题渲染，不进入 cue/timeline 体系。
6. `standard` 和 `asset_based` 两条共享路径拿到相同的 `title_style` 构建结果。
7. 至少一个带标题模板能在最终生成 HTML 中体现 `title_style`。
8. 旧请求和无标题模板场景保持兼容。
