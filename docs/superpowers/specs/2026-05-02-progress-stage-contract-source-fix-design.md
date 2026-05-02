# Pixelle 进度阶段契约源头修复设计

## 背景

当前生成视频时，HyperFrames 路径会在进入 `_post_production_hyperframes()` 时立即上报 `rendering_hyperframes`，而真正的 master audio 合成发生在该消息之后：

1. 上报“正在使用 HyperFrames 渲染...”
2. 执行 `_synthesize_hyperframes_audio(ctx)`
3. 写入 HyperFrames manifest
4. 调用 HyperFrames renderer

这会导致前端从用户视角直接跳到渲染阶段，看不到独立的“生成音频”阶段。问题不是前端漏显示，而是 pipeline 的阶段语义不准确。

更深层原因是进度事件由各 pipeline 和服务分散调用 `_report_progress(...)`，没有统一的阶段契约、阶段顺序约束和后端任务进度 sink。任何渲染路径都可能把音频、资产准备、manifest 构建、最终渲染混在同一个进度事件里。

## 目标

- 建立明确的进度阶段契约，让进度事件表达真实业务阶段，而不是临时 UI 文案。
- HyperFrames 后期流程必须先展示音频合成进度，再展示 HyperFrames 渲染进度。
- 同一套进度事件同时服务 Streamlit 同步界面和 API 异步任务轮询。
- 用测试锁定阶段顺序和 i18n 注册，防止以后回归。
- 避免只在前端补文案或移动单行代码造成新的技术债。

## 非目标

- 不重做整套任务系统、日志系统或历史页面。
- 不改变视频生成结果、音频合成算法、HyperFrames renderer 接口。
- 不把所有历史进度事件一次性重命名；只补齐本次源头问题所需的阶段契约。

## 推荐方案

### 1. 扩展进度事件契约

在 `pixelle_video.models.progress.ProgressEventType` 中新增真实业务阶段：

- `SYNTHESIZING_AUDIO`：顶层音频合成阶段，适用于 master audio、TTS block 合成、音频拼接。
- `PREPARING_RENDER_MANIFEST`：最终渲染前的 manifest、字幕、文字层、音轨、视觉 clip 准备阶段。
- 保留已有 `RENDERING_HYPERFRAMES` 和 `RENDERING_FFMPEG_MANIFEST`，但它们只表示真正进入对应 renderer。

新增阶段必须同步注册到 `PROGRESS_EVENT_I18N_KEYS`，并补齐 `zh_CN`、`en_US` 翻译。

### 2. 收敛进度上报入口

在 pipeline 层增加统一方法，作为后续阶段事件的唯一入口：

```python
def _report_pipeline_stage(
    self,
    ctx: PipelineContext,
    event_type: ProgressEventType,
    progress: float,
    **kwargs,
) -> None:
    self._report_progress(ctx.progress_callback, event_type, progress, **kwargs)
```

第一步保持轻量，不强制迁移所有旧调用，但新增和本次涉及的 post-production 阶段必须使用该入口。这样后续可以逐步在同一入口加入异步任务落库、阶段顺序校验和结构化观测。

### 3. 重排 HyperFrames 后期阶段

`_post_production_hyperframes()` 调整为以下顺序：

1. 校验 timing plan、HyperFrames services、alignment service、audio edit service。
2. 上报 `SYNTHESIZING_AUDIO`，进度约 `0.80` 到 `0.84`。
3. 执行 `_synthesize_hyperframes_audio(ctx)`。
4. 执行字幕对齐、静音裁剪、时间线修正。
5. 上报 `PREPARING_RENDER_MANIFEST`，进度约 `0.84` 到 `0.86`。
6. 编译文本层、字幕、音轨、视觉 clips，写入 HyperFrames project。
7. 上报 `RENDERING_HYPERFRAMES`，进度约 `0.90`。
8. 调用 `hyperframes_renderer.render(...)`。

这样 UI 和 API 任务状态都能看到真实阶段：音频生成 -> 渲染准备 -> HyperFrames 渲染。

### 4. 异步任务进度 sink

当前 API 异步任务通过 `api_task_id` 关联任务，但 pipeline 进度没有统一写入 `TaskStore`。本次新增一个轻量桥接：

- 在 API async 入口创建 progress callback。
- callback 接收 `ProgressEvent`，转换为 `TaskProgress`。
- 写入当前 task 的 `progress.message`、`percentage`、`current`、`total`。
- message 优先使用稳定阶段 key 或英文 fallback，避免 API 层依赖 Streamlit i18n。

这个 sink 只负责结构化任务进度，不影响 Streamlit 同步界面原有 callback。

### 5. 测试策略

新增或更新测试：

- HyperFrames post-production 阶段顺序测试：`synthesizing_audio` 必须早于 `rendering_hyperframes`。
- HyperFrames renderer 调用前必须已经完成 audio synthesis 和 manifest preparation 事件。
- i18n 注册测试覆盖新增 `ProgressEventType`。
- async video API 测试验证生成入口会传入 progress callback，并能更新 task progress。

## 风险与处理

- 进度百分比可能与旧 UI 预期略有变化：控制在后期阶段范围内，只改变阶段含义，不改变总体完成节奏。
- 异步 callback 涉及 async store 写入：如果 pipeline callback 是同步接口，桥接层使用安全的任务调度或 registry 封装，避免阻塞生成流程。
- 旧调用仍可继续用 `_report_progress`：本次只强制新阶段走统一入口，后续可独立清理历史调用，不扩大本次变更范围。

## 验收标准

- 使用 HyperFrames 生成视频时，界面先显示“正在生成音频...”，音频完成后才显示“正在使用 HyperFrames 渲染...”。
- `/api/tasks/{task_id}` 在异步生成期间能返回对应阶段 progress message。
- 新增回归测试失败于旧实现，修复后通过。
- 所有新增进度事件都有中英文翻译。
- 不引入前端临时判断或针对 HyperFrames 文案的硬编码补丁。
