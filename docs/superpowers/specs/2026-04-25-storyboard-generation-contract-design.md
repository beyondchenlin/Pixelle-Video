# Storyboard Generation Contract 设计方案

## 1. 结论

Pixelle 的分镜生成不应继续依赖“先切旁白，再一段旁白生成一个图片提示词”的隐式流程。新的设计应建立平台级 `Storyboard Generation Contract`，把“文案”“分镜计划”“分镜增强”“最终图片提示词”拆成四个独立事实源。

目标链路：

```text
source_text
  -> StoryboardGenerationService
  -> StoryboardPlan
  -> StoryboardEnhancer
  -> ImagePromptComposer
  -> image_prompts
  -> media generation / render
```

核心原则：

- 内容生成只负责得到完整文案，不负责决定画面数量。
- 分镜生成只负责把完整文案解释成视觉分镜，不负责直接生成最终图片 prompt。
- 分镜增强只负责镜头、角色、世界观、一致性。
- 图片提示词编排只负责合成 `StoryboardPlan + prompt_prefix + style profile + storyboard controls`。
- TTS 拆分、字幕拆分、文本渲染不参与分镜数量决策。

这不是给现有 `split_mode` 增加选项，而是把当前隐含在 `ctx.narrations` 里的分镜事实正式建模。`ctx.narrations` 后续应由 `StoryboardPlan.frames[*].narration_text` 派生，而不是作为分镜的上游事实源。

## 2. 背景依据

本次代码扫描覆盖了以下核心位置：

- `web/components/content_input.py`：当前 fixed 模式暴露 `split_mode`，generate 模式暴露 `n_scenes`。
- `web/components/output_preview.py`：前端直连核心生成时会传 `split_mode`、`n_scenes`、storyboard controls、prompt prefix。
- `api/schemas/video.py`：`VideoGenerateRequest` 当前没有 `split_mode`，且 `extra="forbid"`，API 无法接收现有前端的固定文案拆分模式。
- `api/routers/video.py`：只转发 `n_scenes` 和 storyboard controls，不转发新的分镜策略字段。
- `pixelle_video/pipelines/standard.py`：generate 模式用 `n_scenes` 生成 narrations，fixed 模式用 `split_narration_script` 切出 `ctx.narrations`，后续图片 prompt 与 storyboard config 都依赖 `ctx.narrations`。
- `pixelle_video/utils/content_generators.py`：`split_narration_script` 已有 `sentence` 和 `punctuation`，但它只是旁白切分工具；`generate_styled_image_prompt_batch` 仍是一个 narration 对一个 prompt。
- `pixelle_video/services/storyboard_planner.py`：现有 planner 能增强镜头、角色和一致性，但明确要求 “exactly one frame plan per narration”，不能自行决定分镜数量，也不能重组完整文案。
- `pixelle_video/prompts/storyboard_planning.py`：prompt 也是围绕 narrations 输入设计。
- `pixelle_video/models/creation_package.py`：已经有 `storyboard_plan` 字段，可作为新契约的持久化承载点之一。
- `pixelle_video/services/persistence.py` 和 `pixelle_video/services/history_manager.py`：已经持久化 `planning_snapshot`，可扩展记录分镜生成方式、source ranges、诊断信息。

当前根因：

```text
文案切分结果 ctx.narrations
  -> 同时充当旁白单元、分镜单元、图片提示词输入、帧数量来源
```

这会导致：

1. 长文案被句子或标点机械拆碎后，单帧 prompt 只看局部文本。
2. 风格和角色一致性只能在后处理阶段补救。
3. `n_scenes` 在 generate 模式有效，在 fixed 模式被忽略，用户心智不一致。
4. `split_mode`、`tts_split_mode`、`n_scenes` 语义重叠，后续继续扩展会形成技术债。

## 3. 目标

V1 必须支持三种分镜方式：

1. `smart`：智能分镜。默认模式。大模型阅读完整文案，自动决定分镜数量；用户也可以手动指定分镜数量。
2. `punctuation`：按所有标点拆。只要是标点就拆，不区分标点类型，适合用户想强制细切。
3. `sentence`：按完整句意标点拆。按中文 `。！？` 和英文 `.!?` 等能表达独立句意的标点拆。

