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

---

## 2. 为什么要先做 Stage 1A

如果先做完整工作台，而文案、分镜和图片提示词仍然不稳定，工作台会变成“修补错误上游”的界面。

Stage 1A 先解决：

- 用户输入如何变成结构化剧本文案。
- 剧本文案如何变成稳定分镜。
- 每格分镜如何得到图片提示词。
- PromptPlan 如何预留后续 IP / SceneCast 字段。
- `prompt_prefix` 如何从正式事实源降级为 legacy/debug 辅助字段。

---

## 3. 范围

Stage 1A 必须包含：

- ScriptDraft 基础模型。
- StoryboardPlan 继续作为分镜规划模型。
- 每格视觉描述和图片提示词生成。
- PromptPlan 基础结构。
- PromptPlan 预留 `character_ids`、`scene_id`、`prop_ids`、`style_id`。
- 最小 Prompt-only IP 输入字段。
- 图片提示词生成服务与测试。
- 文案、分镜、图片提示词的基础 Trace 入口。

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
  storyboard_panel_id
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
```

Stage 1A 不直接负责调用图片生成 Provider。它只输出稳定、可测试、可追踪的图片提示词和 PromptPlan。

---

## 6. 最小 IP 策略

Stage 1A 可以支持最小 Prompt-only IP 输入：

```text
ip_name
style_hint
character_hint
world_hint
forbidden_elements
```

这些字段只作为 PromptPlan 的上游提示，不建立完整 IPProfile / CharacterProfile 表。

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

---

## 9. 与 Stage 1B 的关系

Stage 1A 输出：

```text
StoryboardPlan
PromptPlan
ImagePromptDraft
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
