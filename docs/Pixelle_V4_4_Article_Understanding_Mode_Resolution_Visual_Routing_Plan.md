# Pixelle-Video V4.4 文章理解、模式解析与视觉具象化策略路由计划

> 版本：V4.4 计划稿  
> 文档状态：V4.3 架构评审后修订版 / 代码实施前冻结建议稿  
> 基准：V4.2 已建立 IP 身份契约、视觉参与结构、Projector 与 Critic 链路；V4.3 已提出文章理解层与视觉具象化策略层  
> V4.4 目标：补齐 Mode Resolution、视觉任务与 IP 参与策略边界、FinalVisualPromptContract、Critic/Repair 闭环、Artifact Manifest 与 V4.2 兼容策略  
> 原则：最佳实践、源头治理、结构化事实源优先、禁止最小改动、禁止把问题继续推给 prompt 拼接

---

## 0. 一句话结论

V4.4 不再把“认知配图 / 主持讲解 / 视觉签名弱植入”混在同一个 mode 层里。

正确架构是：

```text
用户请求
-> Request Normalization / Mode Preflight
-> ArticleUnderstandingPlan
-> FrameUnderstandingPlan
-> Mode Resolution / Route Decision
-> VisualPlanningRouter
-> VisualConcretizationPlan
-> VisualRoleStrategyResolver
-> VisualRoleParticipationPlan
-> FinalVisualPromptContract
-> PromptProjector
-> Critic / Repair / Artifact Manifest
```

V4.4 的核心修正是：

```text
1. visual_planning_mode 只表达“文章内容如何被视觉化”。
2. visual_role_strategy 只表达“固定视觉签名 / IP 如何参与”。
3. 用户选择必须先经过请求预处理与文章理解后的路由决策，不能直接拼进 prompt。
4. 最终 prompt 必须由 FinalVisualPromptContract 投影，不再作为事实源。
5. Critic 发现问题后必须修结构化 plan，再重新投影 prompt。
```

---

## 1. V4.4 相比 V4.3 的关键变化

V4.3 已经提出了文章理解层、视觉具象化策略层、视觉策略路由层。V4.4 在这个方向上继续收敛，重点解决代码实施前的边界问题。

| 领域 | V4.3 状态 | V4.4 修正 |
| --- | --- | --- |
| 模式边界 | `visual_planning_mode` 中混入 `host_explainer`、`signature_presence` | 拆成 `visual_planning_mode` 与 `visual_role_strategy` 两层 |
| 用户选择 | 用户选择直接进入 request，但缺少解析契约 | 新增 `ArticleVisualPlanningRequest`、`ArticleVisualPlanningPreflight`、`VisualPlanningRouteDecision` |
| 文章理解 | `ArticleUnderstandingPlan` 字段偏万能表 | 改成 `primary_lens + lens_payloads + SubjectAnchor + SourceEvidenceSpan` |
| 原文主体保护 | `required_subjects: tuple[str, ...]` 不够可测 | 新增 `SubjectAnchor`，区分重要性、可视策略和丢失策略 |
| IP 权重 | `ip_weight` 与 `max_visual_weight` 可能冲突 | 新增 `VisualRoleWeightContract` 作为唯一最终权重事实源 |
| 可见文字 | `visible_text_policy` / `text_rendering_policy` 命名不统一 | 统一为 `visible_text_policy` |
| 最终 prompt | 提到 `projected_prompt_parts`，但缺最终契约 | 新增 `FinalVisualPromptContract` |
| Repair | 说修 plan，但没有 issue target | 新增 `CriticIssue.target` 与 `RepairTarget` |
| Artifact | 文件多，但缺少统一入口 | 新增 `manifest.json`、runtime snapshot、before/after critic issues |
| 测试 | 容易断言自然语言输出 | 改成三层测试：contract、router、LLM planner 结构性测试 |
| V4.2 兼容 | 只声明默认兼容 | 明确 fallback 条件、artifact 记录与回归测试 |

---

## 2. 当前问题复盘

当前 V4.2 主链路已经具备较好的 IP 身份与参与控制：

```text
BaseVisualBriefPlanner
-> VisualExpressionClassifier
-> VisualRoleRepairLoop
   -> VisualRoleScenePlanner
   -> VisualRolePromptCritic
-> VisualRolePromptProjector
-> prompt_traces / artifacts
```

V4.2 已经解决：

```text
1. 固定视觉签名不再只是贴纸、logo、角标或水印。
2. IP 身份被提升为 VisualRoleIdentityContract。
3. IP 的结构方式、参与方式、融入模式可以端到端进入后端。
4. Projector 开始对最终 prompt 承担责任。
5. Artifact 可以追踪 visual_role_request、profile、identity_contract、plan、critique 和 projected parts。
```

V4.2 未解决：

```text
1. 系统没有先理解整篇文章的核心主张、论证关系、因果机制、认知困境和叙事结构。
2. 当前 planner 主要解决“这一帧如何让 IP 参与”，不是“这篇文章应该如何被视觉化理解”。
3. visual_expression_mode、visual_structure_mode、visual_participation_mode 是低层控制，不应承担文章理解职责。
4. 认知配图只能被近似成 cognitive_metaphor + concept_metaphor + guide_explainer。
5. 最终 prompt 容易呈现线性拼接感。
```

V4.3 方向是对的，但代码实施前必须避免两个新风险：

```text
1. 把文章视觉具象化任务和 IP 参与策略混成一个 mode。
2. 只增加字段透传，却没有 route decision、fallback、critic target、artifact manifest 等可测契约。
```

V4.4 的定位就是补齐这两个风险。

---

## 3. V4.4 顶层原则

### 3.1 用户体验上不要硬边，工程契约上必须有边界

一篇文章可能同时包含：

```text
认知困境
因果机制
前后对比
人物叙事
流程方法
关系结构
隐喻象征
```

所以用户侧可以选择自动判断或软偏好，系统侧必须落到清晰的主任务：

```json
{
  "route_decision_id": "route_frame_003_v44_001",
  "frame_id": "frame_003",
  "primary_visual_task": "cognitive_explanation",
  "secondary_visual_tasks": ["contrast_argument"],
  "resolved_visual_planning_mode": "cognitive_illustration",
  "resolved_visual_role_strategy": "host_explainer",
  "fallback_used": false
}
```

### 3.2 prompt 不是事实源

最终 prompt 只能是投影结果。系统真正的事实源是：

```text
ArticleUnderstandingPlan
FrameUnderstandingPlan
VisualPlanningRouteDecision
VisualConcretizationPlan
VisualRoleParticipationPlan
FinalVisualPromptContract
CriticIssue / RepairAction
Artifact Manifest
```

### 3.3 Repair 不能再把问题追加到 prompt

错误修复必须遵循：

```text
critic issue
-> 定位 target plan
-> 修改结构化 plan
-> 重新生成 FinalVisualPromptContract
-> 重新投影 prompt
-> 再次 critic
```

禁止：

```text
直接把 critic 提醒文本追加到最终 prompt 后面。
```

---

## 4. 用户可见选项

V4.4 建议前端只新增三个高层选择，默认都是自动。

### 4.1 内容理解方式：article_understanding_mode