V1 必须保持解耦：

- 不改变 TTS 拆分契约。
- 不改变字幕和文本渲染契约。
- 不把图片 prompt 生成逻辑塞进智能分镜 prompt。
- 不让 prompt prefix、world preset、shot preset 分散到三种模式的各自实现里。

V1 必须从源头解决割裂感：

- 智能模式必须基于完整文案规划分镜。
- 三种模式都必须进入同一个分镜增强和图片提示词编排出口。
- 每一帧必须记录来自原文的文本范围或来源片段，便于回放、调试和后续编辑。

## 4. 非目标

本设计不包含：

- 图片生成模型能力改造。
- TTS、字幕、文本渲染重构。
- 用户手动逐帧编辑 UI。
- 分镜生成后的 VLM 自动评分闭环。
- 角色参考图、ControlNet 或图生图工作流强制接入。
- 旧 `/content/image-prompt` API 的立即删除。

这些可以在新契约稳定后扩展，但不应进入本轮源头改造。

## 5. 新参数契约

新增分镜专用参数，避免继续复用 `n_scenes` 和 `split_mode`。

```text
storyboard_mode:
  smart
  punctuation
  sentence

storyboard_count_mode:
  auto
  manual

storyboard_scene_count:
  integer | null

script_length_mode:
  auto
  short
  medium
  long
  custom

script_target_words:
  integer | null
```

默认值：

```text
storyboard_mode = smart
storyboard_count_mode = auto
storyboard_scene_count = null
script_length_mode = auto
script_target_words = null
```

约束：

- `smart + auto`：系统决定最终分镜数量。
- `smart + manual`：必须按 `storyboard_scene_count` 输出指定数量的分镜。
- `punctuation`：分镜数量由标点拆分结果决定。
- `sentence`：分镜数量由句意标点拆分结果决定。
- `storyboard_scene_count` 只能在 `storyboard_mode=smart` 且 `storyboard_count_mode=manual` 时出现。
- `storyboard_scene_count` 必须落在全局分镜数量上下限内。
- `script_target_words` 只能在 `script_length_mode=custom` 时出现。
- `script_length_mode` 只影响 generate 内容模式生成完整文案的长度，不影响分镜数量。

合法组合矩阵：

| storyboard_mode | storyboard_count_mode | storyboard_scene_count | 结果 |
| --- | --- | --- | --- |
| `smart` | `auto` | `null` | 合法，LLM 自动决定分镜数量 |
| `smart` | `manual` | `1..max_scene_count` | 合法，LLM 必须输出指定数量 |
| `smart` | `auto` | 非空 | 422 |
| `smart` | `manual` | 空 | 422 |
| `punctuation` | `auto` | `null` | 合法，按所有标点拆 |
| `punctuation` | `manual` | 任意 | 422 |
| `punctuation` | `auto` | 非空 | 422 |
| `sentence` | `auto` | `null` | 合法，按完整句意标点拆 |
| `sentence` | `manual` | 任意 | 422 |
| `sentence` | `auto` | 非空 | 422 |

配置硬契约：

```text
config.storyboard.min_scene_count
config.storyboard.max_scene_count
config.storyboard.max_source_chars
config.storyboard.script_default_target_words
config.storyboard.script_min_target_words
config.storyboard.script_max_target_words
config.storyboard.script_length_profiles.short.target_words
config.storyboard.script_length_profiles.medium.target_words
config.storyboard.script_length_profiles.long.target_words
```

这些不是建议值，而是 API、service 和测试共同依赖的上限/下限事实源。

破坏性迁移策略：

- 视频生成主链路不再接收 `n_scenes`。
- 视频生成主链路不再接收 `split_mode`。
- `VideoGenerateRequest` 必须删除 `n_scenes`，且不得新增 `split_mode`。
- 由于 `VideoGenerateRequest.extra="forbid"`，旧客户端继续传 `n_scenes` 或 `split_mode` 时应直接得到 422，而不是被静默映射。
- 前端 request builder 不再发送 `n_scenes` 或 `split_mode`。
- `standard.py` 不再读取 `ctx.params["n_scenes"]` 或 `ctx.params["split_mode"]`。
- `paragraph` 和 `line` 不进入新分镜系统，也不作为隐藏映射保留。
- 若独立内容生成 API 仍需要“生成 N 段旁白”能力，可以在内容 API 内继续使用 `n_scenes`，但它不属于视频分镜契约，也不能回流到标准视频 pipeline 决定画面数量。
- 历史记录可以只读展示旧任务中的 `n_scenes` 字段，但新任务必须展示 `storyboard_generation.resolved_scene_count`。

