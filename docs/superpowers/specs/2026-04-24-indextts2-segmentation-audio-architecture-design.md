# IndexTTS2 Segmentation Audio Architecture Design

## Goal

重构 Pixelle 的 IndexTTS2 声音生成链路，从源头解决长文本分段、外部分段与引擎内部分段边界不清、段间拼接、字幕对齐和画面提示词耦合带来的语气断裂、爆音、停顿不自然等问题。

目标不是做临时参数补丁，而是建立一套可长期维护的 TTS 分段架构：

- 默认使用 IndexTTS2 官方内部 token/标点分段能力。
- 支持 Pixelle 外部分段成为唯一主分段器。
- 支持大模型只提供语义边界建议，本地严格按原文切片。
- 声音、字幕、画面提示词分开规划，通过明确数据结构连接。
- 所有失败可观测、可回退、可复现，避免静默生成低质量结果。

## Current Problems

### Responsibility Is Mixed

当前链路里，TTS 分段、画面分镜、字幕对齐和音频裁切共享了过多中间结构。这样会导致一个为画面服务的切分结果影响声音自然度，或者一个为 TTS 服务的切分结果影响图片提示词质量。

### IndexTTS2 Is Not Treated As An Engine Contract

当前 ComfyUI IndexTTS2 节点行为更像第三方黑盒调用。Pixelle 没有稳定表达“整段交给内部逻辑”、“外部已经切好，内部禁止再切”、“段间静音如何处理”、“超预算如何失败”等契约。

### Current External Splitting Can Change Speech Intent

现有 TTS block 组织逻辑会把短语拆开再重组，并可能在 block 末尾补终止标点。这会把“还没说完”的语气变成“句子结束”的语气，造成段与段之间不连贯。

### Internal Split Should Remain Engine-Owned

IndexTTS2 官方推理链支持整段输入后内部按 token/标点分段，这是合理能力。Pixelle 不应该为了外部分段而禁止这层内部逻辑；Pixelle 的职责是决定是否先把长文切成更合适的 source segment，再把每个 segment 原样交给现有 IndexTTS2 workflow。

### Audio Boundary Processing Is Too Late And Too Hard

当前部分路径会先生成 master audio，再按时间硬切成 per-frame audio。切点一旦落在音素中间，就容易产生 click、爆音、残留气声。中间使用 MP3 还会放大边界问题。

## Principles

1. 原文是唯一真相。任何模式都不能改写文案内容；分段只能记录原文 span。
2. TTS 分段、视觉分段、字幕对齐是三个规划器，不能混成一个切分器。
3. Pixelle 定义 TTS 分段计划，具体 TTS 引擎只负责执行计划。
4. 所有中间音频使用 WAV/PCM，最终导出阶段再编码。
5. 超预算和对齐失败必须显式记录，不能静默降级成不可解释结果。
6. 默认模式必须质量稳定，高级模式必须可观测、可回退。

## Architecture

### Relationship To `tts_audio_strategy`

`tts_split_mode` 和现有 `tts_audio_strategy` 是两个独立维度：

- `tts_audio_strategy` 决定音频组织方式：`per_frame` 还是 `master_track`。
- `tts_split_mode` 决定一段待合成文本如何交给 IndexTTS2：默认不外切，或 Pixelle 外部预切。

组合规则：

- `master_track + internal_only`：以完整 narration master text 作为一个 Pixelle source unit，交给 IndexTTS2 内部分段并生成 master audio。
- `master_track + external_only`：先对完整 narration master text 生成 `TtsSegmentationPlan`，逐 segment 合成后拼成 master audio。
- `per_frame + internal_only`：每个 frame narration 是一个 Pixelle source unit，不再做 90 字 phrase regroup。
- `per_frame + external_only`：只在单个 frame narration 超预算或用户显式启用时，对该 frame narration 做外部分段。

这样可以避免把“音频按 master 还是 frame 组织”和“文本按什么规则分段”混成一个配置。

### New Responsibility Boundaries

新增三个明确层次：