| 值 | 中文名称 | 说明 |
| --- | --- | --- |
| `auto` | 自动判断 | 系统基于文章结构自动选择主理解方式 |
| `thesis_argument` | 观点论证 | 识别主张、证据、反驳、结论 |
| `causal_mechanism` | 因果机制 | 识别原因、触发条件、结果、反馈循环 |
| `cognitive_state` | 认知状态 | 识别困惑、循环、误区、顿悟、心理卡点 |
| `process_method` | 流程方法 | 识别步骤、顺序、动作、方法层级 |
| `relationship_structure` | 关系结构 | 识别角色、依赖、权力、冲突、网络关系 |
| `contrast_conflict` | 对比冲突 | 识别过去/现在、错误/正确、A/B 选择 |
| `narrative_event` | 叙事事件 | 识别人物、地点、事件、情绪推进 |
| `metaphor_symbolic` | 隐喻象征 | 识别抽象意象、象征关系、文学隐喻 |

### 4.2 视觉具象化方式：visual_planning_mode

`visual_planning_mode` 只回答一个问题：

```text
文章内容如何被视觉化？
```

| 值 | 中文名称 | 说明 |
| --- | --- | --- |
| `auto` | 自动选择 | 系统根据文章理解计划选择最合适的画面任务 |
| `scene_integration` | 场景还原 | 还原文章中的人物、地点、事件和情绪场景 |
| `cognitive_illustration` | 认知配图 | 把抽象困境、循环、误区、顿悟转成解释型画面 |
| `structural_explainer` | 结构图解 | 把系统、组件、层级、关系转成结构化画面 |
| `process_walkthrough` | 流程方法 | 把步骤、路径、方法、操作转成流程画面 |
| `contrast_argument` | 对比论证 | 把冲突、选择、前后变化转成对照画面 |
| `relationship_map` | 关系图谱 | 把人物、组织、要素之间的关系转成图谱画面 |

明确不放入 `visual_planning_mode`：

```text
host_explainer
signature_presence
observer_guide
participant
background_signature
```

这些属于 IP 参与策略。

### 4.3 视觉角色参与策略：visual_role_strategy

`visual_role_strategy` 只回答一个问题：

```text
固定视觉签名 / IP 如何参与表达？
```

| 值 | 中文名称 | 说明 |
| --- | --- | --- |
| `auto` | 自动选择 | 系统根据画面任务和 IP 能力自动决定参与方式 |
| `host_explainer` | 主持讲解 | IP 作为讲解者、导览者、主持人参与表达 |
| `signature_presence` | 视觉签名弱植入 | IP 作为系列识别信号弱存在，不改变原文主体 |
| `observer_guide` | 观察指引 | IP 观察、指示、提醒，但不接管画面主体 |
| `participant` | 情节参与 | IP 成为场景动作参与者，但受原文主体保护约束 |
| `background_signature` | 背景识别 | IP 以背景元素、道具、图腾等方式保持识别 |

---

## 5. 前端信息架构

建议放在当前“系列视觉识别”区域中：

```text
启用视觉签名
选择视觉签名素材库
选择视觉签名形象
视觉签名能力预览
内容理解方式 article_understanding_mode
视觉具象化方式 visual_planning_mode
视觉角色参与策略 visual_role_strategy
高级策略
  - 表达模式 visual_expression_mode
  - 结构方式 visual_structure_mode
  - 参与方式 visual_participation_mode
  - 融入模式 visual_role_mode
  - 角色一致性 visual_consistency_mode
```

信息架构原则：

```text
1. 视觉签名素材库和形象决定“谁参与”。
2. 内容理解方式决定“文章该如何被读懂”。
3. 视觉具象化方式决定“文章理解如何变成画面任务”。
4. 视觉角色参与策略决定“IP 如何参与”。
5. 表达模式、结构方式、参与方式、融入模式、角色一致性属于高级低层控制。
```

不要把“认知配图”放进“表达模式”。它是一级视觉任务，不是低层表达子项。

---

## 6. V4.4 后端目标架构

目标链路：

```text
BaseVisualBriefPlanner
-> ArticleVisualPlanningRequestNormalizer
-> ModePreflightService
-> ArticleUnderstandingPlanner
-> FrameUnderstandingPlanner
-> ModeResolutionService
-> VisualPlanningRouter
   -> SceneIntegrationPlanner
   -> CognitiveIllustrationPlanner
   -> StructuralExplainerPlanner
   -> ProcessWalkthroughPlanner
   -> ContrastArgumentPlanner
   -> RelationshipMapPlanner
-> VisualRoleStrategyResolver
   -> HostExplainerStrategy
   -> SignaturePresenceStrategy
   -> ObserverGuideStrategy
   -> ParticipantStrategy
   -> BackgroundSignatureStrategy
-> VisualRoleParticipationPlanner
-> FinalVisualPromptContractBuilder
-> VisualRolePromptProjector
-> Critic / Repair
-> ArtifactWriter
```

### 6.1 为什么拆出 ModePreflightService 和 ModeResolutionService

用户请求不能直接决定最终 planner，因为会出现：

```text
1. 用户选择 cognitive_illustration，但文章其实是纯流程教程。
2. 用户选择 relationship_map，但单帧内容只有一个人物情绪转折。
3. 用户选择 signature_presence，但文章又要求解释复杂因果机制。
4. auto 模式下没有足够文章上下文。
5. LLM planner 置信度过低，需要 fallback。
```

因此 V4.4 拆成两步：

```text
ModePreflightService：
只做请求归一化、非法值 fallback、显式字段识别、兼容路径候选标记。
它不做最终 planner 选择，因为此时还没有 ArticleUnderstandingPlan。

ModeResolutionService：
在 ArticleUnderstandingPlan 和 FrameUnderstandingPlan 生成之后运行。
它负责将用户请求、文章理解、帧级上下文、IP 能力和系统兼容策略合成可执行的 route decision。
```

这可以避免“先决策模式、再用尚未生成的文章理解解释模式”的循环依赖。

### 6.2 为什么 HostExplainer / SignaturePresence 不进 VisualPlanningRouter

`VisualPlanningRouter` 的职责：

```text
选择文章内容如何被视觉具象化。
```

`VisualRoleStrategyResolver` 的职责：

```text
选择固定视觉签名 / IP 如何参与该视觉任务。
```

所以：

```text
cognitive_illustration 是视觉任务。
host_explainer 是 IP 参与方式。
signature_presence 是 IP 参与方式。
```

如果把它们放在同一个 router，就会产生职责污染。

---

## 7. 核心枚举

### 7.1 ArticleUnderstandingMode

```python
class ArticleUnderstandingMode(Enum):
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

### 7.2 ArticleUnderstandingLens

```python
class ArticleUnderstandingLens(Enum):
    THESIS_ARGUMENT = "thesis_argument"
    CAUSAL_MECHANISM = "causal_mechanism"
    COGNITIVE_STATE = "cognitive_state"
    PROCESS_METHOD = "process_method"
    RELATIONSHIP_STRUCTURE = "relationship_structure"
    CONTRAST_CONFLICT = "contrast_conflict"
    NARRATIVE_EVENT = "narrative_event"
    METAPHOR_SYMBOLIC = "metaphor_symbolic"
