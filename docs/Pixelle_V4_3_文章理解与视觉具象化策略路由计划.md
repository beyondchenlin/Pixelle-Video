# Pixelle-Video V4.3 文章理解与视觉具象化策略路由计划

> 版本：V4.3 计划稿  
> 文档状态：代码实施前置方案 / 架构评审稿  
> 基准：V4.2 已建立 IP 身份契约、视觉参与结构、Projector 与 Critic 链路  
> 目标：从“逐帧配图 + IP 融入”升级为“先理解文章，再选择视觉具象化策略，再让固定视觉签名参与表达”  
> 原则：最佳实践、源头治理、禁止最小改动、禁止留下技术债

---

## 0. 一句话结论

V4.3 不能把“认知配图 / 小黑式配图”做成一个新的 prompt 选项，也不能塞进现有的 `visual_expression_mode`。

正确方向是新增一层文章理解与视觉策略路由：

```text
文章理解层
-> 视觉具象化策略层
-> IP 视觉参与层
-> 最终提示词投影层
-> Critic / Repair / Artifact
```

用户可以选择不同的文章理解方式和具象化方式，但这些选择首先必须进入结构化契约，最后才被投影成最终图片提示词。

---

## 1. 当前 V4.2 逻辑复盘

当前主链路已经完成了重要升级：

```text
BaseVisualBriefPlanner
-> VisualExpressionClassifier
-> VisualRoleRepairLoop
   -> VisualRoleScenePlanner
   -> VisualRolePromptCritic
-> VisualRolePromptProjector
-> prompt_traces / artifacts
```

当前前端控制项主要是：

```text
ip_enabled
ip_asset_bible_id
ip_profile_id
visual_expression_mode
visual_structure_mode
visual_participation_mode
visual_role_mode
visual_consistency_mode
```

V4.2 已经解决的是：

```text
1. 固定视觉签名不再只是贴纸、logo、角标或水印。
2. IP 身份被提升为 VisualRoleIdentityContract。
3. IP 的结构方式、参与方式、融入模式可以端到端进入后端。
4. Projector 开始对最终 prompt 承担责任。
5. Artifact 可以追踪 visual_role_request、profile、identity_contract、plan、critique 和 projected parts。
```

V4.2 尚未解决的是：

```text
1. 系统没有先理解整篇文章的核心主张、论证关系、因果机制、认知困境和叙事结构。
2. 当前 planner 主要处理“这一帧如何让 IP 参与画面”，不是“这篇文章应该如何被视觉化理解”。
3. visual_expression_mode、visual_structure_mode、visual_participation_mode 是低层控制，不应该承担文章理解职责。
4. 认知配图现在只能被近似成 cognitive_metaphor + concept_metaphor + guide_explainer。
5. 最终 prompt 仍然容易呈现拼接感：身份片段、场景片段、角色动作、风格片段、保护规则被线性组合。
```

这些问题会导致以下症状：

```text
1. 原文主体消失，IP 反客为主。
2. IP 权重过高，画面从“文章配图”变成“IP 肖像”。
3. 抽象文案被错误还原成随意场景。
4. 画面出现未受控文字。
5. 用户选择了“认知配图”，但底层仍然是场景融合。
6. 测试只能检查字段是否透传，难以判断系统是否真的理解文章。
```

---

## 2. V4.3 核心判断

V4.3 的核心不是：

```text
多加几个类似“小黑模式”的下拉项。
```

而是：

```text
建立 ArticleUnderstandingPlan，让文章理解成为运行时硬对象。
建立 VisualConcretizationPlan，让具象化策略成为运行时硬对象。
建立 VisualPlanningRouter，让不同画面任务进入不同 planner。
```

因此，用户选择不是直接变成 prompt 文本，而是先变成结构化计划：

```text
用户选择
-> ArticleUnderstandingRequest
-> ArticleUnderstandingPlan
-> FrameUnderstandingPlan
-> VisualConcretizationPlan
-> VisualRoleParticipationPlan
-> FinalVisualPromptContract
```

最终提示词只是投影结果，不是系统的事实源。

---

