# Pixelle HyperFrames 横屏 B/D 模板设计

> 2026-04-27 命名修订：为避免复用既有 `image_full.html` 入口造成语义漂移，`B` 方向的最终模板 id 与普通模板入口统一调整为 `image_landscape_full`。本文后续若仍出现 `image_full`，均应以 `image_landscape_full` 为准；既有 `templates/1920x1080/image_full.html` 继续保留 legacy 语义，在 `HyperFrames Compiled` 下不再作为新增横屏 B 模板入口。

## 1. 结论

本次设计为 Pixelle 的 `HyperFrames Compiled` 路径补齐两个横屏原生模板，并保持和现有模板库的选择链路一致：

- `B` 方向采用现有横屏大图模板入口 `1920x1080/image_full.html`
- `D` 方向新增横屏极简模板入口 `1920x1080/image_landscape_minimal.html`
- `HyperFrames Compiled` 原生模板目录分别为：
  - `resources/hyperframes/templates/image_full`
  - `resources/hyperframes/templates/image_landscape_minimal`

最终视觉规则已经确认如下：

- 横屏字幕必须抬高，不能再贴页脚
- 字幕后面不带背景块
- `作者 / 品牌 / 描述` 必须收纳到左下角或右下角，不能放在字幕正下方
- `B` 使用白字 + 深描边 / 阴影
- `D` 使用深色字 + 轻阴影

本次不调整渲染后端架构，不新增新的后端选择项，不改模板选择链路规则，只补齐横屏模板资产与验证覆盖。

## 2. 背景

当前 `HyperFrames Compiled` 原生模板只覆盖竖屏的少量 `image_*` 模板，横屏 `1920x1080` 没有对应原生模板，因此当用户在横屏模板库中选择某些样式时，`HyperFrames Compiled` 会因为找不到同名原生模板目录而回退到 `legacy`。

现有普通模板库中已经有一组横屏入口：

- `templates/1920x1080/image_book.html`
- `templates/1920x1080/image_film.html`
- `templates/1920x1080/image_full.html`
- `templates/1920x1080/image_ultrawide_minimal.html`
- `templates/1920x1080/image_wide_darktech.html`

本轮用户确认优先补齐两种横屏方向：

- `B`: 大图全铺型
- `D`: 高级白空间

同时，用户对字幕提出了明确反馈：

- 现有横屏理解里字幕太小
- 字幕位置太靠下
- 署名信息不能挂在字幕正下方
- 字幕不能带背景块

因此本设计不仅要补齐模板目录，还要把字幕和署名信息的层级关系做成显式约束。

## 3. 目标

1. 让 `HyperFrames Compiled` 在横屏下支持 `image_full` 和 `image_landscape_minimal` 两个模板。
2. 保持现有模板选择链路不变，继续由 `frame_template` 的文件名 stem 自动映射到 HyperFrames 原生模板目录。
3. 让横屏字幕在结构上具备足够的可读性：更大、更高、与页脚分离。
4. 让 `作者 / 品牌 / 描述` 成为角落信息组，而不是字幕下挂信息。
5. 在不扩大架构改动范围的前提下，为后续继续扩展横屏模板留出统一模式。

## 4. 非目标

- 不在本轮把所有 `1920x1080` 模板都迁移为 HyperFrames 原生模板。
- 不修改 `RenderBackend` 选择器，不新增新的后端枚举。
- 不改造 `frame_template -> template_id` 的映射规则。
- 不做像素级截图回归基线。
- 不在本轮处理更大范围的模板库重构、参数化主题系统或模板底座复用系统。

## 5. 采用方案

采用“两个独立横屏模板成对补齐”的方案，而不是“一个底座模板 + 参数切主题”。

理由如下：

- 当前管线天然要求 `frame_template` 的 stem 与原生模板目录名一致。
- 两个模板直接独立实现，风险最低，和现有回退逻辑最兼容。
- `B` 与 `D` 在字幕策略、信息角落策略、留白比例上差异明显，硬塞进同一个底座模板会引入不必要的参数复杂度。
- 这次用户已经确认的是两个清晰风格方向，独立模板更利于后续精修。

## 6. 文件结构

### 6.1 普通模板入口

- 保留：`templates/1920x1080/image_full.html`
- 新增：`templates/1920x1080/image_landscape_minimal.html`

说明：