```

`Mode` 是用户请求层，`Lens` 是系统理解层。二者可以同名，但不要混为一个类型。

### 7.3 VisualPlanningMode

```python
class VisualPlanningMode(Enum):
    AUTO = "auto"
    SCENE_INTEGRATION = "scene_integration"
    COGNITIVE_ILLUSTRATION = "cognitive_illustration"
    STRUCTURAL_EXPLAINER = "structural_explainer"
    PROCESS_WALKTHROUGH = "process_walkthrough"
    CONTRAST_ARGUMENT = "contrast_argument"
    RELATIONSHIP_MAP = "relationship_map"
```

### 7.4 VisualRoleStrategy

```python
class VisualRoleStrategy(Enum):
    AUTO = "auto"
    HOST_EXPLAINER = "host_explainer"
    SIGNATURE_PRESENCE = "signature_presence"
    OBSERVER_GUIDE = "observer_guide"
    PARTICIPANT = "participant"
    BACKGROUND_SIGNATURE = "background_signature"
```

### 7.5 PrimaryVisualTask

```python
class PrimaryVisualTask(Enum):
    SCENE_RECONSTRUCTION = "scene_reconstruction"
    COGNITIVE_EXPLANATION = "cognitive_explanation"
    STRUCTURE_EXPLANATION = "structure_explanation"
    PROCESS_WALKTHROUGH = "process_walkthrough"
    CONTRAST_ARGUMENT = "contrast_argument"
    RELATIONSHIP_MAPPING = "relationship_mapping"
```

### 7.6 VisibleTextPolicy

```python
class VisibleTextPolicy(Enum):
    NO_VISIBLE_TEXT = "no_visible_text"
    SOURCE_TEXT_ONLY = "source_text_only"
    SYMBOLIC_LABELS_ONLY = "symbolic_labels_only"
    APPROVED_LABELS_ONLY = "approved_labels_only"
```

统一使用字段名：

```python
visible_text_policy: VisibleTextPolicy
```

不要再混用：

```text
text_rendering_policy
visible_text_policy
VisibleTextPolicy
```

默认策略必须是 `NO_VISIBLE_TEXT`。任何允许画面文字的策略都必须绑定白名单、来源证据和模型能力检查：

```text
SOURCE_TEXT_ONLY：只能使用原文中明确出现的短语。
SYMBOLIC_LABELS_ONLY：只能使用非语言符号或极短结构标签。
APPROVED_LABELS_ONLY：只能使用业务侧显式批准的标签白名单。
```

禁止把自由文字、UI overlay、调试标签或提示词说明作为默认画面内容。

### 7.7 IPRoleIntent

```python
class IPRoleIntent(Enum):
    OBSERVE = "observe"
    GUIDE = "guide"
    WARN = "warn"
    COMPARE = "compare"
    DECONSTRUCT = "deconstruct"
    CONNECT = "connect"
    NARRATE = "narrate"
    BACKGROUND_SIGNATURE = "background_signature"
```

---

## 8. Mode Resolution 数据契约

### 8.1 ArticleVisualPlanningRequest

```python
@dataclass(frozen=True)
class ArticleVisualPlanningRequest:
    article_understanding_mode: ArticleUnderstandingMode = ArticleUnderstandingMode.AUTO
    visual_planning_mode: VisualPlanningMode = VisualPlanningMode.AUTO
    visual_role_strategy: VisualRoleStrategy = VisualRoleStrategy.AUTO
    user_intent_hint: str | None = None
    allow_mixed_lenses: bool = True
    strict_user_mode: bool = False
    force_v44_planning: bool = False
```

字段含义：

| 字段 | 说明 |
| --- | --- |
| `article_understanding_mode` | 用户希望系统如何理解文章 |
| `visual_planning_mode` | 用户希望文章如何被视觉化 |
| `visual_role_strategy` | 用户希望 IP 如何参与 |
| `allow_mixed_lenses` | 是否允许主理解 + 辅理解 |
| `strict_user_mode` | 是否严格遵守用户选择，即使有 mismatch |
| `force_v44_planning` | 是否强制走 V4.4 结构化链路 |

### 8.2 ArticleVisualPlanningPreflight

```python
@dataclass(frozen=True)
class ArticleVisualPlanningPreflight:
    preflight_id: str
    requested: ArticleVisualPlanningRequest
    normalized_article_mode: ArticleUnderstandingMode
    normalized_visual_mode: VisualPlanningMode
    normalized_visual_role_strategy: VisualRoleStrategy
    strict_user_mode: bool
    force_v44_planning: bool
    explicit_fields: tuple[str, ...]
    legacy_fallback_candidate: bool
    validation_warnings: tuple[str, ...]
```

`ArticleVisualPlanningPreflight` 只描述请求层状态，不做最终路由决策。它可以判断“这个请求是否像 V4.2 旧请求”，但不能在文章理解完成前决定最终 planner。

### 8.3 VisualPlanningRouteDecision

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
    resolution_status: Literal["resolved", "low_confidence", "planner_failed", "fallback_used"]
    fallback_eligible: bool
    fallback_used: bool
    fallback_target: str | None
    fallback_reason: str | None
    mismatch_warnings: tuple[str, ...]
```

`route_decision_id` 是后续 artifact、FinalVisualPromptContract 和 RenderedMediaPrompt metadata 的追溯主键。即使路由低置信度、planner 失败或最终回退 V4.2，也必须产出一条带状态的 route decision，而不是让回退绕过路由记录。

### 8.4 Mode Resolution 优先级

执行优先级：

```text
1. preflight
   - 归一化非法值。
   - 记录用户显式选择。
   - 标记 legacy fallback candidate。
   - 不做最终 planner 选择。

2. strict_user_mode = true
   - 严格尊重用户选择。
   - 如果内容与模式冲突，生成 mismatch warning。
   - 只有安全、身份、文本策略等硬约束可以阻断。

3. 用户 soft preference
   - 优先尊重用户选择。
   - 如果文章理解强烈不匹配，则允许降级或切换，并记录 reason。

4. auto
   - 基于 ArticleUnderstandingPlan 和 FrameUnderstandingPlan 自动选择。

5. fallback
   - 低置信度、信息不足或 planner 失败时回退到 scene_integration 或 V4.2 默认路径。
   - 回退本身也必须写入 VisualPlanningRouteDecision，使用 resolution_status / fallback_target / fallback_reason 表达原因。
```

### 8.5 Mode Compatibility 基础矩阵

| ArticleUnderstandingLens | 推荐 VisualPlanningMode | 可接受候选 | 避免 |
| --- | --- | --- | --- |
| `cognitive_state` | `cognitive_illustration` | `contrast_argument`, `scene_integration` | `relationship_map` |
| `causal_mechanism` | `structural_explainer` | `process_walkthrough`, `cognitive_illustration` | `relationship_map` |
| `process_method` | `process_walkthrough` | `structural_explainer` | `relationship_map` |
| `relationship_structure` | `relationship_map` | `structural_explainer` | `cognitive_illustration` |
| `contrast_conflict` | `contrast_argument` | `cognitive_illustration`, `scene_integration` | `process_walkthrough` |
| `narrative_event` | `scene_integration` | `contrast_argument` | `structural_explainer` |
| `thesis_argument` | `structural_explainer` | `contrast_argument`, `cognitive_illustration` | 无绝对避免，依赖内容 |
| `metaphor_symbolic` | `cognitive_illustration` | `scene_integration` | `relationship_map` |