## 3. “不要硬边”的正确实现

文章理解方式和视觉具象化方式不能做成互斥硬边。

一篇文章可能同时具备：

```text
认知困境
因果机制
前后对比
人物叙事
流程方法
关系结构
```

所以 V4.3 不应该只有单个 mode，而应该支持主理解 + 辅理解：

```json
{
  "primary_lens": "cognitive_state",
  "secondary_lenses": ["contrast_argument", "causal_mechanism"],
  "lens_confidence": {
    "cognitive_state": 0.82,
    "contrast_argument": 0.64,
    "causal_mechanism": 0.51
  }
}
```

但每一帧必须有清晰主任务：

```json
{
  "frame_id": "frame_003",
  "primary_visual_task": "cognitive_illustration",
  "secondary_visual_tasks": ["contrast_argument"],
  "must_not_mix": ["host_explainer", "signature_presence"]
}
```

产品体验上不要硬边，工程契约上必须有边界。

---

## 4. 用户可见的高层选项

前端不应暴露太多内部分类。建议新增两个高层选择，默认都是自动。

### 4.1 内容理解方式

字段建议：

```text
article_understanding_mode
```

取值建议：

```text
auto
thesis_argument
causal_mechanism
cognitive_state
process_method
relationship_structure
contrast_conflict
narrative_event
metaphor_symbolic
```

用户文案建议：

| 值 | 中文名称 | 说明 |
| --- | --- | --- |
| auto | 自动判断 | 系统基于文章结构自动选择主理解方式 |
| thesis_argument | 观点论证 | 识别主张、证据、反驳、结论 |
| causal_mechanism | 因果机制 | 识别原因、触发条件、结果、反馈循环 |
| cognitive_state | 认知状态 | 识别困惑、循环、误区、顿悟、心理卡点 |
| process_method | 流程方法 | 识别步骤、顺序、动作、方法层级 |
| relationship_structure | 关系结构 | 识别角色、依赖、权力、冲突、网络关系 |
| contrast_conflict | 对比冲突 | 识别过去/现在、错误/正确、A/B 选择 |
| narrative_event | 叙事事件 | 识别人物、地点、事件、情绪推进 |
| metaphor_symbolic | 隐喻象征 | 识别抽象意象、象征关系、文学隐喻 |

### 4.2 视觉具象化方式

字段建议：

```text
visual_planning_mode
```

取值建议：

```text
auto
scene_integration
cognitive_illustration
structural_explainer
process_walkthrough
contrast_argument
relationship_map
host_explainer
signature_presence
```

用户文案建议：

| 值 | 中文名称 | 说明 |
| --- | --- | --- |
| auto | 自动选择 | 系统根据文章理解计划选择最合适的画面任务 |
| scene_integration | 场景还原 | 还原文章中的人物、地点、事件和情绪场景 |
| cognitive_illustration | 认知配图 | 把抽象困境、循环、误区、顿悟转成解释型画面 |
| structural_explainer | 结构图解 | 把系统、组件、层级、关系转成结构化画面 |
| process_walkthrough | 流程方法 | 把步骤、路径、方法、操作转成流程画面 |
| contrast_argument | 对比论证 | 把冲突、选择、前后变化转成对照画面 |
| relationship_map | 关系图谱 | 把人物、组织、要素之间的关系转成图谱画面 |
| host_explainer | 主持讲解 | 让角色以讲解者、导览者身份参与表达 |
| signature_presence | 视觉签名弱植入 | 保持系列识别，但不改变原画面主体 |

---

## 5. 前端位置

在当前“系列视觉识别”区域中，新字段应该放在：

```text
启用视觉签名
选择视觉签名素材库
选择视觉签名形象
视觉签名能力预览
内容理解方式
视觉具象化方式
高级策略
  - 表达模式
  - 结构方式
  - 参与方式
  - 融入模式
  - 角色一致性
```

原因：

```text
1. 视觉签名素材库和形象决定“谁参与”。
2. 内容理解方式决定“文章该如何被读懂”。
3. 视觉具象化方式决定“文章理解如何变成画面任务”。
4. 表达模式、结构方式、参与方式、融入模式、角色一致性只是高级细分控制。
```

