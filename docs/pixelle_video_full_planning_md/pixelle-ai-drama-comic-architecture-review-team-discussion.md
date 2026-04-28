# Pixelle AI 短剧漫剧工作流平台架构评估与改进建议

日期：2026-04-28  
用途：团队架构评审 / 产品路线讨论 / 后续开发拆分参考  
评估对象：`2026-04-28-ai-drama-comic-workflow-platform-architecture-design.md`、配套 01-12 规划文档、Pixelle-Video 最新代码压缩包

---

## 1. 总体结论

你的 `2026-04-28-ai-drama-comic-workflow-platform-architecture-design.md` 方向是合理的，而且是 Pixelle 目前代码继续发展的正确长期架构。

它抓住了当前 Pixelle 的核心矛盾：Pixelle 不能继续只是“单条生成 pipeline + prompt_prefix + 本地文件路径 + 最终视频输出”，而应该升级成一个以结构化剧情、资产、分镜、PromptPlan、Artifact、Trace 为事实源的 AI 短剧/漫剧生产平台。

我对当前方案的判断是：

```text
长期架构合理性：8.5 / 10
当前落地顺序合理性：7 / 10
推荐路线：先降级落地，再逐步平台化
```

也就是说，大方向不要改，但实施顺序需要调整。

最大风险不是架构错，而是太早做完整 Workflow Engine、FlowGram Adapter、SaaS 权限计费和多 Worker 编排，导致真正能给用户带来价值的“短剧/漫剧分镜工作台”迟迟做不出来。

---

## 2. 参考项目定位判断

你对参考项目的定位基本成立。

### 2.1 Toonflow-app

Toonflow-app 最接近“小说/文案改短剧”的完整架构。

适合参考：

```text
小说/文案输入
剧本改编
AI 编剧
分镜
角色设计
视频生成
专业短剧阶段拆分
```

但不建议直接照搬它的 Agent 体系或执行协议。

Pixelle 应吸收它的“创作阶段拆分”思想，而不是把 Toonflow 的内部结构变成 Pixelle 的后端结构。

### 2.2 waoowaoo

waoowaoo 的产品完整度和热度高，适合参考“工业级全流程 AI 影视生产平台”的产品感。

适合参考：

```text
资产中心
项目工作台
分阶段执行体验
GraphRun / GraphStep / GraphArtifact 思路
Prompt JSON 守卫
任务守卫
计费模型
```

但不建议照搬它的前端全栈结构、Prisma 表结构或具体 Graph schema。

Pixelle 的领域模型应该由自身业务决定，而不是由参考项目的工程栈决定。

### 2.3 Huobao Drama

Huobao Drama 的中文短剧 SaaS 形态很清楚。

适合参考：

```text
中文短剧 SaaS 产品形态
剧本生成
角色设计
分镜制作
视频合成
资源管理
工作流体验
```

特别值得借鉴的是：分镜保存前要校验 `scene_id`、`character_ids` 是否属于当前项目或当前剧集。

但不建议照搬它的轻量 SQLite 单体实现，也不建议让 Agent 直接拥有不可控的数据库写权限。

### 2.4 StoryGen Atelier

StoryGen Atelier 适合参考后段视频链路。

适合参考：

```text
Storyboard 生成
Shot A -> Shot B transition analysis
首帧 / 尾帧驱动视频生成
Veo 片段生成
FFmpeg 拼接
Storyboard log / Video log
```

但它不应该提前进入 Pixelle 第一阶段 MVP 主路径。

Pixelle 第一阶段应先稳定图文分镜工作台，后续再扩展到首尾帧、图生视频和片段拼接。

### 2.5 ViMax

ViMax 适合参考多 Agent 总体思想。

适合参考：

```text
角色提取
场景提取
分镜设计
Camera tree
参考图选择器
最佳图选择器
first frame / last frame / motion prompt 拆解
多镜头并行生成
```

但不要让多 Agent 成为 Pixelle 的架构核心。

建议原则：

