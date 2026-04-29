# Pixelle AI 短剧漫剧平台总控方案

日期：2026-04-29  
用途：总方案 / 全部分方案索引 / 分阶段路线图 / 后续 Codex 开发准入依据

---

## 1. 总体判断

Pixelle 不应继续按“本地一键视频生成工具”演进，也不应一开始就按完整 SaaS、完整 Workflow Engine、完整 FlowGram 编排平台推进。

更健康的路线是：

```text
先把 Pixelle 做成可编辑、可重抽、可追踪的分镜图创作工作台；
再把工作台里的稳定流程抽象成最小 Workflow Skeleton；
再接 Worker、Provider、FlowGram、SaaS、Public API 和视频扩展。
```

现有 `01-12` 文档、`ALL_IN_ONE`、架构设计文档、团队评审和 v2 反馈不是互相替代关系，而是不同层级的规划资料。它们需要被收敛进一个总控体系：

```text
总控方案 = 方向、边界、阶段、依赖、准入规则
分方案 = 每个能力域的设计边界和合同
阶段实施计划 = 某个阶段可直接交给 Codex 执行的任务拆分
```

因此，已经生成的阶段一计划只能作为第一个阶段实施计划，不能替代整个项目规划。

---

## 2. 规划层级

后续所有规划文档按四层组织。

```text
L0 总控方案
  MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md

L1 能力分方案
  产品边界、文本链路、IP/AssetBible、PromptComposer、分镜工作台、
  Artifact/Trace、Workflow、Worker、Provider、FlowGram、SaaS、视频扩展等。

L2 阶段实施计划
  每个阶段单独形成可执行计划，包含文件、模型、API、服务、测试、验收。

L3 原子开发任务
  每个任务对应一次可审查、可回滚、可测试的代码变更。
```

这四层不能混在一起。总控方案回答“为什么这样做、按什么顺序做”；分方案回答“模块边界是什么”；实施计划回答“怎么落到代码”；开发任务回答“这一次具体改哪些文件”。

---

## 3. 资料来源与取舍

### 3.1 已采纳为长期方向的文档

- `01_PROJECT_TARGET_AND_SYSTEM_BOUNDARY.md`
- `02_TEXT_GENERATION_PIPELINE_REDESIGN.md`
- `03_IP_LIBRARY_AND_VISUAL_CONSISTENCY.md`
- `04_PROMPT_COMPOSER_AND_SCENE_CASTING.md`
- `05_GENERATION_TRACE_AND_LOGGING.md`
- `06_API_FIRST_SAAS_ARCHITECTURE.md`
- `07_AUTH_PERMISSION_BILLING_AND_RESOURCE_POLICY.md`
- `08_DISTRIBUTED_DEPLOYMENT_AND_WORKERS.md`
- `09_ARTIFACT_VERSIONING_AND_REGENERATION.md`
- `10_PROVIDER_ABSTRACTION_LOCAL_AND_CLOUD.md`
- `11_DATABASE_QUEUE_STORAGE_SCHEMA.md`
- `12_MVP_IMPLEMENTATION_PLAN_FOR_CODEX.md`
- `2026-04-28-ai-drama-comic-workflow-platform-architecture-design.md`

这些文档的长期方向基本成立：Pixelle 应拆成 `Core / Studio / API / Workers`，以结构化剧情、资产、分镜、PromptPlan、Artifact、Trace 作为事实源。

### 3.2 需要修正的部分

原长期架构文档中过早推进了：

```text
WorkflowDefinition
FlowGram Adapter
WorkflowRun / NodeRun
完整 Worker 执行面
SaaS 权限计费
```

这些方向正确，但实施顺序偏早。团队评审和 v2 反馈的修正更合理：第一阶段先完成用户能感知的分镜图工作台闭环，同时只预埋最小合同，避免后续接 Workflow 和 FlowGram 时返工。

### 3.3 `ALL_IN_ONE` 的定位

`ALL_IN_ONE_PIXELLE_VIDEO_FULL_PLAN.md` 继续作为资料合并版保留，但不作为后续开发的直接执行入口。

后续开发入口应是：

