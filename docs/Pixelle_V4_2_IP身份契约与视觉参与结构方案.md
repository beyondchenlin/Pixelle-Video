# Pixelle-Video V4.2 IP 身份契约与视觉参与结构方案

> 版本：V4.2  
> 文档状态：Review 修订版 / 需求对齐 / 架构方案 / 代码实施前置说明  
> 基准：V4.1 视觉角色表达系统已经接通主链路  
> 目标：从“让 IP 出现”升级为“稳定加载 IP 身份契约，并让 IP 按当前内容结构参与画面表达”。  
> 原则：最佳实践、源头治理、禁止最小改动、禁止留下技术债。
> 修订重点：身份契约必须成为结构化硬对象，Projector 必须负责最终拼接与硬校验，不能只依赖 Planner 的自由文本。

---

## 0. 为什么需要 V4.2

V4.1 已经解决了一部分关键问题：

```text
用户启用视觉角色
↓
系统不再把 IP 当作角标 / 水印 / 贴纸
↓
系统开始让 IP 参与画面表达
↓
最终 prompt 可以输出 visual_role_request / profile / plan / critique / artifact
```

但 V4.1 仍然暴露出一个更底层的问题：

```text
IP 的身份识别核没有被明确建模成“不可变契约”。
```

这会导致一种典型失败：

```text
某一帧中 IP 出现了，
但 IP 的关键识别特征丢了。
```

例如用户选择“正定向导兔”，它可以是卡通风、水墨风、像素风、皮克斯风、写实玩具风，也可以站在前景、背景、相框里、书页上、桌面上、画面边缘，甚至作为主角或配角出现。

但只要这个 IP 的设计里规定：

```text
它是兔子。
它有蓝色领结。
```

那么这两个识别点就不能丢。它们不是普通修饰词，而是 IP 身份契约。

V4.2 要解决的是：

```text
不是为“蓝色领结”写特判。
而是建立一套通用的 IP Identity Contract。
```

V4.2 的实施目标不是“多拼几个关键词”，而是把 IP 身份从 prompt 文本中提升为主链路契约：

```text
IPProfile 设计源头
↓
VisualRoleIdentityContract 运行时身份契约
↓
VisualRoleScenePlanner 只规划表达和参与
↓
VisualRolePromptProjector 确定性拼接最终 prompt
↓
VisualRolePromptCritic / Projector final validation 硬校验
↓
Artifact 可追踪每帧身份、结构、参与和检查结果
```

---

## 1. 对参考项目“小黑怪诞正文配图”的重新理解

参考项目 `ian-xiaohei-illustrations` 的价值不在于“把小黑放进图里”，而在于它把文章里的判断、流程、状态和隐喻转成一张有认知动作的解释图。

它的核心流程可以抽象为：

```text
读取内容
↓
提炼认知锚点
↓
选择结构类型
↓
重新发明视觉隐喻
↓
让固定 IP 承担核心动作
↓
用 QA 检查：不是 PPT，不是装饰，不是复刻旧图
```

其中小黑只是固定 IP。真正值得 Pixelle 吸收的是方法论：

```text
1. 先找内容里的认知锚点。
2. 一张图只表达一个核心结构。
3. 固定 IP 必须承担核心动作，不能只是装饰。
4. 构图要根据结构类型生成，而不是平均配图。
5. QA 不是只检查有没有 IP，而是检查 IP 是否参与表达。
```

Pixelle 不能照搬的是：

```text
1. 所有图都白底手绘。
2. 所有图都用小黑。
3. 所有场景都变成认知隐喻。
4. 所有任务都按正文配图处理。
```

Pixelle 是短视频生成系统，需要支持多模板、多风格、多比例、多 IP、多画面任务。因此 V4.2 必须把参考项目的方法论抽象为通用能力。

---

## 2. V4.2 的核心判断

V4.2 的核心不是：

```text
每帧强制补几个固定词。
```

而是：

```text
每个 IP 必须先被解析成一个身份契约。
每一帧必须先加载身份契约，再规划场景表达。
```

这意味着系统要区分两类稳定性：

```text
身份稳定性：
只要选中某个 IP，它的必需识别特征必须稳定保留。

角色连续性：
跨帧时，这个 IP 是否保持主角、辅助角色、固定位置、固定戏份或剧情连贯。
```