```text
Agent 不是 Pixelle 的领域模型。
Agent 只是某些 NodeExecutor 的实现策略。
```

例如：

```text
ScriptDraftNode
  -> 可以由 single LLM executor 实现
  -> 也可以由 WriterAgent + ReviewerAgent 实现

StoryboardNode
  -> 可以由 structured output 实现
  -> 也可以由 DirectorAgent + CameraAgent 实现

ImageSelectNode
  -> 可以由人工选择实现
  -> 也可以由 VLM reviewer 实现
```

---

## 3. 方案最合理的部分

### 3.1 FlowGram 定位正确

当前主文档没有把 FlowGram 当成 Pixelle 的领域核心，而是把它放在 Studio 的可视化编排层，并且通过 Workflow Adapter / Anti-Corruption Layer 转换成 `PixelleWorkflowDefinition`。

这个判断是正确的。

如果直接把 FlowGram schema 当后端事实源，后面会出现三个问题：

```text
1. 前端画布 schema 变化会污染后端领域模型。
2. Workflow Runtime、Python Worker、GPU Provider、Artifact、Billing、Trace 会被切成两套系统。
3. 用户画布会直接影响执行路径，安全和权限边界很难控制。
```

建议继续坚持：

```text
FlowGram = Studio 可视化工作流外壳
FastAPI = control plane
Pixelle Workflow Engine = executable semantics
Workers = execution plane
Artifact / Trace = durable production record
```

### 3.2 Artifact 作为事实源是关键正确点

主文档里“最终 prompt 不是事实源，它只是从上游结构化事实投影出来的渲染产物”这个判断非常重要。

短剧/漫剧平台真正的事实源应该是：

```text
SourceDocument
ScriptDraft
AssetBible
StoryboardPanel
SceneCast
PromptPlan
ArtifactVersion
GenerationTrace
```

而不是：

```text
narration + prompt_prefix + image_prompt
```

Pixelle 要做成工作台，必须让用户能编辑、锁定、重跑、回看每个中间阶段，而不是只看到一个最终视频。

### 3.3 FastAPI 控制面 / Worker 执行面边界正确

FastAPI 应负责：

```text
鉴权
参数校验
额度检查
Workflow CRUD
创建 WorkflowRun
查询状态
返回产物
```

FastAPI 不应该负责：

```text
长时间 LLM 生成
图片生成
TTS
视频生成
FFmpeg 合成
多节点工作流同步执行
```

长任务必须进入队列，由 Worker 执行。

这是未来支持多用户、多 IP、多机器、多 Provider、计费、追踪、重生成和对外 API 的基础。

### 3.4 文本链路重构方向正确

当前主文档和配套文档建议从：

```text
用户主题
  -> generate_narrations_from_topic()
  -> generate_image_prompts()
  -> prompt_prefix
```

升级为：

```text
VideoPlan
  -> ScenePlan
  -> ScriptDraft
  -> ScriptValidation
  -> ScriptRepair
  -> VisualPlan
  -> SceneCasting
  -> BaseImagePrompts
  -> FinalImagePrompts
```

这个方向是对的。

它能让文案、旁白、场景、角色、道具、分镜和 Prompt 之间有稳定中间产物，用户也可以编辑、锁定、局部重跑。

### 3.5 Trace 和版本化是产品化必须项

`GenerationTrace`、`ArtifactVersion`、重抽卡、候选图、selected/rejected 状态不是锦上添花，而是 AI 创作工具的基础能力。

AI 图片天然有抽卡属性，不能覆盖旧图。

用户必须知道：

```text
哪一步失败
第几次 retry 成功
LLM 原始 prompt 是什么
LLM 原始 response 是什么
JSON 解析哪里失败
最终 prompt 为什么这样拼
某一格图片是哪个版本
某次重抽消耗了多少 credit
```

---

## 4. 当前代码与长期方案的匹配情况

基于对最新代码压缩包的静态查看，整体判断是：当前代码已经有升级到这个长期方案的基础，但还停留在“增强版单条 pipeline + 视频生成任务”阶段，距离真正的 Workflow / Artifact 平台还有一层。

