# Pixelle Template Text Bridge Contract Design

## 1. 结论

本次设计采用“显式 bridge contract + 单一适配层”的方案，把 `text_rendering` 的样式契约桥接到 HTML 模板链路中，并明确禁止逐模板补丁。

最终原则如下：

- `text_rendering` 继续是文字样式的唯一业务源头
- 新增 `TemplateTextBridgeContract` 作为模板消费的标准文本样式契约
- 新增 `TemplateTextBridgeResolver` 作为唯一桥接层，负责把 `text_rendering` contract 转成模板可消费的标准槽位与 CSS 变量
- `TemplateVisualMaterializer` 只负责注入 bridge contract，不再隐藏模板专用业务规则
- 模板只消费标准命名槽位和 CSS 变量，不再直接理解 `caption_style` / `overlay_style` 这样的上游业务对象

这套方案是“从源头治理”的做法，因为它把 bridge 规则收敛为 domain contract 和单一 resolver，而不是把同一类逻辑散落在 UI、pipeline、materializer 或各个 HTML 模板里。

## 2. 背景

当前 Pixelle 有两条相关但边界不同的文字链路：

1. `text_rendering` 链路已经具备较好的 contract 结构：
   - 前端通过 `text_rendering` 嵌套对象提交参数
   - API schema 有统一入口
   - `TextRenderingOrchestrator` 统一合并默认值、样式 profile 和 overlay policy

2. 模板正文链路仍然是模板内联样式驱动：
   - `TemplateVisualMaterializer` 目前只处理 `title` / `text` / `image` / `template_params`
   - `HTMLFrameGenerator` 只做变量替换
   - 模板中的 `.subtitle`、`.title`、`.author` 等 CSS 规则仍然写死在 HTML 内

这导致一个认知落差：界面上已经有“字幕字体”之类的设置，但模板里的正文文字和副标题并不会自然遵循这套契约，因为它们根本不在同一条 contract 链路里。

## 3. 问题定义

当前问题不是“某个模板字体没生效”这么简单，而是架构边界不统一：

- `text_rendering` 是 contract 驱动
- template body text 是模板本地 CSS 驱动

如果继续逐模板修改 `.subtitle`、`.body` 或 `.title` 的 CSS，让它们分别去贴 `caption_style`，会产生以下问题：

- 规则分散：每个模板都可能各自实现一套继承逻辑
- 语义混乱：有的模板 `{{text}}` 是正文，有的可能是副标题，有的甚至只是装饰性说明，不应该一律等同于字幕
- 回归风险高：一个样式字段变更后，很难保证所有模板都同步理解
- 长期维护成本高：模板数量越多，债务越多

因此，本次设计的目标不是“让模板自动继承字幕字体”，而是建立一个显式、稳定、可测试的 bridge contract。

## 4. 目标

1. 为模板正文/副标题等槽位建立统一文本 bridge contract。
2. 保持 `text_rendering` 为唯一业务样式源头，避免 UI、pipeline、template 各自做一份解释。
3. 让模板链路通过单一 resolver 消费上游文字样式，而不是逐模板写业务判断。
4. 允许不同模板显式声明自己支持哪些文本槽位、哪些槽位参与桥接。
5. 让迁移可渐进进行：未桥接模板保持现状，已桥接模板走标准 contract。

## 5. 非目标

- 本轮不把所有模板一次性迁完。
- 本轮不把所有模板文字都强制继承 `caption_style`。
- 本轮不重构 `HTMLFrameGenerator` 为完整模板引擎。
- 本轮不改变现有 `text_rendering` UI 的交互结构。
- 本轮不顺手做模板主题系统或通用设计 token 平台。

## 6. 备选方案与取舍

### 6.1 方案 A：逐模板补丁

做法：

- 直接修改各个模板中的 `.subtitle` / `.title` / `.body`
- 按模板手写哪些字段映射到 `caption_style`

优点：

- 起步快

缺点：

- 不是源头治理
- 模板越多，分叉越多
- 无法保证语义一致

结论：

- 明确拒绝

### 6.2 方案 B：仅在 materializer 里硬编码注入 CSS

做法：

- 在 `TemplateVisualMaterializer` 里读取 `caption_style`
- 直接拼接一段 `<style>` 或模板参数，强行覆盖若干类名

优点：

- 逻辑比逐模板补丁集中

缺点：

- `TemplateVisualMaterializer` 会同时承担“桥接规则”和“模板渲染注入”两种职责
- 类名覆盖依赖模板内部实现细节
- 模板作者无法从 contract 层知道哪些槽位会继承

结论：

- 不采用；这只是把模板补丁集中到一处，本质仍是隐式规则

### 6.3 方案 C：显式 bridge contract + resolver + materializer 注入

做法：

- 新增 domain contract 表示“模板可消费的文本样式槽位”
- 新增 resolver 统一做业务桥接
- materializer 只负责把 bridge 结果注入模板
- 模板只消费标准槽位和 CSS 变量

