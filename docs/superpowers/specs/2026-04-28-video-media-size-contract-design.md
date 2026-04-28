# Video And Media Size Contract Design

## 1. 结论

本次改造采用“显式尺寸合同 + 单一预设模型 + 分层消费”的方案，从源头拆开最终视频画布尺寸和素材生成尺寸。

最终原则如下：

- 最终视频尺寸使用 `canvas_width` / `canvas_height` 表达。
- 图片或视频素材生成尺寸继续使用 `media_width` / `media_height` 表达。
- UI 通过统一尺寸预设表选择画幅和分辨率，不再让模板目录或模板 meta 成为最终视频尺寸的业务源头。
- 图片生成尺寸默认固定为 `768x768`。
- 只有用户显式开启“同步到最终视频尺寸”时，`media_width` / `media_height` 才等于当前 `canvas_width` / `canvas_height`。
- 旧参数和旧模板仍保持兼容，但新逻辑必须围绕显式合同运行。

这不是一次最小改动。当前代码把 `media_width` / `media_height` 同时当成素材生成尺寸和部分最终渲染尺寸使用，这是长期技术债的源头。正确做法是建立清晰的尺寸语义，然后让 UI、请求构建、pipeline、render manifest、模板渲染分别消费自己应该消费的尺寸。

## 2. 背景

当前标准生成链路里的尺寸来源比较混杂：

- `web/components/style_config.py` 从当前模板读取 `template_media_width` / `template_media_height`，并把它们写入 session state。
- `web/components/output_preview.py` 在单视频生成时又从 session state 读取模板媒体尺寸，构建 `media_width` / `media_height` 请求。
- `StoryboardConfig` 只有 `media_width` / `media_height`，没有独立的最终画布尺寸字段。
- `FrameProcessor` 使用 `config.media_width` / `config.media_height` 生成图片或视频素材。
- `RenderManifest` 和部分 HyperFrames/FFmpeg manifest 路径也把 `media_width` / `media_height` 当作画布尺寸使用。
- `HTMLFrameGenerator` 通过模板路径解析固定尺寸，例如 `1920x1080` 或 `1080x1920`，模板 HTML 内部也常有写死的像素尺寸。

结果是“最终视频尺寸”和“素材尺寸”被耦合在一起。用户想选择横版 `1280x720` 的最终视频，同时保持图片默认 `768x768` 时，当前模型无法自然表达，只能靠补丁式覆盖。

## 3. 目标

1. 支持用户选择最终视频画幅：横版、竖版、方形。
2. 支持每个画幅选择分辨率预设。
3. 默认最终视频尺寸：
   - 横版：`1280x720`
   - 竖版：`720x1280`
   - 方形：`1024x1024`
4. 支持预设尺寸：
   - 横版：`1280x720`、`1920x1080`、`3840x2160`
   - 竖版：`720x1280`、`1080x1920`、`2160x3840`
   - 方形：`1024x1024`、`2048x2048`、`4096x4096`
5. 图片生成尺寸默认保持 `768x768`。
6. 提供显式同步选项：开启后素材尺寸跟随最终视频尺寸。
7. 让最终渲染、字幕布局、manifest、HyperFrames canvas 使用 `canvas_width` / `canvas_height`。
8. 让图片/视频素材生成工作流使用 `media_width` / `media_height`。
9. 保持旧配置和旧 API 调用可运行，避免破坏已有任务。

## 4. 非目标

- 本次不重写所有 HTML 模板的视觉布局。
- 本次不移除模板目录中现有的 `1080x1920` / `1920x1080` / `1080x1080` 结构。
- 本次不改变具体 ComfyUI 工作流内部节点，只保证传入的 width/height 语义正确。
- 本次不新增任意自定义宽高输入，先只落地确认过的标准预设。
- 本次不处理所有历史输出文件的回填迁移。

## 5. 备选方案

### 5.1 方案 A：继续用模板决定尺寸，仅在 UI 加同步开关

做法：

- UI 保持从模板读取尺寸。
- 如果用户勾选同步，就把模板尺寸写回图片生成尺寸。

优点：

- 改动少。

缺点：

- 没有解决 `media_width` / `media_height` 语义混乱。
- 模板仍然是最终尺寸的隐式源头。
- 用户选择 `1280x720` 这种当前模板目录不存在的尺寸时仍然无法自然表达。
- 后续所有尺寸功能都会继续围绕 session state 和模板 meta 打补丁。

结论：拒绝。它违背“从源头解决问题”的要求。

### 5.2 方案 B：把 `media_width` / `media_height` 统一改成用户选择的视频尺寸

做法：

- 用户选择横版 `1280x720` 后，直接把 `media_width` / `media_height` 设置为 `1280x720`。
- 不新增 `canvas_width` / `canvas_height`。

