合理，而且这份“二次评审意见”比我上一版输出更适合直接进入实施计划。它没有推翻长期平台架构，而是把落地顺序调成更健康的产品节奏：**先把 Pixelle 从“一键生成器”升级成“分镜图创作工作台”，再逐步做 Workflow / FlowGram / SaaS。**

我建议：**基本采纳，但再补 5 个约束，避免阶段 1 做散。**

---

## 我的判断

这份判断我会给：

```text
合理性：9 / 10
可执行性：8.5 / 10
需要补强点：阶段 1 的合同边界、Artifact 模型拆分、raw 参数迁移策略
```

核心结论成立：

```text
长期架构不推翻。
FlowGram 不抢跑。
SaaS 不抢跑。
完整 Workflow Engine 不抢跑。
但 Artifact / Trace / StoryboardPanel / PromptPlan / 帧级重抽必须先做。
```

这和你主架构文档本身并不冲突。主文档已经明确 Pixelle 的核心不是 FlowGram，而是自己的领域模型、工作流定义、执行引擎、任务系统、Artifact 系统和 Trace 系统，同时第一阶段先落地 z-image 分镜图工作台。

---

## 对每条评审意见的判断

### `[P1] 落地顺序调整是正确的`

完全同意。

原主文档的长期架构很完整，但如果按“大平台基础设施”顺序推进，很容易先做：

```text
WorkflowDefinition
WorkflowRun
NodeRun
FlowGram Adapter
SaaS 权限
Billing
Provider Router
```

然后真正能让用户感知价值的东西迟迟没有：

```text
分镜格编辑
每格重抽
候选图选择
Prompt 可查看
Trace 可回放
旧版本不覆盖
局部重跑
```

你同事强调“先分镜工作台”，这是正确产品顺序。你已有的项目目标文档也把第一阶段定位为本地增强版，核心就是 IP 库、Prompt Composer、Trace、帧级重抽卡和基础 API v1，而不是完整 SaaS。

---

### `[P1] FlowGram 后置合理，但不能完全后置合同设计`

这条非常关键，我完全赞成。

正确做法不是：

```text
阶段 1 完全不考虑 Workflow
阶段 5 再突然接 FlowGram
```

而是：

```text
阶段 1 做最小合同
阶段 3 做最小 Workflow Skeleton
阶段 5 再接 FlowGram Adapter
```

也就是说，阶段 1 不需要完整 DAG Engine，但要提前定义这些轻量合同：

```text
ArtifactContract
TraceContract
PromptPlanContract
StoryboardPanelContract
RegenerationJobContract
NodeContractLite
```

其中 `NodeContractLite` 不要做复杂，只需要保证未来不返工：

```python
class NodeContractLite:
    node_type: str
    input_artifact_types: list[str]
    output_artifact_types: list[str]
    executor_key: str
    required_permission_keys: list[str]
    idempotency_scope: str
    trace_stage: str
```

第一阶段不用图形化编排，不用 DAG 调度，不用用户自定义 Workflow。但要让每一步产物都天然能被未来 Workflow 节点引用。

这和主文档“FlowGram 只作为 Studio 可视化编排外壳，必须通过 Workflow Adapter / Anti-Corruption Layer 转成 PixelleWorkflowDefinition”的原则一致。

---

### `[P1] Artifact / Trace 第一批做是必须的`

完全同意，而且这应该是阶段 1 的核心。

没有 Artifact / Trace，Pixelle 还是：

```text
输入主题
生成一堆文件
输出 final.mp4
```

有了 Artifact / Trace，才会变成：

```text
每一格分镜有状态
每一格图片有候选版本
每次重抽不覆盖旧图
用户能选择 selected version
失败能定位到 frame_id / provider / prompt / seed
Prompt 为什么这样拼可以解释
```

你的 Trace 文档已经定义了 `GenerationEvent`、`events.jsonl`、原始 prompt、原始 response、debug payload 和后续 PostgreSQL/Object Storage 迁移方式，这正好适合第一阶段先本地落盘，后面再平台化。