| 模块 | 当前代码状态 | 和长期方案的关系 |
|---|---|---|
| Pipeline | 已经把视频生成拆成 `setup_environment -> generate_content -> plan_visuals -> initialize_storyboard -> produce_assets -> post_production -> finalize` | 这是很好的过渡层，但还不是 DAG Workflow Engine |
| Storyboard | 已有 `StoryboardPlan`，包含 `frame_id`、`source_text`、`visual_goal`、`prompt_intent`、`shot_type`、`continuity_anchors`、`world_elements` | 非常接近规划里的 `StoryboardPanel`，可以直接升级 |
| Prompt | 已有 `ImagePromptComposer`、`PromptContextEnvelope`、`ResolvedStyleSpec` | 是 PromptPlan / PromptComposer 的前身，但还缺 AssetBible、SceneCast、角色/场景/道具 ID 约束 |
| Task | `api/tasks` 已有 TaskStatus、lease、worker heartbeat、fingerprint 复用 | 很有价值，但现在主要是整条视频生成，不是 NodeRun 级别 |
| API | 已有同步和异步视频生成接口 | async 是正确方向；sync endpoint 未来应降级为本地 demo / 调试用途 |
| 资源 | request 仍允许 `prompt_prefix`、`media_workflow`、`frame_template`、`bgm_path`、`ref_audio` 等直接参数 | 和正式 SaaS 安全边界冲突，后面要改成资源 ID |
| Artifact | 当前更偏最终视频和本地 metadata / storyboard 持久化 | 还没有真正的帧级 ArtifactVersion、候选图、selected image version |
| Trace | 已有 observability、stage event、日志落盘思路 | 还需要统一成 `GenerationEvent` JSONL / DB 表 / Trace API |

结论：代码不需要推倒重来。

推荐迁移方式：

```text
StandardPipeline
  -> temporary compatibility pipeline

StoryboardGenerationService
  -> StoryboardNode executor

ImagePromptComposer
  -> PromptPlanNode executor

current media generation
  -> ImageGenerateNode / TTSNode / FinalRenderNode executor
```

---

## 5. 最大改进点：落地顺序需要调整

当前主文档路线大致是：

```text
阶段 1：领域合同层
阶段 2：FlowGram Adapter
阶段 3：Workflow Run Skeleton
阶段 4：Worker 执行面
阶段 5：短剧漫剧 MVP 节点
阶段 6：版本化与工作台
阶段 7：视频扩展
```

这个顺序从大型平台架构角度合理，但从产品落地角度偏重。

建议调整为：

```text
优先级 1：StoryboardPanel / ArtifactVersion / GenerationTrace / PromptPlan
优先级 2：IP Library / AssetBible / SceneCast / PromptComposer
优先级 3：帧级重抽卡、候选图、版本选择、局部重跑
优先级 4：把 StandardPipeline 改造成 System Workflow Preset
优先级 5：NodeContract + fake / in-process WorkflowRun Skeleton
优先级 6：Worker 拆 NodeRun 队列
优先级 7：FlowGram Adapter
优先级 8：SaaS 权限、计费、Public API、企业级 Workflow 自定义
```

核心原因：用户首先需要的是短剧/漫剧分镜工作台，不是可视化工作流编辑器。

FlowGram 很有用，但它解决的是“高级用户如何编排流程”。当前最关键的是：

```text
用户输入小说 / 文案
  -> 生成剧本 / 分镜
  -> 抽取角色 / 场景 / 道具
  -> 每格分镜可编辑
  -> 每格 Prompt 可查看
  -> 每格图片可重抽
  -> 每格候选图可选择
  -> 局部重跑不影响全部
```

这个工作台做出来，Pixelle 的产品价值就出来了。FlowGram 可以后置。

---

## 6. 需要补强的 9 个部分

### 6.1 增加产品状态机，不只是 Workflow 状态机