- `image_full.html` 继续作为 `B` 的用户入口
- `image_landscape_minimal.html` 作为 `D` 的用户入口
- UI 模板库依旧通过文件系统发现模板，无需新增专门注册表

### 6.2 HyperFrames Compiled 原生模板目录

新增或补齐以下目录与文件：

- `resources/hyperframes/templates/image_full/index.template.html`
- `resources/hyperframes/templates/image_full/compositions/captions.template.html`
- `resources/hyperframes/templates/image_full/compositions/text_layer.template.html`
- `resources/hyperframes/templates/image_full/text_capabilities.json`

- `resources/hyperframes/templates/image_landscape_minimal/index.template.html`
- `resources/hyperframes/templates/image_landscape_minimal/compositions/captions.template.html`
- `resources/hyperframes/templates/image_landscape_minimal/compositions/text_layer.template.html`
- `resources/hyperframes/templates/image_landscape_minimal/text_capabilities.json`

### 6.3 测试文件

本轮至少需要修改或补充：

- `tests/test_hyperframes_compiler.py`
- `tests/test_standard_pipeline_hyperframes_mode.py`

如需补充模板可发现性或入口契约，可再加：

- `tests/test_style_config_storyboard_planning_ui.py`

但前提是测试确实依赖固定模板枚举，而不是纯文件系统扫描。

## 7. 映射与契约规则

### 7.1 模板入口到原生模板目录映射

沿用当前规则：

- `1920x1080/image_full.html` -> `template_id = image_full`
- `1920x1080/image_landscape_minimal.html` -> `template_id = image_landscape_minimal`

`HyperFrames Compiled` 路径必须直接命中上述目录，而不是再因为缺目录而 fallback 到 `legacy`。

### 7.2 Canvas 尺寸规则

这两个模板必须按横屏 `1920x1080` 坐标系设计和验证。

显式要求：

- 最终画布尺寸使用模板路径中的 `1920x1080`
- 不能把媒体生成尺寸误当作最终布局坐标系
- 主图区、字幕区、角落信息区的位置都必须按横屏安全区重新定义

### 7.3 数据契约范围

本轮不新增 `TemplateRenderContext` 字段。

继续使用已有字段：

- `title`
- `visuals`
- `captions`
- `text_cues`
- `author`
- `footer`
- `template_params`

其中本轮角落信息组的字段映射约定为：

- `作者` -> `author`
- `描述` -> `template_params.author_desc`
- `品牌` -> `footer`

当前编译器可直接替换的壳层占位符仍然只有 `__AUTHOR__`、`__AUTHOR_DESC__`、`__FOOTER__`，因此本轮不新增独立 `brand` 字段，也不扩展编译器占位符集合。

模板差异通过 HTML/CSS 结构与现有字段的布局消费来表达，不通过扩充 context 模型来表达。

## 8. 共通视觉规则

无论 `B` 还是 `D`，都遵循以下共通规则：

1. 字幕必须抬高，不能贴近底边。
2. 字幕不带背景块。
3. `作者 / 品牌 / 描述` 不能放在字幕正下方。
4. `作者 / 品牌 / 描述` 必须作为角落信息组单独存在。
5. 字幕与角落信息之间必须有明显呼吸区。
6. 角落信息组的作用是署名和识别，不应取得与字幕相同的视觉权重。

为了避免“无背景字幕”失去可读性，本轮允许且建议用以下方式补偿：

- 更大的字号
- 更强的字重
- 明确描边
- 柔和阴影

## 9. B：`image_full` 模板设计

### 9.1 结构定位

`B` 的核心是“主图优先”的横屏大图模板。

推荐结构：

- 标题区：居中放在顶部安全区，视觉上轻于主图
- 主图区：占据画面主体宽度，是最主要视觉区域
- 字幕区：位于主图区下方，但明显高于底边
- 信息角落：位于左下角

### 9.2 字幕规则

`B` 的字幕规则是：

- 白字
- 深描边
- 带阴影
- 无背景块
- 可承载一到两行短句

实现倾向：

- 在 `captions.template.html` 中把字幕定位为横向居中的抬高字幕带，但不使用底板
- 在 `text_layer.template.html` 中，默认 lower-third 风格也应与字幕保持一致，不再使用深色圆角底板

理由：

- `image_full` 画面主体面积大，字幕如果继续做小字会失去存在感
- 直接用大字 + 描边比加底板更不挡图，也更符合用户要求

### 9.3 角落信息规则

`B` 的 `作者 / 品牌 / 描述` 固定放在左下角，作为一组较轻的信息簇。