产物版本化文档也已经明确：图片、音频、提示词、单帧视频、最终视频都可能被重新生成，因此不能覆盖旧结果；`StoryboardFrame` 也应该保存 `selected_image_version_id`、`selected_audio_version_id`、`selected_segment_version_id` 等字段。

---

### `[P1] raw 参数收口要提前`

这条也正确，而且应该尽早做。

你同事指出当前代码还暴露：

```text
tts_workflow
ref_audio
media_workflow
frame_template
prompt_prefix
bgm_path
```

这个判断对。我重新看了压缩包里的 `api/schemas/video.py`，这些字段确实还在请求模型里。

这里的风险不是“现在不能用”，而是如果 App API / Public API 继续暴露这些 raw 参数，后面会很难做：

```text
权限控制
套餐限制
资源白名单
计费倍率
多机器部署
Provider 切换
安全审计
```

正确迁移方式是：

```text
prompt_prefix  -> style_id / style_preset_id
media_workflow -> workflow_preset_id / provider_preset_id
frame_template -> template_id
bgm_path       -> bgm_id
ref_audio      -> voice_id / voice_asset_id
tts_workflow   -> voice_preset_id / tts_provider_id
```

你已有的系统边界文档也明确说，对外 API 不能直接让用户传 workflow 文件路径、本地模板路径、任意 prompt_prefix、任意 bgm_path，而应该改成 `workflow_id`、`template_id`、`style_id`、`ip_id`、`voice_id`、`bgm_id`，由后端按套餐和权限做白名单过滤。

我的补充建议是：不要一刀切删掉旧字段。建议分层处理：

```text
/internal/debug API:
  可以继续接受本地路径、workflow 文件、prompt_prefix
  仅开发环境可用

/app API:
  只接受资源 ID
  可允许 prompt_prefix 作为 legacy 兼容字段，但不推荐

/public API:
  严格禁止 raw path / raw workflow / raw provider URL
  只允许白名单资源 ID
```

---

### `[P2] 本地 JSON ArtifactService 可以做，但必须藏在接口后面`

完全同意。

第一阶段用本地 JSON 是对的，因为你现在最需要验证的是产品闭环，不是数据库工程：

```text
生成
重抽
选择
版本保留
Trace 查看
局部重跑
导出
```

但业务代码绝不能直接依赖：

```text
output/{task_id}/artifacts.json
output/{task_id}/trace/events.jsonl
output/{task_id}/images/frame_001_v2.png
```

正确方式是第一天就定义接口：

```python
class ArtifactService:
    def create_artifact(...)
    def create_version(...)
    def list_versions(...)
    def select_version(...)
    def mark_rejected(...)
    def mark_failed(...)
    def get_selected_version(...)
```

然后第一版实现：

```text
LocalJsonArtifactService
LocalJsonTraceService
```

后面替换成：

```text
PostgresArtifactService
ObjectStorageArtifactStore
PostgresTraceService
```

这样就不会因为 MVP 用本地 JSON 而形成长期技术债。你的数据库文档也已经把未来核心表列出来了，包括 `storyboard_frames`、`artifact_versions`、`generation_jobs`、`generation_events`，说明这个迁移路径是自然的。

---

### `[P2] ProviderCapability 矩阵合理，但不必抢在工作台前面`

同意。

ProviderCapability 长期一定需要，因为未来会有：

```text
本地 Z-Image
ComfyUI
RunningHub
云图像 API
云 TTS
本地 TTS
云视频模型
```

Provider 文档里也已经设计了 TextProvider、ImageProvider、TTSProvider、VideoProvider、RenderProvider、StorageProvider，以及 ProviderRouter 根据套餐、队列长度、GPU 是否忙、任务优先级、成本、质量要求选择 Provider。

但阶段 1 不应该被 ProviderCapability 拖慢。阶段 1 只需要做到：

```text
artifact.provider_id
artifact.model_id
artifact.seed
artifact.workflow_preset_id
artifact.provider_metadata
```

