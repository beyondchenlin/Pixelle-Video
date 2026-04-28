# Pixelle AI 短剧漫剧工作流平台架构设计

日期：2026-04-28

## 1. 设计结论

Pixelle 应按大型项目规划，升级为一个模块解耦、Artifact 驱动、Workflow 可编排的 AI 短剧漫剧生产平台。

本设计确认以下方向：

- Pixelle 的核心不是 FlowGram，也不是任何一个参考项目的拼接。
- FlowGram 只作为 Pixelle Studio 中的可视化工作流编辑器。
- Pixelle 必须拥有自己的领域模型、工作流定义、执行引擎、任务系统、产物系统和 Trace 系统。
- FastAPI 只作为控制面和 API 网关，不直接执行长时间生成任务。
- Worker 才是真正执行文本、分镜、Prompt、图片、音频、视频等生成任务的地方。
- 第一阶段先落地 z-image 分镜图工作台，但底层架构必须兼容未来图生图、首尾帧、图生视频和完整 SaaS。

核心关系如下：

```text
FlowGram canvas schema
  -> Workflow Adapter
  -> PixelleWorkflowDefinition
  -> Pixelle Workflow Engine
  -> WorkflowRun / NodeRun
  -> Queue Jobs
  -> Workers
  -> ArtifactVersion / GenerationTrace / ProviderRun
```

FlowGram 是 Studio 的可视化编排外壳，不是 Pixelle 的领域核心。

## 2. 背景与问题

Pixelle 当前已经具备 AI 短视频生成系统雏形：

```text
用户输入主题或文案
  -> 生成旁白
  -> 生成图片提示词
  -> TTS
  -> 图片或视频生成
  -> 模板渲染
  -> FFmpeg 合成
```

但如果继续沿着“单条 pipeline + 一次性大模型输出 + prompt 直接作为事实源”的方向发展，会遇到这些结构性问题：

- 大模型输出 JSON 不稳定，错误修复依赖兜底，无法从源头解决。
- 文案、角色、场景、道具、分镜、Prompt 之间缺少稳定中间产物。
- 用户无法编辑、锁定、局部重跑某一个阶段。
- 角色和场景一致性依赖 prompt 前缀，缺少资产级约束。
- 产物容易被覆盖，无法支持候选图、重抽卡和版本选择。
- FastAPI 如果直接执行长任务，会阻塞 API 层并妨碍分布式扩展。
- 如果直接绑定 FlowGram Runtime，会把 Python 生成引擎、GPU Worker、Artifact、Billing、Trace 切成两套系统。

因此，Pixelle 需要从源头建立平台级架构，而不是局部修补。

## 3. 参考项目的公允判断

参考项目只作为设计证据，不作为 Pixelle 的结构来源。

### 3.1 Toonflow-app

可借鉴点：

- 专业短剧创作阶段拆分。
- 故事骨架、改编策略、导演规划、分镜表、分镜面板等阶段产物。
- 分镜表中对台词、时长、镜头、角色、场景的严格约束。

不照搬点：

- 不直接照搬它的 Agent 体系。
- 不把 Markdown Skill 作为 Pixelle 的核心执行协议。

### 3.2 waoowaoo

可借鉴点：

- 资产中心、项目工作台、分阶段执行体验。
- GraphRun、GraphStep、GraphArtifact 类似的任务图思路。
- Prompt JSON 守卫、任务守卫、测试覆盖和计费模型。
- 角色、场景、道具在分镜阶段作为上下文输入。

不照搬点：

- 不照搬 Next.js 全栈结构。
- 不把前端状态或 Prisma 表结构作为 Pixelle 的领域核心。

### 3.3 Huobao Drama

可借鉴点：

- 中文短剧 SaaS 形态清晰。
- Agent 工具读写数据库。
- 分镜保存前校验 scene_id 和 character_ids 是否属于当前集。
- 图片、视频、角色、场景、Agent 配置可作为 SaaS 资源管理。

不照搬点：

- 不把轻量 SQLite 单体实现当成 Pixelle 的最终架构。
- 不让 Agent 直接拥有不可控的数据库写权限。