注意：`host_explainer` 和 `signature_presence` 永远不进入此矩阵，因为它们不是视觉具象化方式。

---

## 9. 文章理解数据契约

### 9.1 SourceEvidenceSpan

```python
@dataclass(frozen=True)
class SourceEvidenceSpan:
    source_id: str
    frame_id: str | None
    start_char: int | None
    end_char: int | None
    quote: str
    evidence_role: Literal[
        "core_claim",
        "central_problem",
        "required_subject",
        "causal_link",
        "contrast_axis",
        "process_step",
        "relationship_edge",
        "emotion_or_cognitive_state"
    ]
```

用途：

```text
1. 防止 LLM 凭空理解文章。
2. 让 critic 能追溯判断依据。
3. 让 artifact 能解释为什么系统选择某个 lens。
```

### 9.2 SubjectAnchor

```python
@dataclass(frozen=True)
class SubjectAnchor:
    subject_id: str
    label: str
    source_phrase: str
    evidence_span_ids: tuple[str, ...]
    importance: Literal["critical", "important", "optional"]
    visual_presence: Literal["must_be_visible", "may_be_symbolic", "may_be_implied"]
    loss_policy: Literal["fail", "repair", "warn"]
```

示例：

```json
{
  "subject_id": "subject_repeated_path",
  "label": "重复路径",
  "source_phrase": "总是在同样的地方绕回来",
  "evidence_span_ids": ["evidence_frame_003_required_subject_001"],
  "importance": "critical",
  "visual_presence": "must_be_visible",
  "loss_policy": "fail"
}
```

`source_phrase` 只适合人读；artifact 和 critic 追溯必须依赖 `evidence_span_ids`。同一句话里出现多个相同短语时，禁止只靠字符串匹配回查来源。

### 9.3 Lens Payloads

不要把所有理解字段塞进一个万能 plan。不同 lens 使用不同 payload。

```python
@dataclass(frozen=True)
class CognitiveStatePayload:
    cognitive_conflict: str
    stuck_loop: str | None
    mistaken_assumption: str | None
    turning_point: str | None
    emotional_pressure: str | None
```

```python
@dataclass(frozen=True)
class CausalMechanismPayload:
    causes: tuple[str, ...]
    triggers: tuple[str, ...]
    outcomes: tuple[str, ...]
    feedback_loops: tuple[str, ...]
```

```python
@dataclass(frozen=True)
class ThesisArgumentPayload:
    thesis: str
    supporting_points: tuple[str, ...]
    counterpoints: tuple[str, ...]
    conclusion: str | None
```

```python
@dataclass(frozen=True)
class ProcessMethodPayload:
    steps: tuple[str, ...]
    sequence_rule: str
    dependencies: tuple[str, ...]
    failure_points: tuple[str, ...]
```

```python
@dataclass(frozen=True)
class RelationshipStructurePayload:
    entities: tuple[str, ...]
    relationships: tuple[Mapping[str, str], ...]
    power_or_dependency_axis: str | None
    conflict_edges: tuple[str, ...]
```

```python
@dataclass(frozen=True)
class ContrastConflictPayload:
    left_side: str
    right_side: str
    contrast_axis: str
    transformation: str | None
    resolution: str | None
```

```python
@dataclass(frozen=True)
class NarrativeEventPayload:
    protagonist: str | None
    setting: str | None
    event_sequence: tuple[str, ...]
    emotional_arc: str | None
```

```python
@dataclass(frozen=True)
class MetaphorSymbolicPayload:
    abstract_concept: str
    symbolic_candidates: tuple[str, ...]
    metaphor_mapping: Mapping[str, str]
    forbidden_overliteralization: tuple[str, ...]
```

### 9.4 ArticleUnderstandingPlan

```python
@dataclass(frozen=True)
class ArticleUnderstandingPlan:
    article_id: str
    primary_lens: ArticleUnderstandingLens
    secondary_lenses: tuple[ArticleUnderstandingLens, ...]
    lens_confidence: Mapping[str, float]
    core_claim: str
    central_problem: str
    main_entities: tuple[str, ...]
    required_subjects: tuple[SubjectAnchor, ...]
    lens_payloads: Mapping[str, Any]
    unsuitable_visual_modes: tuple[VisualPlanningMode, ...]
    source_evidence: tuple[SourceEvidenceSpan, ...]
```

artifact schema 中 `lens_confidence` 和 `lens_payloads` 的 key 必须使用 `ArticleUnderstandingLens.value` 字符串。运行时可以在 helper 内转成 enum，但 JSON 边界、测试 fixture 和 manifest 不允许使用 enum object 作为 mapping key。

### 9.5 FrameUnderstandingPlan

```python
@dataclass(frozen=True)
class FrameUnderstandingPlan:
    frame_id: str
    source_text: str
    frame_claim: str
    frame_question: str | None
    primary_lens: ArticleUnderstandingLens
    secondary_lenses: tuple[ArticleUnderstandingLens, ...]
    required_subjects: tuple[SubjectAnchor, ...]
    forbidden_subject_losses: tuple[str, ...]
    visible_text_policy: VisibleTextPolicy
    source_evidence: tuple[SourceEvidenceSpan, ...]
```

---

## 10. 视觉具象化数据契约

### 10.1 VisualConcretizationPlan

```python
@dataclass(frozen=True)
class VisualConcretizationPlan:
    frame_id: str
    visual_planning_mode: VisualPlanningMode
    primary_visual_task: PrimaryVisualTask
    secondary_visual_tasks: tuple[PrimaryVisualTask, ...]
    article_anchor: str
    visual_metaphor: str | None
    composition_structure: str
    scene_subjects: tuple[SubjectAnchor, ...]
    information_structure: Mapping[str, Any]
    visible_text_policy: VisibleTextPolicy
    negative_semantics: tuple[str, ...]
    planner_notes: str | None = None
```

要求：

```text
1. planner 可以输出自然语言解释，但关键控制字段必须 enum 化或结构化。
2. VisualConcretizationPlan 不负责 IP 身份细节。
3. VisualConcretizationPlan 不直接输出最终 prompt。
```

### 10.2 各 planner 职责

| Planner | 输入 | 输出重点 |
| --- | --- | --- |
| `SceneIntegrationPlanner` | 叙事事件、场景型帧 | 人物、地点、事件、情绪、镜头结构 |
| `CognitiveIllustrationPlanner` | 认知状态、隐喻、困境 | 认知卡点、误区、循环、顿悟的可视隐喻 |
| `StructuralExplainerPlanner` | 因果、论证、系统结构 | 层级、组件、因果链、机制解释 |
| `ProcessWalkthroughPlanner` | 方法、步骤、路径 | 顺序、流程节点、动作依赖、失败点 |
| `ContrastArgumentPlanner` | 对比冲突 | 左右对照、前后变化、错误/正确路径 |
| `RelationshipMapPlanner` | 关系结构 | 节点、边、权力/依赖/冲突关系 |

### 10.3 认知配图的硬语义

“认知配图”不是：

```text
固定 IP 出现在每张图里。
```

也不是：

```text
把每段文案都变成抽象隐喻。
```