不要把“认知配图”放进“表达模式”。它是一级视觉任务，不是低层表达子项。

---

## 6. 后端目标架构

### 6.1 新增顶层服务

建议新增：

```text
ArticleUnderstandingPlanner
VisualPlanningRouter
VisualConcretizationPlanner
```

目标链路：

```text
BaseVisualBriefPlanner
-> ArticleUnderstandingPlanner
-> FrameUnderstandingPlanner
-> VisualPlanningRouter
   -> SceneIntegrationPlanner
   -> CognitiveIllustrationPlanner
   -> StructuralExplainerPlanner
   -> ProcessWalkthroughPlanner
   -> ContrastArgumentPlanner
   -> RelationshipMapPlanner
   -> HostExplainerPlanner
   -> SignaturePresencePlanner
-> VisualRoleParticipationPlanner
-> PromptProjector
-> Critic / Repair
-> Artifact
```

### 6.2 为什么不能继续扩 VisualRoleScenePlanner

`VisualRoleScenePlanner` 的职责应该是：

```text
在已知画面任务下，规划固定视觉签名如何参与场景表达。
```

它不应该继续承担：

```text
1. 整篇文章阅读理解。
2. 选择认知、因果、论证、流程、关系等理解方式。
3. 决定全局视觉策略。
4. 负责所有具象化模式。
```

否则它会变成上帝类，后续每加一个模式都堆 prompt、堆 if、堆修补规则。

---

## 7. 核心数据契约

### 7.1 ArticleUnderstandingRequest

```python
@dataclass(frozen=True)
class ArticleUnderstandingRequest:
    enabled: bool = True
    article_understanding_mode: ArticleUnderstandingMode = ArticleUnderstandingMode.AUTO
    visual_planning_mode: VisualPlanningMode = VisualPlanningMode.AUTO
    user_intent_hint: str | None = None
    allow_mixed_lenses: bool = True
```

### 7.2 ArticleUnderstandingPlan

```python
@dataclass(frozen=True)
class ArticleUnderstandingPlan:
    article_id: str
    primary_lens: ArticleUnderstandingLens
    secondary_lenses: tuple[ArticleUnderstandingLens, ...]
    core_claim: str
    central_problem: str
    main_entities: tuple[str, ...]
    required_subjects: tuple[str, ...]
    causal_chain: tuple[str, ...]
    argument_structure: Mapping[str, Any]
    emotional_state: str
    cognitive_conflict: str
    metaphor_candidates: tuple[str, ...]
    unsuitable_visual_modes: tuple[VisualPlanningMode, ...]
    source_evidence: tuple[str, ...]
```

### 7.3 FrameUnderstandingPlan

```python
@dataclass(frozen=True)
class FrameUnderstandingPlan:
    frame_id: str
    source_text: str
    frame_claim: str
    frame_question: str
    primary_lens: ArticleUnderstandingLens
    secondary_lenses: tuple[ArticleUnderstandingLens, ...]
    required_subjects: tuple[str, ...]
    forbidden_subject_losses: tuple[str, ...]
    visible_text_policy: VisibleTextPolicy
```

### 7.4 VisualConcretizationPlan

```python
@dataclass(frozen=True)
class VisualConcretizationPlan:
    frame_id: str
    visual_planning_mode: VisualPlanningMode
    primary_visual_task: str
    visual_metaphor: str
    composition_structure: str
    scene_subjects: tuple[str, ...]
    information_structure: Mapping[str, Any]
    ip_role_intent: str
    ip_weight: VisualRoleWeight
    ip_cardinality: VisualRoleCardinality
    text_rendering_policy: VisibleTextPolicy
    negative_semantics: tuple[str, ...]
```

### 7.5 VisualRoleParticipationPlan

```python
@dataclass(frozen=True)
class VisualRoleParticipationPlan:
    frame_id: str
    identity_contract: VisualRoleIdentityContract
    role_mode: VisualRoleMode
    participation_mode: VisualRoleParticipationMode
    structure_mode: VisualRoleStructureMode
    action_responsibility: str
    subject_preservation_rule: str
    max_visual_weight: str
    cardinality_rule: str
```