优点：

- 源头清晰
- 职责单一
- 可测试
- 可渐进迁移

缺点：

- 首次建设成本高于补丁式方案

结论：

- 采用该方案

## 7. 采用方案

### 7.1 核心边界

各层职责明确如下：

- `TextRenderingOrchestrator`
  - 继续负责解释 `text_rendering`
  - 产出标准 `TextRenderingBuildResult`
  - 不感知具体 HTML 模板类名

- `TemplateTextBridgeResolver`
  - 输入 `TextRenderingBuildResult`
  - 输入模板能力声明
  - 输出 `TemplateTextBridgeContract`
  - 是唯一允许承载“哪个模板槽位绑定哪个 style profile”规则的地方

- `TemplateVisualMaterializer`
  - 输入 bridge contract
  - 把 bridge 数据注入模板
  - 不再直接解释 `caption_style`、`overlay_style`

- HTML 模板
  - 只消费标准命名槽位和 CSS 变量
  - 不直接依赖上游 Python 业务字段名称

### 7.2 新增 domain contract

新增模型建议放在：

- `pixelle_video/models/template_text_bridge.py`

建议定义如下对象：

#### `TemplateTextBridgeContract`

字段建议：

- `slots: dict[str, TemplateTextSlotContract]`
- `css_vars: dict[str, str]`
- `class_tokens: dict[str, tuple[str, ...]]`
- `diagnostics: dict[str, Any]`

用途：

- `slots` 描述模板文本槽位的语义与绑定关系
- `css_vars` 描述模板可直接消费的标准 CSS 变量
- `class_tokens` 允许后续为模板注入稳定 class，而不是依赖模板作者自发命名
- `diagnostics` 用于测试和结果追踪

#### `TemplateTextSlotContract`

字段建议：

- `slot_id`
- `semantic_role`
- `binding_source`
- `style_profile_id`
- `enabled`
- `fallback_behavior`

关键语义：

- `semantic_role` 用于表达 `body` / `subtitle` / `title` / `author` / `footer`
- `binding_source` 用于表达这个槽位来自 `caption_style`、`overlay_style` 还是模板默认值
- `fallback_behavior` 用于表达当上游缺失时，模板该保留默认样式还是禁用桥接

### 7.3 模板能力声明

需要新增或扩展模板能力声明文件，建议优先沿用模板目录下已有元数据文件模式，例如：

- `resources/hyperframes/templates/<template_id>/text_capabilities.json`
- 或 HTML 模板相邻的 `template_text_capabilities.json`

建议字段：

- `bridge_version`
- `supported_slots`
- `slot_bindings`
- `supports_css_vars`
- `supports_class_tokens`

示例语义：

- `supported_slots = ["body", "title", "author", "footer"]`
- `slot_bindings.body = "caption_style"`
- `slot_bindings.title = "template_default"`

这样模板是否参与桥接、参与到什么程度，都由模板显式声明，而不是由 resolver 猜测模板内部类名。

### 7.4 Bridge 变量规范

模板侧不应该直接消费原始 profile 对象，应该消费稳定变量名。

建议第一版标准 CSS 变量包括：

- `--pixelle-text-body-font-family`
- `--pixelle-text-body-font-size`
- `--pixelle-text-body-color`
- `--pixelle-text-body-stroke-color`
- `--pixelle-text-body-stroke-width`
- `--pixelle-text-body-line-limit`

- `--pixelle-text-title-font-family`
- `--pixelle-text-title-font-size`
- `--pixelle-text-title-color`

- `--pixelle-text-author-font-family`
- `--pixelle-text-author-font-size`
- `--pixelle-text-author-color`

命名原则：

- 变量按“槽位语义”命名，不按上游字段名命名
- 这样模板消费的是稳定语义，而不是上游内部实现细节

### 7.5 注入方式

`TemplateVisualMaterializer` 负责把 `TemplateTextBridgeContract` 注入模板，建议通过以下两种形式：

1. `ext` 中增加标准文本 bridge payload
2. 统一注入模板根级 CSS 变量块

推荐优先顺序：

- CSS 变量用于样式
- `ext` 用于少量结构决策或启用标记

不推荐做法：

- 不推荐直接拼接覆盖任意现有类名的散装 CSS
- 不推荐把原始 Python profile dict 原封不动暴露给模板

### 7.6 槽位语义约束

必须明确一条重要规则：

不是所有模板文字都自动等于字幕。

因此需要显式区分：

- `caption_renderer`
  - 程序化字幕渲染链路
  - 继续消费 `caption_style`

- `template_body`
  - 模板正文槽位
  - 可以桥接到 `caption_style`，但这是显式 binding，不是默认推断

- `title` / `author` / `footer`
  - 是否桥接由模板能力声明决定
  - 默认保持模板风格，不自动继承字幕样式