## 6. 核心数据模型

新增模型建议放在：

```text
pixelle_video/models/storyboard_plan.py
```

建议契约：

```python
class StoryboardGenerationMode(str, Enum):
    SMART = "smart"
    PUNCTUATION = "punctuation"
    SENTENCE = "sentence"


class StoryboardCountMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class ScriptLengthMode(str, Enum):
    AUTO = "auto"
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"
    CUSTOM = "custom"


@dataclass
class StoryboardPlanFrame:
    frame_id: str
    index: int
    source_text: str
    narration_text: str
    visual_goal: str
    prompt_intent: str
    shot_type: str | None
    shot_purpose: str | None
    primary_subject: str | None
    secondary_subjects: list[str]
    continuity_anchors: list[str]
    world_elements: list[str]
    source_start: int | None
    source_end: int | None
    metadata: dict[str, Any]


@dataclass
class StoryboardPlan:
    plan_id: str
    revision: int
    mode: StoryboardGenerationMode
    count_mode: StoryboardCountMode
    requested_scene_count: int | None
    resolved_scene_count: int
    source_text: str
    source_digest: str
    frames: list[StoryboardPlanFrame]
    diagnostics: dict[str, Any]
```

不变量：

- `resolved_scene_count == len(frames)`。
- `frame.index` 从 1 开始连续递增。
- `plan_id` 在一次分镜生成中稳定不变。
- `revision` 从 1 开始；任何重分镜、用户锁定字段重放或手动编辑都会递增。
- `frame.frame_id` 在同一个 `plan_id + revision` 内唯一。
- `frame.narration_text` 不为空。
- `frame.source_text` 是完整文案中的片段摘录，不是 source range 的索引基准。
- `source_start/source_end` 永远索引 `StoryboardPlan.source_text`，使用 Python 字符串切片语义：start 包含，end 不包含。
- `source_start/source_end` 都有值时必须满足 `0 <= source_start <= source_end <= len(StoryboardPlan.source_text)`。
- `frame.source_text` 应等于或语义覆盖 `StoryboardPlan.source_text[source_start:source_end]`；智能重组导致非连续来源时，`source_start/source_end` 可为空，并在 `metadata.source_spans` 记录多个来源片段。
- `smart + manual` 必须严格满足用户指定数量，除非超过全局上限或输入为空。
- 后续图片 prompt 数量必须等于 `len(frames)`。

## 7. 组件设计

### 7.0 ScriptGenerationService

新增服务建议放在：

```text
pixelle_video/services/script_generation.py
```

职责：

- 只服务 `mode=generate`。
- 接收用户输入的主题、可选标题、`script_length_mode`、`script_target_words`、语言和内容安全约束。
- 输出完整 `source_text`，而不是 narrations 列表。
- 输出诊断信息，例如目标字数、实际字数、是否触发 repair、使用的 prompt 版本。

长度控制：

- `script_length_mode=auto` 时，目标字数由 `config.storyboard.script_default_target_words`、输入主题复杂度和模板场景共同决定。
- `short/medium/long` 对应配置中的固定目标区间。
- `custom` 必须提供 `script_target_words`，并且落在 `script_min_target_words..script_max_target_words` 内。
- `storyboard_scene_count` 不得反向控制文案长度。

失败处理：

- 生成空文案、低于最小字数、明显偏离主题或结构化输出不合法时，允许一次 repair。
- repair 后仍失败时，返回明确错误。
- 不允许回退到 `generate_narrations_from_topic`，因为那会重新引入“先生成 N 段旁白”的旧事实源。

### 7.1 StoryboardGenerationService

新增服务建议放在：

```text
pixelle_video/services/storyboard_generation/
```

职责：

- 接收完整文案和分镜参数。
- 选择对应 strategy。
- 校验输出 `StoryboardPlan`。
- 返回统一结构给 pipeline。

