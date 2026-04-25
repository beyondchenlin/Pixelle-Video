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
```

默认值：

```text
storyboard_mode = smart
storyboard_count_mode = auto
storyboard_scene_count = null
```

约束：

- `smart + auto`：系统决定最终分镜数量。
- `smart + manual`：必须按 `storyboard_scene_count` 输出指定数量的分镜。
- `punctuation`：分镜数量由标点拆分结果决定，忽略 `storyboard_scene_count`。
- `sentence`：分镜数量由句意标点拆分结果决定，忽略 `storyboard_scene_count`。
- `storyboard_scene_count` 必须有全局上限，建议进入配置，例如 `config.storyboard.max_scene_count`。

兼容策略：

- `n_scenes` 保留为旧入口。若新字段不存在，`mode=generate` 可映射为 `storyboard_mode=smart`，`storyboard_count_mode=manual`，`storyboard_scene_count=n_scenes`。
- `split_mode` 保留为旧入口。若新字段不存在，`split_mode=punctuation` 映射为 `storyboard_mode=punctuation`，`split_mode=sentence` 映射为 `storyboard_mode=sentence`。
- `paragraph` 和 `line` 不进入新 UI。旧请求可继续兼容一段时间，但内部应标记为 legacy deterministic segmentation。

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


@dataclass
class StoryboardPlanFrame:
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
    source_range: tuple[int, int] | None
    metadata: dict[str, Any]


@dataclass
class StoryboardPlan:
    mode: StoryboardGenerationMode
    count_mode: StoryboardCountMode
    requested_scene_count: int | None
    resolved_scene_count: int
    source_text: str
    frames: list[StoryboardPlanFrame]
    diagnostics: dict[str, Any]
```

不变量：

- `resolved_scene_count == len(frames)`。
- `frame.index` 从 1 开始连续递增。
- `frame.narration_text` 不为空。
- `frame.source_text` 不为空。
- `source_range` 有值时必须在 `source_text` 范围内，且 start <= end。
- `smart + manual` 必须严格满足用户指定数量，除非超过全局上限或输入为空。
- 后续图片 prompt 数量必须等于 `len(frames)`。

## 7. 组件设计

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

也就是说内容生成层应新增或改造为“生成完整文案”，而不是“生成固定数量旁白”。旧的 `generate_narrations_from_topic` 可以保留给兼容 API，但标准视频生成链路不应再依赖它决定分镜数量。

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
```

校验：

- `storyboard_count_mode=manual` 时，`storyboard_scene_count` 必须存在。
- `storyboard_scene_count` 超过配置上限时返回 422。
- 旧 `n_scenes` 只作为兼容字段，不作为新 UI 的主要字段。

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

原来的 paragraph/line 选项不进入新 UI。若需要保留历史兼容，可隐藏在 legacy mapping 中，不再作为新产品能力暴露。

## 10. 持久化和可观测性

`CreationPackage.storyboard_plan` 应成为新分镜计划的主要持久化位置之一。`Storyboard.planning_snapshot` 继续记录便于 UI 预览和历史回放的信息。

建议 `planning_snapshot` 增加：

```json
{
  "storyboard_generation": {
    "mode": "smart",
    "count_mode": "auto",
    "requested_scene_count": null,
    "resolved_scene_count": 8,
    "strategy_version": "storyboard_generation_v1",
    "source_text_hash": "...",
    "diagnostics": {}
  },
  "frames": [
    {
      "index": 1,
      "source_text": "...",
      "narration_text": "...",
      "source_range": [0, 24],
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
5. `StoryboardGenerationService`：三种 strategy 路由。
6. `StoryboardEnhancer`：一帧输入对应一帧增强输出。
7. `ImagePromptComposer`：prompt prefix 只应用一次，输出数量等于帧数。
8. `StandardPipeline`：generate/fixed 都先得到 source_text，再得到 `StoryboardPlan`。
9. API schema：新字段校验、旧字段兼容映射。
10. 前端 request builder：默认智能分镜，手动数量传参，确定性模式不传无效数量。
11. 持久化：`storyboard_plan` 和 `planning_snapshot.storyboard_generation` 可保存和恢复。
12. 回归测试：TTS split、text rendering、asset_based pipeline 不因分镜改造改变行为。

## 13. 迁移计划

推荐分阶段实施，但最终交付必须形成完整新契约。

### 阶段 1：契约和确定性策略

- 新增 `StoryboardPlan` 模型。
- 新增 `StoryboardGenerationService`。
- 实现 `punctuation` 和 `sentence` strategy。
- 接入 `StandardPipeline`，让 fixed 文案先走新分镜层。

### 阶段 2：智能分镜

- 新增 smart strategy prompt 和结构化输出模型。
- 支持 auto/manual 数量。
- 加入 repair retry 和不变量校验。

### 阶段 3：增强层和 composer 收口

- 调整现有 `storyboard_planner.py` 为增强 `StoryboardPlanFrame`。
- 抽出 `ImagePromptComposer`。
- 确保三种模式最终统一进入 composer。

### 阶段 4：API、前端和持久化

- 前端新增三种分镜方式。
- API 新增分镜字段。
- `planning_snapshot` 和 `CreationPackage.storyboard_plan` 持久化新结构。
- 添加预览接口。

### 阶段 5：清理旧债

- 新 UI 不再暴露 paragraph/line split。
- `n_scenes` 和 `split_mode` 标记为 legacy compatibility。
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