优点：

- 比方案 A 更接近用户需求。

缺点：

- 图片默认 `768x768` 会被破坏。
- 仍然混淆素材尺寸和最终画布尺寸。
- 方形图片放进横版视频、素材视频放进竖版视频等场景无法清楚表达。

结论：拒绝。它只是把旧混乱换成新混乱。

### 5.3 方案 C：建立显式尺寸合同

做法：

- 新增统一尺寸模型，定义画幅、预设、默认值和同步规则。
- UI 只消费这个模型并输出两个明确尺寸：`canvas_size` 和 `media_size`。
- 请求构建同时携带 `canvas_width` / `canvas_height` 和 `media_width` / `media_height`。
- pipeline、render manifest、模板渲染按语义消费对应尺寸。
- 旧参数兼容保留，但新代码不再把模板 media-size 当成最终尺寸源头。

优点：

- 源头语义清楚。
- 后续新增尺寸预设、API 参数、批量生成和测试都能围绕同一模型扩展。
- 保留图片默认 `768x768`，同时支持显式同步。
- 可以逐步治理模板固定尺寸问题。

缺点：

- 首次改造范围比补丁式方案更大。

结论：采用。

## 6. 采用方案

### 6.1 尺寸模型

新增一个独立模块承载尺寸预设和解析逻辑，建议路径：

- `pixelle_video/models/size_contract.py`

核心对象：

- `SizeSpec`
  - `width: int`
  - `height: int`

- `VideoOrientation`
  - `landscape`
  - `portrait`
  - `square`

- `VideoResolutionPreset`
  - `p720` 或 `1k`
  - `p1080` 或 `2k`
  - `p2160` 或 `4k`

- `GenerationSizeContract`
  - `canvas_width`
  - `canvas_height`
  - `media_width`
  - `media_height`
  - `orientation`
  - `video_resolution_preset`
  - `sync_media_size_to_canvas`

预设表：

| orientation | preset | size |
| --- | --- | --- |
| landscape | 1K / 1280x720 | 1280x720 |
| landscape | 2K | 1920x1080 |
| landscape | 4K | 3840x2160 |
| portrait | 1K / 720x1280 | 720x1280 |
| portrait | 2K | 1080x1920 |
| portrait | 4K | 2160x3840 |
| square | 1K | 1024x1024 |
| square | 2K | 2048x2048 |
| square | 4K | 4096x4096 |

默认值：

- `orientation = landscape`
- `video_resolution_preset = 1K`
- `canvas_size = 1280x720`
- `media_size = 768x768`
- `sync_media_size_to_canvas = false`

兼容约束：

- `GenerationSizeContract` 是新链路的唯一尺寸解析入口。
- `StoryboardConfig` 可以继续被旧测试和旧调用只用 `media_width` / `media_height` 构造。
- 当 `StoryboardConfig` 未收到 `canvas_width` / `canvas_height` 时，`__post_init__` 必须把它们解析为 `media_width` / `media_height`，保持旧行为。
- 当请求入口同时缺少 canvas 和 media 尺寸时，必须通过 `GenerationSizeContract.default()` 得到 `canvas=1280x720`、`media=768x768`，而不是散落在 UI 或 pipeline 中各自写默认值。

### 6.2 UI 行为

在样式/模板区域增加最终视频尺寸设置：

- 画幅选择：横版、竖版、方形。
- 分辨率选择：根据画幅展示对应预设。
- 显示最终视频尺寸：来自 `canvas_width` / `canvas_height`。
- 同步开关：把图片生成尺寸同步到最终视频尺寸。

在图片/视频素材生成区域显示素材尺寸：

- 默认显示 `768x768`。
- 同步开启时显示当前最终视频尺寸。
- 文案必须区分“最终视频尺寸”和“图片生成尺寸”，不再使用“由模板自动决定”的表达。

模板选择仍然保留，但模板只代表版式和视觉样式。模板目录尺寸可以作为兼容信息和模板基础坐标系，不再作为用户最终尺寸选择的唯一来源。

模板与画幅的协调规则：

- 用户切换画幅时，模板列表默认优先展示同画幅模板。
- 当前模板与所选画幅不一致时，UI 应通过一个模板解析函数切换到同类型、同画幅的可用模板。
- 如果同类型同画幅模板不存在，可以保留当前模板，但必须显示兼容性提示，并通过渲染归一化保证最终视频尺寸仍然等于用户选择的 canvas 尺寸。
- 不能让“选了横版但仍静默使用竖版模板”成为默认路径。

### 6.3 请求参数

Web UI 构建请求时必须携带：

- `canvas_width`
- `canvas_height`
- `media_width`
- `media_height`
- `video_orientation`
- `video_resolution_preset`
- `sync_media_size_to_canvas`