- `TtsSegmentationPlanner`：根据模式生成 TTS 分段计划，只处理文本边界。
- `TtsSynthesisEngine`：执行分段计划并返回 segment audio，不决定文本如何切。
- `AudioAssemblyService`：拼接 WAV、处理段间 fade、生成 master audio 和派生 clip。

视觉提示词和字幕对齐不直接复用 TTS 分段器：

- `VisualPromptPlanner` 负责根据语义生成图片提示词规划。
- `SubtitleAlignmentPlanner` 负责把最终音频和文本对齐。
- 两者可以读取 `TtsSegmentationPlan` 作为参考，但不能把它当成唯一切分依据。

### Existing Plugin Boundary

本设计不修改 IndexTTS2 插件内部推理逻辑，也不要求 `split_strategy` 这类新节点参数。Pixelle 只通过现有 workflow 暴露的 `text` 和 `ref_audio` 参数调用 IndexTTS2。

因此：

- `internal_only` 是一次调用，把当前 source unit 完整传给 IndexTTS2。
- `external_only` 是多次调用，Pixelle 先切出多个原文 segment，再分别传给 IndexTTS2。
- 每次调用进入 IndexTTS2 后，插件仍可按它自己的内部 token/标点逻辑继续处理。
- Pixelle 不向 workflow 传递未暴露的假参数，避免形成“看起来可控、实际无效”的技术债。

### TTS Split Modes

#### `internal_only`

默认模式。

行为：

- Pixelle 不做外部分段。
- Pixelle 把当前 source unit 的完整 narration text 传给 IndexTTS2。
- IndexTTS2 使用官方内部 token/标点逻辑分段。
- Pixelle 记录返回的音频、参数和执行结果。

适用场景：

- 大多数普通文案。
- 需要先验证模型原生能力。
- 用户没有特殊边界控制需求。

#### `external_only`

高级模式，默认关闭。

行为：

- Pixelle 根据原文和预算生成 deterministic segment spans。
- 优先在完整句末标点处切分：`。！？；.!?;`
- 找不到完整句末标点时，再在逗号类标点处切分：`，、,`
- 仍然找不到时，按硬预算切分并标记为 `hard_limit`。
- 每个 segment 单独传给 IndexTTS2。
- IndexTTS2 收到每个 segment 后，仍然允许使用现有内部逻辑继续按 token/标点处理。

适用场景：

- 用户需要可控段落边界。
- 后续要与字幕、镜头或提示词进行更细粒度联动。
- 官方内部切分听感不满足项目要求。

#### Future: Semantic Boundary Assistance

当前运行时不暴露大模型语义分段开关。

原因：

- 现阶段没有完整接入边界建议服务、校验回退和可观测 metadata。
- 半实现模式会让用户以为启用了语义分段，但实际只是 deterministic external split。
- 后续如接入大模型，必须保持“大模型只返回边界索引，本地按原文 slice”的原则，并以独立任务实现。

## Data Model

### `TtsSegmentationPlan`

字段：

- `plan_id`
- `mode`
- `source_text_hash`
- `source_char_count`
- `source_unit_type`
- `source_unit_id`
- `segments`
- `engine_segments`
- `config`
- `warnings`
- `engine_request`
- `engine_response_metadata`

用途：

- 作为一次 TTS 生成的可复现输入。
- 给日志、调试、前端预览、字幕对齐、回放分析提供证据。
- `internal_only` 模式下，Pixelle 的 `segments` 可以只有一个覆盖完整 source unit 的 segment；如果 IndexTTS2 返回内部 segment preview，则记录到 `engine_segments`，但不把它当成 Pixelle 主分段。
- 如果 ComfyUI 节点无法返回内部 segment 明细，Pixelle 仍必须记录 request-side plan 和 workflow 参数；内部 segment 明细只作为诊断增强，不作为正确性前提。

### `TtsSegment`

字段：

- `id`
- `text`
- `synthesis_text`
- `source_start`
- `source_end`
- `boundary_type`
- `is_continuation`
- `char_count`
- `token_count`
- `split_reason`
- `synthesis_mode`
- `overflow_policy`
- `audio_path`
- `duration_ms`
- `sample_rate`
- `channels`

约束：