```text
MASTER 总控方案
  -> 对应能力分方案
  -> 对应阶段实施计划
  -> 原子开发任务
```

---

## 4. 产品总目标

Pixelle 的长期目标是 AI 短剧/漫剧生产平台，而不是一次性视频生成脚本。

目标产品形态：

```text
Pixelle Core
  领域模型、生成流程、产物版本、Trace、Provider、Workflow 合同。

Pixelle Studio
  面向用户的 Web 创作工作台，支持剧本、分镜、角色、Prompt、重抽、选择、导出。

Pixelle API
  面向 App 和第三方的强控制 API，不暴露任意本地路径、任意 workflow 文件和任意 raw prompt 注入。

Pixelle Workers
  多机器、多 Provider、多队列的异步执行系统。
```

第一阶段产品目标不是“完整平台”，而是：

```text
用户能从主题或文案进入分镜图工作台；
能查看每格分镜的 PromptPlan；
能为每格生成多张候选图；
能选择、重抽、锁定、保留历史版本；
能查看失败原因和生成 Trace；
能在不覆盖旧产物的前提下继续迭代。
```

---

## 5. 总体架构分层

```text
Studio UI
  创作工作台、分镜格、候选图、Trace Viewer、后续 FlowGram Canvas

App API / Public API / Admin API / Internal API
  鉴权、参数校验、资源解析、额度检查、任务创建、状态查询

Pixelle Core
  SourceDocument
  ScriptDraft
  AssetBible
  StoryboardPanel
  SceneCast
  PromptPlan
  Artifact
  ArtifactVersion
  GenerationTrace
  WorkflowDefinition
  NodeContract

Execution Layer
  GenerationJob
  WorkflowRun / NodeRun
  Worker lease / heartbeat
  Provider routing

Storage Layer
  Local JSON / JSONL first
  PostgreSQL / Redis / MinIO later
```

分层原则：

- Studio 不能直接绑定 ComfyUI、工作流文件、本地路径或生成逻辑。
- FastAPI 是控制面，不是长任务执行面。
- Worker 是执行面，负责长任务、重试、恢复、Provider 调用。
- Artifact 和 Trace 是生产记录，不是临时日志。
- FlowGram 是可视化编排外壳，不是 Pixelle 的领域核心。
- Provider 是能力实现，不是业务模型。

---

## 6. 核心事实源

Pixelle 的事实源不能是 `prompt_prefix + image_prompt + final.mp4`。

长期事实源应是：

```text
SourceDocument
  用户输入、原始文案、参考资料

ScriptDraft
  剧本文本、旁白、镜头拆分、结构化场景

AssetBible
  IP、角色、场景、道具、世界观、风格

StoryboardPanel
  面板级分镜事实，包含 frame_id、source_span、画面目标和工作台状态

SceneCast
  每格分镜引用哪些角色、场景、道具、风格

PromptPlan
  从结构化事实投影出的提示词计划，不等同于最终 prompt 文本

Artifact
  稳定逻辑产物，例如 frame_003_image

ArtifactVersion
  某一次生成结果，例如 frame_003_image_v2

GenerationTrace
  每次生成、重抽、失败、选择、导出的可追踪事件
```

最终 prompt、图片、音频、视频片段和 final render 都是这些事实源的投影或产物版本。

---

## 7. 全部分方案索引

### 7.1 产品形态与系统边界分方案

来源：`01_PROJECT_TARGET_AND_SYSTEM_BOUNDARY.md`

目标：

- 定义 Pixelle Core / Studio / API / Workers。
- 明确本地增强版、多机器版、SaaS/API 版、混合云版边界。
- 规定 UI、API、Worker、Artifact、Provider 的责任。

验收：

- 任意新功能都能判断属于 Core、Studio、API 还是 Workers。
- 不再把本地路径、任意 workflow 文件、任意 raw prompt 作为长期公开合同。

### 7.2 文本与剧本生成分方案

来源：`02_TEXT_GENERATION_PIPELINE_REDESIGN.md`

目标：

- 将主题输入、视频策划、剧本草稿、旁白、视觉场景拆开。
- 不再让一个 prompt 同时负责所有文本任务。
- 为后续 ScriptDraft、ScenePlan、StoryboardPanel 提供结构化输入。