它应该是：

```text
把文章里的认知卡点、困境、循环、误区、顿悟、选择压力或心理结构，
转成一个可被读者一眼理解的画面。
```

认知配图模式下必须明确：

```text
1. 这一帧解释的认知问题是什么。
2. 这个问题用什么视觉隐喻表达。
3. 原文主体有哪些必须保留。
4. IP 承担什么认知动作：观察、指引、提醒、拆解、对照、牵引。
5. IP 是辅助理解，不默认替代原文主体。
6. 未明确允许时，不在画面里生成文字。
```

示例结构：

```json
{
  "primary_lens": "cognitive_state",
  "visual_planning_mode": "cognitive_illustration",
  "core_claim": "人会在熟悉模式里重复困境",
  "cognitive_conflict": "知道自己在绕圈，但仍然回到原点",
  "visual_metaphor": "迷宫中的重复路径",
  "required_subjects": [
    {
      "label": "迷路的人",
      "importance": "critical",
      "visual_presence": "must_be_visible",
      "loss_policy": "fail"
    },
    {
      "label": "重复路径",
      "importance": "critical",
      "visual_presence": "must_be_visible",
      "loss_policy": "fail"
    }
  ],
  "visible_text_policy": "no_visible_text"
}
```

---

## 11. IP 视觉参与数据契约

### 11.1 VisualRoleWeightContract

V4.4 只保留一个最终权重事实源。

```python
@dataclass(frozen=True)
class VisualRoleWeightContract:
    requested_weight: VisualRoleWeight | None
    resolved_weight: VisualRoleWeight
    max_frame_area_ratio: float | None
    dominance_policy: Literal[
        "never_replace_original_subject",
        "may_lead",
        "background_only"
    ]
    reason: str
```

避免冲突：

```text
VisualConcretizationPlan.ip_weight = supporting
VisualRoleParticipationPlan.max_visual_weight = dominant
```

V4.4 不允许两个字段各自成为事实源。

### 11.2 VisualRoleParticipationPlan

```python
@dataclass(frozen=True)
class VisualRoleParticipationPlan:
    frame_id: str
    identity_contract: VisualRoleIdentityContract
    visual_role_strategy: VisualRoleStrategy
    role_mode: VisualRoleMode
    participation_mode: VisualRoleParticipationMode
    structure_mode: VisualRoleStructureMode
    ip_role_intent: IPRoleIntent
    action_responsibility: str
    subject_preservation_rule: str
    weight_contract: VisualRoleWeightContract
    cardinality_rule: str
    identity_lock: bool = True
```

### 11.3 IP 参与策略解析规则

| VisualRoleStrategy | 适合场景 | 约束 |
| --- | --- | --- |
| `host_explainer` | 讲解型、图解型、教程型 | 不允许遮挡核心主体；讲解姿态服务信息结构 |
| `signature_presence` | 文章主体很强、IP 只需保持系列识别 | IP 权重必须低，只能作为真实场景内低权重实体、道具或环境细节；禁止角标、水印、贴纸、UI overlay |
| `observer_guide` | 认知配图、对比论证 | IP 观察、指向、提醒，不替代主角 |
| `participant` | 叙事场景或互动场景 | 受 SubjectAnchor 保护，不得吞掉原文人物 |
| `background_signature` | 氛围、品牌统一、弱连续性 | 不能改变核心语义 |

### 11.4 与现有高级字段的优先级

V4.4 新增 `visual_role_strategy` 后，不能让它和现有字段各自成为事实源。

以下字段都只能作为 `VisualRoleStrategyResolver` 的输入：

```text
visual_role_strategy
visual_expression_mode
visual_structure_mode
visual_participation_mode
visual_role_mode
visual_consistency_mode
```

唯一输出事实源是：

```text
VisualRoleParticipationPlan
VisualRoleWeightContract
```

冲突处理规则：

```text
1. 身份契约、安全策略、SubjectAnchor、visible_text_policy 优先级最高。
2. visual_role_strategy 决定 IP 参与的语义意图。
3. 现有高级字段是约束或提示，不直接写入最终 prompt。
4. 如果 visual_role_strategy 与高级字段冲突：
   - strict_user_mode = true：生成 unsupported_mode_combination 或 mismatch warning；硬约束冲突时阻断。
   - strict_user_mode = false：Resolver 选择更符合文章理解和主体保护的组合，并记录 mismatch_warnings。
5. visual_consistency_mode = primary_character 不得无条件升级为 subject_replacement。
   只有 SubjectAnchor 允许原主体被替代，或用户明确选择主体型 IP 任务时，才允许升级。
6. visual_role_mode = subject_replacement 与 signature_presence / observer_guide 默认冲突。
   默认应降级为 supporting_integration，并记录原因。
```

代码落地约束：

```text
现有 pixelle_video.models.visual_role_strategy.VisualRoleStrategyControls 已经会根据 visual_consistency_mode 推导 effective_role_mode。
Phase 1 必须把 primary_character -> subject_replacement 的自动升级移动到 VisualRoleStrategyResolver 之后，或让 effective_role_mode 接收 SubjectAnchor / visual_role_strategy 上下文。
禁止让现有 effective_role_mode 在没有主体保护信息时直接成为最终事实源。
```

示例：

```json
{
  "visual_role_strategy": "observer_guide",
  "visual_role_mode": "subject_replacement",
  "resolved_role_mode": "supporting_integration",
  "mismatch_warnings": [
    "observer_guide cannot replace critical source subjects; subject_replacement was downgraded"
  ]
}
```

---

## 12. FinalVisualPromptContract

### 12.1 为什么需要最终合约

Projector 不能继续只是字符串拼接器。V4.4 中，最终 prompt 生成前必须先形成可审计合约。

兼容迁移约束：

```text
当前代码中已经存在 final_visual_prompt_contract.v1，字段为 scene / composition / style_assignment / character_layer_style / world_layer_style / integration_priority。
V4.4 实施时禁止一次性替换这个 dataclass，否则现有 FinalVisualPromptContractBuilder、VisualRolePromptProjector、ProviderPromptProjector 和相关测试会被打断。
推荐路径：
1. 新增 FinalVisualPromptContractV44 或 versioned payload adapter。
2. 保留现有 v1 字段和构造入口，先把 V4.4 追溯字段写入 metadata / adapter 输出。
3. 所有 projector 同时支持 v1 渲染和 v4.4 追溯 metadata。
4. 等现有 builder/projector/test 全部迁移后，再决定是否合并类名。
```

```python
@dataclass(frozen=True)
class ProjectedPromptPart:
    part_id: str
    priority: int
    source_plan_type: str
    source_field: str
    content: str
    locked: bool
    critic_check_required: bool
```

```python
@dataclass(frozen=True)
class FinalVisualPromptContract:
    contract_schema_version: str
    contract_id: str
    frame_id: str
    primary_visual_task: PrimaryVisualTask
    article_anchor: str
    required_subjects: tuple[SubjectAnchor, ...]
    visual_concretization_summary: str
    identity_contract: VisualRoleIdentityContract | None
    visual_role_strategy: VisualRoleStrategy
    weight_contract: VisualRoleWeightContract | None
    visible_text_policy: VisibleTextPolicy
    projected_prompt_parts: tuple[ProjectedPromptPart, ...]
    negative_semantics: tuple[str, ...]
    route_decision_id: str
```