- `text == source_text[source_start:source_end]`
- 所有 segment 按顺序拼接后必须等于原文。
- `synthesis_text` 是传给具体 TTS 引擎的文本，允许由引擎适配层做官方 normalization；它不能反向覆盖 `text` 或原文 span。
- `source_start` 和 `source_end` 使用 Python 字符索引，不使用 byte offset。

### `boundary_type`

取值：

- `sentence`：在完整句末标点切分。
- `clause`：在逗号类标点切分。
- `hard_limit`：没有合适标点，被预算强制切分。
- `llm`：来自 LLM 建议，且本地校验通过。
- `internal`：`internal_only` 模式下由 IndexTTS2 内部处理，Pixelle 不声明内部边界。

### `is_continuation`

用于表达语气是否应当连续。

- `false`：自然句末或语义完整段。
- `true`：该段是被预算切开的续接段，不应在外部补句号或强造句末语气。

## Deterministic External Splitter

### Budget Model

外部分段使用字符预算：

- 前端展示 `max_chars_per_tts_segment`，默认 `90`。

字符预算是用户可理解且 Pixelle 能可靠执行的主参数。IndexTTS2 内部 token 安全由插件自己的分段逻辑继续处理。

如果文本包含换行、连续空白或 Markdown 残留，外部分段器仍然以原文索引切片；清理或 normalizer 只允许发生在 `synthesis_text` 层，并且需要记录到 plan metadata。

### Boundary Search

对每个窗口：

1. 从当前位置向后取 `max_chars_per_tts_segment` 作为目标点。
2. 在目标点附近查找完整句末标点。
3. 找不到时查找逗号类标点。
4. 找不到时使用硬切。
5. 切分结果保留原文文本，不补标点、不删标点、不改标点。

边界搜索要有可配置窗口，例如目标点前后各 `20` 个字符。默认优先选择不超过预算的边界；只有允许 `soft_overflow` 时才可向后越过预算寻找更自然边界。

### Continuation Rules

如果切在逗号类标点、硬限制、或 LLM 判断的非完整语义结尾：

- `is_continuation=true`
- 不补句号
- 不在拼接阶段插入长静音

如果切在完整句末标点：

- `is_continuation=false`
- 可使用正常 segment gap

## LLM Boundary Adapter

### LLM Output Contract

LLM 只能输出边界位置，不输出文本段落。

推荐输出：

```json
{
  "boundaries": [
    {"end": 42, "reason": "sentence"},
    {"end": 96, "reason": "semantic_scene"}
  ]
}
```

### Local Validation

Pixelle 必须执行：

1. 边界必须为整数。
2. 边界必须严格递增。
3. 边界必须落在原文范围内。
4. 根据边界切出的所有片段拼接后必须与原文完全一致。
5. 每段必须满足字符预算和 token 预算。
6. 任何失败都不能使用 LLM 结果。

### Fallback

失败时：

- 记录 warning 和失败原因。
- 回退 deterministic `external_only`。
- 前端可显示“语义分段建议未通过校验，已使用本地分段”。

## ComfyUI IndexTTS2 Boundary

Pixelle 不修改 IndexTTS2 插件内部逻辑。当前 workflow contract 只依赖已存在并可被 `WorkflowParser` 识别的参数：

- `text`
- `ref_audio`

Pixelle 不传递以下未在 workflow 中暴露的参数：

- `split_strategy`
- `max_text_tokens_per_segment`
- `interval_silence_ms`
- `overflow_policy`

如果未来确实需要控制这些参数，必须先让 workflow 显式暴露参数并补充 workflow parser 测试；否则不允许在仓库侧传递“看起来存在、实际不生效”的参数。

当前阶段的 `external_only` 含义是“Pixelle 外部预切分”，不是“IndexTTS2 内部禁止切分”。

## Audio Assembly

### Intermediate Format

所有中间音频统一使用 WAV/PCM。

禁止：

- segment 阶段输出 MP3 后再切。
- master audio 阶段用有损格式中转。

允许：

- 最终视频 mux 或导出阶段编码成目标格式。

所有 segment audio 在拼接前必须统一：