### 3.4 StoryGen Atelier

可借鉴点：

- Shot A -> Shot B 的 transition analysis。
- 首帧/尾帧驱动的视频片段生成。
- 片段并行生成后通过 FFmpeg 拼接。
- Storyboard log 和 Video log。

不照搬点：

- 不把后段视频链路提前放入 MVP 主路径。
- 不让视频生成模型决定上游分镜事实源。

### 3.5 ViMax / AI-Creator

可借鉴点：

- 多 Agent 分工。
- 角色提取、场景提取、分镜设计、Camera tree。
- 参考图选择器和最佳图选择器。
- first frame、last frame、motion prompt 拆解。

不照搬点：

- 不在第一阶段直接追求端到端长视频。
- 不让参考图选择逻辑替代基础资产和分镜模型。

## 4. 架构原则

### 4.1 领域核心独立

Pixelle Core 必须不依赖 FlowGram、Streamlit、Next.js、Vue、React 或任意具体 UI。

Pixelle Core 只关心：

- 领域模型。
- 合同校验。
- WorkflowDefinition。
- WorkflowRun。
- NodeRun。
- ArtifactVersion。
- GenerationTrace。
- ProviderRun。

### 4.2 UI 不直接绑定生成逻辑

Studio 可以通过 FlowGram 提供可视化编辑，但它只调用 API：

```text
create workflow
update workflow
validate workflow
publish workflow
run workflow
read run events
read artifacts
```

Studio 不应该直接调用 Python service，不应该直接调用 ComfyUI，不应该直接拼接生成 prompt。

### 4.3 FastAPI 是控制面，不是执行面

FastAPI 负责：

- 鉴权。
- 参数校验。
- 权限和额度检查。
- Workflow CRUD。
- Workflow validate。
- 创建 WorkflowRun。
- 查询任务状态。
- 返回事件和产物。

FastAPI 不负责：

- 长时间 LLM 生成。
- 图片生成。
- TTS。
- 视频生成。
- FFmpeg 合成。
- 多节点工作流同步执行。

### 4.4 Worker 是执行面

所有耗时任务进入队列：

```text
queue.script
queue.asset
queue.storyboard
queue.prompt
queue.image
queue.tts
queue.video
queue.render
queue.upload
```

Worker 根据任务类型和 Provider 能力消费任务。

### 4.5 Artifact 是阶段事实源

每个阶段输出都必须是可保存、可校验、可追踪、可版本化的 Artifact。

最终 prompt 不是事实源，它只是从上游结构化事实投影出来的渲染产物。

### 4.6 FlowGram 必须通过防腐层接入

FlowGram Schema 不能成为 Pixelle 的唯一事实源。

必须引入：

```text
Workflow Adapter / Anti-Corruption Layer
```

职责：

- 将 FlowGram canvas schema 转成 PixelleWorkflowDefinition。
- 将 PixelleWorkflowDefinition 转回 FlowGram 可展示 schema。
- 校验 FlowGram 节点类型是否映射到 PixelleNodeContract。
- 屏蔽 FlowGram 内部 schema 变化对 Pixelle Core 的影响。

## 5. 总体分层

```text
Pixelle Studio
  - FlowGram workflow editor
  - asset workspace
  - storyboard workspace
  - artifact gallery
  - trace viewer

Pixelle API
  - App API
  - Public API
  - Admin API
  - Internal Worker API

Pixelle Workflow Control Plane
  - workflow definition service
  - workflow validation service
  - workflow compiler
  - workflow run scheduler

Pixelle Core
  - domain models
  - node contracts
  - artifact contracts
  - trace contracts
  - provider contracts

Pixelle Execution Plane
  - queue
  - workers
  - provider router
  - retry policy
  - idempotency

Pixelle Storage Plane
  - database
  - object storage
  - artifact versions
  - generation events
```

## 6. 核心领域模型

### 6.1 项目与输入

```text
Workspace
Project
SourceDocument
SourceSegment
EpisodePlan
ClipPlan
```

SourceDocument 是所有输入的标准化结果，支持：

- 主题。
- 长文。
- 小说。
- SRT。
- 已有剧本。

