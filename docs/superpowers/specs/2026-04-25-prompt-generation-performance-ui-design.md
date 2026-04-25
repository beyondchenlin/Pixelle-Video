# 提示词生成性能入口设计

## 背景

LLM 图片/视频提示词生成已经支持批量大小和并发数配置。当前入口只在系统配置里，技术上能生效，但用户在生成视频时不容易发现，也容易和「批量生成模式」或 RunningHub 并发混淆。

## 目标

- 系统配置继续作为全局默认值，保护模型服务限流、成本和稳定性。
- 快速创作页增加本次任务覆盖入口，让用户在生成前决定提示词生成阶段是否提速。
- UI 与现有 Streamlit 表单风格统一，不引入新的视觉体系。
- 标题和控件不使用齿轮图标。

## 非目标

- 不移除系统配置中的默认性能字段。
- 不改变 RunningHub 图片生成并发配置。
- 不把本次任务覆盖值持久化为全局默认值。
- 不改动 LLM 批处理执行器的并发、重试和观测语义。

## 交互设计

在快速创作页左侧「视频脚本」卡片内，分镜数控件下方新增折叠区：

```text
提示词生成性能
```

折叠区默认关闭。关闭状态下不增加普通用户的操作负担。展开后显示：

- `自定义提示词生成性能`：checkbox，默认关闭。
- 默认关闭时显示当前系统默认值摘要，例如：`使用系统默认：每批 10 条，并发 1`。
- 开启后显示两个并排数字输入：
  - `提示词批量大小`，范围 `1-50`。
  - `提示词并发数`，范围 `1-10`。

控件说明必须明确：

- 只影响大模型生成图片/视频提示词阶段。
- 不影响 RunningHub 图片/视频生成并发。
- 并发越高通常越快，但更容易触发模型服务限流或增加瞬时成本。

## 数据流

新增一个专门的提示词生成性能 UI/helper 层，避免把字段名和渲染逻辑散落在 `content_input.py`、`output_preview.py`、批量管理器和 API 适配里。该 helper 负责：

- 渲染「提示词生成性能」折叠区。
- 读取并展示全局 LLM 默认值。
- 只在用户启用自定义时返回覆盖字段。
- 提供共享字段名常量，避免调用链中手写字符串。

返回的 `video_params` 在用户启用自定义时增加两个字段：

- `llm_prompt_batch_size`
- `llm_prompt_batch_concurrent_limit`

当用户未启用自定义时，不写入这两个字段。后端继续读取系统配置默认值。不要把 `None` 写入请求、共享配置或任务日志；这样可以避免「未覆盖」和「覆盖为空」两种状态混在一起。

单视频生成时，`build_single_generation_request()` 将可选字段传入 `generate_video()` 请求。

批量生成时，`build_batch_shared_config()` 将可选字段写入共享配置，使批量内每个视频使用同一组本次任务覆盖值。

`StandardPipeline.plan_visuals()` 将这两个参数传入 `generate_styled_image_prompt_batch()`，最终进入统一的 prompt batch runner。

`CustomPipeline` 中已有的 `generate_styled_image_prompt_batch()` 调用也必须透传这两个参数，避免 Web UI 以外的自定义 pipeline 路径表现不一致。

API 层也必须支持同一契约：

- `api.schemas.video.VideoGenerateRequest` 增加两个可选字段，并使用与配置相同的范围约束。
- `api.routers.video.build_video_generation_params()` 只在请求字段不为 `None` 时写入生成参数。
- `api.schemas.content.ImagePromptGenerateRequest` 增加两个可选字段。
- `api.routers.content.generate_image_prompts_endpoint()` 将字段传给 `generate_styled_image_prompt_batch()`。

这样 Web、同步 API、异步 API、直接内容提示词 API 和 pipeline 内部调用都使用同一套参数语义。

## 系统配置调整

系统配置里的字段保留，但文案定位改为默认值，例如：

```text
LLM 默认性能配置
```

这说明系统配置不是唯一入口，而是生成页未覆盖时的默认值来源。

## 错误处理

- 前端数字输入限制范围，避免非法值进入后端。
- API schema 和全局配置 schema 使用相同范围约束，避免不同入口允许不同值。
- 后端保留已有归一化逻辑，继续兜底处理缺失值或异常值。
- 本次任务覆盖不改变现有失败、重试、取消和观测行为。

## 测试

- 配置默认值测试：未传覆盖值时仍使用全局 LLM 配置。
- 单视频请求构建测试：开启覆盖时请求包含两个字段；未开启时两个字段完全不存在。
- 批量共享配置测试：开启覆盖时共享配置包含两个字段；未开启时两个字段完全不存在。
- Pipeline 参数传递测试：`StandardPipeline` 将覆盖值传给提示词生成函数。
- Pipeline 参数传递测试：`CustomPipeline` 将覆盖值传给提示词生成函数。
- API 参数传递测试：视频生成 API 和内容提示词 API 都能接收并透传这两个字段。
- 前端结构通过现有 Streamlit 组件路径验证，确保不使用齿轮图标文案。
