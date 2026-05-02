# Pixelle Stage1 / Stage2 零技术债主线重排设计

日期：2026-05-02

用途：在不推翻既有总控方案和分方案的前提下，重新确立 Pixelle Stage 0.5、Stage 1A、Stage 1B、Stage 2 的唯一主线，解决当前“Stage 1 一直修改、Stage 2 先行补下游、事实源分散”的结构性问题。

上级文档：

- `docs/pixelle_video_full_planning_md/MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`
- `docs/pixelle_video_full_planning_md/12A_TEXT_IMAGE_PROMPT_STAGE1A_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/12B_LLM_INTERACTION_TRACE_STAGE1A_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/13_STORYBOARD_WORKBENCH_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/15_ASSETBIBLE_SCENECAST_PROMPTCOMPOSER_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/23_STAGE1_STAGE2_PARALLEL_DEVELOPMENT_STRATEGY.md`
- `docs/pixelle_video_full_planning_md/24_PLATFORM_FOUNDATION_ZERO_TECH_DEBT_SUBPLAN.md`

---

## 1. 设计目标

本设计不新增能力域，而是回答一个更基础的问题：

```text
Pixelle 当前到底应以什么为唯一创作源头？
哪些现有入口是正式主链路？
哪些现有实现只能作为兼容层，不能再继续扩张？
Stage 1A / Stage 1B / Stage 2 应按什么强约束顺序推进，才能不留下技术债？
```

本设计的目标不是“补一个缺口”，而是重新确立主线。

---

## 2. 当前问题判断

现有总控和分方案的方向本身基本正确：

- Stage 0.5 定义平台级 Repository / Store / Resolver 合同。
- Stage 1A 定义 `ScriptDraft -> StoryboardPlan -> ImagePromptDraft -> PromptPlan -> LLMInteractionTrace` 上游创作合同。
- Stage 1B 定义 Workbench / Artifact / ArtifactVersion / GenerationTrace。
- Stage 2 定义 AssetBible / SceneCast / PromptComposer，对 Stage 1A 的 PromptPlan 预留字段做结构化填充。

问题不在文档方向，而在实现主线没有完全收口：

1. Stage 1A 的模型和部分服务已存在，但还没有成为唯一正式入口。
2. legacy 内容入口、标准管线、planning snapshot、Workbench 桥接、Stage 2 preview 仍在共同承担部分事实源职责。
3. `LLMInteractionTrace` 已有基础设施，但尚未确保所有 Stage 1A 源头调用都统一经过 trace context 和 recorder。
4. Stage 2 的 preview loop 已接近完成，但它当前只是下游预览闭环，不应被误判为可替代 Stage 1A/1B 主线的产品闭环。

如果继续按“下游先补 UI 和 preview，再回头补上游”的方式推进，结果会是：

```text
Stage 1A 没有成为唯一源头
Stage 1B 持续吸收上游责任
Stage 2 被迫替上游补结构化语义
standard pipeline 继续承担兼容逻辑和事实源拼装
最终留下跨阶段的系统性技术债
```

---

## 3. 核心判断

### 3.1 IP 总方案是正确的，但它不是当前第一优先主线

`AssetBible / SceneCast / PromptComposer / PromptPlan reserved fields / PromptProjection` 这一套 Structured IP 方向是正确的。

它解决的是：

```text
角色一致性
场景一致性
风格一致性
世界观一致性
后续 reference-augmented IP 扩展能力
```

但它成立的前提是：

```text
Stage 1A 必须先成为唯一创作事实源
Stage 1B 必须只消费 Stage 1A 合同
Stage 2 必须只对 Stage 1A 预留字段做受控结构化扩展
```

如果 Stage 1A 没有先立住，Stage 2 即使设计正确，也会被拖成“替系统补结构化秩序的半主链路”。

### 3.2 当前最优先问题不是 IP 不合理，而是主线事实源没有唯一化

真正需要先解决的源头问题是：

```text
谁定义故事脚本？
谁定义分镜事实？
谁定义每格图像提示词草稿？
谁定义正式 PromptPlan？
谁负责将 IP 结构化事实 apply 到 PromptPlan？
谁负责消费 PromptPlan 生成候选图和选中版本？
```

本设计给出的唯一答案是：

```text
Stage 1A 定义创作事实
Stage 2 apply 结构化 IP 事实
Stage 1B 消费 PromptPlan 和 Artifact 合同
Provider / generation 只消费已完成 apply 的正式 PromptPlan
```

---

## 4. 重新确立的唯一主线

Pixelle 后续一切生成相关能力，统一服从这条主线：