SourceSegment 和 ClipPlan 负责将长文本拆分为可处理的剧情片段。

### 6.2 剧本与资产

```text
ScriptDraft
ScriptScene
AssetBible
CharacterAsset
CharacterAppearance
SceneAsset
SceneSlot
PropAsset
StyleBible
WorldBible
VoiceAsset
```

AssetBible 是角色、场景、道具、风格、世界观的项目级资产集合。

所有分镜、Prompt 和生成节点只能引用 AssetBible 中的资产 ID，禁止模型编造 ID。

### 6.3 分镜与 Prompt

```text
Storyboard
StoryboardPanel
SceneCast
PromptPlan
PromptProjection
```

StoryboardPanel 保存一格画面或一个镜头的结构化事实：

- source_text。
- description。
- shot_type。
- camera_move。
- action。
- dialogue。
- duration。
- character_ids。
- scene_id。
- prop_ids。
- source_span。
- continuity_anchors。
- first_frame_plan。
- last_frame_plan。
- motion_plan。

PromptPlan 保存面向模型的结构化提示词计划：

- subject_block。
- action_block。
- scene_block。
- camera_block。
- style_block。
- continuity_block。
- negative_prompt。
- provider_specific_payload。

最终给 z-image 或 ComfyUI 的 prompt 是 PromptProjection，不是事实源。

### 6.4 任务与产物

```text
WorkflowDefinition
WorkflowNode
WorkflowEdge
WorkflowRun
NodeRun
GenerationJob
ProviderRun
GenerationTrace
ArtifactVersion
ArtifactRef
```

ArtifactVersion 支持候选、选中、失败、废弃等状态。

典型 artifact_type：

```text
source_document
script_draft
asset_bible
clip_plan
storyboard
storyboard_panel
prompt_plan
image
audio
video_segment
final_video
trace
```

## 7. WorkflowDefinition 设计

PixelleWorkflowDefinition 是 Pixelle 的内部工作流事实源。

```python
class PixelleWorkflowDefinition(BaseModel):
    workflow_id: str
    version: int
    name: str
    description: str | None
    mode: Literal["system", "workspace", "project"]
    input_schema: dict
    output_schema: dict
    nodes: list[PixelleWorkflowNode]
    edges: list[PixelleWorkflowEdge]
    metadata: dict = {}
```

```python
class PixelleWorkflowNode(BaseModel):
    node_id: str
    node_type: str
    title: str
    contract_version: int
    inputs: dict
    outputs: dict
    config: dict
    retry_policy: dict | None = None
    resource_policy: dict | None = None
```

```python
class PixelleWorkflowEdge(BaseModel):
    source_node_id: str
    source_output: str
    target_node_id: str
    target_input: str
```

FlowGram 的 nodes、edges、meta.position 只属于展示层。

PixelleWorkflowDefinition 只保存可执行语义。

## 8. FlowGram Adapter 设计

FlowGram Adapter 的职责是隔离 FlowGram 和 Pixelle。

```text
flowgram_schema_to_pixelle_definition()
pixelle_definition_to_flowgram_schema()
validate_flowgram_mapping()
extract_canvas_layout()
merge_canvas_layout()
```

保存时：

```text
FlowGram schema
  -> adapter
  -> PixelleWorkflowDefinition
  -> validation
  -> persist definition
  -> persist canvas layout separately
```

读取时：

```text
PixelleWorkflowDefinition
  + canvas layout
  -> adapter
  -> FlowGram schema
  -> Studio render
```

关键规则：

- FlowGram node.type 必须映射到 Pixelle node_type。
- FlowGram inputsValues 必须映射到 Pixelle inputs。
- Pixelle 不信任前端传入的 Provider、workflow 路径、本地路径、API Key。
- Provider、模型、模板、资源都必须由后端根据权限和白名单解析。

### 8.1 FlowGram 部署与集成边界

推荐形态：

```text
Pixelle Studio
  -> Workflow Editor module powered by FlowGram
  -> Pixelle FastAPI workflow APIs
  -> PixelleWorkflowDefinition
```