`FinalVisualPromptContract` 不拥有最终字符串 prompt。最终字符串由 `PromptProjector` 从 `projected_prompt_parts` 渲染为 `RenderedMediaPrompt`，并在 metadata 中记录 contract id、route decision id 与 projected parts 摘要。

这样可以保证：

```text
FinalVisualPromptContract 是事实源。
RenderedMediaPrompt.prompt 是派生结果。
critic / repair 修改 contract 或上游 plan，再重新投影 prompt。
```

### 12.2 Prompt 投影优先级

最终 prompt 按结构化语义块投影：

```text
1. Primary visual task
2. Article understanding anchor
3. Required original subjects
4. Visual concretization structure
5. Fixed visual identity contract
6. Visual role action responsibility
7. Subject preservation and IP weight rules
8. Composition and style contract
9. Visible text policy
10. Safety / identity protection rules
```

### 12.3 Projector 硬要求

Projector 必须：

```text
1. 保证 required_subjects 进入最终 prompt。
2. 保证 identity_contract 的 required_identity_traits 进入最终 prompt。
3. 保证 visible_text_policy 不被 planner 文本绕过。
4. 保证 IP cardinality 和 visual weight 规则进入最终 prompt。
5. 记录 projected_prompt_parts。
6. 不泄漏内部 enum 名、debug 字段、artifact 路径。
```

---

## 13. Critic / Repair 闭环

### 13.1 RepairTarget

```python
class RepairTarget(Enum):
    ARTICLE_UNDERSTANDING_PLAN = "article_understanding_plan"
    FRAME_UNDERSTANDING_PLAN = "frame_understanding_plan"
    VISUAL_CONCRETIZATION_PLAN = "visual_concretization_plan"
    VISUAL_ROLE_PARTICIPATION_PLAN = "visual_role_participation_plan"
    FINAL_PROMPT_CONTRACT = "final_prompt_contract"
```

### 13.2 CriticIssue

```python
@dataclass(frozen=True)
class CriticIssue:
    code: str
    severity: Literal["error", "warning", "info"]
    target: RepairTarget
    frame_id: str | None
    message: str
    evidence: tuple[str, ...]
    suggested_repair: str | None
```

### 13.3 必须新增的 issue code

```text
article_lens_mismatch
primary_claim_lost
required_subject_lost
ip_overdominance
ip_cardinality_violation
visible_text_policy_violation
concretization_too_generic
mode_prompt_leakage
conflicting_visual_tasks
route_decision_low_confidence
unsupported_mode_combination
source_evidence_missing
```

### 13.4 RepairAction

```python
@dataclass(frozen=True)
class RepairAction:
    action_id: str
    issue_code: str
    target: RepairTarget
    frame_id: str | None
    before_summary: str
    after_summary: str
    changed_fields: tuple[str, ...]
    reproject_required: bool = True
```

### 13.5 执行顺序

```text
1. ArticleUnderstandingCritic
2. FrameUnderstandingCritic
3. VisualConcretizationCritic
4. VisualRoleParticipationCritic
5. FinalPromptContractCritic
6. Repair by target plan
7. Rebuild FinalVisualPromptContract
8. Re-project final prompt
9. Final critic pass
```

### 13.6 Repair 硬限制

```text
max_repair_rounds = 2
repair 不允许直接追加 issue 文本到 prompt
repair 必须产出 repair_actions artifact
repair 后必须重新投影 prompt
repair 后必须重新跑 FinalPromptContractCritic
```

---

## 14. Artifact 规范

### 14.1 Manifest

新增统一入口：

```text
prompt_traces/manifest.json
```

最小字段：

```json
{
  "schema_version": "v4.4",
  "article_id": "article_001",
  "frames": ["frame_001", "frame_002"],
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
  "route_decision_ids": {
    "frame_001": "route_frame_001_v44_001",
    "frame_002": "route_frame_002_v44_001"
  },
  "fallbacks": [],
  "critic_status": "passed",
  "repair_rounds": 0
}
```

### 14.2 文件布局

```text
prompt_traces/
  manifest.json
  runtime_config_snapshot.json
  article_understanding/
    article_visual_planning_request.json
    article_visual_planning_preflight.json
    article_understanding_plan.json
    frame_understanding_plan_{frame_id}.json
  router/
    route_decisions.json
    visual_planning_router_decision_{frame_id}.json
  visual_concretization/
    visual_concretization_plan_{frame_id}.json
  visual_role/
    visual_role_participation_plan_{frame_id}.json
    visual_role_weight_contract_{frame_id}.json
  final_prompt_contracts/
    final_visual_prompt_contract_{frame_id}.json
  critic/
    critic_issues_before_repair.json
    critic_issues_after_repair.json
  repair/
    repair_actions.json
  final_visual_prompts.md
```

### 14.3 Artifact 验收要求

```text
1. 任意最终 prompt 都能追溯到 route decision。
2. 任意 required subject 都能追溯到 source evidence。
3. 任意 IP 权重限制都能追溯到 VisualRoleWeightContract。
4. 任意 repair 都能看到 before / after / changed_fields。
5. fallback 必须记录原因，不能静默发生。
6. manifest 必须记录 frame_id -> route_decision_id 映射，FinalVisualPromptContract 和 RenderedMediaPrompt metadata 必须包含同一个 route_decision_id。
```

---

## 15. V4.2 兼容策略

### 15.1 兼容原则

V4.4 默认不破坏 V4.2 行为，但不是永远绕过 V4.4。

推荐策略：

```text
V4.4 结构化链路默认可用。
当 auto + 低置信度 + 缺少文章上下文 + legacy 请求特征明显时，允许回退 V4.2 路径。
```

### 15.2 兼容适配器

```python
class V42CompatibilityAdapter:
    def should_use_v42_path(self, params, preflight, route_decisions) -> bool:
        route_allows_v42_fallback = (
            not route_decisions
            or any(
                decision.fallback_eligible
                and decision.fallback_target == "v4.2_visual_role_path"
                for decision in route_decisions
            )
        )
        return (
            preflight.requested.article_understanding_mode == ArticleUnderstandingMode.AUTO
            and preflight.requested.visual_planning_mode == VisualPlanningMode.AUTO
            and preflight.requested.visual_role_strategy == VisualRoleStrategy.AUTO
            and not preflight.requested.force_v44_planning
            and self._article_context_is_insufficient(params)
            and self._legacy_visual_role_request_is_present(params)
            and route_allows_v42_fallback
        )
```

禁止把 `not route_decisions` 当成唯一 fallback 条件。低置信度或 planner 失败时，系统应该已经有一条 `resolution_status` 为 `low_confidence` / `planner_failed` 的 route decision；这类 decision 仍然可以触发 V4.2 fallback，但必须被 artifact 记录下来。

### 15.3 Fallback 必须可见

如果回退 V4.2，artifact 必须记录：

```json
{
  "fallback_used": true,
  "fallback_target": "v4.2_visual_role_path",
  "fallback_reason": "auto modes with insufficient article context and legacy request shape"
}
```

### 15.4 不允许的兼容方式