身份稳定性是底层硬约束。  
角色连续性是前端可选策略。

所以：

```text
visual_consistency_mode = off
不代表 IP 身份可以漂移。

它只代表：
不强制跨帧位置、戏份、动作连续。
```

### 2.1 V4.2 的核心逻辑红线

V4.2 实施时必须遵守以下红线：

```text
1. 身份契约不是 Planner prompt guidance，而是运行时硬对象。
2. required_identity_traits 必须逐项满足，不能只命中任意 identity token。
3. Planner 不能独占最终 prompt 的生成权。
4. Projector 必须确定性拼接 fixed_identity_clause、参与表达、风格约束和身份保护规则。
5. Critic 必须检查 projected final prompt，而不是只检查 Planner 的 integrated_scene_prompt。
6. visual_consistency_mode 只影响跨帧角色连续性，不影响身份契约加载。
7. visual_structure_mode 和 visual_participation_mode 必须端到端传递，不能只停留在前端控件或文档字段。
8. positive-only 工作流也必须收到 forbidden_identity_loss_rules，此时保护规则进入正向 prompt。
```

这一组红线的目的，是防止 V4.2 被实现成 V4.1 的局部补丁：

```text
错误实现：
在最终 prompt 末尾追加 identity_lock 文本。

正确实现：
身份契约参与 Planner 输入、Projector 拼接、Critic 校验和 Artifact 记录。
```

---

## 3. 前端开关的正确语义

### 3.1 启用视觉角色

字段：

```text
ip_enabled
```

语义：

```text
关：不加载 IP，不走视觉角色链路。
开：必须加载选中的 IP，并让它参与画面表达。
```

默认值：

```text
false
```

启用后硬规则：

```text
IP 的身份契约必须被加载。
最终 prompt 不允许丢失 required_identity_traits。
```

---

### 3.2 视觉角色模式

字段：

```text
visual_role_mode
```

取值：

```text
auto
subject_replacement
supporting_integration
```

语义：

```text
auto：
系统根据画面任务决定主角代替或辅助融入。

subject_replacement：
IP 成为画面主角或核心主体。

supporting_integration：
保留原主体，IP 作为讲解、陪伴、导览、操作、指示、见证、摆件、投影等方式参与表达。
```

默认值：

```text
auto
```

它控制的是：

```text
IP 在画面里的职责和戏份。
```

它不控制：

```text
IP 的固定身份特征是否保留。
```

---

### 3.3 角色一致性

字段：

```text
visual_consistency_mode
```

取值：

```text
off
supporting_character
primary_character
```

语义：

```text
off：
身份契约仍然固定，但不强调跨帧固定站位、固定动作、固定戏份。

supporting_character：
IP 作为固定辅助角色跨帧出现，身份、职责和存在感更稳定。

primary_character：
IP 作为固定主角跨帧出现，并强制等价于 subject_replacement。
```

默认值：

```text
off
```

必须在前端说明：

```text
角色一致性控制跨帧角色定位，不控制 IP 身份核。
启用视觉角色后，IP 的必需识别特征始终保持。
```

---

### 3.4 表达类型

字段：

```text
visual_expression_mode
```

取值：

```text
auto
narrative_scene
explanatory_diagram
cognitive_metaphor
infographic_layout
comparison_or_debate_scene
product_or_object_scene
portrait_or_host_scene
environment_branding
```

语义：

```text
这一帧属于哪类画面表达任务。
```

默认值：

```text
auto
```

它不是 IP 模式，而是画面任务模式。

---

### 3.5 V4.2 新增：视觉结构类型

建议新增字段：

```text
visual_structure_mode
```

参考“小黑”项目的结构类型，但做通用化。建议取值：

```text
auto
workflow
system_part
before_after
role_state
concept_metaphor
method_layers
map_route
comic_sequence
plain_scene
product_demo
host_explainer
```

语义：

```text
这一帧用什么结构组织画面。
```

它和 `visual_expression_mode` 的区别：

```text
visual_expression_mode：
这张图是什么表达任务。

visual_structure_mode：
这张图用什么结构来表达这个任务。
```

例如：

```text
visual_expression_mode = explanatory_diagram
visual_structure_mode = workflow

表示：
这是解释图解，用流程结构表达。
```

---