FlowGram 可以作为 Studio 内的前端包、独立子应用或微前端接入，但它只负责：

- 画布交互。
- 节点拖拽。
- 节点配置表单。
- 连线与布局。
- 工作流可视化调试。

FlowGram 不负责：

- 保存 Pixelle 的领域事实源。
- 直接调度生产任务。
- 直接访问 Provider。
- 直接读写 Artifact。
- 直接写入 Billing、Trace、Worker 状态。

如果未来需要使用 FlowGram Runtime 做本地预览或教学演示，只能作为隔离的 preview service，不能进入生产执行主路径。生产执行必须经过 Pixelle WorkflowCompiler、WorkflowRun、NodeRun、Queue 和 Worker。

因此，FastAPI 不是 FlowGram 的替代品，FlowGram 也不是 FastAPI 的替代品：

```text
FlowGram = visual workflow authoring
FastAPI = control plane and resource boundary
Pixelle Workflow Engine = executable semantics and scheduling
Workers = generation execution
```

数据持久化建议拆成两类：

```text
pixelle_workflow_definitions
pixelle_workflow_canvas_layouts
```

前者保存可执行语义，后者保存 FlowGram 展示布局。任何 FlowGram schema 变化都只能影响 layout adapter，不能迫使 Pixelle Core 修改领域模型。

## 9. 节点合同

第一批节点应是平台级节点，而不是底层技术节点。

```text
InputSourceNode
ScriptDraftNode
AssetExtractNode
AssetBibleNode
ClipPlanNode
StoryboardNode
SceneCastingNode
PromptPlanNode
ImageGenerateNode
ImageSelectNode
TTSNode
VideoPrepareNode
VideoGenerateNode
FinalRenderNode
EndNode
```

### 9.1 节点合同格式

```python
class PixelleNodeContract(BaseModel):
    node_type: str
    version: int
    display_name: str
    category: str
    input_schema: dict
    output_schema: dict
    config_schema: dict
    produces_artifact_types: list[str]
    consumes_artifact_types: list[str]
    queue_name: str | None
    permissions: list[str]
```

### 9.2 节点执行接口

```python
class NodeExecutor(Protocol):
    node_type: str

    async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
        ...
```

```python
class NodeExecutionContext(BaseModel):
    workflow_run_id: str
    node_run_id: str
    project_id: str
    workspace_id: str
    user_id: str
    inputs: dict
    config: dict
    artifact_refs: dict
    trace_context: dict
```

```python
class NodeExecutionResult(BaseModel):
    outputs: dict
    artifacts: list[ArtifactRef]
    events: list[GenerationEvent]
```

## 10. API 设计

FastAPI 提供控制面 API。

### 10.1 Workflow API

```http
POST /api/v1/app/workflows
GET  /api/v1/app/workflows
GET  /api/v1/app/workflows/{workflow_id}
PATCH /api/v1/app/workflows/{workflow_id}
POST /api/v1/app/workflows/{workflow_id}/validate
POST /api/v1/app/workflows/{workflow_id}/publish
```

### 10.2 Run API

```http
POST /api/v1/app/workflows/{workflow_id}/runs
GET  /api/v1/app/workflow-runs/{run_id}
GET  /api/v1/app/workflow-runs/{run_id}/events
GET  /api/v1/app/workflow-runs/{run_id}/artifacts
POST /api/v1/app/workflow-runs/{run_id}/cancel
```

### 10.3 Node Contract API

```http
GET /api/v1/app/workflow-node-contracts
GET /api/v1/app/workflow-node-contracts/{node_type}
```

Studio 用这个 API 渲染 FlowGram 节点面板和节点配置表单。

### 10.4 Internal Worker API

```http
POST /api/v1/internal/workers/heartbeat
POST /api/v1/internal/workflow-runs/{run_id}/node-runs/{node_run_id}/events
POST /api/v1/internal/artifacts
PATCH /api/v1/internal/node-runs/{node_run_id}
```

## 11. 执行流程

用户点击运行工作流后：