单视频和批量生成必须走同一套复制逻辑，避免单视频从 session state 读旧模板尺寸、批量从 `video_params` 读新尺寸。

API schema 可新增可选字段：

- `canvas_width`
- `canvas_height`
- `media_width`
- `media_height`

兼容规则：

- 如果请求没有 `canvas_width` / `canvas_height`，但有 `media_width` / `media_height`，旧调用继续使用媒体尺寸作为画布尺寸。
- 如果两者都没有，使用默认合同：最终视频 `1280x720`，素材 `768x768`。

### 6.4 Pipeline 和 StoryboardConfig

`StoryboardConfig` 新增：

- `canvas_width: int`
- `canvas_height: int`

保留：

- `media_width: int`
- `media_height: int`

消费规则：

- `FrameProcessor._step_generate_media` 使用 `media_width` / `media_height`。
- 最终视频段、字幕、manifest、HyperFrames canvas 使用 `canvas_width` / `canvas_height`。
- 渲染包中的 `canvas_width` / `canvas_height` 写最终视频尺寸。
- 渲染包中的 `media_width` / `media_height` 写素材生成尺寸。
- 元素动画、分割、微动合成如果处理的是已合成帧，使用 `canvas_width` / `canvas_height`；只有处理原始生成素材时才使用 `media_width` / `media_height`。

### 6.5 模板渲染

当前 `HTMLFrameGenerator` 从模板路径解析 viewport，例如 `1920x1080`。为了支持用户最终选择 `1280x720`，需要增加目标画布尺寸输入：

- `HTMLFrameGenerator(template_path, canvas_width=None, canvas_height=None)`

渲染策略：

- 默认兼容：没有传入目标画布尺寸时，继续使用模板路径尺寸。
- 新链路：传入目标画布尺寸时，最终输出图像必须归一化到 `canvas_width` / `canvas_height`。
- 对模板内部写死坐标的情况，不直接把 viewport 改小后截图，因为这会裁切固定像素布局。
- 推荐策略是先按模板基础坐标系完整渲染，再用高质量缩放把结果归一化到目标 canvas；同画幅模板走等比缩放，不改变布局比例。
- 如果模板画幅与目标画幅不一致，归一化必须采用显式策略，例如 contain 留边或 cover 裁切，并在 UI 提示模板画幅不匹配。

这样既不需要一次重写所有模板，又能保证最终输出尺寸真正等于用户选择的尺寸。

### 6.6 测试策略

先写失败测试，再实现。

核心测试：

1. 尺寸合同默认值：
   - 默认 canvas 为 `1280x720`
   - 默认 media 为 `768x768`
   - 默认不同步

2. 横版/竖版/方形预设解析：
   - 横版 2K 为 `1920x1080`
   - 竖版 2K 为 `1080x1920`
   - 方形 4K 为 `4096x4096`

3. 同步规则：
   - 同步关闭时 media 保持 `768x768`
   - 同步开启时 media 等于 canvas

4. 请求构建：
   - 单视频请求不能再从 `template_media_width` / `template_media_height` 覆盖新尺寸。
   - 批量共享配置携带同一套尺寸合同。

5. Pipeline 初始化：
   - `StoryboardConfig.canvas_width/canvas_height` 与 `media_width/media_height` 可以不同。

6. 渲染 manifest：
   - `canvas_width/canvas_height` 使用最终视频尺寸。
   - `media_width/media_height` 使用素材尺寸。

7. 模板渲染：
   - 传入 `1280x720` 时，生成帧图像实际尺寸为 `1280x720`。

## 7. 迁移和兼容

- 旧模板 meta `template:media-width` / `template:media-height` 可继续作为模板推荐素材尺寸，但不再覆盖用户选择。
- 旧 API 请求只传 `media_width` / `media_height` 时继续可运行。
- 现有模板目录尺寸继续保留，用于模板基础坐标系和兼容解析。
- 新 UI 默认不再依赖模板 meta 决定图片尺寸，图片默认来自尺寸合同。

## 8. 成功标准

- 新建任务默认最终视频为 `1280x720`，图片生成尺寸为 `768x768`。
- 用户选择竖版 2K 时，最终视频尺寸为 `1080x1920`。
- 用户选择横版 4K 且不开同步时，图片生成仍为 `768x768`。
- 用户开启同步时，图片生成尺寸与最终视频尺寸一致。
- 单视频和批量生成尺寸行为一致。
- 测试覆盖默认值、预设解析、同步规则、请求构建、pipeline 初始化和 manifest 输出。
- 代码中不再新增依赖 `template_media_width` / `template_media_height` 作为新链路尺寸源头的逻辑。