验收：

- 文本阶段可单独重跑。
- 文案、旁白、视觉描述可以独立追踪、独立版本化。

### 7.3 IP / AssetBible / 视觉一致性分方案

来源：`03_IP_LIBRARY_AND_VISUAL_CONSISTENCY.md`

目标：

- 建立 IPProfile、CharacterProfile、AssetProfile、WorldProfile、StyleProfile。
- 第一阶段支持 Prompt-only IP。
- 为后续 reference-augmented IP 预留字段。

验收：

- 分镜和 PromptPlan 通过 ID 引用角色、场景、道具和风格。
- 不以知名 IP 复刻作为默认产品策略，优先原创角色和灵感风格。

### 7.4 SceneCast / PromptComposer 分方案

来源：`04_PROMPT_COMPOSER_AND_SCENE_CASTING.md`

目标：

- SceneCast 负责决定每格分镜出现哪些角色、场景、道具和风格。
- PromptComposer 负责从结构化事实生成 PromptPlan 和 PromptProjection。
- 降低 `prompt_prefix` 的权重，避免它成为正式事实源。

验收：

- PromptPlan 可追溯到 StoryboardPanel、SceneCast 和 AssetBible。
- 修改角色或风格后，下游 PromptPlan 和图片产物能标记为 stale。

### 7.5 分镜图工作台分方案

来源：团队评审、v2 反馈、阶段一实施计划

目标：

- 建立 StoryboardPanel / StoryboardFrame 工作台模型。
- 支持候选图、选择、重抽、锁定、stale flags。
- 保留现有视频生成路径兼容性。

验收：

- 用户能按 frame 生成、选择、重抽图片。
- 旧图不被覆盖。
- 每格分镜能看到当前选中版本和候选版本。

### 7.6 Artifact / ArtifactVersion / Trace 分方案

来源：`05_GENERATION_TRACE_AND_LOGGING.md`、`09_ARTIFACT_VERSIONING_AND_REGENERATION.md`

目标：

- 区分稳定逻辑产物 `Artifact` 和具体生成版本 `ArtifactVersion`。
- 用 GenerationTrace 记录每次生成、重抽、失败、选择和导出。
- 第一阶段本地 JSON / JSONL 落盘，后续迁移到 PostgreSQL / Object Storage。

验收：

- 任意图片、音频、视频片段和最终视频都能追踪生成来源。
- 重抽不会覆盖旧版本。
- Trace event 至少包含 job_id、stage、status、frame_id、artifact_version_id。

### 7.7 Regeneration / 局部重跑分方案

来源：`09_ARTIFACT_VERSIONING_AND_REGENERATION.md`

目标：

- 支持 prompt.regenerate、image.regenerate、tts.regenerate、render.regenerate。
- 建立依赖失效规则。
- 建立 lock policy，避免用户锁定内容被自动覆盖。

验收：

- 改文案会让相关 PromptPlan 和图片标记 stale。
- 锁定图片不会被上游重跑自动替换。
- 局部重跑能保留历史版本和 Trace。

### 7.8 Workflow Skeleton 分方案

来源：长期架构文档、v2 反馈

目标：

- 先做最小 NodeContractLite、WorkflowRunLite、NodeRunLite。
- 把现有固定流程整理为 System Workflow Preset。
- 不在早期做用户自定义完整 DAG 产品。

验收：

- 工作台流程可以被记录成系统预设工作流。
- NodeContractLite 能描述输入产物、输出产物、executor_key 和 trace_stage。
- 不引入完整 FlowGram 依赖。

### 7.9 Worker / Queue / 分布式执行分方案

来源：`08_DISTRIBUTED_DEPLOYMENT_AND_WORKERS.md`

目标：

- 拆分 generation job 类型。
- 复用现有 lease / heartbeat / task 基础。
- 逐步接 Redis、Postgres、多机器 Worker。

验收：

- 长任务不由 FastAPI 同步执行。
- Worker 崩溃后任务能恢复、重试或失败归档。
- 图片、TTS、合成任务可以独立排队。