```text
1. FastAPI 校验 workflow_id、权限、额度、输入参数。
2. WorkflowCompiler 将 WorkflowDefinition 编译成 DAG。
3. 创建 WorkflowRun。
4. 创建初始 NodeRun。
5. Scheduler 将可执行节点投递到队列。
6. Worker 领取 NodeRun。
7. Worker 调用对应 NodeExecutor。
8. NodeExecutor 产出 ArtifactVersion 和 GenerationEvent。
9. Scheduler 检查下游节点依赖是否满足。
10. 下游节点继续入队。
11. 所有 EndNode 完成后 WorkflowRun 完成。
```

## 12. 错误处理与重试

错误分四类：

```text
validation_error
provider_error
resource_error
system_error
```

规则：

- 合同校验失败不重试。
- Provider 临时失败可按节点 retry_policy 重试。
- 资源不存在或权限不足不重试。
- Worker 崩溃后通过 heartbeat 和 lease 回收 NodeRun。
- 所有失败都必须写入 GenerationTrace。
- 不允许静默兜底生成另一套内容。

LLM JSON 失败处理：

```text
structured output
  -> schema validation
  -> semantic validation
  -> repair prompt with precise validation errors
  -> retry same stage
  -> if still failed, return diagnostic error
```

## 13. Artifact 与版本化

每个节点输出 ArtifactVersion。

```python
class ArtifactVersion(BaseModel):
    artifact_id: str
    artifact_type: str
    version: int
    status: Literal["pending", "running", "candidate", "selected", "rejected", "failed"]
    workflow_run_id: str
    node_run_id: str
    project_id: str
    frame_id: str | None
    object_key: str | None
    payload: dict | None
    provider: str | None
    metadata: dict
```

重抽卡不覆盖旧图片：

```text
ImageGenerateNode
  -> image artifact v1 candidate
  -> image artifact v2 candidate
  -> user selects v2
  -> selected_image_version_id = v2
```

## 14. Trace 设计

GenerationTrace 需要覆盖：

- workflow_run started。
- node_run queued。
- node_run started。
- LLM prompt sent。
- LLM raw response received。
- validation result。
- retry reason。
- provider request。
- provider response。
- artifact created。
- node_run completed。
- workflow_run completed。

普通用户看到简化进度。

高级用户看到 Storyboard、PromptPlan、Artifact 版本。

管理员看到 raw prompt、raw response、stack trace、provider latency、token usage。

## 15. 权限与安全

禁止前端直接传：

```text
本地 workflow 路径
本地 template 路径
本地模型路径
任意 provider URL
任意 API Key
任意 prompt_prefix
任意 bgm_path
```

必须改成：

```text
workflow_preset_id
template_id
provider_id
model_id
style_id
voice_id
bgm_id
asset_id
```

后端根据 workspace、plan、permission、resource whitelist 解析。

## 16. 与现有 Pixelle 的关系

现有 Pixelle 已经有：

- StoryboardPlan。
- PromptContextEnvelope。
- ImagePromptComposer。
- StandardPipeline。
- Video API。
- Task API。
- File API。
- Size Contract 和 Rendering Contract。

新架构不应推倒重来，而是逐步将现有能力模块化：

```text
StandardPipeline
  -> temporary compatibility pipeline

StoryboardGenerationService
  -> StoryboardNode executor

ImagePromptComposer
  -> PromptPlanNode executor

current media generation
  -> ImageGenerateNode / TTSNode / FinalRenderNode executor

existing tasks
  -> GenerationJob / NodeRun
```

兼容期允许旧 pipeline 调新服务，但新工作流不应依赖旧 pipeline 内部状态。

## 17. 分阶段实施路线

### 阶段 0：架构定稿

目标：

- 确认平台定位。
- 确认 FlowGram 解耦原则。
- 确认 PixelleWorkflowDefinition。
- 确认节点合同。
- 确认 API 边界。

验收：

- 设计文档被确认。
- 实施计划被确认。

### 阶段 1：领域合同层

目标：

- 新增 WorkflowDefinition、WorkflowRun、NodeRun。
- 新增 ArtifactVersion、ArtifactRef。
- 新增 GenerationTrace 模型。
- 新增 NodeContract 注册表。

验收：