### 3.6 V4.2 新增：视觉参与方式

建议新增字段：

```text
visual_participation_mode
```

取值：

```text
auto
companion_witness
guide_explainer
operator_demonstrator
pointer_annotator
metaphor_symbol
structure_carrier
environment_branding
```

语义：

```text
IP 以什么方式参与当前画面表达。
```

它和 `visual_role_mode` 的区别：

```text
visual_role_mode：
主角还是辅助。

visual_participation_mode：
具体如何参与。
```

示例：

```text
visual_role_mode = supporting_integration
visual_participation_mode = guide_explainer

表示：
保留原主体，IP 作为导览 / 讲解角色参与。
```

---

### 3.7 字段端到端落地要求

V4.2 的字段不能只作为 UI 字段存在，必须完整进入以下边界：

```text
Web 控件
↓
API schema / request contract
↓
Video generation params normalization
↓
VisualRoleRequest
↓
VisualPromptPlanningService
↓
Planner / Projector / Critic
↓
planning_snapshot
↓
visual_role_artifacts
```

必须端到端支持：

```text
visual_expression_mode
visual_structure_mode
visual_participation_mode
visual_role_mode
visual_consistency_mode
```

禁止出现以下实现：

```text
1. 前端有控件，API schema 不接收。
2. API 接收了字段，但 VisualRoleRequest 丢弃。
3. Planner 能看到字段，但 artifact 不记录。
4. 字段只进入 metadata，不参与实际 planning / projection / critique。
```

---

## 4. IP 身份契约模型

V4.2 新增核心模型：

```text
VisualRoleIdentityContract
```

它不是提示词片段，而是运行时身份契约。

建议结构：

```python
@dataclass(frozen=True)
class VisualRoleIdentityContract:
    canonical_identity_name: str

    required_identity_traits: tuple[str, ...]
    important_identity_traits: tuple[str, ...]
    optional_appearance_traits: tuple[str, ...]

    fixed_identity_clause: str
    style_adaptation_rules: tuple[str, ...]
    forbidden_identity_loss_rules: tuple[str, ...]

    reference_assets: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

字段语义：

| 字段 | 含义 |
|---|---|
| canonical_identity_name | IP 的正式身份名 |
| required_identity_traits | 必须每帧保留的识别特征 |
| important_identity_traits | 重要但可按风格变化表达的识别特征 |
| optional_appearance_traits | 可选外观描述 |
| fixed_identity_clause | 每帧最终 prompt 必须携带的固定身份短语 |
| style_adaptation_rules | 跨风格保持身份的规则 |
| forbidden_identity_loss_rules | 不能丢失、替换、误变形的规则 |
| reference_assets | 后续可接参考图、IP-Adapter、LoRA |

### 4.1 身份契约的模型约束

`VisualRoleIdentityContract` 必须满足：

```text
1. canonical_identity_name 不能为空。
2. required_identity_traits 不能为空。
3. fixed_identity_clause 必须由 canonical_identity_name + required_identity_traits 构造。
4. fixed_identity_clause 不能只写 IP 名称，必须显式包含每个 required trait。
5. forbidden_identity_loss_rules 必须合并 default forbidden role forms、negative_constraints、identity_suppression_rules。
6. metadata 必须记录 source_ip_profile_id、builder_version、required_trait_sources。
7. to_dict / from_dict 必须稳定，artifact 和测试不能依赖 dataclass repr。
```

身份契约的判断单位是：

```text
required_identity_traits 中每一个元素都必须进入最终 prompt。
```

不能使用：

```text
prompt 命中 identity_kernel 任意一个 token 就算通过。
```

因为这会放过：

```text
prompt 出现“正定向导兔”
但没有“兔子”
也没有“蓝色领结”
```

---

## 5. IPProfile 到身份契约的映射规则

现有 `IPProfile` 已经有很多字段，但语义需要重新分层。

### 5.1 映射表

| IPProfile 字段 | V4.2 目标字段 | 说明 |
|---|---|---|
| name | canonical_identity_name | IP 正式名 |
| identity_lock | required_identity_traits | 最高优先级，必须保留 |
| minimal_traits | required_identity_traits | 最小可识别集合，也必须保留 |
| identity_anchors | important_identity_traits 或 required_identity_traits | 如果用户标记为必须，则进入 required |
| visual_summary | optional_appearance_traits | 自然描述，不全部强制 |
| style_hint | style_adaptation_rules | 风格倾向，不是身份硬核 |
| world_hint | style_adaptation_rules | 世界观 / 场景倾向 |
| negative_constraints | forbidden_identity_loss_rules | 禁止丢失和误变形 |
| identity_suppression_rules | forbidden_identity_loss_rules | 身份不能被压制或隐藏 |
| role_presets | role_affordances | 可扮演职责 |
| adaptable_slots | supporting_role_affordances | 可辅助融入方式 |
| presence_spectrum | role prominence policy | 存在感策略 |
| visible_text_whitelist | image text policy | 图中文字白名单 |
| metadata.reference_assets | reference_assets | 参考图或资产 |

---

### 5.2 必需身份特征的提取优先级

```text
第一优先级：identity_lock
第二优先级：minimal_traits
第三优先级：metadata.required_identity_traits
第四优先级：明确标记为 required 的 identity_anchors
第五优先级：从 name / visual_summary 中抽取最低必要身份类别
```

不能把所有字段都塞进 required。否则会导致每帧 prompt 过长、过死板、无法适配风格。

### 5.2.1 required trait 的合并规则

V4.2 required trait 的来源规则如下：

```text
required_identity_traits =
identity_lock
+ minimal_traits
+ metadata.required_identity_traits
+ metadata.identity_anchors_required
+ 明确标记 required 的 identity_anchors
+ 必要时从 name / visual_summary 抽取的最低身份类别
```

合并时必须做语义去重：

```text
蓝色领结
蓝色领结一角
```

可以同时存在，但 artifact 需要记录来源：

```text
蓝色领结：identity_lock
蓝色领结一角：minimal_traits
```

如果 prompt 只允许局部出场，Planner 可以让 IP 以局部方式出现，但 Projector 仍必须让最终 prompt 明确包含 required trait 的可见表达。

### 5.2.2 generation readiness 规则

启用视觉角色时，ready 条件不能只看 `identity_lock` 或 `identity_anchors`。

V4.2 ready 条件：

```text
至少存在一个可构造 required_identity_traits 的来源：
identity_lock
minimal_traits
metadata.required_identity_traits
明确 required 的 identity_anchors
```

如果只有 `visual_summary` 能推断身份类别，也可以用于兜底，但 artifact 必须标记：

```text
required_trait_source = inferred_from_visual_summary
confidence = fallback
```

这种兜底只适合旧数据兼容，不作为新 IP 设计推荐路径。

---

### 5.3 正定向导兔示例

资产设计：

```text
name:
正定向导兔

