# 12A Stage 1A 文案与图片提示词分方案

用途：定义阶段 1A 的正式能力边界，让 Pixelle 先稳定“主题/文案 -> 分镜规划 -> 图片提示词 -> PromptPlan”的创作源头链路。  
上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`

---

## 1. 定位

Stage 1A 是阶段 1 的前半段。它先不做完整分镜图工作台，也不做完整 IP 库，而是把创作源头链路做稳。

核心目标：

```text
用户主题/文案
  -> ScriptDraft
  -> StoryboardPlan
  -> 每格视觉目标
  -> 图片提示词
  -> PromptPlan
```

这样 Stage 1B 的候选图、选择、重抽、Artifact、Trace 才有稳定上游。

同时，Stage 1A 必须把大模型输入输出追踪作为基础设施一起完成。文案、分镜规划、图片提示词和 PromptPlan 都依赖 LLM，如果不能看到每次提交给模型的内容、返回内容、解析结果和错误原因，后续工作台会继续停留在黑盒调试状态。具体追踪合同见 `12B_LLM_INTERACTION_TRACE_STAGE1A_SUBPLAN.md`。

---

## 2. 为什么要先做 Stage 1A

如果先做完整工作台，而文案、分镜和图片提示词仍然不稳定，工作台会变成“修补错误上游”的界面。

Stage 1A 先解决：

- 用户输入如何变成结构化剧本文案。
- 剧本文案如何变成稳定分镜。
- 每格分镜如何得到图片提示词。
- PromptPlan 如何预留后续 IP / SceneCast 字段。
- `prompt_prefix` 如何退出正式事实源，由 `style_id`、`StyleProfile` 和 `ResourceResolver` 接管。

---

## 3. 范围

Stage 1A 必须包含：

- ScriptDraft 基础模型。
- StoryboardPlan 继续作为分镜规划模型。
- 每格视觉描述和图片提示词生成。
- PromptPlan 基础结构。
- PromptPlan 预留 `character_ids`、`scene_id`、`prop_ids`、`style_id`。
- 资产引用字段只保存 Stage 2 合同产生的 ID。
- 图片提示词生成服务与测试。
- 文案、分镜、图片提示词的基础 Trace 入口。
- LLMInteractionTrace 基础设施，记录每一次大模型调用的输入、输出、解析结果和错误。
- Studio 左侧或侧边 LLM Trace Panel 的数据合同。

Stage 1A 不包含：

- 多候选图片生成。
- 图片选择和重抽。
- ArtifactVersion 完整选择状态。
- 完整 AssetBible。
- 完整 SceneCast 校验。
- FlowGram。
- SaaS。
- 视频片段生成。

---

## 4. 领域模型

建议模型边界：

```text
ScriptDraft
  script_draft_id
  project_id
  source_text
  title
  scenes
  narration_blocks
  status

StoryboardPlan
  plan_id
  source_text
  frames
  frame_id
  source_spans

ImagePromptDraft
  frame_id
  visual_goal
  image_prompt
  negative_prompt
  style_hint
  source_storyboard_plan_id

PromptPlan
  prompt_plan_id
  frame_id
  storyboard_plan_id
  image_prompt_draft_id
  character_ids
  scene_id
  prop_ids
  style_id
  prompt_sections
```

Stage 1A 可以先让 `character_ids`、`scene_id`、`prop_ids`、`style_id` 为空，但字段必须存在。

---

## 5. 数据流

```text
UserInput
  -> ScriptDraftService
  -> StoryboardPlanner
  -> ImagePromptComposer
  -> PromptPlanBuilder
  -> PromptPlan
  -> LLMInteractionTrace
```

Stage 1A 不直接负责调用图片生成 Provider。它只输出稳定、可测试、可追踪的图片提示词和 PromptPlan。

所有服务调用大模型时必须经过统一 `LLMService` 网关，并传入 trace context。业务服务只描述语义上下文，不能各自手写 prompt 日志。

---

## 6. IP / Asset 引用策略

Stage 1A 不再创建基于自然语言提示的 IP 平行事实源。它只允许在 PromptPlan 中保留由 Stage 2 或草稿资产接口产生的资源 ID：

```text
asset_bible_id
style_id
character_ids
scene_id
prop_ids
```

如果用户在 Stage 1A 输入了“角色形象”“世界观”“风格方向”等自然语言提示，必须被转交给 Stage 2 AssetBible 草稿能力，生成 `IPProfile`、`CharacterProfile` 或 `StyleProfile` 后再以 ID 回填。Stage 1A 不保存这些提示作为长期事实源。

完整 IP / AssetBible 放到 Stage 2。

---

## 7. API 边界

建议 Stage 1A App API：

```text
POST /api/content/script-draft
POST /api/content/storyboard-plan
POST /api/content/image-prompts
POST /api/content/prompt-plans
GET  /api/content/prompt-plans/{prompt_plan_id}
GET  /api/content/tasks/{task_id}/llm-interactions
GET  /api/content/tasks/{task_id}/llm-interactions/{interaction_id}
```

如果现有 API 已经覆盖部分能力，优先扩展现有 `content` 或 `storyboard` 合同，不重复造入口。

---

## 8. 验收标准

- 输入主题或文案后，能得到结构化 ScriptDraft。
- ScriptDraft 能生成稳定 StoryboardPlan。
- 每个 StoryboardPlan frame 都有稳定 `frame_id`。
- 每个 frame 能生成图片提示词。
- 每个 frame 能生成 PromptPlan。
- PromptPlan 预留 SceneCast 字段。
- 不需要生成真实图片也能测试 Stage 1A。
- `prompt_prefix` 不再被定义为长期事实源。
- 每一次生成 ScriptDraft、StoryboardPlan、ImagePromptDraft、PromptPlan 的 LLM 调用都有可查询的 LLMInteractionTrace。
- 左侧或侧边 Trace Panel 能展示大模型输入、输出、解析结果、校验错误和重试链路。
- raw request / raw response 保存为调试产物，但默认只在 Admin / Local Debug 可见。

---

## 9. 与 Stage 1B 的关系

Stage 1A 输出：

```text
StoryboardPlan
PromptPlan
ImagePromptDraft
LLMInteractionTrace
```

Stage 1B 消费这些输出，继续完成：

```text
Artifact / ArtifactVersion
候选图
选择
单格重抽
GenerationTrace
lock / stale
```

Stage 1B 不应该重新定义文案和图片提示词生成逻辑。

---

## 10. 非目标

- 不做完整 AssetBible。
- 不做复杂 SceneCast。
- 不做角色参考图管理。
- 不做图片生成和候选图选择。
- 不做视频生成。
- 不做 Public API。