它不应该：

- 调用图片生成。
- 拼最终 image prompt。
- 操作 TTS 拆分。
- 直接写 `Storyboard` 或 `StoryboardConfig`。

### 7.1.1 Override Identity

当前 `frame_overrides` 依赖 `scene_id` 和 `snapshot_identity`。新契约下，智能分镜会改变帧数量、顺序和来源片段，只靠 index 或 scene id 不能保证用户编辑回放到正确帧。

新 override 绑定模型：

```text
plan_id
plan_revision
frame_id
source_digest
locked_fields
override_source
```

规则：

- `frame_id` 是 frame override 的主绑定键。
- `plan_id + plan_revision + source_digest` 用于防止把旧计划的锁定字段应用到新文案或新分镜上。
- 当 source digest 或 revision 不匹配时，override 必须拒绝或进入显式 rebase 流程，不能静默套用。
- `scene_id` 可在历史 snapshot 中只读展示，但不再作为新 override 的主身份。

### 7.2 Strategy 层

建议结构：

```text
pixelle_video/services/storyboard_generation/strategy.py
pixelle_video/services/storyboard_generation/smart.py
pixelle_video/services/storyboard_generation/punctuation.py
pixelle_video/services/storyboard_generation/sentence.py
```

`SmartStoryboardStrategy`：

- 使用结构化 LLM 输出。
- 输入完整 `source_text`、可选目标分镜数量、storyboard controls 摘要。
- `auto` 模式让 LLM 决定数量，但必须受全局 min/max 限制。
- `manual` 模式要求 LLM 输出指定数量。
- 输出的是分镜语义计划，不是最终图片 prompt。

`PunctuationStoryboardStrategy`：

- 按 Unicode punctuation 类字符拆分。
- 保留标点在前一个片段中。
- 删除空片段。
- 不调用 LLM 决定数量。

`SentenceStoryboardStrategy`：

- 按中文 `。！？`、英文 `.!?` 拆分。
- 应保留结尾引号、括号等常见闭合符。
- 删除空片段。
- 不调用 LLM 决定数量。

确定性模式输出的 `visual_goal` 和 `prompt_intent` 可以先由原文片段派生，再交给增强层补足镜头和一致性信息。

### 7.3 StoryboardEnhancer

现有 `pixelle_video/services/storyboard_planner.py` 应调整为增强层或被增强层包装。

新职责：

- 接收 `StoryboardPlan.frames`，不是裸 `narrations`。
- 基于 world preset、shot preset、content mode、consistency strength、role strategy、frame overrides 增强每帧。
- 补充 `shot_type`、`shot_purpose`、`primary_subject`、`continuity_anchors`、`world_elements`。
- 保留 source frame identity，不改变帧数量，除非明确进入 replan 流程。

现有 “exactly one frame plan per narration” 的约束应改为：

```text
exactly one enhanced frame per StoryboardPlanFrame
```

### 7.4 ImagePromptComposer

新增或抽出统一提示词编排器。

职责：

- 接收增强后的 `StoryboardPlan`。
- 接收 resolved style profile、prompt prefix、media workflow、text rendering policy、native prompt hints。
- 调用或复用现有 `assemble_storyboard_prompt` / `build_image_prompt` 能力。
- 输出最终 `image_prompts`。

它是唯一允许把以下信息合成最终图片 prompt 的地方：

- prompt prefix
- style profile
- world preset
- shot preset
- frame visual goal
- frame prompt intent
- continuity anchors
- text rendering policy

这能避免 smart/punctuation/sentence 三种模式各自拼 prompt，造成风格不一致和后续难维护。

## 8. Pipeline 集成

### 8.1 StandardPipeline

当前 `standard.py` 应从：

```text
generate_content -> ctx.narrations
plan_visuals(ctx.narrations) -> image_prompts
initialize_storyboard(zip(narrations, image_prompts))
```

调整为：

```text
generate_content -> ctx.source_text
plan_storyboard(ctx.source_text) -> ctx.storyboard_plan
plan_visuals(ctx.storyboard_plan) -> ctx.image_prompts
initialize_storyboard(ctx.storyboard_plan, ctx.image_prompts)
```