identity_lock:
兔子
蓝色领结

minimal_traits:
兔子
蓝色领结

identity_anchors:
长耳朵
圆润脸型
亲和向导感

visual_summary:
一个亲和的兔子向导形象，带蓝色领结，适合在知识场景里做陪伴、指引和讲解。

role_presets:
指路
讲解
陪伴
观察
提示重点
```

运行时身份契约：

```text
canonical_identity_name:
正定向导兔

required_identity_traits:
兔子
蓝色领结

important_identity_traits:
长耳朵
圆润脸型
亲和向导感

optional_appearance_traits:
白色
卡通感
温和表情
向导气质

fixed_identity_clause:
正定向导兔：一个兔子形象，必须佩戴清晰可见的蓝色领结。

forbidden_identity_loss_rules:
不能变成非兔类
不能丢失蓝色领结
不能作为角标、水印、贴纸或无意义装饰
```

这才是通用逻辑。  
不是系统写死“蓝色领结”，而是这个 IP 的身份契约规定了“蓝色领结”。

---

## 6. 提示词链路分层

V4.2 最终 prompt 不应是单层字符串，而应先形成结构化中间对象。

建议：

```text
identity_contract_clause
+
content_structure_clause
+
participation_clause
+
style_clause
+
negative_guard_clause
```

### 6.1 identity_contract_clause

来自 `VisualRoleIdentityContract.fixed_identity_clause`。

例如：

```text
固定 IP 身份：正定向导兔，一个兔子形象，必须佩戴清晰可见的蓝色领结。
```

这一段必须进入每帧最终 prompt。

### 6.2 content_structure_clause

来自内容理解：

```text
这一帧表达什么认知锚点、视觉结构或叙事目标。
```

例如：

```text
表现“人在孤独中恢复力量”的前后状态变化。
```

### 6.3 participation_clause

来自角色参与规划：

```text
IP 在当前结构里做什么。
```

例如：

```text
正定向导兔站在人物身边，作为陪伴见证者，与人物一起望向远方。
```

### 6.4 style_clause

来自模板 / 用户风格 / 工作流：

```text
像素风
水墨风
写实玩具风
卡通插画
```

但 style 不允许覆盖身份契约：

```text
像素风的正定向导兔仍然必须是兔子，并佩戴蓝色领结。
```

### 6.5 negative_guard_clause

来自 forbidden rules：

```text
不要变成非兔类。
不要丢失蓝色领结。
不要作为水印、角标、贴纸或无意义装饰。
```

注意：

```text
negative_guard_clause 不是传统 negative_prompt 的同义词。
```

对于支持 negative prompt 的工作流，可以同时写入 negative prompt。

对于 Z-Image 等 positive-only 工作流，`forbidden_identity_loss_rules` 必须进入正向最终 prompt，例如：

```text
身份保护：保持兔子物种与蓝色领结清晰可见；不要将该角色表现为角标、水印、贴纸或无意义装饰。
```

禁止因为 provider 不支持 negative prompt 就丢弃身份保护规则。

---

## 7. Planner 的职责边界

V4.2 要求 Planner 只规划表达，不重写身份。

Planner 可以决定：

```text
IP 是主角还是配角。
IP 在前景还是背景。
IP 是实体角色、相框图像、书页插图、摆件还是投影。
IP 做什么动作。
IP 如何适配当前画风。
```

Planner 不允许决定：

```text
删除 required_identity_traits。
把 required_identity_traits 改成可选。
让 IP 变成另一个物种或另一个角色。
把固定身份变成水印、角标、贴纸。
```

也就是说：

```text
身份契约由 IP 设计层提供。
表达规划由 Planner 生成。
最终 prompt 由 Projector 组合。
```

不能让 Planner 独占整个最终 prompt 的自由解释权。

Planner 的输出必须拆成可审计字段：

```text
structure_mode
structure_reason
participation_mode
participation_action
participation_location
content_structure_clause
integrated_scene_prompt
```

其中 `integrated_scene_prompt` 是场景表达草案，不是最终 prompt。

如果 LLM Planner 返回的内容删除、弱化或替换 required trait，不能由 Planner 自行修正通过，必须进入 repair / critic / projector validation。

---

## 8. Critic 的职责边界

V4.2 Critic 必须从“有没有 IP”升级成“身份契约是否被满足”。

必须检查：

```text
fixed_identity_clause_missing
required_identity_trait_missing
identity_contract_weakened
identity_replaced_by_style
role_decorative_only
participation_missing
structure_mode_mismatch
style_overrode_identity
```

Critic 的规则层必须执行：

```text
for trait in identity_contract.required_identity_traits:
    trait 必须在 projected final prompt 中可见