---

## 8. 认知配图的正确语义

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
  "required_subjects": ["迷路的人", "重复路径"],
  "ip_role_intent": "固定视觉签名在关键观察点提示路径选择",
  "ip_weight": "supporting",
  "text_rendering_policy": "no_visible_text"
}
```

---

## 9. Prompt 投影规则

V4.3 最终 prompt 不应表现为：

```text
Fixed IP identity + scene + action + style + protection rules
```

而应由结构化计划投影成有优先级的语义块：

```text
1. Primary visual task
2. Article understanding anchor
3. Required original subjects
4. Visual concretization structure
5. Fixed visual identity contract
6. Visual role action responsibility
7. Subject preservation and IP weight rules
8. Composition and style contract
9. Text rendering policy
10. Safety / identity protection rules
```

Projector 的职责：

```text
1. 读取 ArticleUnderstandingPlan 和 VisualConcretizationPlan。
2. 保证 required_subjects 进入最终 prompt。
3. 保证 identity_contract 的 required_identity_traits 进入最终 prompt。
4. 保证 text_rendering_policy 不被 planner 文本绕过。
5. 保证 IP cardinality 和 visual weight 规则进入最终 prompt。
6. 记录 projected_prompt_parts，便于测试和 artifact 追踪。
```

---

## 10. Critic 与 Repair 升级

V4.3 Critic 不能只检查有没有 IP 或身份是否保留。

必须新增检查：

```text
1. article_lens_mismatch：画面任务与文章理解方式不匹配。
2. primary_claim_lost：核心主张丢失。
3. required_subject_lost：原文必须主体丢失。
4. ip_overdominance：IP 权重过高，替代了原主体。
5. ip_cardinality_violation：固定视觉签名数量失控。
6. visible_text_policy_violation：画面文字违反策略。
7. concretization_too_generic：具象化过于泛化，没有解释文章。
8. mode_prompt_leakage：最终 prompt 泄漏内部模式名或调试字段。
9. conflicting_visual_tasks：一帧混入过多任务，画面目标不清。
```

Repair 必须基于结构化 issue 修复 plan，不应只把 issue 文字追加到 prompt。

---

## 11. Artifact 要求

每次任务必须新增以下可追踪 artifact：

```text
prompt_traces/article_understanding/article_understanding_request.json
prompt_traces/article_understanding/article_understanding_plan.json
prompt_traces/article_understanding/frame_understanding_plan_{frame_id}.json
prompt_traces/visual_concretization/visual_concretization_plan_{frame_id}.json
prompt_traces/visual_concretization/visual_planning_router_decision_{frame_id}.json
prompt_traces/visual_role/visual_role_participation_plan_{frame_id}.json
prompt_traces/visual_role/visual_role_critique_{frame_id}.json
prompt_traces/final_visual_prompts.md
```

这些 artifact 是测试、review 和产品调试的事实源。

---

## 12. 实施阶段

### Phase 0：冻结边界

只做文档和评审，不动代码。

验收：

```text
1. V4.3 计划文档通过 review。
2. 确认不把认知配图塞进 visual_expression_mode。
3. 确认不在 VisualRoleScenePlanner 内继续堆所有模式。
4. 确认默认行为必须兼容 V4.2。
```

### Phase 1：新增模型契约

新增：

```text
pixelle_video/models/article_understanding.py
pixelle_video/models/visual_planning_mode.py
pixelle_video/models/visual_concretization.py
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
3. 默认 auto 不改变现有 V4.2 输出。
4. 所有新增字段有 to_dict / from_mapping / normalize 测试。
```

### Phase 2：新增文章理解 Planner

新增：

```text
ArticleUnderstandingPlanner
FrameUnderstandingPlanner
```

职责：

```text
1. 读取整篇文案和分镜上下文。
2. 输出 ArticleUnderstandingPlan。
3. 输出每帧 FrameUnderstandingPlan。
4. 支持 primary_lens + secondary_lenses。
5. 保留 source_evidence，避免模型凭空理解。
```

验收：

```text
1. 能识别观点论证、因果机制、认知状态、流程方法、关系结构、对比冲突、叙事事件、隐喻象征。
2. 能为每帧给出主任务。
3. 能标记 required_subjects 和 forbidden_subject_losses。
```

### Phase 3：新增视觉策略路由

新增：

```text
VisualPlanningRouter
CognitiveIllustrationPlanner
StructuralExplainerPlanner
ProcessWalkthroughPlanner
ContrastArgumentPlanner
RelationshipMapPlanner
SignaturePresencePlanner
```

保留并收敛：

```text
SceneIntegrationPlanner
HostExplainerPlanner
```

验收：

```text
1. 不同 visual_planning_mode 进入不同 planner。
2. auto 可以基于 ArticleUnderstandingPlan 自动选择 planner。
3. 每个 planner 输出同一类 VisualConcretizationPlan。
4. 不允许 planner 直接输出最终 prompt 作为唯一事实源。
```

### Phase 4：升级 Projector

目标：

```text
1. 从 VisualConcretizationPlan + VisualRoleParticipationPlan 投影最终 prompt。
2. 减少线性拼接感。
3. 输出 projected_prompt_parts。
4. 保护 required_subjects、identity_contract、text_rendering_policy。
```

验收：

```text
1. final prompt 中可追踪每个语义块来源。
2. 不泄漏内部枚举名、debug 字段、artifact 路径。
3. 不把 visible text 作为默认画面元素。
```

### Phase 5：升级 Critic / Repair

新增：

```text
ArticleUnderstandingCritic
VisualConcretizationCritic
VisualRoleParticipationCritic
```

验收：

```text
1. 能发现原文主体丢失。
2. 能发现 IP 过度抢戏。
3. 能发现认知配图没有解释核心认知点。
4. 能发现最终 prompt 与选择的文章理解方式冲突。
5. Repair 修改结构化 plan，不直接堆 prompt。
```

### Phase 6：前端接入

修改：

```text
web/components/ip_prompt_chain_controls.py
web/components/content_ip_world_controls.py
web/i18n/locales/zh_CN.json
web/i18n/locales/en_US.json
```

UI：

```text
视觉签名能力预览
内容理解方式
视觉具象化方式
高级策略
```

验收：

```text
1. 新字段位置符合信息架构。
2. 默认 auto 不增加用户负担。
3. 高级策略仍可覆盖低层控制。
4. 认知配图不叫“小黑模式”，但帮助文案可说明其参考的是正文认知配图方法。
```

### Phase 7：端到端输出与回归

验收：

```text
1. prompt_traces 中出现 article_understanding 和 visual_concretization artifact。
2. 同一篇文章可以被不同理解方式生成不同计划。
3. 认知配图输出不再只靠 prompt 拼接。
4. V4.2 默认路径保持兼容。
5. 针对 V4.3 的测试集全部通过。
```

---

## 13. 测试计划

### 13.1 模型契约测试

新增测试：

```text
tests/models/test_article_understanding.py
tests/models/test_visual_planning_mode.py
tests/models/test_visual_concretization.py
```

覆盖：

```text
1. enum normalize。
2. invalid value fallback auto。
3. to_dict / from_mapping。
4. primary_lens + secondary_lenses。
5. visible_text_policy。
```

### 13.2 API / 前端透传测试

新增或扩展：

```text
tests/test_video_api.py
tests/test_ip_generation_request_contract.py
tests/test_content_ip_world_controls.py
tests/test_output_preview.py
tests/test_style_config_ip_controls.py
```

覆盖：

```text
1. article_understanding_mode 端到端透传。
2. visual_planning_mode 端到端透传。
3. 默认 auto 不破坏旧请求。
4. 前端控件位置和 session_state key 稳定。
```

### 13.3 Planner 测试

新增：

```text
tests/services/test_article_understanding_planner.py
tests/services/test_visual_planning_router.py
tests/services/test_cognitive_illustration_planner.py
tests/services/test_visual_concretization_planners.py
```

覆盖：

```text
1. 认知状态文章进入 cognitive_illustration。
2. 因果解释文章进入 structural_explainer 或 process_walkthrough。
3. 对比文章进入 contrast_argument。
4. 关系文章进入 relationship_map。
5. auto 能生成 primary_lens + secondary_lenses。
```

### 13.4 Projector 测试

扩展：

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
```