`ctx.narrations` 可以继续存在，但应成为派生字段：

```text
ctx.narrations = [frame.narration_text for frame in ctx.storyboard_plan.frames]
```

### 8.2 Generate 内容模式

当前 generate 模式是直接生成 `n_scenes` 个 narrations。新契约下更好的做法是：

```text
topic/text prompt -> complete script/source_text -> storyboard generation
```

也就是说内容生成层应新增 `ScriptGenerationService`，把主题生成完整文案，而不是生成固定数量旁白。`generate_narrations_from_topic` 可以继续服务独立内容 API 或测试工具，但标准视频生成链路不应再依赖它决定分镜数量。

generate 模式流程：

```text
user topic / instruction
  -> ScriptGenerationService
  -> source_text
  -> StoryboardGenerationService
  -> StoryboardPlan
```

`ScriptGenerationService` 的输出必须进入 `ctx.source_text`，后续分镜数量只由 `StoryboardGenerationService` 决定。若完整文案生成失败，pipeline 应直接失败并返回可理解错误，不得降级到旧 narration 生成路径。

### 8.3 Fixed 内容模式

用户输入文案时：

```text
user text -> source_text -> storyboard generation
```

fixed 模式不再直接调用 `split_narration_script` 产出最终分镜，而是根据 `storyboard_mode` 选择 strategy。

## 9. API 和前端

### 9.1 API

`api/schemas/video.py` 新增：

```python
storyboard_mode: StoryboardGenerationMode = "smart"
storyboard_count_mode: StoryboardCountMode = "auto"
storyboard_scene_count: Optional[int] = None
script_length_mode: ScriptLengthMode = "auto"
script_target_words: Optional[int] = None
```

校验：

- `storyboard_mode/storyboard_count_mode/storyboard_scene_count` 必须满足第 5 节合法组合矩阵。
- `storyboard_scene_count` 超过配置上下限时返回 422。
- `script_length_mode=custom` 时，`script_target_words` 必须存在。
- `script_length_mode!=custom` 时，`script_target_words` 必须为空。
- `script_target_words` 超过配置上下限时返回 422。
- `n_scenes` 和 `split_mode` 不属于 `VideoGenerateRequest`。
- 视频生成 API 收到 `n_scenes` 或 `split_mode` 时返回 422，不做静默映射。
- 独立内容 API 若继续保留 `n_scenes`，必须在文档中说明它只表示“生成几段文本”，不表示“视频分镜数量”。

`api/routers/video.py` 应把这些字段转发到核心生成参数。

建议新增独立预览接口：

```text
POST /content/storyboard-plan
```

用途：

- 只生成分镜计划，不生成图片。
- 便于前端未来做分镜预览、调试和手动编辑。
- 便于测试智能分镜质量。

### 9.2 前端

文案输入区应拆成两个概念：

```text
内容来源：
  - AI 生成文案
  - 使用用户文案

分镜方式：
  - 智能分镜
  - 按所有标点拆
  - 按完整句子拆
```

智能分镜下显示：

```text
分镜数量：
  - 自动
  - 手动指定 N 个
```

确定性模式下不显示分镜数量控制，只显示说明：分镜数量由拆分结果决定。

原来的 paragraph/line 选项不进入新 UI，也不作为隐藏映射保留。

## 10. 持久化和可观测性

`CreationPackage.storyboard_plan` 应成为新分镜计划的主要持久化位置之一。`Storyboard.planning_snapshot` 继续记录便于 UI 预览和历史回放的信息。

建议 `planning_snapshot` 增加：

```json
{
  "storyboard_generation": {
    "plan_id": "plan_...",
    "revision": 1,
    "mode": "smart",
    "count_mode": "auto",
    "requested_scene_count": null,
    "resolved_scene_count": 8,
    "strategy_version": "storyboard_generation_v1",
    "source_digest": "...",
    "diagnostics": {}
  },
  "frames": [
    {
      "frame_id": "frame_01_...",
      "index": 1,
      "source_text": "...",
      "narration_text": "...",
      "source_start": 0,
      "source_end": 24,
      "visual_goal": "...",
      "prompt_intent": "...",
      "shot_type": "...",
      "continuity_anchors": []
    }
  ]
}
```

日志应记录：