```text
1. 静默忽略 article_understanding_mode。
2. 静默忽略 visual_planning_mode。
3. 静默忽略 visual_role_strategy。
4. 只在 prompt 后面追加“认知配图风格”。
5. 无 artifact 记录地回退旧链路。
```

---

## 16. 实施阶段

### Phase 0：冻结边界

目标：先冻结 V4.4 边界，不动代码。

验收：

```text
1. 确认 cognitive_illustration 不进入 visual_expression_mode。
2. 确认 host_explainer / signature_presence 不属于 visual_planning_mode。
3. 确认 visual_role_strategy 独立存在。
4. 确认 V4.2 兼容策略。
5. 确认 FinalVisualPromptContract 兼容迁移策略是 Phase 1 必做项。
```

### Phase 1：新增枚举、请求模型、Preflight 与 RouteDecision 契约

新增：

```text
pixelle_video/models/article_understanding.py
pixelle_video/models/visual_planning_mode.py
pixelle_video/models/visual_role_strategy.py（扩展现有文件，禁止破坏 VisualRoleStrategyControls 兼容）
pixelle_video/models/mode_resolution.py
pixelle_video/models/final_visual_prompt_contract.py（保留 v1 contract，新增 V4.4 adapter 或 versioned payload）
```

修改：

```text
VisualRoleRequest
VideoGenerationParams
api/schemas/video.py
api/routers/video.py
pixelle_video/contracts/ip_generation_request.py
```

验收：

```text
1. article_understanding_mode 可以从前端/API 进入后端。
2. visual_planning_mode 可以从前端/API 进入后端。
3. visual_role_strategy 可以从前端/API 进入后端。
4. invalid value fallback auto。
5. to_dict / from_mapping / normalize 测试通过。
6. VisualPlanningRouteDecision 可单测，且必须包含 route_decision_id / resolution_status / fallback_target。
7. 现有 FinalVisualPromptContract v1、FinalVisualPromptContractBuilder、VisualRolePromptProjector 测试继续通过。
```

### Phase 2：API / UI 透传

新增或修改：

```text
web/components/ip_prompt_chain_controls.py
web/components/content_ip_world_controls.py
web/i18n/locales/zh_CN.json
web/i18n/locales/en_US.json
tests/test_video_api.py
tests/test_content_ip_world_controls.py
```

验收：

```text
1. 三个新字段端到端透传。
2. 默认 auto 不增加用户负担。
3. 高级策略仍可覆盖低层控制。
4. session_state key 稳定。
```

### Phase 3：ArticleUnderstandingPlanner + FrameUnderstandingPlanner

新增：

```text
ArticleUnderstandingPlanner
FrameUnderstandingPlanner
SourceEvidenceExtractor
SubjectAnchorBuilder
```

验收：

```text
1. 输出 ArticleUnderstandingPlan。
2. 输出每帧 FrameUnderstandingPlan。
3. 支持 primary_lens + secondary_lenses。
4. 输出 lens_confidence。
5. 输出 source_evidence。
6. 输出 SubjectAnchor，而不是裸字符串 required_subjects。
```

### Phase 4：VisualPlanningRouter + 各类 VisualConcretizationPlanner

新增：

```text
VisualPlanningRouter
SceneIntegrationPlanner
CognitiveIllustrationPlanner
StructuralExplainerPlanner
ProcessWalkthroughPlanner
ContrastArgumentPlanner
RelationshipMapPlanner
```

验收：

```text
1. 不同 visual_planning_mode 进入不同 planner。
2. auto 可以基于 ArticleUnderstandingPlan 自动选择 planner。
3. 每个 planner 输出同一类 VisualConcretizationPlan。
4. 不允许 planner 直接输出最终 prompt 作为唯一事实源。
5. route decision artifact 完整。
```

### Phase 5：VisualRoleStrategyResolver + VisualRoleParticipationPlanner

新增或收敛：

```text
VisualRoleStrategyResolver
HostExplainerStrategy
SignaturePresenceStrategy
ObserverGuideStrategy
ParticipantStrategy
BackgroundSignatureStrategy
VisualRoleWeightContractBuilder
```

验收：

```text
1. visual_role_strategy 与 visual_planning_mode 解耦。
2. IP 权重由 VisualRoleWeightContract 统一。
3. 原文主体不会被 IP 替代。
4. cardinality_rule 稳定。
5. identity_contract 保留。
```

### Phase 6：PromptProjector + FinalVisualPromptContract

新增或升级：

```text
FinalVisualPromptContractBuilder
VisualRolePromptProjector
ProviderPromptProjector
```

验收：

```text
1. final prompt 中可追踪每个语义块来源。
2. projected_prompt_parts 完整。
3. required_subjects、identity_contract、visible_text_policy 都进入 contract。
4. 不泄漏内部枚举名、debug 字段、artifact 路径。
5. 不把 visible text 作为默认画面元素。
6. V4.4 追溯字段先通过 versioned adapter / metadata 接入，不能破坏现有 v1 contract 构造路径。
```

### Phase 7：Critic / Repair 闭环

新增或升级：

```text
ArticleUnderstandingCritic
FrameUnderstandingCritic
VisualConcretizationCritic
VisualRoleParticipationCritic
FinalPromptContractCritic
StructuredRepairLoop
RepairActionWriter
```

验收：

```text
1. issue 有 target。
2. repair 修改结构化 plan。
3. repair 后重新生成 FinalVisualPromptContract。
4. repair 后重新投影 prompt。
5. before / after critic artifacts 完整。
6. max_repair_rounds = 2。
```

### Phase 8：E2E 回归与发布冻结

验收：

```text
1. V4.2 默认路径兼容。
2. V4.4 四类核心 fixture 通过。
3. artifact manifest 完整。
4. 同一篇文章在不同理解方式下生成不同 ArticleUnderstandingPlan。
5. 认知配图不再只靠 prompt 拼接。
6. 所有 targeted V4.4 tests 通过。
```

---

## 17. 测试计划

### 17.1 Contract Tests：纯 Python 确定性测试

新增：

```text
tests/models/test_article_understanding.py
tests/models/test_visual_planning_mode.py
tests/models/test_visual_role_strategy.py
tests/models/test_mode_resolution.py
tests/models/test_final_visual_prompt_contract.py
```

覆盖：

```text
1. enum normalize。
2. invalid value fallback auto。
3. to_dict / from_mapping。
4. SubjectAnchor 序列化。
5. SourceEvidenceSpan 序列化。
6. VisibleTextPolicy 统一字段名。
7. VisualPlanningRouteDecision 必填字段。
8. FinalVisualPromptContract projected parts。
9. route_decision_id 在 route decision、contract、rendered prompt metadata 中一致。
10. lens_confidence / lens_payloads artifact 使用字符串 key。
```

### 17.2 Router Tests：fake plan 确定性测试

新增：

```text
tests/services/test_mode_resolution_service.py
tests/services/test_visual_planning_router.py
tests/services/test_visual_role_strategy_resolver.py
```

覆盖：

```text
1. cognitive_state -> cognitive_illustration。
2. causal_mechanism -> structural_explainer 或 process_walkthrough。
3. contrast_conflict -> contrast_argument。
4. relationship_structure -> relationship_map。
5. host_explainer 不进入 VisualPlanningRouter。
6. signature_presence 不进入 VisualPlanningRouter。
7. strict_user_mode 产生 warning 但尊重选择。
8. low confidence 触发 fallback。
```