当前文档强调 `WorkflowRun`、`NodeRun`、`ArtifactVersion`，但短剧/漫剧产品还需要显式的人工编辑状态。

建议给 `StoryboardPanel` 或 `StoryboardFrame` 增加：

```python
status: Literal[
    "draft",
    "generated",
    "edited",
    "locked",
    "approved",
    "stale",
    "failed"
]

lock_policy: Literal[
    "none",
    "lock_text",
    "lock_prompt",
    "lock_image",
    "lock_all"
]
```

这样用户可以锁定某一格的文案、Prompt、角色、图片，不会因为上游重跑被覆盖。

这是人机协作工作台必须有的产品状态层。

### 6.2 明确 Artifact 和 ArtifactVersion 的区别

建议拆成：

```text
Artifact
  artifact_id
  project_id
  artifact_type
  logical_key
  current_selected_version_id

ArtifactVersion
  artifact_version_id
  artifact_id
  version
  status
  object_key
  payload
  provider_run_id
  created_by_node_run_id
```

原因：

```text
一个“分镜第 3 格图片”是稳定逻辑对象。
它下面可以有 v1、v2、v3 多个候选版本。
用户选择的是某个 version。
下游最好引用稳定 Artifact，再通过 selected version 解析。
```

当前文档已有“重抽卡不覆盖旧图片，用户选择 v2”的方向，建议在模型层进一步拆清楚。

### 6.3 补充依赖失效规则

当前文档已经提到：改文案会影响 narration、image prompt、TTS、image、frame segment、final video；改图片提示词会影响 image、frame segment、final video；重新生成图片不影响旁白和音频。

建议把这个规则提升到主架构文档。

示例：

```text
script_scene.changed
  -> storyboard_panel.stale
  -> prompt_plan.stale
  -> image_artifact.stale
  -> video_segment.stale
  -> final_video.stale

prompt_plan.changed
  -> image_artifact.stale
  -> video_segment.stale
  -> final_video.stale

selected_image_version.changed
  -> video_segment.stale
  -> final_video.stale
```

这比简单“局部重跑”更工程化。

### 6.4 SceneCast 要从描述升级成强约束引用

当前文档已经提出：所有分镜、Prompt 和生成节点只能引用 AssetBible 中的资产 ID，禁止模型编造 ID。

建议进一步明确：

```python
class SceneCast(BaseModel):
    panel_id: str
    character_ids: list[str]
    scene_id: str
    prop_ids: list[str]
    must_include_asset_ids: list[str]
    optional_asset_ids: list[str]
    forbidden_asset_ids: list[str]
    continuity_from_panel_id: str | None
```

同时增加校验：

```text
character_ids 必须属于当前 Project / AssetBible
scene_id 必须属于当前 Episode / Clip
prop_ids 必须属于当前 AssetBible
模型输出未知 ID 直接 validation_error
```

### 6.5 Provider 抽象需要能力矩阵

当前 Provider 抽象已有 TextProvider、ImageProvider、TTSProvider、VideoProvider、BGMProvider、RenderProvider，并且有 ProviderRouter 选择 Provider。

建议补充 `ProviderCapability`：

```python
class ProviderCapability(BaseModel):
    provider_id: str
    modality: Literal["text", "image", "tts", "video", "render"]
    supports_text_to_image: bool = False
    supports_image_to_image: bool = False
    supports_first_last_frame: bool = False
    supports_reference_image: bool = False
    supports_lora: bool = False
    max_width: int | None = None
    max_height: int | None = None
    avg_latency_ms: int | None = None
    cost_multiplier: float = 1.0
    queue_names: list[str]
```

这样未来接 Z-Image、ComfyUI、RunningHub、云图像 API、云视频模型时，不会把 Provider 选择逻辑散落在业务代码里。

### 6.6 API 安全边界要提前落地

主文档里禁止前端直接传本地 workflow 路径、本地 template 路径、本地模型路径、任意 provider URL、API Key、prompt_prefix、bgm_path，这一点非常重要。

但当前代码仍允许：