### 7.10 Provider 抽象分方案

来源：`10_PROVIDER_ABSTRACTION_LOCAL_AND_CLOUD.md`

目标：

- 建立 ImageProvider、TTSProvider、VideoProvider、LLMProvider。
- 引入 ProviderCapability，但不让它拖慢第一阶段。
- 后续支持本地 ComfyUI、RunningHub、云模型混合。

验收：

- 业务层依赖 Provider 接口，不依赖具体 ComfyUI workflow 路径。
- Provider 选择由资源、套餐、队列、能力和成本共同决定。

### 7.11 FlowGram Adapter 分方案

来源：长期架构文档、团队评审

目标：

- FlowGram 只作为 Studio 可视化编排外壳。
- 通过 Adapter 转换为 PixelleWorkflowDefinition。
- 只允许映射到已注册 NodeContract。

验收：

- FlowGram schema 变化不污染 Pixelle Core。
- 画布布局和可执行语义分开保存。
- FlowGram 不能直接执行生成任务。

### 7.12 SaaS / 权限 / 计费 / Public API 分方案

来源：`06_API_FIRST_SAAS_ARCHITECTURE.md`、`07_AUTH_PERMISSION_BILLING_AND_RESOURCE_POLICY.md`

目标：

- 建立 User、Workspace、APIKey、PlanPolicy、UsageLedger。
- 通过 ResourceResolver 控制 style_id、template_id、voice_id、workflow_preset_id。
- 对外 API 只接受强控制资源 ID。

验收：

- Public API 禁止 raw path、raw workflow、raw provider URL。
- 资源权限和额度由后端控制，不靠前端隐藏按钮。
- 重抽、生成、导出能计量和审计。

### 7.13 视频扩展分方案

来源：`StoryGen Atelier` 参考判断、长期架构文档

目标：

- 在图文分镜稳定后接 first frame / last frame。
- 支持 motion prompt、transition analysis、video segment artifact、final render artifact。
- 不破坏上游 AssetBible、StoryboardPanel、PromptPlan 和 Artifact 合同。

验收：

- 图片分镜可以升级为视频片段输入。
- 每段视频有独立 ArtifactVersion 和 Trace。
- 最终视频是可追踪的 render artifact。

### 7.14 Quality Evaluation / 管理后台分方案

来源：团队评审、v2 反馈

目标：

- 质量评分后置，不阻塞第一阶段。
- 第一阶段只做结构校验。
- 后续引入 VLM 评分、失败统计、Provider 成功率、成本分析。

验收：

- 结构校验覆盖 Artifact、PromptPlan、SceneCast、Trace。
- 主观质量评分不会阻塞工作台核心闭环。

---

## 8. 分阶段路线图

### 阶段 0：总方案与全部分方案定稿

目标：

- 确认本总控方案。
- 为全部能力分方案建立索引和优先级。
- 明确哪些文档是长期蓝图，哪些文档是实施计划。

验收：

- 本文档被确认。
- 每个阶段有明确输入、输出和禁止项。
- 阶段一计划挂到总控方案下，不再被误认为完整总方案。

### 阶段 1：分镜图工作台核心

已有计划：

`../superpowers/plans/2026-04-29-storyboard-workbench-stage1-implementation.md`

目标：

- StoryboardPanel / StoryboardFrame 工作台字段。
- PromptPlan 基础结构。
- Artifact / ArtifactVersion。
- GenerationTrace。
- frame lock / stale flags。
- image candidates / select / regenerate。
- LocalJsonArtifactService / LocalJsonTraceService。
- raw 参数开始收口。
- 最小 ContractLite，不做完整 Workflow Engine。

禁止：

- 不接完整 FlowGram。
- 不做完整 SaaS 计费。
- 不做完整 ProviderCapability 矩阵。
- 不做用户自定义 DAG。

### 阶段 2：AssetBible / SceneCast / PromptComposer

目标：

- IPProfile / CharacterProfile / SceneAsset / PropAsset / StyleProfile。
- SceneCast 校验。
- PromptPlan -> PromptProjection。
- prompt_prefix 降级为 legacy/debug 字段。

依赖：