```text
UserInput
  -> ScriptDraft
  -> StoryboardPlan
  -> ImagePromptDraft
  -> PromptPlanBundle
  -> LLMInteractionTrace
  -> AssetBible / SceneCast apply
  -> Applied PromptPlanBundle
  -> Artifact / ArtifactVersion / GenerationTrace
  -> Provider PromptProjection
  -> image / audio / video artifacts
```

必须明确：

- `ScriptDraft / StoryboardPlan / ImagePromptDraft / PromptPlanBundle / LLMInteractionTrace` 是创作上游事实源。
- `AssetBible / SceneCast` 不是替代创作上游，而是对上游进行结构化约束和扩展。
- `Artifact / ArtifactVersion / GenerationTrace` 是下游产物和执行事实，不得反向成为上游创作事实源。
- `PromptProjection` 是 Provider 级投影，不得回写为新的 PromptPlan 事实源。

---

## 5. 唯一正式事实源

### 5.1 Stage 1A 正式事实源

Stage 1A 正式事实源固定为：

```text
ScriptDraft
StoryboardPlan
ImagePromptDraft
PromptPlan
PromptPlanBundle
LLMInteractionTrace
```

这些模型必须回答：

- 谁生成了它？
- 它属于哪个 `project_id` / `storyboard_plan_id` / `frame_id`？
- 它可否追溯到对应的 LLM interaction？
- 它是否可被 Stage 1B 和 Stage 2 稳定消费？

### 5.2 Stage 2 正式事实源

Stage 2 正式事实源固定为：

```text
AssetBible
IPProfile
CharacterProfile
SceneAsset
PropAsset
StyleProfile
SceneCast
```

Stage 2 的事实只负责：

```text
定义角色/场景/道具/风格的结构化来源
校验 SceneCast 引用合法性
向 PromptPlan 预留字段做 apply
```

Stage 2 不负责重新定义故事分镜，不负责绕过 Stage 1A 直接定义最终提示词计划。

### 5.3 Stage 1B 正式事实源

Stage 1B 正式事实源固定为：

```text
StoryboardPanel / StoryboardFrameWorkbenchState
Artifact
ArtifactVersion
GenerationTrace
Stale dependency graph / stale marks
```

Stage 1B 只能消费：

```text
Stage 1A 的 PromptPlan
Stage 2 apply 后的正式 PromptPlan
```

Stage 1B 不能重新生成或重新定义 PromptPlan 主结构。

---

## 6. 明确降级为兼容层的现有实现

为避免继续扩散事实源，以下现有路径必须明确降级为兼容层，而不是主线扩展点。

### 6.1 legacy `/api/content/*` 入口

现有：

```text
POST /api/content/narration
POST /api/content/image-prompt
POST /api/content/title
```

这些入口可以继续保留用于兼容、调试或局部迁移，但不应继续承担 Stage 1A 正式主线职责。

要求：

- 不再围绕它们新增 Stage 1A 正式能力。
- Stage 1A 正式链路应迁移到分阶段定义的 canonical content contracts。
- legacy content utilities 只作为 adapter 或 compatibility route。

### 6.2 `standard.py` 标准管线中的兼容事实拼装

现有标准管线包含：

- script generation
- storyboard generation
- image prompt generation
- prompt plan bundle persistence
- workbench artifact registration
- planning snapshot 同步和 legacy fallback

这说明它当前既像 orchestration layer，又像兼容桥，又像局部事实聚合层。

后续要求：

- `StandardPipeline` 只能消费正式 Stage 1A / 1B / 2 合同。
- 不再允许新增新的“snapshot-only 事实”或“pipeline 内部专有事实”。
- pipeline 中的 legacy 兼容逻辑要集中收敛，不能继续向外扩散。

### 6.3 planning snapshot

`planning_snapshot` 可以继续存在，但其定位必须固定为：

```text
调试/回放快照
兼容视图
前端预览辅助摘要
```

不得作为：

```text
PromptPlan 正式事实源
AssetBible 正式事实源
Artifact 正式事实源
Stage 2 apply 的持久化事实源
```

### 6.4 Stage 2 projection preview

当前 `PromptPlanProjectionPreview` 边界保持有效：

```text
preview-only
不保存 PromptPlan
不标记 stale
不接主生成链路
不承担 Provider routing / projection
```

后续允许继续优化其 UX，但禁止把它演化成“半正式 apply 流程”。

必须新增独立 `apply` 合同，而不是在 preview 路径上偷偷扩容。

---

## 7. 重新定义的阶段闸门

### Gate 0.5：平台基础闸门

必须满足：

- `TraceRepository`
- `RawPayloadStore`
- `ArtifactRepository`
- `ArtifactObjectStore`
- `AssetBibleRepository`
- `PromptPlanRepository`
- `ResourceResolver`

正式存在，且生产 profile 缺配置时 fail fast。

未通过前：