```text
media_workflow
frame_template
prompt_prefix
bgm_path
ref_audio
tts_workflow
```

进入正式 App API / Public API 后必须替换成：

```text
workflow_preset_id
template_id
style_id
voice_id
bgm_id
provider_id
model_id
asset_id
```

建议增加 `ResourceResolver`：

```python
resolve_workflow_preset(workspace_id, user_id, workflow_preset_id)
resolve_template(workspace_id, user_id, template_id)
resolve_style(workspace_id, user_id, style_id)
resolve_voice(workspace_id, user_id, voice_id)
resolve_bgm(workspace_id, user_id, bgm_id)
```

旧字段可以保留为 internal / local / debug API，但不要进入正式 App / Public API。

### 6.7 Multi-Agent 要作为执行策略，不要作为架构核心

建议在主文档中明确：

```text
Agent 不是 Pixelle 的领域模型。
Agent 只是某些 NodeExecutor 的实现策略。
```

这样既能吸收 ViMax 的多 Agent 优点，又不会让 Agent 直接控制数据库、工作流、Artifact、计费和权限。

### 6.8 增加质量评估与守卫

建议增加一类 `Quality Evaluation`：

```text
script_quality_score
storyboard_coverage_score
asset_reference_validity
character_consistency_score
prompt_adherence_score
image_selection_score
tts_readability_score
```

这对 AI 短剧/漫剧很重要。

否则系统只能知道“跑通了”，不知道“好不好”。

### 6.9 MVP 边界要更硬

建议把 MVP 明确压成：

```text
MVP = z-image 分镜图工作台
不等于完整视频平台
不等于完整 FlowGram 工作流平台
不等于完整 SaaS
```

MVP 验收建议：

```text
1. 用户输入主题 / 文案 / 小说片段
2. 生成 ScriptDraft
3. 生成 StoryboardPanel
4. 抽取或选择角色、场景、道具
5. 生成 SceneCast
6. 生成 PromptPlan
7. 生成每格 z-image 候选图
8. 用户可重抽某一格
9. 用户可选择候选图
10. Trace 可查看
11. 旧版本不覆盖
12. 可导出 storyboard package
```

暂时不要把完整视频合成作为第一验收目标。

---

## 7. 建议调整后的主文档结构

建议把主方案改成下面这个逻辑顺序：

```text
1. 产品定位
   Pixelle = AI 短剧/漫剧生产平台
   第一阶段 = z-image 分镜图工作台
   长期 = Workflow + SaaS + Video + API

2. 产品对象模型
   Workspace
   Project
   Series / IP
   Episode
   Clip
   SourceDocument
   ScriptDraft
   AssetBible
   Storyboard
   StoryboardPanel
   PromptPlan
   Artifact
   ArtifactVersion

3. 事实源原则
   prompt 不是事实源
   FlowGram 不是事实源
   本地路径不是事实源
   Artifact + structured domain model 才是事实源

4. 现有 StandardPipeline 迁移策略
   StandardPipeline = compatibility workflow
   StoryboardGenerationService = StoryboardNode executor
   ImagePromptComposer = PromptPlanNode executor
   FrameProcessor = Image / TTS / Render executor

5. MVP 工作台
   ScriptDraft
   AssetBible
   StoryboardPanel
   SceneCast
   PromptPlan
   Image candidates
   Regeneration
   Trace

6. Workflow 平台层
   WorkflowDefinition
   NodeContract
   WorkflowRun
   NodeRun
   Queue
   Worker

7. FlowGram Adapter
   作为高级编排 UI
   不进入第一阶段主路径

8. SaaS / API / 权限 / 计费
   App API
   Public API
   Admin API
   Internal API
   PlanPolicy
   ResourceResolver

9. 视频扩展
   first frame
   last frame
   motion prompt
   transition analysis
   video segment
   final render
```

---

## 8. 对现有代码的具体改造优先级

### 8.1 第一组：新增核心模型

建议新增：