也就是说，**先记录 Provider 信息，暂时不做复杂路由**。

ProviderCapability 可以放到：

```text
接入第二个图像 Provider 之前
或 Worker 队列拆分之前
```

这样更务实。

---

### `[P3] Quality Evaluation 很好，但应作为阶段 2/3 增强项`

同意，但我要加一个区分。

阶段 1 不做复杂质量评分：

```text
script_quality_score
character_consistency_score
prompt_adherence_score
image_selection_score
```

这些可以后置。

但阶段 1 必须做**结构校验**，例如：

```text
frame_id 唯一
frame_index 连续
ArtifactVersion 状态合法
selected_image_version_id 必须指向当前 frame 的 image artifact version
SceneCast 里的 character_id 必须存在
PromptPlan 必须能追溯到 StoryboardPanel
Trace event 必须有 job_id / stage / status
```

也就是说：

```text
主观质量评分可以后置。
工程合同校验不能后置。
```

---

## 我建议在你同事方案上再加 5 个收紧点

### 1. 阶段 1 要拆清楚 `Artifact` 和 `ArtifactVersion`

你同事写的是：

```text
Artifact + ArtifactVersion
```

这个方向对，但实现时建议明确拆成两个概念：

```text
Artifact = 稳定逻辑产物
ArtifactVersion = 某一次生成出来的版本
```

例如：

```text
frame_003_image 是 Artifact
frame_003_image_v1 / v2 / v3 是 ArtifactVersion
```

这样用户选择图片时，实际是：

```text
Artifact.current_selected_version_id = version_2
```

而不是把某个 version 的 `status` 改来改去承担全部含义。

推荐结构：

```python
class Artifact:
    artifact_id: str
    project_id: str
    storyboard_id: str | None
    frame_id: str | None
    artifact_type: str
    logical_key: str
    current_selected_version_id: str | None
    created_at: datetime
    updated_at: datetime


class ArtifactVersion:
    artifact_version_id: str
    artifact_id: str
    version: int
    status: str  # pending / running / candidate / selected / rejected / failed
    object_key: str | None
    url: str | None
    provider_id: str | None
    model_id: str | None
    prompt: str | None
    seed: int | None
    metadata: dict
    created_at: datetime
```

---

### 2. `PromptPlan` 放阶段 1 可以，但要预留 SceneCast 字段

你同事建议：

```text
阶段 1：StoryboardPanel / PromptPlan
阶段 2：AssetBible / SceneCast / PromptComposer
```

这个顺序基本可行，但有一个隐患：`PromptPlan` 本来就应该依赖角色、场景、道具和风格上下文。如果阶段 1 完全没有 SceneCast，后面可能要改 PromptPlan schema。

建议阶段 1 先做一个可空的结构：

```python
class PromptPlan:
    prompt_plan_id: str
    panel_id: str

    base_prompt: str
    final_prompt: str | None
    negative_prompt: str | None

    style_id: str | None = None
    world_id: str | None = None
    character_ids: list[str] = []
    scene_id: str | None = None
    prop_ids: list[str] = []

    composer_version: str | None = None
    debug_parts: dict = {}
```

阶段 1 可以先不真正实现复杂 SceneCast，但字段要在。这样阶段 2 接 AssetBible / SceneCast 时不会迁移大模型。

---

### 3. `prompt_prefix` 降级要有明确策略

不能只是说“降级为兼容字段”，建议写成制度：

```text
prompt_prefix:
  - internal/debug API: allowed
  - app API: deprecated, only for legacy compatibility
  - public API: forbidden
  - persisted artifact: can record as legacy_style_text
  - future replacement: style_id + StyleProfile
```

否则它会一直以“临时兼容”的名义存在，最后继续变成视觉一致性的事实源。

---

### 4. `stale_flags` 要配合依赖失效规则

你同事提到：

```text
frame lock / stale flags
```

