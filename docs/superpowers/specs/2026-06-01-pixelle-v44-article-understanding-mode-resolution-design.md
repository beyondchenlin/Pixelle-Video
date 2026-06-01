# Pixelle V4.4 文章理解与模式解析开发设计

## 1. 结论

V4.4 的目标不是继续扩展 prompt 拼接，而是把“文章如何被理解”“文章内容如何被视觉化”“固定视觉签名 / IP 如何参与”拆成三个可审计、可测试、可回退的结构化层。

正式开发必须先落地契约基础层，再逐步接入 planner、router、projector、critic/repair 和 artifact manifest。禁止直接把 `cognitive_illustration`、`host_explainer`、`signature_presence` 等用户选择拼进最终 prompt。

本设计基于：

- `docs/Pixelle_V4_4_Article_Understanding_Mode_Resolution_Visual_Routing_Plan.md`
- 现有 `final_visual_prompt_contract.v1`
- 现有 `VisualRoleStrategyControls`
- 现有 `prompt_traces` artifact 体系

## 2. 目标

1. 新增文章理解请求、preflight、route decision、visual planning mode、visual role strategy 等稳定契约。
2. 为每帧产出唯一 `route_decision_id`，贯穿 route decision、FinalVisualPromptContract、RenderedMediaPrompt metadata 和 manifest。
3. 用 `SubjectAnchor.evidence_span_ids` 建立 required subject 到 source evidence 的可审计链路。
4. 保持现有 `FinalVisualPromptContract` v1 builder/projector 兼容，V4.4 字段先通过 versioned adapter 或 metadata 接入。
5. 阻止现有 `VisualRoleStrategyControls.effective_role_mode` 在没有主体保护上下文时直接升级为最终事实源。
6. 让 V4.2 fallback 可见、可测试、可解释，而不是静默发生。

## 3. 非目标

本轮正式文档不要求一次性实现全部 V4.4 功能。

明确不做：

1. 不一次性替换现有 `FinalVisualPromptContract` dataclass。
2. 不重写全部视觉角色链路。
3. 不直接实现所有 LLM planner。
4. 不在 Phase 1 做 UI 复杂交互。
5. 不改变未启用 V4.4 字段时的 V4.2 默认链路。

## 4. 当前代码基线

当前仓库已经具备：

- `pixelle_video/models/final_visual_prompt_contract.py`
  - `FinalVisualPromptContract` v1 字段为 `scene / composition / style_assignment / character_layer_style / world_layer_style / integration_priority`
  - `RenderedMediaPrompt` 持有 `prompt_contract`
- `pixelle_video/services/final_visual_prompt_contract_builder.py`
  - 基于现有视觉风格与 IP profile 生成 v1 contract
- `pixelle_video/services/visual_role_prompt_projector.py`
  - 从 `VisualRoleIntegratedPromptPlan` 投影最终 prompt，并把 projected parts 写入 metadata
- `pixelle_video/models/visual_role_strategy.py`
  - 已有 `VisualRoleMode / VisualConsistencyMode / VisualRoleStrategyControls`
  - `VisualRoleStrategyControls.effective_role_mode` 当前会根据 `PRIMARY_CHARACTER` 直接推导 `SUBJECT_REPLACEMENT`
- `api/schemas/video.py` 和 `api/routers/video.py`
  - 已有标准视频请求参数透传模式
- `pixelle_video/pipelines/standard.py`
  - 已有 `prompt_traces/final_visual_prompts.md` 与 `prompt_traces/visual_role/*` artifact 写入模式

## 5. 目标架构

```text
VideoGenerateRequest / UI params
-> ArticleVisualPlanningRequest
-> ArticleVisualPlanningPreflight
-> ArticleUnderstandingPlan
-> FrameUnderstandingPlan
-> VisualPlanningRouteDecision
-> VisualConcretizationPlan
-> VisualRoleStrategyResolver
-> VisualRoleParticipationPlan
-> FinalVisualPromptContractV44 adapter
-> Existing PromptProjector / RenderedMediaPrompt
-> prompt_traces/manifest.json
```

核心边界：

- `article_understanding_mode` 决定文章从什么 lens 被理解。
- `visual_planning_mode` 决定文章内容如何被视觉具象化。
- `visual_role_strategy` 决定固定视觉签名 / IP 如何参与画面表达。
- `visual_expression_mode / visual_structure_mode / visual_participation_mode / visual_role_mode / visual_consistency_mode` 仍是低层 controls，只能作为 resolver 输入。

## 6. 核心契约

### 6.1 文章理解

```python
class ArticleUnderstandingMode(str, Enum):
    AUTO = "auto"
    THESIS_ARGUMENT = "thesis_argument"
    CAUSAL_MECHANISM = "causal_mechanism"
    COGNITIVE_STATE = "cognitive_state"
    PROCESS_METHOD = "process_method"
    RELATIONSHIP_STRUCTURE = "relationship_structure"
    CONTRAST_CONFLICT = "contrast_conflict"
    NARRATIVE_EVENT = "narrative_event"
    METAPHOR_SYMBOLIC = "metaphor_symbolic"
```

`ArticleUnderstandingLens` 与 `ArticleUnderstandingMode` 同值但不同语义：Mode 属于用户请求层，Lens 属于系统理解层。

