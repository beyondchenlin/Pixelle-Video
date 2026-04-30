# 23 Stage 1 / Stage 2 并行开发策略

用途：在不破坏阶段边界的前提下，允许 Stage 1A、Stage 1B 和 Stage 2 的部分工作并行推进。

上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`

---

## 1. 总结

可以并行开发，但必须先通过 Stage 0.5 平台基础闸门，再按“合同先行、实现后接入”的方式推进。

```text
Stage 0.5 负责平台基础合同：
  Repository / Object Store / ResourceResolver / API raw boundary

Stage 1A 负责上游创作合同：
  ScriptDraft / StoryboardPlan / ImagePromptDraft / PromptPlan / LLMInteractionTrace

Stage 1B 负责工作台和产物合同：
  StoryboardFrame workbench state / Artifact / ArtifactVersion / GenerationTrace

Stage 2 负责 IP 和资产合同：
  AssetBible / IPProfile / CharacterProfile / SceneCast / PromptComposer extension
```

并行开发不是把三个阶段都接进主生成链路，而是让不同小组先实现各自独立的领域合同、服务接口和测试。只有当平台基础合同和上游合同稳定后，才允许下游集成。

文字渲染样式和实施预览属于跨阶段渲染合同，不属于 Stage 1A 的 `PromptPlan`，也不属于 Stage 2 的 IP / AssetBible 风格事实源。`caption_style`、`title_style` 和实施预览只能消费正式渲染契约、模板 preset、`media_placement`、Artifact 和 Object Store，不得在 Stage 1A、Stage 1B 或 Stage 2 中派生第二套事实源。

---

## 2. 并行开发红线

必须遵守：

- Stage 1A 是 `PromptPlan` 首次定义和生成的唯一来源。
- Stage 1B 只能消费 Stage 1A 的 `PromptPlan`，不能重新定义 `PromptPlan` 或 `PromptPlanBuilder`。
- Stage 2 可以实现 `AssetBible`、`IPProfile`、`CharacterProfile` 和 `SceneCast`，但不能直接改 Stage 1A 的主生成流程。
- Stage 2 可以读取和填充 Stage 1A 预留的 `character_ids`、`scene_id`、`prop_ids`、`style_id` 字段。
- Stage 1A、Stage 1B 和 Stage 2 的持久化都必须依赖 Stage 0.5 的 Repository / Store 接口。
- App/Public API 必须通过 `ResourceResolver` 解析资源 ID，raw 参数只能进入 Internal/Debug 边界。
- `text_rendering.caption_style` 和 `text_rendering.title_style` 是渲染契约；Stage 1A 不得把它们写进 `PromptPlan` 主结构，Stage 2 不得把它们并入 IP `StyleProfile`。
- 实施预览区是渲染契约的下游视图；真实预览帧必须通过 Artifact / Object Store 或受控预览 artifact key 表达，不能返回本地路径。
- FlowGram、SaaS、完整 ProviderCapability、视频片段生成不进入 Stage 1 / Stage 2 并行主线。
- 所有任务必须能形成原子提交，并按 AGENTS.md 使用中文提交说明。

禁止：

- 在 Stage 1B 中新增第二套 PromptPlan 模型。
- 在 Stage 2 中提前要求完整参考图、LoRA、图生图或 Provider 路由。
- 为了并行速度绕过 LLMInteractionTrace。
- 让前端或 API 直接传本地 workflow 路径、模型路径或任意 provider URL 作为正式合同。
- 让前端或 API 直接传本地字体路径、预览图片路径或真实预览帧路径作为正式合同。
- 在工作台、AssetBible 或 PromptComposer 中新增标题/字幕样式默认值副本。
- 在 active 计划中新增本地 JSON、JSONL、`_runtime` 或 Local*Service 作为正式路径。

---

## 3. 并行开发矩阵

| 并行线 | 可立即做 | 必须等待 | 文件写入边界 |
| --- | --- | --- | --- |
| Stage 0.5 Platform Foundation | Repository、Object Store、ResourceResolver、API raw boundary、production fail-fast | 无，必须最先完成 | `pixelle_video/repositories/*`、`pixelle_video/storage/*`、`pixelle_video/services/resource_resolver.py`、`api/config.py` |
| Stage 1A Text / Prompt / Trace | `LLMInteractionTrace`、`PromptPlan`、`ImagePromptDraft`、Trace API、PromptPlanBuilder | Gate 0.5 后才能接入持久化和 LLMService 追踪 | `pixelle_video/models/prompt_plan.py`、`pixelle_video/models/llm_interaction_trace.py`、`pixelle_video/services/llm_interaction_recorder.py`、`pixelle_video/services/prompt_plan_service.py` |
| Stage 1B Workbench | `Artifact`、`ArtifactVersion`、`GenerationEvent`、工作台 lock/stale 模型、仓储接入 | Gate 0.5；不能执行 PromptPlan 定义任务，必须消费 Stage 1A 合同 | `pixelle_video/models/artifact.py`、`pixelle_video/models/generation_event.py`、`pixelle_video/models/storyboard_workbench.py`、`pixelle_video/services/storyboard_workbench.py` |
| Stage 2 IP / AssetBible | `AssetBible`、`IPProfile`、`CharacterProfile`、`SceneCast` 模型、校验器、仓储接入 | Gate 0.5；主链路接入必须等 Stage 1A PromptPlan 字段稳定 | `pixelle_video/models/asset_bible.py`、`pixelle_video/models/scene_cast.py`、`pixelle_video/services/scene_casting.py`、`pixelle_video/services/prompt_composer.py` |
| Rendering / Preview Contract | `title_style`、`caption_style`、模板文字 preset、实施预览快照、真实预览帧缓存合同 | Gate 0.5 后才能持久化真实预览帧；Stage 1B 后优先消费 selected ArtifactVersion | `api/schemas/text_rendering.py`、`pixelle_video/models/text_style.py`、`pixelle_video/services/text_rendering_orchestrator.py`、`web/components/text_rendering_*` |
| API / Studio | Trace 只读接口、资产库草稿接口、工作台查询接口 | 写入主生成链路必须等对应服务通过测试 | `api/schemas/*`、`api/routers/*`、`web/*` |

---

## 4. 集成闸门

### Gate 0.5：平台基础合同稳定

满足条件：

- `TraceRepository`、`RawPayloadStore`、`ArtifactRepository`、`ArtifactObjectStore`、`AssetBibleRepository`、`PromptPlanRepository` 和 `ResourceResolver` 接口存在。
- dev/test adapter 不向领域模型返回本地绝对路径。
- production profile 缺少 PostgreSQL 或对象存储配置时 fail fast。
- App/Public API 与 Internal/Debug API 的 raw 参数边界明确。
- active 计划中不出现本地 JSON、JSONL 或 `_runtime` 作为正式合同。

通过后允许：

- Stage 1A 接入 LLMService trace recorder。
- Stage 1B 接入 Artifact / GenerationEvent repository。
- Stage 2 接入 AssetBible repository。

### Gate A：Stage 1A 合同稳定

满足条件：

- `PromptPlan` 模型存在，并包含 `character_ids`、`scene_id`、`prop_ids`、`style_id`。
- `ImagePromptDraft` 能追溯到 `StoryboardPlan.frame_id`。
- `LLMInteractionTrace` 能记录 request、response、parsed output、validation error 和 retry。
- `LLMInteractionRecorder` 只依赖 `TraceRepository` 和 `RawPayloadStore`。
- Stage 1A 相关测试通过。

通过后允许：

- Stage 1B 使用 PromptPlan 生成候选图和工作台状态。
- Stage 2 使用 reserved fields 填充角色、场景、道具和风格引用。

### Gate B：Stage 1B 产物合同稳定

满足条件：

- `Artifact` 和 `ArtifactVersion` 区分清楚。
- 重抽不会覆盖旧版本。
- `GenerationTrace` 可记录生成、选择、失败和重抽事件。
- `StoryboardFrame` 或增量工作台状态能保存 selected/candidate/lock/stale。

通过后允许：

- Stage 2 的 SceneCast 和 PromptComposer 变更触发 stale 标记。
- 后续 Stage 3 建立更完整的局部重跑策略。

### Gate C：Stage 2 IP 合同稳定

满足条件：

- `AssetBible` 能保存角色、场景、道具和风格。
- `SceneCast` 引用的 ID 必须属于当前 AssetBible。
- `PromptComposer` 只填充 Stage 1A 的 reserved fields，不改 PromptPlan 主结构。
- 结构校验覆盖无效角色 ID、无效场景 ID 和重复资产 ID。

通过后允许：

- 将 IP 形象一致性接入正式生成链路。
- 后续增加参考图、角色资产库、Provider 级 PromptProjection。

---

## 5. 推荐并行顺序

```text
第一批并行：
  F1: Stage 0.5 Repository / Store / ResourceResolver 合同
  A1: Stage 1A LLMInteractionTrace / PromptPlan 纯模型合同
  B1: Stage 1B Artifact / ArtifactVersion / GenerationEvent 纯模型合同
  C1: Stage 2 AssetBible / IPProfile / CharacterProfile 纯模型合同

第二批并行：
  F2: Stage 0.5 dev/test adapters 和 production fail-fast
  A3: Stage 1A LLMService 网关追踪，通过 TraceRepository
  A4: Stage 1A PromptPlanBuilder 接现有 StoryboardPlan / ImagePromptComposer
  B2: Stage 1B GenerationEvent / ArtifactRepository 接入
  C2: Stage 2 SceneCast 模型和校验器

第三批并行：
  A5: Stage 1A Trace API / Studio Trace Panel 数据合同
  B3: Stage 1B workbench select / regenerate / stale，通过仓储接口
  C3: Stage 2 PromptComposer extension，只填充 PromptPlan reserved fields
```

---

## 6. 施工计划入口

Stage 0.5：

`../superpowers/plans/2026-04-30-platform-foundation-zero-technical-debt-implementation.md`

Stage 1A：

`../superpowers/plans/2026-04-30-stage1a-text-image-prompt-trace-implementation.md`

Stage 1B：

`../superpowers/plans/2026-04-29-storyboard-workbench-stage1-implementation.md`

Stage 2：

`../superpowers/plans/2026-04-30-stage2-assetbible-ip-scenecast-implementation.md`

---

## 7. 验收标准

- 每条并行线都有独立可运行的测试命令。
- 每条并行线都有清晰文件写入边界。
- Gate 0.5 先于任何持久化服务接入。
- Stage 1B 不再创建或重定义 PromptPlan。
- Stage 2 在 Gate A 前只实现合同和校验，不接主链路。
- App/Public API 不再新增 raw path、workflow path、provider URL 或 arbitrary prompt prefix。
- 标题/字幕样式、字体资源、模板资源和预览帧不绕过 ResourceResolver / Object Store / Artifact 合同。
- 所有合并都能回答：属于哪个阶段、服务哪个分方案、修改哪个领域合同、是否提前引入后续复杂度、如何测试。