- strategy 名称。
- 输入字数。
- requested/resolved 分镜数量。
- LLM retry 次数。
- fallback 或失败原因。
- prompt composer 输出数量。

## 11. 错误处理

智能分镜：

- 使用结构化输出。
- 第一次输出不满足 schema 时，进行一次 repair retry。
- repair 后仍不合法时，不应静默降级到句子拆分；应返回明确错误，避免用户以为使用了智能分镜。
- 若用户手动指定数量，LLM 输出数量不匹配时必须 repair；不能直接截断当作成功。

确定性分镜：

- 输入为空时返回用户可理解错误。
- 拆分后没有有效片段时，将整段文本作为一个分镜。
- 超过全局最大分镜数时，应返回错误或要求用户改用智能分镜；不应静默截断。

Prompt 编排：

- 最终 image prompt 数量必须等于 `StoryboardPlan.frames` 数量。
- prompt prefix 只能在 composer 层应用一次。
- 如果 storyboard enhancer 失败，可根据配置允许跳过增强，但必须在 snapshot 中记录 `enhancement_status=skipped/failed`。

## 12. 测试范围

必须新增或更新测试：

1. `StoryboardPlan` 模型不变量。
2. `punctuation` strategy：中英文标点、连续标点、空片段、全标点输入。
3. `sentence` strategy：中文句号问号感叹号、英文 `.?!`、引号闭合。
4. `smart` strategy：mock LLM 结构化输出、auto 数量、manual 数量、repair。
5. `ScriptGenerationService`：auto/short/medium/long/custom 长度控制、repair、失败不回退到 narrations。
6. `StoryboardGenerationService`：三种 strategy 路由。
7. 参数矩阵：非法的 `storyboard_mode/storyboard_count_mode/storyboard_scene_count` 组合返回 422。
8. `source_start/source_end`：索引基准永远是 `StoryboardPlan.source_text`。
9. override identity：`plan_id/frame_id/source_digest/revision` 不匹配时拒绝静默套用。
10. `StoryboardEnhancer`：一帧输入对应一帧增强输出。
11. `ImagePromptComposer`：prompt prefix 只应用一次，输出数量等于帧数。
12. `StandardPipeline`：generate/fixed 都先得到 source_text，再得到 `StoryboardPlan`。
13. API schema：新字段校验，视频生成 API 对 `n_scenes` 和 `split_mode` 返回 422。
14. 前端 request builder：默认智能分镜，手动数量传参，确定性模式不传无效数量。
15. 持久化：`storyboard_plan` 和 `planning_snapshot.storyboard_generation` 可保存和恢复。
16. 回归测试：TTS split、text rendering、asset_based pipeline 不因分镜改造改变行为。

## 13. 迁移计划

推荐分阶段实施，但切换到新入口必须是原子切换，不能先删除旧字段再补新能力。

### 阶段 1：内部契约落地，不切入口

- 新增 `StoryboardPlan` 模型，包括 `plan_id`、`revision`、`source_digest`、`frame_id`、`source_start/source_end`。
- 新增配置硬契约：分镜数量上下限、source text 最大长度、script target words 上下限。
- 新增 `ScriptGenerationService` 和 `StoryboardGenerationService` 的空集成测试。
- 旧视频生成入口保持不变，避免中间断档。

### 阶段 2：三种 strategy 和完整文案生成

- 实现 `ScriptGenerationService`。
- 实现 `punctuation`、`sentence`、`smart` 三种 strategy。
- smart strategy 支持 auto/manual 数量、repair retry 和不变量校验。
- 所有 strategy 只输出 `StoryboardPlan`，不生成最终 image prompt。

### 阶段 3：增强层和 composer 收口

- 调整现有 `storyboard_planner.py` 为增强 `StoryboardPlanFrame`。
- 抽出 `ImagePromptComposer`。
- 确保三种模式最终统一进入 composer。
- 在内部测试路径中验证 `StoryboardPlan -> enhanced plan -> image_prompts` 完整闭环。

### 阶段 4：视频主链路原子切换