```

这和 V4.1 的 `identity_kernel_missing` 不同。

V4.1 可以接受：

```text
identity_kernel 中任意 token 命中
```

V4.2 必须接受：

```text
required_identity_traits 全部命中，或命中经规则认可的等价表达。
```

如果采用等价表达，Critic artifact 必须记录：

```text
required_trait: 蓝色领结
matched_expression: 清晰可见的蓝色蝴蝶结领饰
match_source: rule_alias 或 llm_critic
```

示例：

```text
prompt 出现“正定向导兔”，但没有“蓝色领结”
=> required_identity_trait_missing

prompt 写了“一个白色兔子”
但 required_identity_traits 包含“蓝色领结”
=> required_identity_trait_missing

prompt 写了“蓝色领结图案在角落”
=> role_decorative_only 或 forbidden_visual_form

prompt 写了“像素兔子”
但没有保留身份契约
=> style_overrode_identity
```

---

## 9. Projector 的职责边界

V4.2 Projector 不能只透传 Planner 的 `integrated_scene_prompt`。

它必须执行：

```text
1. 拼接 fixed_identity_clause。
2. 拼接场景表达。
3. 拼接参与方式。
4. 拼接风格约束。
5. 拼接禁止丢失规则。
6. 再做最终校验。
```

如果最终 prompt 丢失 required_identity_traits：

```text
raise VisualRolePromptProjectionError
```

而不是静默生成。

Projector 是 V4.2 的最终责任边界。它必须接收：

```text
base_visual_brief
identity_contract
structure_decision
participation_decision
visual_role_plan
visual_role_critique
style / workflow capabilities
```

并输出结构化中间对象：

```text
VisualRoleProjectedPromptParts:
  identity_contract_clause
  content_structure_clause
  participation_clause
  style_clause
  negative_guard_clause
  final_prompt
  final_validation