### 6.2 SourceEvidenceSpan 与 SubjectAnchor

```python
@dataclass(frozen=True)
class SourceEvidenceSpan:
    evidence_id: str
    source_id: str
    frame_id: str | None
    start_char: int | None
    end_char: int | None
    quote: str
    evidence_role: str
```

```python
@dataclass(frozen=True)
class SubjectAnchor:
    subject_id: str
    label: str
    source_phrase: str
    evidence_span_ids: tuple[str, ...]
    importance: str
    visual_presence: str
    loss_policy: str
```

`source_phrase` 只为人读。critic、artifact 和测试必须依赖 `evidence_span_ids`。

### 6.3 Mode Resolution

```python
@dataclass(frozen=True)
class VisualPlanningRouteDecision:
    route_decision_id: str
    frame_id: str
    preflight_id: str
    requested_article_mode: ArticleUnderstandingMode
    requested_visual_mode: VisualPlanningMode
    requested_visual_role_strategy: VisualRoleStrategy
    resolved_primary_lens: ArticleUnderstandingLens
    resolved_secondary_lenses: tuple[ArticleUnderstandingLens, ...]
    resolved_visual_planning_mode: VisualPlanningMode
    resolved_visual_role_strategy: VisualRoleStrategy
    primary_visual_task: PrimaryVisualTask
    secondary_visual_tasks: tuple[PrimaryVisualTask, ...]
    confidence: float
    decision_reason: str
    resolution_status: str
    fallback_eligible: bool
    fallback_used: bool
    fallback_target: str | None
    fallback_reason: str | None
    mismatch_warnings: tuple[str, ...]
```

`route_decision_id` 是 V4.4 的主追溯键。任何 fallback 都必须先有 route decision。

### 6.4 FinalVisualPromptContract 兼容策略

现有 v1 contract 保留。V4.4 新增 `FinalVisualPromptContractV44` 或 adapter：

- v1 继续服务现有 builder/projector。
- V4.4 追溯字段进入 v44 dataclass 和 v1 metadata。
- 渲染时 `RenderedMediaPrompt.metadata` 必须含 `route_decision_id` 和 `contract_id`。
- 完整迁移完成前，不改现有 v1 constructor 签名。

### 6.5 Artifact Manifest

新增：

```text
prompt_traces/manifest.json
```

最小字段：

```json
{
  "schema_version": "v4.4",
  "article_id": "article_001",
  "frames": ["frame_001"],
  "route_decision_ids": {
    "frame_001": "route_frame_001_v44_001"
  },
  "requested_modes": {
    "article_understanding_mode": "auto",
    "visual_planning_mode": "auto",
    "visual_role_strategy": "auto"
  },
  "resolved_modes": {
    "primary_lens": "cognitive_state",
    "visual_planning_mode": "cognitive_illustration",
    "visual_role_strategy": "observer_guide"
  },
  "fallbacks": [],
  "critic_status": "not_run",
  "repair_rounds": 0
}
```

## 7. 分阶段实施

### Phase 1：契约基础层

目标：新增稳定 dataclass / enum / adapter / API 透传 / manifest serializer。

完成后系统仍可走 V4.2 链路，但 V4.4 字段已经能被请求、序列化、测试和 artifact 追踪。

### Phase 2：API / UI 最小透传

目标：前端只暴露三个高层选项，默认 `auto`。后端能从 `VideoGenerateRequest` 收到 V4.4 字段并生成 `ArticleVisualPlanningPreflight`。

### Phase 3：ArticleUnderstandingPlanner

目标：输出 ArticleUnderstandingPlan、FrameUnderstandingPlan、SourceEvidenceSpan、SubjectAnchor。

### Phase 4：ModeResolutionService 与 VisualPlanningRouter

目标：基于 request + article/frame understanding 产出 route decision，并选择 visual concretization planner。

### Phase 5：VisualRoleStrategyResolver

目标：把 `visual_role_strategy` 与现有低层 controls 合成为唯一 `VisualRoleParticipationPlan` 和 `VisualRoleWeightContract`。

### Phase 6：FinalVisualPromptContractV44 与 projector 接入

目标：projector 继续渲染最终 prompt，但事实源由 V4.4 contract 和 projected parts 管理。

### Phase 7：Critic / Repair 闭环

目标：critic issue 带 target，repair 修改结构化 plan，重新生成 contract 并重新投影。

### Phase 8：E2E 回归与发布冻结

目标：V4.2 默认兼容、V4.4 fixtures 覆盖、manifest 完整、fallback 可见。

## 8. 测试策略

Phase 1 必须先建立纯 Python contract tests：

- enum normalize
- invalid value fallback auto
- `to_dict / from_mapping`
- route decision required fields
- v1 contract 兼容
- v44 metadata adapter
- manifest writer
- video request pass-through

后续 planner/LLM 测试只断言结构，不断言完整自然语言。

## 9. 发布门槛

V4.4 任何阶段合入前必须满足：

1. 未启用 V4.4 字段时，现有 V4.2 行为不变。
2. 新字段默认值均为 `auto` 或关闭态。
3. 所有 fallback 都写入 route decision 和 manifest。
4. 所有 final prompt 都能回查 `route_decision_id`。
5. 不把内部 enum、debug 字段、artifact 路径泄漏到最终 provider prompt。