- 同一次变更内切换 `StandardPipeline`、`VideoGenerateRequest`、`api/routers/video.py`、前端 request builder。
- 视频生成请求新增 `storyboard_mode/storyboard_count_mode/storyboard_scene_count/script_length_mode/script_target_words`。
- 视频生成请求删除 `n_scenes`，并继续禁止 `split_mode`。
- 前端不再发送 `n_scenes/split_mode`。
- `standard.py` 不再调用 `generate_narrations_from_topic` 或 `split_narration_script` 决定分镜。
- 测试必须证明新入口可完整生成 storyboard 和 image prompts。

### 阶段 5：持久化、历史和预览

- `planning_snapshot` 和 `CreationPackage.storyboard_plan` 持久化新结构。
- 历史页新任务展示 `resolved_scene_count`，旧任务只读展示旧 `n_scenes`。
- 添加 `/content/storyboard-plan` 预览接口。
- override 使用 `plan_id/frame_id/source_digest/revision`。

### 阶段 6：旧事实源隔离

- 新 UI 不再暴露 paragraph/line split。
- 独立内容 API 可以继续保留 `n_scenes`，但文档和测试必须证明它不会流入标准视频 pipeline。
- 旧 `/content/image-prompt` 只作为独立内容工具保留，不属于标准视频分镜主链路。
- 更新文档和测试，防止新代码继续依赖 `ctx.narrations` 作为分镜事实源。

## 14. 两轮设计复审结论

第一轮复审结论：

- 原方案中 “StoryboardPlan 作为统一出口” 是正确方向。
- 但必须进一步明确：智能分镜不能直接生成最终图片 prompt，只能生成分镜语义计划。
- 最终图片 prompt 必须由统一 composer 合成。

第二轮复审结论：

- 最大技术债风险不是三种模式本身，而是继续复用 `n_scenes`、`split_mode`、`ctx.narrations` 这三个旧事实源。
- 新契约必须显式引入 `storyboard_mode`、`storyboard_count_mode`、`storyboard_scene_count`。
- `ctx.narrations` 必须降级为派生字段。
- `CreationPackage.storyboard_plan` 和 `planning_snapshot` 必须承担回放和诊断责任。

最终判断：

这项改造的最佳实践不是“新增智能分镜选项”，而是建立 `Storyboard Generation Contract`。只有把分镜计划变成正式事实源，才能从源头解决长文案图片割裂、风格不统一、数量控制混乱和后续难维护的问题。

## 15. 旧字段清理专项复审

用户确认倾向于“不要兼容旧字段”后，重新检查了旧字段在当前代码里的扩散范围：

- `n_scenes` 当前散落在 API、前端、pipeline、history、tests 和内容生成工具中。
- `split_mode` 当前散落在前端、标准 pipeline、拆分工具和测试中。
- `ctx.narrations` 当前仍被标准 pipeline 当作分镜事实源使用。
- `generate_narrations_from_topic` 当前会让 generate 模式天然回到“先生成 N 段旁白”的旧思路。
- `split_narration_script` 当前会让 fixed 模式天然回到“按文本片段就是分镜”的旧思路。

专项复审结论：

1. `n_scenes` 不能作为 `storyboard_scene_count` 的兼容别名。旧语义是“生成几段旁白”，新语义是“智能分镜目标数量”，静默映射会制造长期误用。
2. `split_mode` 不能作为 `storyboard_mode` 的兼容别名。旧语义包含 paragraph/line/sentence/punctuation，新语义只允许 smart/punctuation/sentence。
3. `paragraph` 和 `line` 不应保留为隐藏模式。它们不属于本轮用户确认的三种分镜方式，保留会让新系统继续携带旧产品心智。
4. 独立内容 API 可以继续拥有 `n_scenes`，但必须和视频分镜 API 隔离。它只能表示“生成几段文本”，不能表示“视频几张分镜”。
5. 视频生成 API 应利用 `extra="forbid"` 明确拒绝旧字段。这样错误会尽早暴露，不会在 pipeline 内部产生难排查的行为差异。

最终决策：

视频生成主链路执行破坏性迁移，不做旧字段兼容。新请求只接受 `storyboard_mode`、`storyboard_count_mode`、`storyboard_scene_count`、`script_length_mode`、`script_target_words` 等新契约字段。旧字段只允许出现在历史记录读取、独立内容生成 API 或已隔离的旧测试中，不能参与新视频分镜流程。