- 不允许把新的 Stage 1A / 1B / 2 服务接成主路径。
- 只允许模型、纯服务、fake/in-memory 测试。

### Gate A：Stage 1A 主线稳定闸门

必须满足：

- `ScriptDraft -> StoryboardPlan -> ImagePromptDraft -> PromptPlanBundle` 闭环存在。
- 每一步 LLM 调用都可挂 `LLMTraceContext` 和 `LLMInteractionRecorder`。
- `PromptPlan` 是唯一正式主结构，包含 `character_ids / scene_id / prop_ids / style_id` 预留字段。
- Stage 1A 正式入口与 legacy `/content/*` 入口职责分离。
- 不再新增 prompt-only IP 平行事实源。

通过 Gate A 后才允许：

- Stage 1B 作为正式消费层展开。
- Stage 2 从 preview-only 合同向 `apply` 合同设计推进。

### Gate B：Stage 1B 消费层稳定闸门

必须满足：

- Workbench 只读取 PromptPlan，不重定义 PromptPlan。
- Artifact / ArtifactVersion / GenerationTrace 正式落位。
- selected/candidate/stale/lock 都只挂在下游产物合同。
- preview 区和渲染区不新增第二套图片事实源。

通过 Gate B 后才允许：

- 正式把 applied PromptPlan 接入候选图 / 重抽 / stale 传播闭环。

### Gate C：Stage 2 合同稳定闸门

当前已基本满足的是 preview loop。

但新的 Gate C 需要拆成两层：

```text
Gate C1: preview-only projection stable
Gate C2: apply contract stable
```

只有 Gate C2 完成后，Stage 2 才能进入主生成链路。

---

## 8. Stage 1A 的重新优先级

从本设计生效起，Stage 1A 不是“一个并行线”，而是当前最高优先级主线。

必须优先完成的不是更多 UI，而是以下四件事：

### 8.1 确立 canonical content flow

统一的 Stage 1A 主链路必须成为唯一正式入口：

```text
ScriptDraftService
StoryboardGenerationService
ImagePromptComposer
PromptPlanBuilder
PromptPlanRepository
LLMInteractionRecorder
```

### 8.2 贯穿式 LLM trace

`LLMService` 已支持 trace context / recorder，但必须确保：

- `ScriptGenerationService`
- `StoryboardGenerationService`
- `ImagePromptComposer` / prompt batch path
- `PromptPlanBuilder` 相关流程

都不再出现“未挂 trace context 的 Stage 1A 主调用”。

### 8.3 入口迁移

正式主入口必须迁移到 Stage 1A canonical contracts，而不是继续围绕 legacy `content` utilities 增补功能。

允许保留兼容入口，但必须：

- 明确标注 compatibility role
- 不再作为新增正式能力的首要落点

### 8.4 标准管线去事实源化

`StandardPipeline` 只负责 orchestration，不再定义或拼装新的长期事实。

---

## 9. Stage 1B 的重新定位

Stage 1B 继续重要，但必须完全退回消费位。

后续只允许做：

- Workbench 读取 PromptPlan
- Artifact / ArtifactVersion 挂接
- image candidate / select / regenerate
- GenerationTrace
- stale / lock

不允许做：

- 重定义 PromptPlan
- 从 Workbench UI 生成第二套 PromptPlan 事实
- 让 selected image、preview cache、本地图片路径成为新的长期事实源

Stage 1B 的成功标准不是“Workbench 看起来能用”，而是：

```text
它消费上游合同，没有篡位
它能把所有下游选择、版本、重抽、stale 收在 Artifact 体系里
```

---

## 10. Stage 2 的重新定位

Stage 2 不是暂停，而是重新定责。

### 10.1 保留现有 preview loop 成果

已有的：

```text
AssetBible repository-backed drafts
SceneCast validation
PromptPlanProjectionPreview
projection selection flow UX
```

这些都保留。

### 10.2 明确下一步不是继续扩 preview，而是设计 apply 合同

Stage 2 的后续唯一正确主线是：

```text
AssetBible / SceneCast
  -> validate
  -> apply to PromptPlanBundle
  -> save applied PromptPlanBundle through PromptPlanRepository
  -> trigger stale / downstream integration through formal services
```

严禁：

- 在 preview API 上偷偷增加保存行为
- 把 preview response 当成正式生成输入
- 跳过 PromptPlanRepository 直接把投影结果塞进 pipeline runtime state

### 10.3 Stage 2 的真正完成定义

Stage 2 只有满足以下条件，才算真正从“设计正确”变成“产品可用”：

- 用户可在正式 IP Workbench 编辑 AssetBible
- SceneCast 可在 Storyboard/Workbench 语义里绑定，而不是裸 ID 调试
- 存在独立 `apply` 合同
- apply 后的 PromptPlan 才是主链路输入
- stale 和 trace 能识别这次 apply 的影响范围

