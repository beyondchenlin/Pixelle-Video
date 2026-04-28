# 尺寸合同与通用输出规格设计

## 背景

当前生成链路把三个概念混在一起展示和理解：

- 最终视频输出尺寸，例如 1280x720。
- AI 素材生成尺寸，例如插图生成 768x768 或跟随视频画布。
- 模板基础坐标尺寸，例如 `templates/1920x1080/image_landscape_minimal.html`。

这会导致用户看到模板路径里的 `1920x1080`，同时 UI 又显示 `1K (1280x720)`，误以为已经设置成另一个尺寸。实际成片由 `canvas_width` 和 `canvas_height` 决定，模板目录只是布局坐标基准。

## 目标

建立一个清晰、可测试、可扩展的尺寸合同，让所有生成链路只从合同读取最终输出和素材尺寸。模板只声明设计坐标和兼容方向，不再暗示或决定最终导出尺寸。

标准预设只保留主流交付规格，不新增 `1920x720` 这类非通用尺寸。非通用尺寸如果未来需要，应进入高级自定义能力，并带有明确的非标准提示。

## 非目标

- 不为每个输出分辨率复制模板目录。
- 不把模板目录名改造成最终输出尺寸枚举。
- 不把 `1920x720` 做成内置标准预设。
- 不在本次设计中实现完整高级自定义尺寸编辑器。

## 标准尺寸预设

内置预设应从“清晰度等级 + 方向”改为“通用交付规格”：

| 方向 | 显示名称 | 尺寸 |
| --- | --- | --- |
| 横屏 | HD 横屏 | 1280x720 |
| 横屏 | Full HD 横屏 | 1920x1080 |
| 横屏 | 4K 横屏 | 3840x2160 |
| 竖屏 | HD 竖屏 | 720x1280 |
| 竖屏 | Full HD 竖屏 | 1080x1920 |
| 竖屏 | 4K 竖屏 | 2160x3840 |
| 方屏 | 方屏 1K | 1024x1024 |
| 方屏 | 方屏 Full HD | 1080x1080 |
| 方屏 | 方屏 2K | 2048x2048 |

素材尺寸默认继续独立于最终视频尺寸。图片素材可保留 `768x768` 作为轻量默认值，也可以选择通用横屏、竖屏、方屏规格。开启“图片尺寸同步到视频”时，素材尺寸等于最终画布尺寸。

## 架构设计

### 尺寸合同

`pixelle_video/models/size_contract.py` 继续作为尺寸真源，但语义需要升级：

- 用稳定 preset id 表达标准输出规格，例如 `landscape_hd`、`landscape_full_hd`、`landscape_4k`、`portrait_full_hd`、`square_full_hd`。
- 输出合同明确包含 `canvas_width`、`canvas_height`、`media_width`、`media_height`。
- 合同提供向后兼容解析，把旧值 `1k`、`2k`、`4k` 映射到对应方向下的通用规格。
- 合同拒绝非标准内置 preset id，避免把临时尺寸混进主流程。

### 模板合同

模板工具层需要把模板信息表达成独立合同：

- `template_design_width` 和 `template_design_height` 来自模板目录或模板元信息。
- `template_orientation` 表示模板适配横屏、竖屏或方屏。
- 模板兼容性只检查方向，不要求模板坐标尺寸等于最终输出尺寸。
- UI 中展示“模板坐标尺寸”，并明确它是布局基准。

可以扩展现有 `pixelle_video/utils/template_util.py`，也可以新增 `pixelle_video/models/template_contract.py` 承载结构化模型。实施时优先选择更小、更清晰的边界。

### UI 设计

`web/components/style_config.py` 中的尺寸区域拆成三段信息：

- 最终视频尺寸：使用通用规格标签，例如 `Full HD 横屏 (1920x1080)`。
- 图片生成尺寸：显示素材尺寸，并保留同步开关。
- 模板坐标尺寸：显示当前模板的设计坐标，例如 `1920x1080，仅用于布局缩放`。

界面不再使用裸 `1K`、`2K` 作为主标签。历史 preset 值可以继续解析，但新 UI 不再主动产生旧标签。

### 渲染数据流

生成请求进入后端时先构建尺寸合同：

1. Web UI 收集标准尺寸 preset 和同步开关。
2. `GenerationSizeContract.from_params()` 归一化为明确像素值。
3. `build_single_generation_request()` 和批量生成请求只传合同输出的尺寸字段。
4. storyboard、render package、HyperFrames manifest、ffmpeg 导出全部使用 `canvas_width` 和 `canvas_height`。
5. 模板渲染器读取模板设计坐标，并按最终画布比例缩放布局。

最终导出尺寸必须只由尺寸合同决定，不能从模板路径反推。

## 兼容性

旧任务和旧配置中可能存在以下字段：

- `video_resolution_preset: "1k"` 映射到当前方向下的 HD。
- `video_resolution_preset: "2k"` 映射到当前方向下的 Full HD。
- `video_resolution_preset: "4k"` 映射到当前方向下的 4K。
- 旧的显式 `canvas_width` 和 `canvas_height` 继续优先于 preset。
- 仅传 `media_width` 和 `media_height` 的旧请求继续按现有兼容逻辑处理，避免破坏历史 API。

UI 展示历史任务时以实际像素为准，不尝试把非标准尺寸伪装成标准 preset。

## 错误处理

- 未知 preset id 返回清晰错误，提示支持的标准规格。
- 模板方向和最终视频方向不匹配时，继续沿用兼容模板自动切换逻辑；如果没有兼容模板，显示错误并阻止生成。
- 显式像素尺寸必须为正整数。
- 如果未来引入高级自定义尺寸，必须单独验证宽高范围、偶数约束、平台兼容性和模板方向。

## 测试策略

需要覆盖以下层级：

- 尺寸合同单元测试：标准 preset、旧 preset 兼容、显式像素优先、非法 preset 拒绝。
- UI 请求构建测试：单视频和批量请求都传递合同尺寸，不从模板 session state 取最终尺寸。
- 模板合同测试：模板设计尺寸可以和最终输出尺寸不同，但方向必须兼容。
- 渲染 manifest 测试：HyperFrames manifest 中的 `width`、`height`、`canvas_width`、`canvas_height` 等于尺寸合同结果。
- 预览摘要测试：右侧生成结果显示实际输出尺寸，而不是模板尺寸。

## 验收标准

- 选择横屏 Full HD 时，最终视频、metadata、storyboard、manifest、结果摘要全部显示 1920x1080。
- 选择横屏 HD 时，最终视频、metadata、storyboard、manifest、结果摘要全部显示 1280x720。
- 当前模板路径为 `1920x1080/...` 时，仍可导出 1280x720，UI 明确说明模板尺寸只是布局坐标。
- 标准预设列表中不存在 1920x720。
- 旧的 `1k`、`2k`、`4k` 请求仍能生成，并被归一化到通用尺寸。
- 自动化测试覆盖尺寸合同、请求构建、模板合同和 manifest 输出。
