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

不能继续让 pipeline 直接把 `ProgressEvent` 发给一个裸 callback。最佳实践是把进度上报收敛为统一 dispatcher，由 dispatcher 把同一个事件分发给多个 sink：

- UI sink：给 Streamlit 同步界面做本地化展示。
- Task progress sink：给 async task store 写入结构化进度。
- 未来可扩展 observability sink：把关键阶段事件写入结构化日志或指标。

推荐抽象：

```python
class ProgressSink(Protocol):
    def emit(self, event: ProgressEvent) -> None:
        ...


class ProgressDispatcher:
    def __init__(self, sinks: Sequence[ProgressSink]):
        self._sinks = list(sinks)

    def emit(self, event: ProgressEvent) -> None:
        for sink in self._sinks:
            sink.emit(event)
```

`PipelineContext` 不再只持有一个 `progress_callback`，而是持有统一 `progress_dispatcher`。pipeline 内部通过单一入口发阶段事件，例如：

```python
def _report_pipeline_stage(
    self,
    ctx: PipelineContext,
    event_type: ProgressEventType,
    progress: float,
    **kwargs,
) -> None:
    if ctx.progress_dispatcher is None:
        return
    ctx.progress_dispatcher.emit(
        ProgressEvent(event_type=event_type, progress=progress, **kwargs)
    )
```

本次实现不要求一口气迁移所有历史调用点，但 post-production、新增阶段和 async task 进度写入必须走 dispatcher。后续历史 `_report_progress(...)` 也要逐步收口到同一入口，而不是继续扩散。

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

当前 API 异步任务通过 `api_task_id` 关联任务，但 pipeline 进度没有统一写入 `TaskStore`。这个问题不能在 API reserve 入口用 Python callback 解决，因为：

- reserve 入口不是实际执行者；
- worker 模式下生成发生在独立进程；
- running task 的进度写入必须带 `owner_id + lease_token`，否则会破坏 fencing 语义。

正确做法是：**在实际执行者侧创建 task progress sink**。

分两种执行模式：

- `embedded` 模式：`TaskManager._execute_registry_task(...)` 在拿到 `owner_id + lease_token` 后创建 task progress sink，并注入 pipeline dispatcher。
- `worker` 模式：`GenerationWorker.run_once()` 在 claim 到 task lease 后创建 task progress sink，并注入 `PixelleVideoCore.generate_video(...)` 的 dispatcher。

task progress sink 的职责：

- 接收 `ProgressEvent`。
- 转换为持久化 `TaskProgress`。
- 通过 `GenerationRegistry.update_progress(...)` 或等价封装写入 store。
- 每次写入都带当前执行者的 `owner_id + lease_token`，保证失去租约的旧执行者不能继续覆盖进度。

为避免 `TaskProgress.message` 再次退化为展示文案，持久化层应补充稳定字段，至少包含：

- `event_type`: `synthesizing_audio` / `preparing_render_manifest` / `rendering_hyperframes` 等稳定阶段值；
- `message`: 面向 API 调试的稳定 fallback 文本；
- `percentage`: 0-100；
- `current`、`total`：仅在有天然计数语义时填写，否则允许保持 0。

UI 本地化仍发生在展示层。Streamlit 同步界面可以继续消费 `ProgressEvent` 做本地化，API `/api/tasks/{task_id}` 返回的则是结构化 task progress，而不是仅靠中文或英文文案承载语义。

### 5. 测试策略

新增或更新测试：

- HyperFrames post-production 阶段顺序测试：`synthesizing_audio` 必须早于 `rendering_hyperframes`。
- HyperFrames renderer 调用前必须已经完成 audio synthesis 和 manifest preparation 事件。
- i18n 注册测试覆盖新增 `ProgressEventType`。
- embedded 执行模式测试验证 executor 创建了带 lease 的 task progress sink，并能更新 task progress。
- worker 执行模式测试验证 worker 在 claim lease 后创建 task progress sink，并能更新 task progress。
- registry/store 测试验证失去 lease 的执行者无法继续写 progress。

## 风险与处理

- 进度百分比可能与旧 UI 预期略有变化：控制在后期阶段范围内，只改变阶段含义，不改变总体完成节奏。
- dispatcher 需要兼容现有同步 callback 风格：sink 设计优先保持 emit 接口简单，必要时由执行者侧桥接 async registry 写入。
- `TaskProgress` 结构扩展会影响 API 返回模型和测试：需要同步更新 schema、store 序列化和断言。
- 旧调用仍可暂时通过兼容层转发，但不允许新增直接依赖裸 `_report_progress(...)` 的 post-production 阶段代码。

## 验收标准

- 使用 HyperFrames 生成视频时，界面先显示“正在生成音频...”，音频完成后才显示“正在使用 HyperFrames 渲染...”。
- `/api/tasks/{task_id}` 在异步生成期间能返回对应阶段 progress message。
- `/api/tasks/{task_id}` 返回的 progress 具有稳定阶段字段，不依赖某一种展示文案作为唯一语义。
- 新增回归测试失败于旧实现，修复后通过。
- 所有新增进度事件都有中英文翻译。
- 不引入前端临时判断或针对 HyperFrames 文案的硬编码补丁。