```

最终 media prompt 只能来自 `final_prompt`，不能直接透传 Planner 的 `integrated_scene_prompt`。

---

## 10. Artifact 要补充身份契约

V4.2 每个任务必须额外输出：

```text
visual_role_identity_contract.json
visual_role_structure_decision_frame_001.json
visual_role_participation_decision_frame_001.json
```

每帧 artifact 至少能回答：

```text
这个 IP 的必需识别特征是什么？
这些特征是否进入最终 prompt？
当前帧是什么结构类型？
IP 是如何参与结构表达的？
如果某个识别特征缺失，critic 为什么没有放过？
```

V4.2 artifact 需要同时保留 Projector 最终检查结果：

```text
visual_role_projected_prompt_frame_001.json
```

字段至少包含：

```text
identity_contract_clause
content_structure_clause
participation_clause
style_clause
negative_guard_clause
final_prompt
required_trait_checks
projector_validation_passed
critic_validation_passed
```

---

## 11. 前端产品建议

### 11.1 当前必须保留的基础控件

```text
启用视觉角色
选择素材库
选择视觉角色形象
视觉角色模式
角色一致性
表达类型
```

### 11.2 文案必须调整

角色一致性旁边加说明：

```text
控制跨帧角色定位，不控制 IP 身份。启用视觉角色后，IP 的必需识别特征始终保持。
```

### 11.3 高级设置建议

新增折叠区：

```text
高级视觉表达
```

包含：

```text
结构类型
参与方式
```

默认都是：

```text
自动
```

不要默认暴露太多复杂选项。  
普通用户只需要启用 IP。  
高级用户才需要选择结构类型和参与方式。

---

## 12. 实施阶段

### Phase 0：冻结 V4.1 局部补丁

不要继续执行只针对蓝色领结的临时补丁。  
如果已经执行，需要评估是否改名升级为 V4.2 identity contract。

同时确认当前 dev 的 V4.1 主链路作为基线：

```text
VisualRoleRequest
VisualRoleProfile
VisualRoleScenePlanner
VisualRolePromptCritic
VisualRolePromptProjector
visual_role_artifacts
```

V4.2 只能沿这条主链路升级，不能另起一条平行链路。

运行时版本口径：

```text
VisualRoleRequest.pipeline_version = "v4_2_identity_contract"
```

历史 `v4_expression` 只作为迁移兼容版本保留，允许继续进入同一条 V4 主链路；新请求和新 artifact 不应继续产出 V4.1 命名。

### Phase 1：新增身份契约模型，不改变生成行为

新增：

```text
VisualRoleIdentityContract
VisualRoleIdentityContractBuilder
VisualRoleStructureMode
VisualRoleParticipationMode
```

修改：

```text
VisualRoleProfile
VisualRoleProfileBuilder
```

要求：

```text
1. VisualRoleProfile 增加 identity_contract。
2. VisualRoleProfileBuilder 从 IPProfile 构造 identity_contract。
3. generation readiness 接入 required_identity_traits 来源。
4. planning_snapshot 增加 visual_role_identity_contract。
5. 本阶段不改变最终 prompt。
```

### Phase 2：字段端到端透传

新增或修改：

```text
Web 控件
API schema
video generation contract
VisualRoleControlsContract
VisualRoleRequest
VisualPromptPlanningService
planning_snapshot
```

必须支持：

```text
visual_expression_mode
visual_structure_mode
visual_participation_mode
```

验收：

```text
字段从 UI / API 请求进入 Planner 输入和 artifact，不丢失、不只留 metadata。
```

### Phase 3：接入身份契约到 Planner

修改：

```text
VisualRoleScenePlanner
VisualRoleIntegratedPromptPlan
```

要求：

```text
Planner 输入必须包含 identity_contract。
Planner 输出不能删除 required traits。
Planner 输出 structure_decision 和 participation_decision。
integrated_scene_prompt 只是场景表达草案，不是最终 prompt。
```

### Phase 4：接入 Projector

修改：

```text
VisualRolePromptProjector
```

要求：

```text
最终 prompt 必须显式包含 fixed_identity_clause。
最终 prompt 必须包含 required_identity_traits。
positive-only workflow 必须把 forbidden_identity_loss_rules 写入正向 prompt。
Projector final validation 失败时 raise VisualRolePromptProjectionError。
```

### Phase 5：接入 Critic

修改：

```text
VisualRolePromptCritic
```

新增 blocking issue：

```text
fixed_identity_clause_missing
required_identity_trait_missing
identity_contract_weakened
identity_replaced_by_style
role_decorative_only
participation_missing
structure_mode_mismatch
style_overrode_identity
```

Critic 必须检查 projected final prompt，而不是只检查 Planner 草案。

### Phase 6：Artifact

输出：

```text
visual_role_identity_contract.json
visual_role_structure_decision_frame_xxx.json
visual_role_participation_decision_frame_xxx.json
visual_role_projected_prompt_frame_xxx.json
```

### Phase 7：前端文案和高级设置

新增或调整：

```text
角色一致性说明
结构类型
参与方式
```

前端文案必须明确：

```text
角色一致性控制跨帧角色定位，不控制 IP 身份。
启用视觉角色后，IP 必需识别特征始终保持。
```

---

## 13. 验收标准

V4.2 完成后必须满足：

```text
1. 用户选择正定向导兔时，每帧最终 prompt 必须保留“兔子”和“蓝色领结”。
2. 用户选择另一个没有蓝色领结的 IP 时，系统不能强行加蓝色领结。
3. 风格切换为像素、水墨、写实玩具时，required identity traits 仍然保留。
4. visual_consistency_mode = off 时，身份核仍然保留。
5. supporting_integration 时，IP 不能只是站旁边或装饰，必须承担参与职责。
6. subject_replacement 时，IP 必须成为核心主体。
7. cognitive_metaphor 只是表达类型之一，不是总逻辑。
8. visual_structure_mode 能支持 workflow、system_part、before_after、role_state、concept_metaphor 等结构。
9. 最终 prompt 缺失 required trait 时，critic 必须 blocking。
10. projector 不允许静默回退。
11. artifact 能显示 identity contract 和每帧检查结果。
12. visual_expression_mode / visual_structure_mode / visual_participation_mode 能从 UI/API 进入 planning_snapshot 和 artifact。
13. minimal_traits 能参与 required_identity_traits 构造，不再被 readiness 忽略。
14. positive-only workflow 不会丢弃 forbidden_identity_loss_rules。
15. Projector final validation 失败时抛错，而不是继续生成。
```

---

## 14. 测试要求

新增测试：

```text
test_identity_contract_required_traits_from_ip_profile
test_identity_contract_does_not_force_blue_bowtie_for_other_ip
test_fixed_identity_clause_enters_final_prompt
test_required_identity_trait_missing_blocks_critic
test_style_adaptation_cannot_remove_identity_traits
test_consistency_off_still_preserves_identity_contract
test_structure_mode_auto_detects_workflow
test_participation_mode_operator_demonstrator_requires_action
test_xiaohei_methodology_not_hardcoded_to_whiteboard_style
test_visual_role_v42_fields_pass_through_api_and_web_contracts
test_projector_final_validation_rejects_missing_required_trait
test_positive_only_workflow_keeps_identity_guard_in_positive_prompt
test_minimal_traits_can_build_required_identity_contract
test_projected_prompt_artifact_records_required_trait_checks
```

---

## 15. 最终结论

V4.2 的目标不是把 V4.1 改成“小黑系统”，也不是给“正定向导兔”写蓝色领结特判。

V4.2 的目标是：

```text
从 IP 设计源头建立身份契约，
让任何 IP 都能在不同风格、动作、位置、结构中保持可识别，
并且让 IP 参与画面表达，而不是成为装饰。
```

一句话：

```text
IP 身份由契约固定。
画面表达由结构和参与方式动态生成。
风格可以变化，身份核不能漂移。
```