```text
pixelle_video/models/artifact.py
pixelle_video/models/generation_event.py
pixelle_video/models/ip_profile.py
pixelle_video/models/scene_cast.py
pixelle_video/models/prompt_plan.py
pixelle_video/models/storyboard_panel.py
```

其中当前 `StoryboardPlanFrame` 已经很接近 `StoryboardPanel`，可以不用完全新建，也可以先做 `StoryboardPanelV2` 或扩展现有模型。

### 8.2 第二组：扩展 StoryboardFrame

当前 `StoryboardFrame` 主要包含：

```text
index
narration
image_prompt
audio_path
image_path
video_path
video_segment_path
shot_type
shot_purpose
frame_source
```

建议补充：

```text
frame_id
panel_id
source_span
base_image_prompt
final_image_prompt
negative_prompt
prompt_plan_id
prompt_debug
character_ids
scene_id
prop_ids
selected_image_version_id
selected_audio_version_id
selected_segment_version_id
lock_policy
stale_flags
```

这一步比 Workflow Engine 更重要。

### 8.3 第三组：新增 ArtifactService

第一版不用 PostgreSQL，可以直接本地 JSON：

```text
output/{task_id}/artifacts.json
output/{task_id}/trace/events.jsonl
output/{task_id}/artifacts/
  panels/
  prompts/
  images/
  audio/
  video_segments/
```

实现：

```python
create_artifact()
create_version()
list_versions()
select_version()
mark_rejected()
mark_failed()
get_selected_version()
```

### 8.4 第四组：新增 GenerationTraceService

把现有 observability、stage event、日志汇总到统一事件模型：

```python
record_event()
record_llm_call()
record_validation()
record_retry()
record_provider_request()
record_artifact_created()
load_events()
```

API 第一版：

```http
GET /api/v1/app/jobs/{job_id}/events
GET /api/v1/app/jobs/{job_id}/trace
```

### 8.5 第五组：改造 ImagePromptComposer

下一步不要只是传 `prompt_prefix`，而是改成：

```text
StoryboardPanel
+ AssetBible
+ SceneCast
+ StyleProfile
+ WorldProfile
+ ContinuityMemory
= PromptPlan
= PromptProjection
```

这样 PromptComposer 才能真正承担视觉一致性职责。

### 8.6 第六组：新增帧级重抽 API

第一版可以先做：

```http
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/regenerate-image
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/select-image-version
GET  /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/artifacts
```

这会立刻把 Pixelle 从“一键生成工具”推进到“AI 创作工作台”。

### 8.7 第七组：把当前 Task 升级为兼容层

当前 `api/tasks` 已有 task registry、lease、worker heartbeat，可以保留。

短期先不要拆完整 `NodeRun`，可以先增加：

```text
task_type = storyboard_image_regeneration
task_type = prompt_regeneration
task_type = frame_tts_regeneration
```

等 Artifact / Trace / Frame 工作台稳定后，再升级为：

```text
WorkflowRun
NodeRun
GenerationJob
```

---

## 9. 最需要避免的技术债

建议团队明确以下红线：

```text
不要让 FlowGram schema 进入执行引擎。
不要让 Agent 直接写数据库。
不要让 prompt_prefix 继续作为视觉一致性的主方案。
不要让前端传本地路径、workflow 文件名、API Key、provider URL。
不要把重抽卡做成覆盖旧图片。
不要让 Task 只保存 final.mp4，而不保存每一阶段产物。
不要在 FastAPI 里继续执行完整视频长任务。
不要把完整视频生成作为第一阶段 MVP 的核心验收。
```

其中最紧急的是：

```text
prompt_prefix
media_workflow
frame_template
bgm_path
ref_audio
```

这些 raw 参数要逐步收口到资源 ID：

```text
style_id
workflow_preset_id
template_id
bgm_id
voice_id
provider_id
model_id
asset_id
```

---

## 10. 推荐的一句话架构表述

建议在团队内部把 Pixelle 的长期方向表述为：