### 13.5 Critic / Repair 测试

新增：

```text
tests/services/test_article_understanding_critic.py
tests/services/test_visual_concretization_critic.py
tests/services/test_visual_role_participation_critic.py
```

覆盖：

```text
1. 原主体丢失。
2. IP 过度主导。
3. 多个固定 IP 实例失控。
4. 画面文字违反策略。
5. 认知配图没有认知动作。
6. Repair 不直接追加 issue 文本到 prompt。
```

### 13.6 回归测试

必须建立至少四类 fixture：

```text
1. 认知困境型文章。
2. 因果机制型文章。
3. 流程方法型文章。
4. 对比论证型文章。
```

每类 fixture 至少验证：

```text
1. ArticleUnderstandingPlan 正确。
2. VisualConcretizationPlan 正确。
3. IP 身份契约保留。
4. 原文主体保留。
5. 最终 prompt 不退化成单纯拼接。
```

---

## 14. 验收标准

V4.3 完成后必须满足：

```text
1. 用户选择“认知配图”时，系统进入 cognitive_illustration planner，而不是只改 prompt 文案。
2. 用户选择不同文章理解方式时，系统生成不同 ArticleUnderstandingPlan。
3. 同一篇文章可以主理解 + 辅理解混合，但每帧必须有唯一 primary_visual_task。
4. 最终 prompt 可从 projected_prompt_parts 追踪来源。
5. required_subjects、identity_contract、visible_text_policy、ip_weight、ip_cardinality 均可测试。
6. V4.2 默认路径不被破坏。
7. 新增 targeted V4.3 测试全部通过。
```

