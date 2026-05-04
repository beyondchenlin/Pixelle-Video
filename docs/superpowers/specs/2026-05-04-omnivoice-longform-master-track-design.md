# OmniVoice 超长主音轨配音设计

## 背景

Pixelle 当前默认本地 TTS 链路仍以 IndexTTS2 为中心，项目侧提供了外部分段能力，用于缓解 IndexTTS2 长旁白生成慢、不稳定、边界难控的问题。OmniVoice 本地验证后表现出更高生成速度，并且 `OmniVoiceLongformTTS` 节点本身支持长文本内部智能分块。

本次目标是把默认配音链路调整为更适合 OmniVoice 的架构：普通用户不需要理解或配置超长分块；项目后端自动判断超长主音轨任务，在自然句末切成较大的保护块，再交给 OmniVoice Longform 内部分句生成。

## 目标

- 默认 TTS 工作流切换到 OmniVoice bf16 的项目 API 工作流。
- 使用 `OmniVoiceLongformTTS` 承接长文本，而不是继续用普通 `OmniVoiceVoiceCloneTTS` 承接默认长稿。
- 对 `master_track` 主音轨模式增加后端自动超长保护分块。
- 超长保护分块不暴露给普通用户，不新增普通前端主开关。
- 保留现有 IndexTTS2 外部分段能力，避免影响旧工作流和回退场景。
- 保存音色功能支持 OmniVoice，并在二次使用时传入保存的 `reference_audio_text`，跳过重复 ASR。

## 非目标

- 不为普通用户新增“OmniVoice 超长分段”前端开关。
- 不把每个句号都拆成一次 TTS 调用。
- 不删除 IndexTTS2 工作流、外部分段模式或已有高级配置。
- 不修改 ComfyUI 第三方插件源码来实现项目级分块。
- 不把 30 分钟全文一次性提交给单个 ComfyUI 节点作为默认产品行为。

## 方案选型

### 方案 A：整篇文本一次交给 OmniVoice Longform

优点是实现最简单，完全依赖 `OmniVoiceLongformTTS.words_per_chunk` 内部分块。缺点是 10-30 分钟级别任务一旦中途失败，整个 ComfyUI 任务需要重跑；最终拼接在单节点内完成，进度、恢复和时间轴记录都较弱。

### 方案 B：复用 IndexTTS2 的短文本外部分段

优点是已有代码和 UI 可复用。缺点是这是几十字到几百字级的短分段策略，会破坏 OmniVoice 的长文本优势，增加调用次数，并提高语气不连贯概率。

### 方案 C：后端自动主音轨保护分块，块内交给 OmniVoice Longform

这是推荐方案。Pixelle 只在 `master_track` 主音轨模式下，对超长文本按段落和中英文句末累计成 5-10 分钟级别的大块。每个大块调用一次 OmniVoice Longform，块内仍由 OmniVoice 自己按 `words_per_chunk` 细分。最后 Pixelle 拼接大块音频并记录时间轴。

该方案保留 OmniVoice 的速度优势，同时降低超长任务失败重跑成本，不把复杂度暴露给用户。

## 最终设计

### 默认工作流

新增项目 API 工作流：

`workflows/selfhost/tts_omnivoice_bf16.json`

该工作流应满足项目 `WorkflowParser` 可解析，暴露以下参数：

- `text`：当前要合成的文本块。
- `ref_audio`：保存音色或上传参考音频。
- `reference_audio_text`：参考音频转写文本，对应 OmniVoice 节点的 `ref_text`。

工作流内部使用 `OmniVoiceLongformTTS`，默认模型使用 `OmniVoice-bf16`，`words_per_chunk` 使用插件默认值或显式设置为适合长文本的稳定值。保存音色二次使用时，项目会传入 `reference_audio_text`，从而避免每次生成都重新做 Whisper ASR。

### 超长保护分块

新增项目级服务模块，负责把主音轨文本拆成“大块”：

- 仅在 `tts_audio_strategy == "master_track"` 时启用。
- 仅对 OmniVoice 工作流启用。
- 仅当文本长度超过阈值时启用；短文本直接交给单次 OmniVoice Longform。
- 切分目标是 5-10 分钟级别的大块，初始实现可用字符预算近似时长。
- 优先在段落空行断开。
- 其次在中英文句末断开：`。`、`！`、`？`、`!`、`?`、英文句号 `.`。
- 英文句号需要避免常见误切：小数、域名、缩写、人名头衔等。
- 如果预算附近找不到自然断点，允许软溢出到下一个句末；超过硬上限时才按字符安全切分。

