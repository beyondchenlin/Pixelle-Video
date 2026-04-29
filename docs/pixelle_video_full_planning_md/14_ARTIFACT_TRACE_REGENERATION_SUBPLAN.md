# 14 Artifact / Trace / Regeneration 分方案

用途：定义 Pixelle 的产物版本、生成记录和局部重跑体系。  
上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`

---

## 1. 定位

Artifact、ArtifactVersion 和 GenerationTrace 是 Pixelle 的生产记录基础。

Pixelle 不能把生成结果当作普通文件路径堆在目录里，也不能在重抽时覆盖旧文件。每次生成都必须留下可追踪的版本和事件。

---

## 2. 核心概念

```text
Artifact
  稳定逻辑产物，例如 frame_003_image。

ArtifactVersion
  某一次具体生成结果，例如 frame_003_image_v2。

GenerationTrace
  某次生成、重抽、选择、失败、导出的事件流。

RegenerationJob
  一次局部重跑请求。
```

Artifact 表示“是什么”，ArtifactVersion 表示“这一次生成出了什么”。

---

## 3. Artifact 类型

阶段 1 先支持：

```text
prompt_plan
image
```

阶段 3 补齐：

```text
script_draft
narration_audio
bgm
video_segment
render_package
final_video
```

---

## 4. 状态

ArtifactVersion 状态：

```text
pending
running
candidate
selected
rejected
failed
archived
```

Artifact 保存当前选中版本：

```text
current_selected_version_id
```

不要只靠 version 的 `status=selected` 表达当前选择，否则历史状态会变得难以审计。

---

## 5. Trace 事件

每条事件至少包含：

```text
event_id
job_id
project_id
storyboard_id
frame_id
stage
status
artifact_id
artifact_version_id
provider_id
request_snapshot
response_snapshot
error_code
created_at
```

普通用户只看摘要，高级用户可看 prompt、seed、provider，管理员可看 debug payload。

---

## 6. Regeneration 类型

```text
prompt.regenerate
image.regenerate
tts.regenerate
bgm.regenerate
segment.regenerate
render.regenerate
```

阶段 1 只实现 `image.regenerate` 和 PromptPlan 相关基础能力。其他类型在阶段 3 之后补齐。

---

## 7. stale 与 lock

上游变化必须能传播 stale：

```text
ScriptDraft changed -> StoryboardPanel stale
StoryboardPanel changed -> PromptPlan stale
PromptPlan changed -> image Artifact stale
AssetBible changed -> SceneCast / PromptPlan / image Artifact stale
```

lock policy：

```text
unlocked
locked_content
locked_prompt
locked_artifact
locked_all
```

锁定内容不能被自动重跑覆盖，但可以提示用户手动确认。

---

## 8. 存储路线

阶段 1：

```text
LocalJsonArtifactService
LocalJsonTraceService
```

阶段 3 以后：

```text
PostgreSQL: artifacts / artifact_versions / generation_events
Object Storage: binary assets
```

业务代码只能依赖服务接口，不能依赖本地目录结构。

---

## 9. 验收标准

- 重抽图片不会覆盖旧版本。
- 每个 frame 能列出候选版本和当前选择。
- 每次生成失败有可读错误。
- 每次选择图片产生 Trace。
- stale 传播规则可测试。
- lock policy 可阻止自动覆盖。

---

## 10. 非目标

- 阶段 1 不做复杂质量评分。
- 阶段 1 不做完整对象存储迁移。
- 阶段 1 不做完整 UsageLedger。