这一约束是为了防止“为了让模板正文跟随字体设置”而错误地把整个模板的所有文本都绑到同一套字幕样式上。

## 8. 数据流

目标数据流如下：

1. 前端提交 `text_rendering`
2. API schema 验证并透传
3. `TextRenderingOrchestrator.build(...)` 产出标准文字样式结果
4. 模板渲染链路读取模板能力声明
5. `TemplateTextBridgeResolver.resolve(...)` 生成 `TemplateTextBridgeContract`
6. `TemplateVisualMaterializer` 把 bridge contract 注入模板
7. 模板通过标准 CSS 变量和槽位配置消费 bridge 结果

这样数据流中的每一层都只做一件事，没有哪一层需要同时承担“业务解释 + 模板细节 + 回退策略”三种职责。

## 9. 迁移策略

### 9.1 第一阶段：搭建 bridge 基础设施

新增：

- `TemplateTextBridgeContract`
- `TemplateTextBridgeResolver`
- 模板能力声明读取逻辑
- `TemplateVisualMaterializer` 注入能力

要求：

- 默认不改变现有模板输出
- 对未声明 bridge 能力的模板，materializer 不做样式注入

### 9.2 第二阶段：迁移代表性模板

优先迁移代表性模板：

- `templates/1920x1080/image_landscape_minimal.html`
- 如需要可再加 `templates/1920x1080/image_landscape_full.html`

迁移方式：

- 把模板中的正文/副标题样式改成消费标准 CSS 变量
- 保持模板视觉结构不变
- 只替换样式来源，不重做版式

### 9.3 第三阶段：收敛 legacy 逻辑

当代表性模板验证通过后：

- 逐步迁移其他适合桥接的模板
- 删除与 bridge 重复的模板局部硬编码
- 把“模板是否支持 text bridge”作为模板契约的一部分沉淀下来

## 10. 风险与控制

### 10.1 风险：模板语义误判

表现：

- 把正文槽位误判成字幕槽位
- 把标题也错误继承为字幕字体

控制：

- 强制模板能力声明显式列出 `supported_slots` 和 `slot_bindings`
- resolver 不根据类名或占位符自动猜测

### 10.2 风险：桥接后破坏模板原有视觉语言

表现：

- 某些模板因直接继承 `caption_style` 而失去既有风格

控制：

- `title` / `author` / `footer` 默认不桥接
- 只为明确声明的槽位注入 bridge

### 10.3 风险：materializer 职责膨胀

表现：

- materializer 再次变成隐式规则中心

控制：

- 业务映射只允许在 resolver 内
- materializer 只接收 bridge 结果并注入

## 11. 测试策略

至少补齐以下测试层级：

### 11.1 Domain / Resolver 测试

- `TemplateTextBridgeResolver` 在不同模板能力声明下的绑定结果
- `caption_style` 到 `template_body` 的变量生成是否稳定
- 缺失字段时的 fallback 行为是否符合 contract

### 11.2 Materializer 测试

- `TemplateVisualMaterializer` 是否正确注入 bridge payload
- 未声明 bridge 能力的模板是否保持现状
- 禁止将原始 profile dict 直接暴露给模板

### 11.3 模板集成测试

- 代表性模板在 bridge 开启后是否消费标准 CSS 变量
- 改变 `text_rendering.caption_style.font_family` 后，桥接模板输出 HTML 是否发生预期变化
- 未桥接模板输出是否不受影响

### 11.4 回归验证

- 程序化字幕链路继续遵循原有 `caption_style`
- overlay / image text policy 行为不因 bridge 功能发生语义漂移

## 12. 落地文件边界建议

预计涉及：

- `pixelle_video/models/template_text_bridge.py`
- `pixelle_video/services/template_text_bridge_resolver.py`
- `pixelle_video/services/template_visual_materializer.py`
- `pixelle_video/models/template_render_context.py`
- `pixelle_video/services/text_rendering_orchestrator.py`
- `pixelle_video/services/frame_html.py`
- `templates/1920x1080/image_landscape_minimal.html`
- `tests/test_template_visual_materializer.py`
- `tests/test_text_rendering_orchestrator.py`
- 新增 resolver 对应测试文件

说明：

- `frame_html.py` 如果只需要透传 `ext` 和标准变量，可以保持轻量，不应演化为业务解释层
- `template_render_context.py` 可以作为统一模板契约的汇聚点，但不应在该 dataclass 内直接写具体模板绑定规则

## 13. 最终判断

“在 template materializer 做桥接，而不是逐模板补丁”这句话本身只有一半是对的。

真正的最佳实践应当是：

- bridge 规则定义在显式 contract 和 resolver 中
- materializer 作为唯一注入层执行该 contract
- 模板只消费稳定变量和命名槽位

只有这样，才算从源头解决问题，而不是把技术债从模板文件搬运到另一个 Python 文件里。