- sample rate
- channel layout
- sample format
- loudness 或 peak normalization policy

如果任一 segment 规格不一致，`AudioAssemblyService` 负责显式转换并记录 metadata。

### Segment Concatenation

拼接规则：

- `sentence` 边界可插入短静音，例如 `20-80ms`。
- `clause` 和 `hard_limit` 边界默认不插入长静音。
- 所有 segment 边界做极短 fade，例如 `5-10ms`。
- fade 只处理接口 click，不承担降噪职责。
- 默认使用 fade-out/fade-in，不默认使用 overlap crossfade；只有 continuation 边界经过验证后才允许启用短 crossfade。

### Master Track And Frame Clip

master track 是声音主产物。

如果 legacy 渲染仍需要 per-frame audio：

- 从 master track 派生 frame clip。
- 派生 clip 使用 WAV。
- clip 边界做短 fade。
- 对齐失败不能静默比例分配为最终高质量路径。

对齐失败策略：

- `strict`：失败即报错。
- `fallback_per_segment`：回退到 TTS segment 时间线。
- `duration_estimate`：仅作为低优先级兼容模式，并写入 warning。

## Visual Prompt Planning

视觉提示词不直接复用 TTS segment。

原因：

- TTS segment 追求声音自然和模型预算。
- 视觉 prompt 追求画面完整性和镜头语义。
- 一句话可能适合多张图，两句话也可能只适合一张图。

推荐设计：

- `VisualPromptPlanner` 读取全文和可选 TTS plan。
- 支持按句、按语义块、按 LLM 规划生成 prompt units。
- LLM 生成视觉规划时可以改写 prompt，但不能改写原始 narration。

## Subtitle Alignment

字幕同步不应反推 TTS 分段。

推荐设计：

- TTS 先生成 master audio。
- 字幕对齐使用最终 master audio 和原文。
- 有 forced aligner 时使用 forced aligner。
- 没有 forced aligner 时使用 segment 时间线和字符比例作为降级路径，并明确标记精度等级。

字幕数据需要记录：

- `alignment_source`
- `confidence`
- `source_text_span`
- `audio_start`
- `audio_end`

## Configuration

新增配置字段：

- `tts_split_mode`: `internal_only | external_only`
- `max_chars_per_tts_segment`
- `tts_split_overflow_policy`
- `tts_boundary_search_radius`
- `tts_soft_overflow_chars`
- `tts_audio_boundary_fade_ms`

默认值：

- `tts_split_mode=internal_only`
- `max_chars_per_tts_segment=90`
- `tts_split_overflow_policy=hard_limit`
- `tts_audio_boundary_fade_ms=8`

## Frontend

默认界面只显示：

- `TTS 分段模式：内部智能分段`

高级设置显示：

- `外部分段`
- `最大字符数`
- `边界淡入淡出`
- `溢出策略`

前端文案原则：

- 默认推荐 `内部智能分段`。
- `外部分段` 标注为“更可控，适合精调”。
- `语义辅助分段` 标注为“实验，本地会校验并自动回退”。

## Implementation Phases

### Phase 1: Core Types And Planner Boundary

新增 `TtsSegmentationPlan` 和 `TtsSegment`，让后续所有路径围绕同一数据结构工作。

产出：

- 类型定义。
- deterministic external splitter。
- plan validation。
- 单元测试覆盖原文拼接不变、标点边界、硬切、LLM 失败回退。

### Phase 2: Existing IndexTTS2 Workflow Boundary

产出：

- 确认 `workflows/selfhost/tts_index2.json` 只依赖 `text` 和 `ref_audio` 动态输入。
- 仓库侧不传未暴露的假参数。
- `external_only` 通过多次 TTS 调用实现，每段调用后仍由 IndexTTS2 内部逻辑处理。
- workflow parser 测试覆盖当前参数边界。

### Phase 3: Pixelle Pipeline Integration

把 Pixelle 默认 IndexTTS2 路径接到 `internal_only`。

产出：

- 默认不再执行旧的 90 字 phrase regroup。
- 保留现有流程兼容。
- 输出 plan metadata。
- 日志能看到使用的 split mode 和 segment summary。
- `StoryboardConfig`、config schema、persistence、render package、Web UI request path 全部贯通新增字段。