这不是替代 OmniVoice 的内部 `words_per_chunk`，而是保护 ComfyUI 单任务边界。块内仍由 `OmniVoiceLongformTTS` 自己细分。

### 数据流

默认长主音轨链路：

1. 用户脚本或分镜旁白进入标准流水线。
2. 项目判断当前是 OmniVoice 工作流和 `master_track`。
3. 文本未超过阈值时，直接调用一次 TTS。
4. 文本超过阈值时，项目生成超长保护分块计划。
5. 每个大块调用一次 `tts_omnivoice_bf16.json`。
6. 每次调用都传入同一个 `ref_audio` 和 `reference_audio_text`。
7. 项目将大块音频拼接为主音轨。
8. 主音轨再按既有逻辑对齐分镜时间轴。

逐帧 `per_frame` 模式暂不启用超长保护分块。单个分镜文本如果长到 10 分钟级别，说明问题更应该在脚本或分镜规划层修正，而不是由 TTS 层兜底。

### 保存音色

现有保存音色 manifest 已经包含 `audio_path`、`ref_audio_text`、`workflow_key`、`model_slug`。需要补充 OmniVoice slug 识别：

- OmniVoice 工作流统一归类为 `omnivoice`。
- 保存名称建议形成独立后缀，例如 `班哥-omnivoice`。
- IndexTTS2 音色和 OmniVoice 音色分开展示，避免不同模型复用同一条不兼容配置。

当用户选择 OmniVoice 保存音色时，项目应把保存的 `ref_audio_text` 注入新工作流的 `reference_audio_text` 参数。

### 前端行为

普通前端不新增 OmniVoice 超长分块开关。默认体验应是：

- 选择或默认使用 OmniVoice 工作流。
- 用户选择保存音色或上传参考音频。
- 长稿直接提交。
- 后端自动处理超长保护分块。

现有 `TTS 分段模式` 文案需要调整，不再写成只服务 IndexTTS2 的默认说明。推荐把普通展示收敛为“内部智能分段”，把 IndexTTS2 外部分段保留在高级场景或兼容路径中。

### 错误处理

- 如果某个大块生成失败，错误信息应包含块序号、总块数和文本预览。
- 失败不应静默吞掉，也不应报告整篇文本不明原因失败。
- 拼接前必须验证每个大块输出文件存在且音频时长可读取。
- 如果保存音色没有 `reference_audio_text`，允许工作流回退到 OmniVoice 的 Whisper ASR，但日志应明确说明发生了自动转写。
- 如果工作流不是 OmniVoice，不启用该超长保护分块。

### 观测与验证

生成任务应记录分块计划，至少包含：

- 分块模式：`omnivoice_master_track_longform`
- 块数量
- 每块字符数
- 每块文本预览
- 每块输出路径
- 最终拼接音频路径

测试重点：

- 新 OmniVoice API 工作流可被 `WorkflowParser` 解析出 `text`、`ref_audio`、`reference_audio_text`。
- 默认 TTS 工作流切换到 `selfhost/tts_omnivoice_bf16.json`。
- OmniVoice 工作流 slug 推断为 `omnivoice`。
- 主音轨超长文本会生成多个保护块。
- 短文本不会被项目级保护分块。
- 逐帧模式不会启用超长保护分块。
- 英文小数、域名、常见缩写不会被句号误切。
- 大块失败时错误包含块序号和文本预览。

## 风险与约束

- OmniVoice Longform 虽然没有明显 4 分钟总时长硬限制，但半小时全文单次提交仍不适合作为默认产品行为。
- 按字符预算近似 5-10 分钟不是精确时长，后续可以基于语速或历史音频时长校准。
- 不同语言的句末识别复杂度不同，初始版本应覆盖中文和英文主路径，并通过测试保护常见误切。
- 该设计依赖新的 API 工作流正确暴露参数，不能直接把 UI 版 `OmniVoice_bf16.json` 作为项目默认 TTS 工作流。

## 通过标准

- 新项目默认配置使用 OmniVoice bf16 API 工作流。
- OmniVoice 保存音色可以保存、列表过滤、二次选择，并传入参考文本。
- 10-15 分钟主音轨文本会被自动保护分块，用户无需额外设置。
- 30 分钟级文本不会作为单个 ComfyUI 任务整体提交。
- IndexTTS2 原有外部分段和回退能力不被破坏。
- 相关测试通过，文档说明补齐。