```text
Pixelle 不是一个视频生成脚本，
也不是 FlowGram 的后端执行器，
而是一个以 SourceDocument、AssetBible、StoryboardPanel、PromptPlan、ArtifactVersion、GenerationTrace 为事实源的 AI 短剧/漫剧生产平台。

FlowGram 负责高级可视化编排；
FastAPI 负责控制面和权限边界；
Workflow Engine 负责编译和调度；
Workers 负责真实生成；
Artifact / Trace 负责可编辑、可重跑、可审计、可计费。
```

---

## 11. 推荐团队决策事项

本次团队讨论建议围绕以下问题做决策：

### 11.1 第一阶段 MVP 是否明确为“分镜图工作台”

建议结论：是。

第一阶段不要以完整视频平台、完整 FlowGram 平台、完整 SaaS 为验收目标。

### 11.2 FlowGram 是否后置

建议结论：是。

FlowGram 适合进入高级编排阶段，但第一阶段不应该阻塞分镜、Artifact、Trace、重抽卡。

### 11.3 Artifact / Trace 是否作为第一批基础设施

建议结论：是。

没有 Artifact 和 Trace，就没有真正的工作台，也没有可靠的局部重跑。

### 11.4 prompt_prefix 是否继续作为主视觉一致性方案

建议结论：否。

`prompt_prefix` 可以保留为临时兼容参数，但长期必须由 IP Library、AssetBible、SceneCast、PromptComposer 接管。

### 11.5 是否立即做完整 Workflow Engine

建议结论：否。

先做 in-process / fake WorkflowRun Skeleton，等工作台能力稳定后再拆 NodeRun 队列。

---

## 12. 建议阶段路线

### 阶段 0：现有 Pipeline 兼容整理

目标：不破坏当前可运行能力。

```text
保留 StandardPipeline
保留当前视频生成入口
梳理当前 StoryboardFrame / ImagePromptComposer / Task 模型
标记 raw 参数为 debug/internal only
```

### 阶段 1：分镜图工作台核心

目标：做出真正可编辑、可重抽的 AI 分镜工作台。

```text
ScriptDraft
StoryboardPanel
AssetBible
SceneCast
PromptPlan
ArtifactVersion
GenerationTrace
Frame image regeneration
Candidate image selection
```

### 阶段 2：本地 API + Worker 雏形

目标：让长任务脱离 API 同步执行。

```text
GenerationJob
queue-based task
worker heartbeat
frame-level regeneration task
trace event API
artifact list API
```

### 阶段 3：Workflow Skeleton

目标：把当前 System Pipeline 编译成可执行工作流。

```text
WorkflowDefinition
NodeContract
WorkflowRun
NodeRun
System Workflow Preset
```

### 阶段 4：FlowGram Adapter

目标：让 Studio 可视化编排工作流。

```text
FlowGram canvas schema
Workflow Adapter
PixelleWorkflowDefinition
Workflow validation
Workflow publish
```

### 阶段 5：SaaS / 权限 / 计费 / Public API

目标：商业化。

```text
Workspace
PlanPolicy
UsageLedger
APIKey
ResourceResolver
Public API
Webhook
```

### 阶段 6：视频扩展

目标：从分镜图工作台升级为视频生产平台。

```text
first frame
last frame
motion prompt
transition analysis
video segment generation
final render
multi-provider video generation
```

---

## 13. 最终建议

这套方案可以继续推进。

真正要改的是实施顺序：

```text
先做分镜图工作台和帧级 Artifact，
再做完整 Workflow / FlowGram / SaaS。
```

更具体地说：

```text
第一优先级：StoryboardPanel + ArtifactVersion + GenerationTrace + PromptPlan
第二优先级：IP Library + AssetBible + SceneCast + PromptComposer
第三优先级：帧级重抽卡 + 候选图选择 + 局部重跑
第四优先级：Worker 化和 Workflow Skeleton
第五优先级：FlowGram Adapter
第六优先级：SaaS、计费、Public API、完整视频扩展
```

如果按这个顺序走，Pixelle 的长期架构不会浪费，短期产品价值也能更快出现。