要求：

- 不与字幕同轴垂直堆叠
- 视觉权重显著低于字幕
- 行高紧凑，避免做成第二个标题块

## 10. D：`image_landscape_minimal` 模板设计

### 10.1 结构定位

`D` 的核心是“留白与秩序”的极简横屏模板。

推荐结构：

- 标题区：偏小，放在左上安全区
- 主图区：居中陈列，像展板或画框
- 字幕区：位于主图区下方，但不贴底
- 信息角落：位于右下角

### 10.2 字幕规则

`D` 的字幕规则是：

- 深色字
- 轻阴影
- 无背景块
- 文案更短，偏一句有分量的说明句

实现倾向：

- 在 `captions.template.html` 中把字幕做成“漂浮于留白区的版心文案”
- 不加说明卡底板，不加高对比块面，不做标签感组件
- 在 `text_layer.template.html` 中默认也不使用底板式 lower-third

理由：

- `D` 的气质依赖留白和克制
- 字幕若带背景块，会破坏极简气质，像贴标签而不是版心文字

### 10.3 角落信息规则

`D` 的 `作者 / 品牌 / 描述` 固定放在右下角，作为“签名式信息组”存在。

要求：

- 更小、更轻
- 与中部文案和主图区保持距离
- 视觉上更像落款，而不是正文

## 11. 文本层实现约束

用户最终确认的“字幕无背景”不是软建议，而是模板硬约束。

因此本轮对两个模板的实现约束是：

- `captions.template.html` 中的 `.caption-text` 不允许使用背景块
- `text_layer.template.html` 中默认 lower-third / subtitle 表现也不允许使用背景块
- 如未来某个模板需要恢复底板，必须显式作为该模板的独立设计变体处理，不能在这两个模板里隐式保留

这条规则用于避免：

- `captions` 层无底板，但 `text_layer` 层仍出现底板
- 同一模板内部出现两套相互冲突的字幕语法

## 12. 测试边界

本轮只验证结构正确、链路正确、契约正确，不做重型像素回归。

### 12.1 编译层

需要验证：

- `image_full` 能编译出 `index.html`
- `image_full` 能编译出 `captions.html`
- `image_full` 能编译出 `text_layer.html`
- `image_landscape_minimal` 能编译出对应三类编译产物

同时应验证模板产物中：

- 没有远程字体依赖
- 没有 CDN 资源引用
- 引用了本地 runtime 资源

### 12.2 管线层

需要验证：

- `render_backend = hyperframes_compiled`
- `frame_template = 1920x1080/image_full.html`
- `frame_template = 1920x1080/image_landscape_minimal.html`

在以上情况下：

- `StandardPipeline` 不应 fallback 到 `legacy`
- `template_id` 应与入口模板 stem 一致
- 输出 render execution plan 时，effective backend 应保持 `hyperframes_compiled`

### 12.3 契约层

需要验证：

- 横屏 canvas 使用 `1920x1080`
- 字幕位置不是贴底
- 角落信息不在字幕正下方
- 字幕相关 CSS 不带背景块

这部分优先做结构断言和编译产物文本断言，不做像素级截图比对。

## 13. 风险与控制

### 13.1 最大风险

最大风险不是模板无法编译，而是横屏模板“仍然带着竖屏思维”：

- 字幕太低
- 字幕太小
- 角落信息压字幕
- 主图区比例不合理
- `text_layer` 和 `captions` 的风格不一致

### 13.2 风险控制策略

本轮实现优先保证：

1. 字幕与角落信息的层级关系正确
2. 横屏安全区比例正确
3. `HyperFrames Compiled` 不发生 fallback
4. 字幕无背景块约束在 `captions` 与 `text_layer` 两层都成立

视觉细节如边框粗细、阴影强弱、间距微调可以留在下一轮样式精修。

## 14. 验收标准

本设计的完成标准是：

- 用户能在模板库中选到 `1920x1080/image_full.html`
- 用户能在模板库中选到 `1920x1080/image_landscape_minimal.html`
- 两者在 `HyperFrames Compiled` 下都能命中对应原生模板目录
- `B` 的字幕为无背景大字并抬高，署名信息在左下角
- `D` 的字幕为无背景短句并抬高，署名信息在右下角
- `作者 / 品牌 / 描述` 不再出现在字幕正下方
- 编译产物与执行计划均体现横屏模板已生效且未回退