### 17.3 LLM Planner Tests：结构完整性测试

不要断言完整自然语言结果。

不要这样测：

```python
assert plan.visual_metaphor == "迷宫中的重复路径"
```

应该这样测：

```python
assert plan.primary_visual_task == PrimaryVisualTask.COGNITIVE_EXPLANATION
assert plan.required_subjects
assert plan.source_evidence
assert plan.visible_text_policy == VisibleTextPolicy.NO_VISIBLE_TEXT
assert any(anchor.importance == "critical" for anchor in plan.required_subjects)
```

### 17.4 Projector Tests

新增或扩展：

```text
tests/services/test_visual_role_projector_and_service_v4.py
tests/services/test_provider_prompt_projector.py
tests/services/test_final_visual_prompt_contract_builder.py
```

覆盖：

```text
1. required_subjects 必须进入 final prompt。
2. identity_contract 必须进入 final prompt。
3. visible_text_policy 必须进入 final prompt。
4. projected_prompt_parts 能追踪来源。
5. final prompt 不出现内部调试标签。
6. route_decision_id 写入 contract。
7. 现有 v1 FinalVisualPromptContract builder/projector 行为保持兼容。
```

### 17.5 Critic / Repair Tests

新增：

```text
tests/services/test_article_understanding_critic.py
tests/services/test_visual_concretization_critic.py
tests/services/test_visual_role_participation_critic.py
tests/services/test_final_prompt_contract_critic.py
tests/services/test_structured_repair_loop.py
```

覆盖：

```text
1. 原主体丢失。
2. IP 过度主导。
3. 多个固定 IP 实例失控。
4. 画面文字违反策略。
5. 认知配图没有认知动作。
6. issue target 正确。
7. Repair 不直接追加 issue 文本到 prompt。
8. Repair 后重新 projector。
```

### 17.6 Regression Fixtures

至少建立六类 fixture：

```text
1. 认知困境型文章。
2. 因果机制型文章。
3. 流程方法型文章。
4. 对比论证型文章。
5. 关系结构型文章。
6. 叙事场景型文章。
```

每类 fixture 至少验证：

```text
1. ArticleUnderstandingPlan 正确。
2. VisualPlanningRouteDecision 正确。
3. VisualConcretizationPlan 正确。
4. VisualRoleParticipationPlan 正确。
5. FinalVisualPromptContract 完整。
6. IP 身份契约保留。
7. 原文主体保留。
8. artifact manifest 完整。
```

---

## 18. 验收标准

V4.4 完成后必须满足：

```text
1. 用户选择“认知配图”时，系统进入 CognitiveIllustrationPlanner，而不是只改 prompt 文案。
2. 用户选择不同文章理解方式时，系统生成不同 ArticleUnderstandingPlan。
3. 同一篇文章可以主理解 + 辅理解混合，但每帧必须有唯一 primary_visual_task。
4. host_explainer / signature_presence 不再混入 visual_planning_mode。
5. visual_role_strategy 可以独立控制 IP 参与方式。
6. 最终 prompt 可从 projected_prompt_parts 追踪来源。
7. required_subjects、identity_contract、visible_text_policy、ip_weight、ip_cardinality 均可测试。
8. Critic issue 有 target，Repair 修改结构化 plan。
9. V4.2 fallback 可测试、可追踪、不会静默发生。
10. prompt_traces/manifest.json 是调试入口。
```

---

## 19. 明确不做

V4.4 不做：

```text
1. 不把“小黑模式”作为正式产品名称。
2. 不把认知配图硬塞进 visual_expression_mode。
3. 不把 host_explainer / signature_presence 放进 visual_planning_mode。
4. 不用一个 VisualRoleScenePlanner 承担所有文章理解和视觉策略。
5. 不把用户选择直接拼进 prompt。
6. 不把所有内部 lens 暴露给普通用户。
7. 不用负面 prompt 代替结构化 visible_text_policy。
8. 不为单个 IP 写特判。
9. 不让 Repair 直接追加 critic 文本到 prompt。
10. 不静默 fallback 到 V4.2。
```

---

## 20. 风险与控制

| 风险 | 影响 | V4.4 控制方式 |
| --- | --- | --- |
| 模式过多导致用户困惑 | 前端复杂度上升 | 前端只暴露三项高层选择，默认 auto |
| planner 数量变多 | 维护成本上升 | 所有视觉 planner 输出统一 VisualConcretizationPlan |
| LLM 误判文章理解 | 画面偏题 | source_evidence + lens_confidence + critic + repair |
| 认知配图被滥用 | 所有画面都变抽象 | auto 可回退 scene_integration，router 有兼容矩阵 |
| IP 抢戏 | 原文表达被替代 | SubjectAnchor + VisualRoleWeightContract + critic 强校验 |
| prompt 继续拼接 | 技术债延续 | FinalVisualPromptContract + projected_prompt_parts |
| fallback 不可见 | Debug 困难 | manifest 记录 fallback_used / reason / target |
| 测试不稳定 | CI 波动 | contract/router 确定性测试，LLM 测结构而非措辞 |

---

## 21. 建议落地顺序

建议按以下原子顺序提交：

```text
1. docs: define V4.4 mode resolution and separated visual role strategy
2. test: cover V4.4 enums, request, resolution, route decision contracts
3. feat: add article visual planning request and mode resolution models
4. feat: plumb article_understanding_mode, visual_planning_mode, visual_role_strategy through API/UI
5. feat: add SubjectAnchor, SourceEvidenceSpan, ArticleUnderstandingPlan lens payloads
6. feat: add ArticleUnderstandingPlanner and FrameUnderstandingPlanner artifacts
7. feat: add VisualPlanningRouter and visual concretization planners
8. feat: add VisualRoleStrategyResolver and VisualRoleWeightContract
9. feat: add FinalVisualPromptContract and projected prompt parts
10. feat: add targeted critics and structured repair loop
11. test: add V4.2 compatibility and V4.4 regression fixtures
12. chore: add prompt_traces manifest and runtime config snapshot
```

每一步必须：

```text
可回滚
可测试
可解释
有 artifact 证据
不靠 prompt 追加修补问题
```

---

## 22. 最终判断

V4.4 是 V4.3 进入代码实施前必须完成的架构收敛版。

V4.3 解决了方向问题：

```text
Pixelle 需要文章理解层和视觉具象化策略层。
```

V4.4 解决了落地问题：

```text
模式怎么解析。
路由怎么决策。
IP 参与和内容视觉化怎么拆边界。
最终 prompt 怎么可追踪。
critic 怎么定位修复目标。
fallback 怎么可见。
测试怎么稳定。
```

最终建议：

```text
不要直接从 V4.3 进入 Phase 1 写代码。
先用 V4.4 冻结模型契约、路由边界和 artifact 规范。
然后按 Phase 1 -> Phase 8 实施。
```

V4.4 完成后，Pixelle-Video 的视觉生成链路才会真正从：

```text
逐帧配图 + IP 融入 + prompt 修补
```

升级为：

```text
文章理解 -> 视觉任务选择 -> IP 参与策略 -> 合约化 prompt 投影 -> 可审计修复闭环
```
