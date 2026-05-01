# 15 AssetBible / SceneCast / PromptComposer 分方案

用途：定义角色、场景、道具、风格与 PromptPlan 的结构化生成体系。  
上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`

---

## 1. 定位

AssetBible、SceneCast 和 PromptComposer 负责把“文案”转成“可稳定生成视觉画面”的结构化事实。

它们解决的问题不是让 prompt 更长，而是让每格分镜知道：

```text
有哪些角色
在哪个场景
使用哪些道具
采用什么风格
哪些信息来自 IP 资产库
最终 prompt 为什么这样组成
```

---

## 2. 核心模型

```text
AssetBible
  ip_profiles
  character_profiles
  scene_assets
  prop_assets
  style_profiles

SceneCast
  frame_id
  character_ids
  scene_id
  prop_ids
  style_id
  continuity_notes

PromptPlan
  prompt_plan_id
  frame_id
  storyboard_plan_id
  image_prompt_draft_id
  scene_cast_id
  character_ids
  scene_id
  prop_ids
  style_id
  prompt_sections

PromptPlanProjectionPreview
  prompt_plan
  source_asset_bible_id
  source_scene_cast_id
  source_prompt_plan_id
  persistence: none

PromptProjection
  final_prompt
  negative_prompt
  provider_params
  source_prompt_plan_id
```

PromptPlan 是结构化计划。`PromptPlanProjectionPreview` 是 Stage 2 当前允许实现的非持久化预览：它把经过校验的 SceneCast 引用填充到 PromptPlan 预留字段，返回新的 PromptPlan 结果，不保存、不标记 stale、不接入主生成链路。

PromptProjection 是后续 Provider 级最终投影，负责把稳定 PromptPlan 转成 `final_prompt`、`negative_prompt`、`provider_params` 等 Provider 输入。它不能和 Stage 2 的 PromptPlan 预览 API 混用。

这里的 `StyleProfile` 是 IP / 视觉风格事实源，用于描述画面风格、世界观和 provider prompt 投影。它不等同于文字渲染的 `TextStyleProfile`，不得承载 `caption_style`、`title_style`、字体文件、字幕背景或标题背景默认值。

---

## 3. 阶段拆分

阶段 1：

- PromptPlan 先存在。
- 预留 `character_ids / scene_id / prop_ids / style_id`。
- 不实现复杂 AssetBible。
- Stage 1A 负责文案、分镜规划、图片提示词和 PromptPlan。
- Stage 1B 负责把 PromptPlan 接入工作台、候选图、Artifact 和 Trace。

阶段 2：

- 实现 AssetBible 草稿事实源。
- 实现 SceneCast 校验。
- 实现 PromptComposer。
- 让 `prompt_prefix` 退出正式入口，由 `style_id`、`StyleProfile` 和 `ResourceResolver` 接管。
- 当前只通过 `style_id` / SceneCast / PromptComposer 填充 PromptPlan 的 `character_ids / scene_id / prop_ids / style_id` 预留字段，并提供非持久化预览。
- Provider 级 PromptProjection 放到后续阶段，不在 Stage 2 内提前实现 Provider 路由、最终 prompt 参数化或主生成链路接入。
- 不直接改写标题或字幕样式。

后续：

- Reference-augmented IP。
- VLM 辅助角色一致性检查。
- 多风格资产管理。

---

## 4. 约束

- SceneCast 引用的角色、场景、道具必须属于当前项目或当前工作区。
- PromptComposer 不允许直接读取本地任意路径。
- Public API 不能接受任意 `prompt_prefix`。
- PromptProjection 可以因 Provider 不同而不同，但 PromptPlan 必须稳定。
- Stage 2 的 PromptPlan 预览 API 不得持久化 PromptPlan，不得标记 stale，不得触发图片生成，也不得替代未来 Provider 级 PromptProjection。
- AssetBible 持久化必须通过 `AssetBibleRepository`，不能由 Stage 2 自建本地 JSON 服务作为正式路径。
- `StyleProfile` 不得成为 `caption_style` 或 `title_style` 的默认值副本；标题/字幕样式由文字渲染契约和模板文字 preset 管理。
- PromptComposer 不得把 `text_rendering.image_text` 当作第二套图片提示词事实源。

---

## 5. Prompt 拼接顺序

建议顺序：

```text
style_profile
world_profile
scene_description
character_descriptions
prop_descriptions
camera_language
composition
lighting
quality_constraints
negative_prompt
```

每一段都要保留 source reference，便于 Trace 和调试。

---

## 6. API 合同

```text
POST /api/projects/{project_id}/asset-bible
GET  /api/projects/{project_id}/asset-bible
POST /api/storyboards/{storyboard_id}/frames/{frame_id}/scene-cast
POST /api/storyboards/{storyboard_id}/frames/{frame_id}/prompt-plan
POST /api/projects/{project_id}/asset-bible/{asset_bible_id}/scene-casts/{scene_cast_id}/prompt-plan-projection
```

`prompt-plan-projection` 是 Stage 2 当前预览 API，只返回 SceneCast 应用后的 PromptPlan 结果，不持久化。阶段 2 以内，这些 API 可以是 App API，不开放 Public API。

后续 Provider 级 API 可单独定义为：

```text
POST /api/prompt-plans/{prompt_plan_id}/projection
```

该 API 用于最终 Provider 投影，不属于当前 Stage 2 预览范围。

---

## 7. 验收标准

- PromptPlan 能追溯到 StoryboardPanel 和 SceneCast。
- SceneCast 中的 ID 都能校验存在。
- Stage 2 预览 API 能返回填充 SceneCast 引用后的 PromptPlan，并保持源 PromptPlan 不被原地修改。
- 修改 CharacterProfile 后，相关 PromptPlan 标记 stale 属于 Stage 1B / 后续集成能力，不由当前 Stage 2 预览 API 直接完成。
- Provider 级 PromptProjection 可以为不同 Provider 输出不同参数，但属于后续阶段验收，不作为当前 Stage 2 预览的完成条件。
- `prompt_prefix` 不再作为正式事实源。
- Stage 2 风格事实源与文字渲染样式事实源保持解耦，互不复制默认值。

---

## 8. 非目标

- 不做官方知名 IP 复刻。
- 不承诺 Prompt-only 模式能做到绝对角色一致。
- 不在阶段 2 做复杂训练、LoRA 管理或角色模型微调。