---

## 15. 明确不做

V4.3 不做：

```text
1. 不把“小黑模式”作为正式产品名称。
2. 不把认知配图硬塞进 visual_expression_mode。
3. 不用一个 VisualRoleScenePlanner 承担所有文章理解和视觉策略。
4. 不把用户选择直接拼进 prompt。
5. 不把所有内部 lens 暴露给普通用户。
6. 不用负面 prompt 代替结构化 text policy。
7. 不为单个 IP 写特判。
```

---

## 16. 风险与控制

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 模式过多导致用户困惑 | 前端复杂度上升 | 前端只暴露理解方式和具象化方式，默认 auto |
| planner 数量变多 | 维护成本上升 | 所有 planner 输出统一 VisualConcretizationPlan |
| LLM 误判文章理解 | 画面偏题 | source_evidence + critic + repair |
| 认知配图被滥用 | 所有画面都变抽象 | auto 模式必须允许回退 scene_integration |
| IP 抢戏 | 原文表达被替代 | ip_weight、required_subjects、critic 强校验 |
| prompt 继续拼接 | 技术债延续 | Projector 使用结构化语义块和 projected_prompt_parts |

---

## 17. 建议落地顺序

建议按以下原子顺序提交：

```text
1. docs: define V4.3 article understanding and visual planning route
2. test: cover article understanding and visual planning contracts
3. feat: add article understanding and visual planning request models
4. feat: plumb article understanding controls through API and UI
5. feat: add article understanding planner and artifacts
6. feat: add visual planning router and cognitive illustration planner
7. feat: project visual concretization plans into final prompts
8. test: cover V4.3 critic, repair, and regression fixtures
```

每一步都必须可回滚、可测试、可解释。

---

## 18. 最终判断

V4.3 的价值不是新增一个“认知配图按钮”，而是补上 Pixelle 当前最缺的一层：

```text
文章理解层。
```

有了这一层，认知配图、结构图解、流程方法、对比论证、关系图谱、主持讲解、场景还原才能成为并列的视觉策略。

没有这一层，所有模式最终都会退化成 prompt 拼接。