- 阶段 1 的 PromptPlan 必须已经预留 `character_ids`、`scene_id`、`prop_ids`、`style_id`。

### 阶段 3：Artifact / Trace / Regeneration 完整闭环

目标：

- 补齐图片、音频、视频片段、最终渲染的 Artifact 类型。
- 建立完整 stale 传播规则。
- 建立 lock policy。
- 完成局部重跑 API。

依赖：

- 阶段 1 的基础 Artifact / Trace。
- 阶段 2 的 SceneCast / PromptComposer。

### 阶段 4：最小 Workflow Skeleton

目标：

- NodeContractLite。
- WorkflowRunLite。
- NodeRunLite。
- System Workflow Preset。
- StandardPipeline 迁移成 compatibility workflow。

禁止：

- 不做完整用户自定义 Workflow 产品。
- 不让 Workflow Skeleton 膨胀成 FlowGram Runtime。

### 阶段 5：Worker / Queue / 多机器执行

目标：

- 拆 generation job 类型。
- image.regenerate / prompt.regenerate / tts.regenerate。
- 复用现有 Task lease / heartbeat。
- 引入 Redis / Postgres / Worker Registry 的迁移路径。

依赖：

- 阶段 4 的 NodeRunLite 或系统任务合同。

### 阶段 6：Provider Router / Capability / ResourceResolver

目标：

- ProviderRegistry。
- ProviderCapability。
- ResourceResolver。
- 本地 ComfyUI 与云 Provider 的能力抽象。

依赖：

- 阶段 5 的任务队列。
- 阶段 2 的资源 ID。
- 阶段 3 的 Artifact 类型。

### 阶段 7：FlowGram Adapter

目标：

- FlowGram canvas -> PixelleWorkflowDefinition。
- PixelleWorkflowDefinition -> FlowGram view schema。
- NodeContract 渲染节点配置。
- FlowGram layout 与 executable semantics 分离。

依赖：

- 阶段 4 的 Workflow Skeleton。
- 阶段 6 的 Provider / ResourceResolver。

### 阶段 8：SaaS / Billing / Public API

目标：

- User / Workspace / APIKey / PlanPolicy。
- UsageLedger。
- Public API v1。
- Webhook。
- Resource permission。

依赖：

- 强控制资源 ID。
- Provider 路由。
- Artifact / Trace / Usage 可审计。

### 阶段 9：视频扩展

目标：

- first frame / last frame。
- motion prompt。
- video segment artifact。
- transition analysis。
- final render artifact。

依赖：

- 图片分镜工作台稳定。
- Artifact / Trace / Provider / Worker 稳定。

### 阶段 10：质量评估 / 管理后台 / 商业化增强

目标：

- VLM 质量评分。
- Provider 成功率、成本、耗时统计。
- Admin dashboard。
- 运营侧项目、用户、任务、额度管理。

依赖：

- SaaS、UsageLedger、Trace、Provider 数据稳定。

---

## 9. 阶段依赖总览

```text
阶段 0 总方案
  -> 阶段 1 分镜图工作台核心
    -> 阶段 2 AssetBible / SceneCast / PromptComposer
      -> 阶段 3 Artifact / Trace / Regeneration 完整闭环
        -> 阶段 4 Workflow Skeleton
          -> 阶段 5 Worker / Queue
            -> 阶段 6 Provider Router / ResourceResolver
              -> 阶段 7 FlowGram Adapter
                -> 阶段 8 SaaS / Billing / Public API

阶段 9 视频扩展依赖阶段 1、3、5、6
阶段 10 质量评估和管理后台依赖阶段 3、6、8
```

关键原则：

- 阶段 1 可以开始实现，但只能实现工作台闭环和最小合同。
- 阶段 4 之前不做用户自定义 Workflow 产品。
- 阶段 7 之前不把 FlowGram 接入主执行路径。
- 阶段 8 之前不开放 Public API 强商业化能力。
- 阶段 9 之前不把视频片段生成放入主路径。

---

## 10. 开发准入规则

任意阶段开始开发前，必须满足：

