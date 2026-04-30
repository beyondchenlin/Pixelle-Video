# 13 分镜图工作台分方案

用途：Stage 1B 的正式能力分方案，约束分镜图工作台的领域模型、交互边界、API 合同和验收标准。
上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`

---

## 1. 定位

分镜图工作台是 Pixelle 从“一键生成器”升级为“创作平台”的第一层产品闭环，但它不再是阶段 1 的第一步。Stage 1A 先稳定文案、分镜规划、图片提示词和 PromptPlan，Stage 1B 再把这些上游结果接入工作台。

它不负责完整 Workflow 编排，也不负责 SaaS 权限计费。它负责让用户围绕每一格分镜进行可编辑、可重抽、可选择、可追踪的图文创作。

核心目标：

```text
Stage 1A 输出的 StoryboardPlan / PromptPlan
  -> StoryboardPanel
  -> 候选图
  -> 选择/重抽
  -> 可追踪版本
  -> 实施预览消费选中版本
```

---

## 2. 范围

阶段 1 必须包含：

- StoryboardPanel / StoryboardFrame 工作台扩展。
- 消费 Stage 1A 产出的 PromptPlan，不重新定义 PromptPlan。
- 每格候选图列表。
- 当前选中图片版本。
- 图片重抽。
- frame lock。
- stale flags。
- GenerationTrace 查看入口。
- 为实施预览区提供当前 selected/candidate ArtifactVersion 引用。

Stage 1B 的前置输入：

- Stage 1A 生成的 StoryboardPlan。
- Stage 1A 生成的 PromptPlan。
- PromptPlan 中预留的 `character_ids`、`scene_id`、`prop_ids`、`style_id` 字段。

Stage 1B 不包含：

- FlowGram Canvas。
- 用户自定义 Workflow。
- SaaS 计费。
- 完整 ProviderCapability 矩阵。
- 视频片段生成。
- 标题/字幕样式默认值。
- 独立图片预览事实源。

---

## 3. 领域模型

建议新增或扩展：

```text
StoryboardPanel
  panel_id
  project_id
  source_document_id
  frames
  status
  created_at
  updated_at

StoryboardFrameWorkbenchState
  frame_id
  prompt_plan_id
  selected_image_artifact_id
  selected_image_version_id
  candidate_image_version_ids
  lock_policy
  stale_flags
  last_generation_job_id
```

原则：

- 不破坏现有 `StoryboardFrame` 的最终媒体输出语义。
- 工作台状态可以作为增量模型存在。
- 所有 frame 必须有稳定 `frame_id`。
- 所有候选图必须通过 ArtifactVersion 引用。
- 实施预览区只能读取这些 ArtifactVersion 引用，不得把预览图片路径或缓存文件路径写回工作台状态。

---

## 4. 关键状态

```text
draft
prompt_ready
generating
candidate_ready
selected
stale
locked
failed
```

状态只描述工作台层面的创作状态，不替代任务系统的 job 状态。

---

## 5. API 合同

阶段 1 建议提供 App API：

```text
GET  /api/storyboards/{storyboard_id}/workbench
POST /api/storyboards/{storyboard_id}/frames/{frame_id}/images
POST /api/storyboards/{storyboard_id}/frames/{frame_id}/select-image
POST /api/storyboards/{storyboard_id}/frames/{frame_id}/lock
POST /api/storyboards/{storyboard_id}/frames/{frame_id}/unlock
GET  /api/storyboards/{storyboard_id}/frames/{frame_id}/trace
```

API 不直接接受本地 workflow 文件路径。图片生成参数来自 PromptPlan、资源 ID 和后端 preset。

实施预览相关 API 如需读取当前画面，应返回 selected/candidate `ArtifactVersion`、storage key 或受控访问 URL；不得返回本地绝对路径。

---

## 6. 依赖关系

依赖：

- `StoryboardPlan.frame_id`
- `PromptPlan`
- `Artifact / ArtifactVersion`
- `GenerationTrace`

被依赖：

- AssetBible / SceneCast
- Regeneration
- Workflow Skeleton
- 视频扩展

---

## 7. 验收标准

- 用户能看到每格分镜的候选图。
- 用户能选择某张候选图作为当前版本。
- 用户能对单格重新生成图片。
- 重抽不会覆盖旧图。
- 锁定 frame 后，上游变化不会自动替换其选中图。
- 修改上游文案或 PromptPlan 后，相关 frame 能标记 stale。
- 每次生成和选择都有 Trace。
- 实施预览区能消费当前选中图片版本，但工作台不新增第二套预览图片状态。

---

## 8. 后续实施入口

对应阶段计划：

`../superpowers/plans/2026-04-29-storyboard-workbench-stage1-implementation.md`

该计划是本分方案的 Stage 1B 施工图，不代表 Pixelle 全平台完整实施计划，也不替代 Stage 1A 文案与图片提示词实施计划。
