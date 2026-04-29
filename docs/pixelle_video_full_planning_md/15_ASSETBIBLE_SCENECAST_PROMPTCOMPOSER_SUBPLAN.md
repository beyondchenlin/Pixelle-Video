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
  storyboard_panel_id
  scene_cast_id
  character_ids
  scene_id
  prop_ids
  style_id
  prompt_sections

PromptProjection
  final_prompt
  negative_prompt
  provider_params
  source_prompt_plan_id
```

PromptPlan 是结构化计划，PromptProjection 是面向某个 Provider 的最终投影。

---

## 3. 阶段拆分

阶段 1：

- PromptPlan 先存在。
- 预留 `character_ids / scene_id / prop_ids / style_id`。
- 不实现复杂 AssetBible。

阶段 2：

- 实现 Prompt-only AssetBible。
- 实现 SceneCast 校验。
- 实现 PromptComposer。
- 将 `prompt_prefix` 降级为 legacy/debug 字段。

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
POST /api/prompt-plans/{prompt_plan_id}/projection
```

阶段 2 以内，这些 API 可以是 App API，不开放 Public API。

---

## 7. 验收标准

- PromptPlan 能追溯到 StoryboardPanel 和 SceneCast。
- SceneCast 中的 ID 都能校验存在。
- 修改 CharacterProfile 后，相关 PromptPlan 标记 stale。
- PromptProjection 可以为不同 Provider 输出不同参数。
- `prompt_prefix` 不再作为正式事实源。

---

## 8. 非目标

- 不做官方知名 IP 复刻。
- 不承诺 Prompt-only 模式能做到绝对角色一致。
- 不在阶段 2 做复杂训练、LoRA 管理或角色模型微调。