这非常对，但需要加上依赖关系，否则 stale 只是一个标记，不知道怎么传播。

建议阶段 1 至少支持这些规则：

```text
修改 narration:
  prompt_plan stale
  image artifact stale
  audio artifact stale
  frame_segment stale
  final_video stale

修改 final_prompt:
  image artifact stale
  frame_segment stale
  final_video stale

选择新的 image version:
  frame_segment stale
  final_video stale

修改 audio version:
  frame_segment stale
  final_video stale

锁定 image:
  上游重跑不能覆盖 selected_image_version_id
```

这和你产物版本化文档中的依赖影响规则是一致的。

---

### 5. 阶段 3 的 Workflow Skeleton 不要变成完整 Workflow Engine

你同事建议：

```text
阶段 3：最小 Workflow Skeleton
- NodeContract
- in-process WorkflowRun
- System Workflow Preset
```

这个方向对，但要防止阶段 3 膨胀。

阶段 3 只做：

```text
System Workflow Preset
NodeContractLite
Run record
NodeRunLite record
Artifact input/output record
Trace event record
```

暂时不做：

```text
用户自定义 DAG
复杂条件分支
可视化编排
FlowGram canvas 双向同步
跨工作流复用
企业 workflow marketplace
```

换句话说，阶段 3 的目标不是“做 Workflow 产品”，而是把当前工作台流程整理成可记录、可追踪、可扩展的系统预设。

---

## 我建议最终采用这个版本的阶段路线

你同事的阶段路线已经不错，我建议微调成下面这样：

```text
阶段 1：分镜图工作台核心
- StoryboardPanel / StoryboardFrame 扩展
- PromptPlan 基础结构
- Artifact + ArtifactVersion
- GenerationTrace
- frame lock / stale flags
- image candidates / select / regenerate
- LocalJsonArtifactService / LocalJsonTraceService
- raw 参数开始收口
- 最小 ContractLite，不做完整 Workflow Engine

阶段 2：AssetBible / SceneCast / PromptComposer
- IPProfile / CharacterProfile / SceneAsset / PropAsset / StyleProfile
- 角色、场景、道具 ID 约束
- SceneCast 校验
- PromptPlan -> PromptProjection
- prompt_prefix 降级为 legacy/debug 字段

阶段 3：最小 Workflow Skeleton
- NodeContractLite
- in-process WorkflowRun
- NodeRunLite
- System Workflow Preset
- StandardPipeline 迁移成 compatibility workflow

阶段 4：Worker / Queue
- 拆 generation job 类型
- image.regenerate / prompt.regenerate / tts.regenerate
- lease / heartbeat 继续复用现有 Task 基础
- 后续再升级为真正 NodeRun 队列

阶段 5：FlowGram Adapter
- FlowGram canvas -> PixelleWorkflowDefinition
- PixelleWorkflowDefinition -> FlowGram view schema
- 只允许映射到已注册 NodeContract
- FlowGram 不作为事实源

阶段 6：SaaS / Billing / Public API
- User / Workspace / APIKey / PlanPolicy
- UsageLedger
- ResourceResolver
- Public API 强控制

阶段 7：视频扩展
- first frame / last frame
- motion prompt
- video segment artifact
- transition analysis
- final render artifact
```

---

## 最终结论

你的同事判断是合理的，建议采纳。

但采纳时要写成一个更明确的工程决议：

```text
我们不降低长期平台目标；
我们只是调整建设顺序。

第一目标不是 Workflow 平台，
而是分镜图工作台。

第一阶段必须交付：
StoryboardPanel、PromptPlan、ArtifactVersion、GenerationTrace、帧级重抽、候选图选择、局部重跑、Trace 查看。

FlowGram、完整 Workflow、SaaS、Billing、ProviderCapability、Quality Evaluation 后置，
但最小合同、Artifact 接口、Trace 接口、资源 ID 边界必须提前定义。
```

一句话：**这份二次评审是对的。它不是否定大架构，而是把大架构拆成了更可能成功的产品落地路径。**