```text
1. 对应分方案已经写清楚。
2. 对应实施计划已经写清楚。
3. 输入、输出、领域模型、API、服务、测试、验收标准明确。
4. 不与当前阶段禁止项冲突。
5. 能形成原子提交。
```

任意实现任务开始前，必须回答：

```text
这个改动属于哪个阶段？
它服务于哪个分方案？
它产生或修改哪个领域合同？
它是否提前引入了后续阶段复杂度？
它是否能被测试验证？
```

如果回答不清楚，就不能进入代码实现。

---

## 11. 当前阶段判断

当前项目处于：

```text
阶段 0：总方案收敛
阶段 1：分镜图工作台核心准备开始
```

已有可复用基础：

- `StoryboardPlan` 已有 `frame_id` 和 `source_spans` 基础。
- `PersistenceService` 已有本地 JSON 持久化思路。
- `api/tasks` 已有 lease / heartbeat / PostgreSQL task 基础。
- 图像、TTS、视频、帧渲染已有局部服务能力。

当前明显缺口：

- Artifact / ArtifactVersion 未成为统一领域模型。
- GenerationTrace 仍未成为所有生成步骤的统一事实记录。
- StoryboardFrame 更偏最终媒体输出，缺少工作台选择、重抽、锁定和 stale 状态。
- API 仍暴露 `tts_workflow`、`ref_audio`、`media_workflow`、`frame_template`、`prompt_prefix`、`bgm_path` 等 raw 参数。
- Workflow / FlowGram / SaaS 还不能进入主实施路径。

因此，下一步应继续围绕阶段 1，但必须在本总控方案约束下执行。

---

## 12. 文档关系

后续文档关系如下：

```text
00_INDEX.md
  -> MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md
    -> 01-12 原始规划文档
    -> 团队评审与 v2 反馈
    -> superpowers/specs 下的长期架构设计
    -> superpowers/plans 下的阶段实施计划
```

`01-12` 文档继续作为能力域资料。正式能力分方案已经从 `13_STORYBOARD_WORKBENCH_SUBPLAN.md` 到 `22_QUALITY_EVALUATION_ADMIN_SUBPLAN.md` 建立，后续评审和实施应优先引用这些分方案。

阶段一实施计划继续有效，但它的定位是：

```text
阶段 1 子计划：分镜图工作台核心
```

不是：

```text
全项目总方案
```

---

## 13. 后续文档工作

正式分方案已经按以下顺序建立：

```text
13_STORYBOARD_WORKBENCH_SUBPLAN.md
14_ARTIFACT_TRACE_REGENERATION_SUBPLAN.md
15_ASSETBIBLE_SCENECAST_PROMPTCOMPOSER_SUBPLAN.md
16_WORKFLOW_SKELETON_SUBPLAN.md
17_WORKER_QUEUE_DISTRIBUTED_SUBPLAN.md
18_PROVIDER_RESOURCE_RESOLVER_SUBPLAN.md
19_FLOWGRAM_ADAPTER_SUBPLAN.md
20_SAAS_BILLING_PUBLIC_API_SUBPLAN.md
21_VIDEO_EXTENSION_SUBPLAN.md
22_QUALITY_EVALUATION_ADMIN_SUBPLAN.md
```

每份分方案确认后，再生成对应阶段或子阶段实施计划。已有阶段一计划继续作为 `13_STORYBOARD_WORKBENCH_SUBPLAN.md` 的第一份实施计划。

---

## 14. 最终结论

Pixelle 的正确路线不是：

```text
写一个阶段一计划 -> 直接全面开发
```

也不是：

```text
先做完整 Workflow / FlowGram / SaaS 平台 -> 再回头做创作体验
```

而是：

```text
总控方案定方向
分方案定边界
阶段计划定执行
原子任务定代码
```

当前最合理路线是：

```text
确认本总控方案
  -> 以阶段一计划启动分镜图工作台核心
  -> 同步补齐 Artifact / Trace / Regeneration 和 AssetBible / SceneCast 分方案
  -> 等工作台闭环稳定后，再进入 Workflow、Worker、Provider、FlowGram、SaaS、视频扩展
```

这样既不会丢掉大平台方向，也不会被平台复杂度拖住第一阶段产品价值。