### Phase 4: External Split Mode

接入 `external_only`。

产出：

- external 分段结果可预览。
- 所有 warning 可被任务日志和前端展示。

### Phase 5: Audio Assembly Redesign

重做中间音频格式和拼接边界处理。

产出：

- 中间 WAV/PCM。
- segment concat fade。
- master track 作为主音频。
- legacy frame clip 派生时使用 WAV 和短 fade。
- 对齐失败策略显式化。

### Phase 6: Frontend And Validation Suite

前端接入两种模式和高级参数。

产出：

- 默认 internal-only。
- 高级开关默认关闭。
- A/B 听感样本脚本。
- 200 字、500 字、1000 字文本测试集。
- 回归测试确认旧配置仍可运行。

## Acceptance Criteria

1. 默认 `internal_only` 能整段传入 IndexTTS2，不再走旧的 90 字 phrase regroup。
2. `external_only` 生成的所有 segment 拼接后与原文完全一致。
3. `external_only` 下 Pixelle 会先做外部预切分，但每个 segment 进入 IndexTTS2 后仍允许插件内部继续处理。
4. 拼接和派生音频链路使用 WAV/PCM；TTS 引擎原始输出可先被标准化成 WAV。
5. segment 边界有短 fade，且不会引入明显额外停顿。
6. 对齐失败在日志和 metadata 中可见。
7. 前端默认模式为 internal-only，高级模式默认关闭。
8. 任务输出包含 TTS split mode、segment count、warnings、audio assembly strategy。
9. 仓库不向 `tts_index2.json` 传递 workflow 未暴露的假参数。
10. workflow parser 测试覆盖 `tts_index2.json` 当前参数边界。

## Test Strategy

### Unit Tests

覆盖：

- deterministic splitter 在句号、问号、感叹号、分号处优先切分。
- 找不到完整句末标点时使用逗号类标点。
- 找不到标点时使用 hard limit。
- 所有 segment 拼接后等于原文。
- `is_continuation` 在 clause 和 hard limit 下为 true。

### Integration Tests

覆盖：

- `internal_only` 不调用 external splitter。
- `external_only` 传递 segment list 给 TTS engine。
- ComfyUI workflow 参数不包含未暴露的 split mode、interval silence 或 token budget。
- pipeline metadata 记录 plan summary。

### Audio Validation

使用固定文本集生成样本：

- 120-200 字短文本。
- 400-600 字中长文本。
- 1000 字以上长文本。
- 多标点中文文本。
- 中英数字混合文本。

验证：

- 没有明显爆音。
- 段间没有异常长停顿。
- 句意不被外部分段破坏。
- 失败场景有明确错误或 warning。
- 自动检测 boundary sample discontinuity、峰值削波和异常静音长度；人工听感只作为最终确认，不作为唯一验证。

## Risks

### Risk: Official IndexTTS2 Internal Split Is Still Better

缓解：

- 保持 `internal_only` 为默认。
- `external_only` 作为高级模式，不强行替代默认路径。

### Risk: External Only Exposes Token Budget Errors

缓解：

- 先用 token 估算做预检。
- `external_only` 默认 `error`，让 Pixelle 重新规划。

### Risk: Refactor Touches Existing Render Paths

缓解：

- 先引入数据结构和新 planner。
- 旧路径保持兼容。
- 每个 phase 独立测试和提交。

### Risk: Pixelle-Owned Node Diverges From Upstream IndexTTS2

缓解：

- 适配层尽量薄，只控制参数、分段契约、metadata 和错误语义。
- upstream 更新通过显式升级任务处理。
- workflow 和节点参数测试捕捉破坏性变更。

## Out Of Scope

以下内容不在本设计第一轮实现范围：

- 训练或微调 IndexTTS2 模型。
- 完全保留原始标点字形给模型。
- 重新设计所有字幕 UI。
- 重新设计图片生成提示词系统。
- 替换 forced aligner。

这些可以在新架构稳定后作为独立设计继续推进。