- 能定义一个不可执行的工作流。
- 能校验节点和边。
- 能序列化和反序列化。

### 阶段 2：FlowGram Adapter

目标：

- 将 FlowGram schema 转 PixelleWorkflowDefinition。
- 将 PixelleWorkflowDefinition 转 FlowGram schema。
- 保存 canvas layout。
- 节点配置由后端 NodeContract 渲染。

验收：

- Studio 可以画一个简单工作流并保存。
- 后端能校验并返回 PixelleWorkflowDefinition。
- 修改 FlowGram 展示布局不影响 PixelleWorkflowDefinition。

### 阶段 3：Workflow Run Skeleton

目标：

- 实现 WorkflowCompiler。
- 实现 WorkflowRun 和 NodeRun 状态机。
- 实现同步 fake executor 或 in-process executor 用于测试。
- 实现 run events。

验收：

- 一个 Start -> ScriptDraft -> End 的测试工作流能跑通。
- 每个节点有 NodeRun 和事件。

### 阶段 4：Worker 执行面

目标：

- NodeRun 入队。
- Worker 领取执行。
- Worker heartbeat。
- NodeRun lease。
- 失败重试。

验收：

- FastAPI 不同步执行长任务。
- Worker 崩溃后 NodeRun 可恢复或失败。

### 阶段 5：短剧漫剧 MVP 节点

目标：

- InputSourceNode。
- ScriptDraftNode。
- AssetExtractNode。
- AssetBibleNode。
- ClipPlanNode。
- StoryboardNode。
- SceneCastingNode。
- PromptPlanNode。
- ImageGenerateNode。

验收：

```text
主题或文案
  -> 剧本草稿
  -> 角色/场景/道具资产
  -> 分镜面板
  -> PromptPlan
  -> z-image 分镜图候选
```

### 阶段 6：版本化与工作台

目标：

- 图片候选版本。
- 重抽卡。
- 选择版本。
- 局部重跑。
- Trace viewer。

验收：

- 用户能重抽某一格分镜图。
- 不覆盖旧图。
- 下游依赖能标记为需要重算。

### 阶段 7：视频扩展

目标：

- first frame / last frame。
- motion prompt。
- Shot A -> Shot B transition analysis。
- 图生视频 Provider。
- video segment artifact。
- final render。

验收：

- 在不改上游资产和分镜模型的前提下接入视频链路。

## 18. 测试策略

### 18.1 合同测试

- WorkflowDefinition schema 测试。
- NodeContract schema 测试。
- FlowGram Adapter round-trip 测试。
- ArtifactVersion 状态流转测试。

### 18.2 执行测试

- WorkflowCompiler DAG 测试。
- NodeRun 状态机测试。
- Retry policy 测试。
- Worker lease 和 heartbeat 测试。

### 18.3 业务测试

- SourceDocument -> ScriptDraft。
- ScriptDraft -> AssetBible。
- ClipPlan -> StoryboardPanel。
- StoryboardPanel -> PromptPlan。
- PromptPlan -> ImageGenerate request。

### 18.4 回归守卫

- 禁止 API 直接长时间执行节点。
- 禁止 FlowGram schema 直接进入执行引擎。
- 禁止前端提交 provider secret。
- 禁止模型输出未注册 asset_id。
- 禁止 Artifact 覆盖旧版本。

## 19. 非目标

本设计当前不做：

- 不直接实现完整视频生成平台。
- 不直接重写前端 Studio。
- 不直接迁移到 K8S。
- 不直接照搬 FlowGram Runtime 作为生产后端。
- 不直接将所有旧 StandardPipeline 删除。
- 不直接实现复杂多 Agent 自主编排。

这些能力可以在架构稳定后分阶段进入。

## 20. 需要确认的最终选择

本设计建议采用：

```text
FlowGram UI + Pixelle WorkflowDefinition + FastAPI control plane + Python Workflow Engine + Worker execution plane
```

这是最符合“最佳实践、源头解决问题、禁止最小改动、不留技术债、大型项目分步开发”的方案。

用户确认后，下一步应创建实施计划，将阶段 1 到阶段 3 拆成可执行任务。