---

## 11. 禁止项升级

本设计生效后，以下行为一律视为违反零技术债主线：

1. 在 Stage 1B 或 Stage 2 中新增第二套 PromptPlan 事实源。
2. 在 Workbench、preview、text rendering、template preview、snapshot 中保存新的长期 prompt 事实。
3. 继续围绕 legacy `/api/content/*` 路由扩张 Stage 1A 正式能力，而不迁移到 canonical flow。
4. 在 Stage 2 preview 路径中加入任何保存、stale 写入、主生成触发逻辑。
5. 让 `standard.py` 继续吸收新的领域定义责任，而不是收敛为 orchestration + compatibility。
6. 让 text rendering、title_style、caption_style、font、preview frame 成为 PromptPlan 或 AssetBible `StyleProfile` 的隐式来源。
7. 为了“先跑通”而让 pipeline runtime state、session state、snapshot payload 直接替代 Repository 合同。

---

## 12. 推荐实施顺序

本设计确认后，后续实施顺序必须调整为：

```text
第一优先级：
  Stage 0.5 收口检查
  Stage 1A canonical flow 收口
  Stage 1A trace 全链路贯穿
  legacy content entry 降级与迁移策略
  standard pipeline 去事实源化

第二优先级：
  Stage 1B 继续只做消费层收口
  Artifact / Trace / stale / lock 正式闭环

第三优先级：
  Stage 2 从 preview-only 进入 apply 合同设计
  IP Workbench 正式化
  SceneCast 进入 storyboard/workbench 语义绑定

第四优先级：
  主生成链路只消费 applied PromptPlan
```

注意：

- 不是停止 Stage 1B / Stage 2，而是它们不得再抢主线。
- 任何新任务都必须先回答：它是否在加强 Stage 1A 主位，还是又在给兼容层加能力。

---

## 13. 对现有计划的处理

本设计不废弃现有计划，但调整它们的执行优先级和解释方式。

### 保留并继续有效

- `2026-04-30-platform-foundation-zero-technical-debt-implementation.md`
- `2026-04-30-stage1a-text-image-prompt-trace-implementation.md`
- `2026-04-29-storyboard-workbench-stage1-implementation.md`
- `2026-04-30-stage2-assetbible-ip-scenecast-implementation.md`
- `2026-05-01-stage2-prompt-plan-projection-implementation.md`
- `2026-05-02-stage2-projection-selection-flow-implementation.md`

### 重新解释

- Stage 1A plan：升为当前唯一主线计划。
- Stage 1B plan：只能在不夺取 Stage 1A 主位的前提下执行。
- Stage 2 plan：已完成的 preview loop 保留，但后续必须转向 apply contract，而不是继续扩 preview。

### 必须补的新计划

本设计之后，必须新增一份实现计划，主题应是：

```text
Pixelle Stage1 canonical source flow consolidation
```

该计划负责：

- 统一 Stage 1A 正式入口
- 将 trace 贯穿脚本、分镜、图片提示词、PromptPlan 全链路
- 将 legacy content routes 降级为兼容层
- 收敛 `StandardPipeline` 的事实源职责

---

## 14. 验收标准

本设计被认为落实，必须同时满足：

1. 可以明确指出 Stage 1A 的唯一正式入口和唯一正式事实源。
2. `ScriptDraft -> StoryboardPlan -> ImagePromptDraft -> PromptPlanBundle -> LLMInteractionTrace` 形成稳定主链路。
3. legacy `/content/*` 不再被当作 Stage 1A 主线继续扩张。
4. `StandardPipeline` 不再继续长出新的长期事实。
5. Stage 1B 明确只消费 PromptPlan 和 Artifact 合同。
6. Stage 2 preview 保持 preview-only，且后续转向 apply 合同设计。
7. 所有新任务都能明确回答自己是在加强主线，还是只是在扩兼容层。

---

## 15. 非目标

本设计不直接完成：

- Stage 1A API 的全部迁移实现
- Stage 1B Workbench 的全部收口实现
- Stage 2 apply contract 的具体代码
- Provider 路由与 PromptProjection 主链路接入

这些都属于本设计后的实施计划范围。

---

## 16. 最终结论

Pixelle 现在不是“没有计划”，而是“缺少一份把现有计划重新压到唯一主线上的设计”。

这份主线设计给出的最终要求是：

```text
先确立 Stage 1A 为唯一创作源头
再让 Stage 1B 回到消费位
再让 Stage 2 从 preview 过渡到 apply
最后让主生成链路只读取正式 PromptPlan
```

只有这样，现有 IP 总方案才会成为最佳实践的一部分，而不是一个设计正确但被系统主线拖累的半成品。
