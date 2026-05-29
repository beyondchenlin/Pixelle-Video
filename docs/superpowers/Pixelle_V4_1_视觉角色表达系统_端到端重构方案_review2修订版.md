# Pixelle-Video V4.1 视觉角色表达系统：端到端生成链路重构方案

> 版本：V4.1  
> 文档状态：Review2 修订版 / 可实施方案  
> 基准分支：`dev`  
> 基准文件 SHA：`dfde26a9b3b4cf918ceaac59f0aa5a3315f80bb9`  
> 目标：从源头重构「用户输入文本 / 完整文案 → 分镜 → 图片提示词 → 图片生成」链路，让视觉 IP 不再是后置锚点、角标、贴纸或兜底元素，而是作为“视觉角色”参与画面表达。  
> 原则：最佳实践、源头治理、禁止最小改动式修补、禁止留下技术债。

---

## Review2 修订说明

本修订版在原 V4.1 方案基础上补齐了 6 类关键内容：

```text
1. 增加当前 dev 分支真实代码状态审计。
2. 增加 P0 运行风险：ProviderPromptProjector.project() 参数不匹配。
3. 明确 visual_expression_mode 的端到端字段链路。
4. 将 Phase 0 从“清理半应用状态”升级为“半 V4 代码迁移与边界收敛”。
5. 明确 V4 projector fail-closed 语义，禁止静默回 base prompt。
6. 将测试要求改成可执行 pytest 断言清单。
```

本文件仍是设计与实施文档，不直接修改代码。  
代码落地时必须先修复 P0，再开始 V4.1 主体迁移。

---

## 0. 执行摘要

当前 Pixelle-Video 的视觉 IP 改造，在 V3 系列中经历了：

```text
IP 角色出场
↓
视觉锚点
↓
视觉签名
↓
场景绑定
↓
fail-closed / suppressed / fallback
```

这些改造解决了一部分“角标化”和“贴纸化”问题，但也引入了新的根本矛盾：

```text
系统把视觉 IP 当成后置追加元素，而不是画面表达机制的一部分。
```

V4.1 的目标是彻底改掉这个抽象。

新系统不再问：

```text
这个视觉锚点能不能放进去？
如果不合适，要不要隐藏？
如果 LLM 失败，要不要 fallback？
```

而是改成：

```text
当前图像任务是什么表达类型？
视觉 IP 在画面里扮演什么角色？
视觉 IP 如何参与画面表达？
最终完整融合提示词是什么？
如果融合不合格，如何重写？
```

V4.1 的核心系统叫：

```text
Visual Role Expression System
视觉角色表达系统
```

视觉 IP 的角色不再局限于“锚点”，它可能是：

```text
主角
固定主持人
故事行动者
讲解者
观察者
导览者
操作者
信息图中的角色化指示物
商品演示者
墙面照片
桌面摆件
投影中的角色
展板图像
环境品牌化装置
```

但无论哪种形态，都必须满足：

```text
视觉 IP 必须参与画面表达。
视觉 IP 不能只是角标、水印、贴纸、logo 或无意义装饰。
启用视觉角色后，不允许静默生成无视觉角色图。
失败后进入修复循环。
修复失败则明确报错。
```

---

## 1. 当前链路现状、真实调用链与 dev 状态审计

### 1.1 当前端到端链路

当前 Pixelle-Video 从用户输入到图片 prompt 的主链路大致是：

```text
用户输入主题 / 完整文案
↓
StandardPipeline
↓
脚本生成 / 文案拆分
↓
StoryboardGenerationService / StoryboardPlan
↓
ImagePromptComposer
↓
generate_styled_image_prompt_batch
↓
基础图片提示词生成
↓
VisualPromptPlanningService
↓
BaseVisualBriefPlanner
↓
VisualAnchorIntegrationPlanner / VisualAnchorPlacementPlanner
↓
ProviderPromptProjector
↓
最终图片 prompt
↓
ComfyUI / RunningHub / 自托管图像工作流
```

经过排查，真实调用链中非常关键的一环是：

```text
StandardPipeline
→ ImagePromptComposer.compose()
→ generate_styled_image_prompt_batch()
→ VisualPromptPlanningService.plan_image_prompts()
```

之前假设 `StandardPipeline` 直接调用 `generate_styled_image_prompt_batch()` 是错误的。  
后续所有 V4.1 改造都必须以真实调用链为准。

---

### 1.2 Review2 当前 dev 状态审计

当前 `dev` 分支不是“纯 V3 状态”，而是已经出现了部分 V4 思想的半应用状态。

已存在的能力：

```text
VisualRoleMode
VisualConsistencyMode
VisualRoleStrategyControls
primary_character → subject_replacement 的 effective role 归一化
mandatory visual-role integration 的 repair loop 雏形
```

但这些能力仍然挂在旧命名和旧结构上：

```text
VisualAnchorIntegrationPlanner
VisualAnchorPlacementPlan
ProviderPromptProjector v3_2_visual_signature_scene_bound
visual_anchor_enabled
anchor_profile
anchor_packages
```

也就是说，当前状态是：

```text
V4 思想已经部分进入代码，
但仍被 V3 anchor 命名、V3 plan 对象、V3 projector 结构承载。
```

这会造成三个问题：

```text
1. 后续继续改会把 V4 设计写进 V3 类名，形成长期技术债。
2. 文档说“不继续在 VisualAnchorIntegrationPlanner 上打补丁”，但代码已经在这里继续演进。
3. V4 fail-closed 语义无法在旧 projector 中稳定表达。
```

因此 Phase 0 不能只写“清理半应用状态”。  
必须改成：

```text
审计当前半 V4 实现
保留可迁移能力
修复 P0 运行风险
将 V4 主逻辑迁出旧 anchor 模块
旧模块降级为 legacy adapter
```

---

### 1.3 P0 运行风险：ProviderPromptProjector.project 参数不匹配

当前 `VisualPromptPlanningService.plan_image_prompts()` 在调用 projector 时传入了：

```python
visual_role_strategy=role_strategy
```

但当前 `ProviderPromptProjector.project()` 的签名没有该参数。

这会导致运行时错误：

```text
TypeError: project() got an unexpected keyword argument 'visual_role_strategy'
```

这是 P0，必须先修复。  
在正式进入 V4.1 实施前，必须二选一处理：

#### 方案 A：短期止血

从调用处移除 `visual_role_strategy=role_strategy`。  
适合只恢复现有链路运行，但不推荐作为 V4.1 最终方案。

#### 方案 B：V4.1 正向修复

扩展 projector 签名：

```python
def project(
    self,
    *,
    base_visual_brief: BaseVisualBrief,
    visual_anchor_plan: VisualAnchorPlacementPlan | None = None,
    negative_rules: Sequence[str] = (),
    capabilities: Any = None,
    workflow: str | None = None,
    visual_signature_policy: VisualSignaturePolicy | None = None,
    visual_role_strategy: VisualRoleStrategyControls | None = None,
) -> RenderedMediaPrompt:
    ...
```

但这只是兼容旧 V3 projector 的过渡修复。  
V4.1 最终应新增：

```text
VisualRolePromptProjector
```

并让 V4 enabled 任务走新的 fail-closed projector。

---

### 1.4 V3 系列的根本问题

V3 系列虽然引入了视觉签名、场景绑定、节奏控制、fail-closed 等设计，但底层仍然是：

```text
第一阶段先生成一张图
第二阶段再尝试把视觉 IP 加进去
```

这种结构天然导致视觉 IP 变成：

```text
后置追加物
```

后置追加物很容易退化为：

```text
角标
水印
贴纸
小 logo
画面边角装饰
和主体无关的小物件
```

为了避免这些退化，V3 又引入：

```text
suppressed
hidden
fallback
fail_closed
prefer_suppressed_when_uncertain
```

这进一步导致另一个问题：

```text
用户明明启用了视觉 IP，但最终图片 prompt 里没有视觉 IP。
```

所以 V3 的核心矛盾是：

```text
为了避免角标化，系统开始倾向于隐藏视觉 IP。
但产品目标是让视觉 IP 必须参与画面表达。
```

V4.1 要从源头改变这个逻辑。

---

## 2. V4.1 顶层原则

### 2.1 视觉 IP 是视觉角色，不是后置锚点

V4.1 不再把视觉 IP 当作：

```text
Visual Anchor
视觉锚点
```

而是定义为：

```text
Visual Role
视觉角色
```

视觉角色的核心职责不是“出现”，而是：

```text
参与画面表达。
```

---

### 2.2 保留第一阶段语义，不保留第一阶段字面结构

第一阶段输出的基础画面 prompt 不是最终不可变画面。

它应该被理解为：

```text
Base Visual Intent
基础视觉意图
```

第二阶段可以：

```text
重新构图
重新取景
加入新载体
改变表达方式
把原场景转化为电视、投影、展板、相框、课堂板书、信息图、展览空间等
```

但必须保留：

```text
核心主题
主体关系
叙事目标
信息重点
情绪风格
原始用户意图
```

---

### 2.3 启用视觉角色后，必须输出带视觉角色的最终 prompt

V4.1 禁止：

```text
hidden 作为成功结果
suppressed 作为成功结果
fallback 到无视觉角色图
LLM 失败后静默跳过视觉角色
最终 prompt 丢掉视觉角色
projector 静默回 base prompt
```

允许：

```text
repair loop
修复循环
```

也就是说：

```text
失败 → 重写
多次重写失败 → 明确报错
```

而不是：

```text
失败 → 不出现
```

---

### 2.4 用户策略优先，模型判断其次

前端用户可以指定：

```text
视觉表达类型
视觉角色模式
角色一致性模式
```

如果用户明确选择：

```text
主体代替
```

模型不能改成辅助融入。

如果用户明确选择：

```text
辅助融入
```

模型不能替代主体。

如果用户选择：

```text
自动
```

模型可以判断更合适的表达方式，但仍然必须输出视觉角色。

---

### 2.5 V4 enabled 是硬边界，不是软提示

当内部请求满足：

```text
VisualRoleRequest.enabled = True
VisualRoleRequest.pipeline_version = "v4_expression"
```

系统必须满足：

```text
必须走 V4 VisualRoleScenePlanner。
必须经过 V4 VisualRolePromptCritic。
必须经过 V4 VisualRoleRepairLoop。
最终 prompt 必须来自 integrated_scene_prompt。
任何静默回退都视为 bug。
```

---

## 3. V4.1 三大核心字段

V4.1 引入三个核心字段：

```text
visual_expression_mode
visual_role_mode
visual_consistency_mode
```

---

### 3.1 visual_expression_mode：视觉表达类型

回答：

```text
这张图属于哪种表达任务？
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

| 值 | 中文 | 适用场景 |
|---|---|---|
| auto | 自动判断 | 默认 |
| narrative_scene | 叙事场景 | 故事、旅行、剧情、小说解说 |
| explanatory_diagram | 解释图解 | 科普、机制、流程、原理 |
| cognitive_metaphor | 认知隐喻 | 抽象观点、方法论、心理状态、商业思考 |
| infographic_layout | 信息图表 | 列表、层级、时间线、结构图 |
| comparison_or_debate_scene | 对比 / 辩论场景 | 双主体对比、观点对照、技术路线比较 |
| product_or_object_scene | 商品 / 物件场景 | 商品展示、设备说明、包装展示 |
| portrait_or_host_scene | 人物 / 主持人场景 | 固定主持人、数字人、人物一致性 |
| environment_branding | 环境品牌化 | 系列感、频道品牌、空间统一 |

重要判断：

```text
认知锚点不是总逻辑。
认知锚点属于 cognitive_metaphor 这一类表达类型。
Pixelle V4.1 必须比认知锚点更通用。
```

---

### 3.2 visual_role_mode：视觉角色模式

回答：

```text
视觉 IP 在画面中扮演什么角色？
```

取值：

```text
auto
subject_replacement
supporting_integration
```

| 值 | 中文 | 说明 |
|---|---|---|
| auto | 自动 | 由系统判断主角代替或辅助融入，但必须出现 |
| subject_replacement | 主体代替 | 视觉 IP 可以成为画面主角 |
| supporting_integration | 辅助融入 | 保留原主体，视觉 IP 作为场景职责元素融入 |

---

### 3.3 visual_consistency_mode：角色一致性模式

回答：

```text
视觉 IP 是否跨帧保持一致？
```

取值：

```text
off
supporting_character
primary_character
```

| 值 | 中文 | 说明 |
|---|---|---|
| off | 关闭 | 不强调跨帧一致 |
| supporting_character | 辅助角色一致 | 视觉 IP 作为固定辅助角色 / 识别物出现 |
| primary_character | 主角一致 | 视觉 IP 作为固定主角跨帧出现 |

硬规则：

```text
visual_consistency_mode = primary_character
必须强制等价于：
visual_role_mode = subject_replacement
```

也就是说，用户选择“主角一致”后，系统不能输出小摆件、墙面照片、书页纹章等辅助形式。

---

## 4. V4.1 字段端到端链路

Review2 明确要求补齐 `visual_expression_mode` 的字段链路。

### 4.1 外部参数层

前端 / API / video_params 必须支持：

```text
ip_enabled
ip_asset_bible_id
ip_profile_id
visual_expression_mode
visual_role_mode
visual_consistency_mode
generation_world_hint
```

旧字段保留兼容：

```text
ip_enabled
ip_asset_bible_id
ip_profile_id
```

新字段作为 V4 主入口：

```text
visual_expression_mode
visual_role_mode
visual_consistency_mode
```

---

### 4.2 Contract 层

新增：

```text
VisualRoleControlsContract
VisualRoleStrategyControls
VisualRoleRequestContract
```

旧的：

```text
IPControlsContract
```

只作为 legacy adapter，不能继续承载 V4 主能力。

职责分工：

```text
IPControlsContract：
兼容旧字段 ip_enabled / ip_asset_bible_id / ip_profile_id。

VisualRoleControlsContract：
接收和校验 V4 字段：
visual_expression_mode / visual_role_mode / visual_consistency_mode。

VisualRoleRequest：
生成服务内部唯一标准对象。
```

---

### 4.3 Pipeline 层

`StandardPipeline.plan_visuals()` 不应该继续散传：

```text
ip_enabled
ip_profile
visual_role_mode
visual_consistency_mode
```

最终目标应改为：

```text
visual_role_request: VisualRoleRequest
visual_role_profile: VisualRoleProfile | None
scene_casts_by_frame
```

过渡阶段允许同时传旧字段和新对象，但必须在 Phase 2 后收敛成：

```text
内部服务只接收 VisualRoleRequest。
```

---

### 4.4 ImagePromptComposer 层

`ImagePromptComposer.compose()` 必须新增参数：

```python
visual_role_request: VisualRoleRequest | None = None
```

过渡期可以保留旧参数：

```python
ip_enabled: bool = False
ip_profile = None
visual_expression_mode: str | None = None
visual_role_mode: str | None = None
visual_consistency_mode: str | None = None
```

但内部必须立即归一化：

```python
request = VisualRoleRequest.from_legacy_inputs(
    ip_enabled=ip_enabled,
    ip_profile=ip_profile,
    visual_expression_mode=visual_expression_mode,
    visual_role_mode=visual_role_mode,
    visual_consistency_mode=visual_consistency_mode,
    generation_world_hint=generation_world_hint,
)
```

---

### 4.5 generate_styled_image_prompt_batch 层

`generate_styled_image_prompt_batch()` 必须新增：

```python
visual_role_request: VisualRoleRequest | None = None
visual_expression_mode: str | None = None
```

并在调用 `VisualPromptPlanningService.plan_image_prompts()` 时传入：

```python
visual_role_request=visual_role_request
visual_role_profile=visual_role_profile
```

---

### 4.6 VisualPromptPlanningService 层

V4.1 目标签名：

```python
async def plan_image_prompts(
    self,
    *,
    base_prompts: Sequence[str],
    frame_contexts: Sequence[Mapping[str, Any]],
    frame_plans: Sequence[Any] = (),
    visual_style_contract: VisualStyleLayerContract | None = None,
    generation_world_profile: Any = None,
    world_preset: Mapping[str, Any] | None = None,
    visual_role_request: VisualRoleRequest | None = None,
    visual_role_profile: VisualRoleProfile | None = None,
    workflow: str | None = None,
    capabilities: Any = None,
    extra_negative_rules: Sequence[str] = (),
    llm_service: Any | None = None,
    trace_context: Any = None,
    trace_recorder: Any = None,
) -> VisualPromptPlanningResult:
    ...
```

V4 enabled 时必须走：

```text
BaseVisualBriefPlanner
→ VisualExpressionClassifier
→ VisualRoleScenePlanner
→ VisualRolePromptCritic
→ VisualRoleRepairLoop
→ VisualRolePromptProjector
```

V4 disabled 时才允许走原有非角色生成路径。

---

## 5. V4.1 新内部请求对象：VisualRoleRequest

当前系统里，参数容易散落在：

```text
ip_enabled
ip_asset_bible_id
ip_profile_id
generation_world_hint
visual_expression_mode
visual_role_mode
visual_consistency_mode
```

如果每层都散传字符串，很容易出现：

```text
某一层漏传字段
某一层默认值不一致
某一层继续使用旧 ip_enabled
某一层不知道策略是否归一化
```

V4.1 必须新增统一内部对象：

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class VisualRoleRequest:
    enabled: bool
    asset_bible_id: str | None
    profile_id: str | None
    strategy: VisualRoleStrategyControls
    expression_mode: VisualExpressionMode = VisualExpressionMode.AUTO
    generation_world_hint: str | None = None
    pipeline_version: str = "v4_expression"
```

原则：

```text
边界层可以兼容旧字段。
内部服务只接收 VisualRoleRequest。
```

这样可以从源头避免字段散传导致的技术债。

---

### 5.1 VisualRoleRequest 必须提供的构造方法

必须新增：

```python
@classmethod
def from_mapping(cls, params: Mapping[str, Any] | None) -> "VisualRoleRequest":
    ...

@classmethod
def from_legacy_ip_contract(
    cls,
    ip_contract: IPControlsContract,
    *,
    visual_expression_mode: str | None = None,
    generation_world_hint: str | None = None,
) -> "VisualRoleRequest":
    ...

@classmethod
def disabled(cls) -> "VisualRoleRequest":
    ...
```

---

### 5.2 VisualRoleRequest 必须提供的校验

必须新增：

```python
def validate(self) -> None:
    if not self.enabled:
        return
    if self.asset_bible_id is None:
        raise ValueError("asset_bible_id is required when visual role is enabled")
    if self.profile_id is None:
        raise ValueError("profile_id is required when visual role is enabled")
```

---

### 5.3 VisualRoleRequest 的归一化规则

必须满足：

```text
visual_consistency_mode = primary_character
→ effective visual_role_mode = subject_replacement

visual_role_mode 非法
→ auto

visual_consistency_mode 非法
→ off

visual_expression_mode 非法
→ auto

enabled = false
→ 不触发 V4
```

---

## 6. 旧 IPControlsContract 的处理

当前项目已有：

```text
IPControlsContract
```

V4.1 不应该继续把核心新能力挂在 `IPControlsContract` 这个旧名字下。

正确做法：

```text
IPControlsContract 保留为 legacy adapter。
新增 VisualRoleControlsContract / VisualRoleRequestContract。
```

职责分工：

```text
IPControlsContract：
兼容旧字段 ip_enabled / ip_asset_bible_id / ip_profile_id。

VisualRoleControlsContract：
接收和校验 V4 字段 visual_expression_mode / visual_role_mode / visual_consistency_mode。

VisualRoleRequest：
内部标准对象。
```

Review2 注意：

```text
当前 dev 中 IPControlsContract 已经包含 visual_role_mode / visual_consistency_mode。
这属于过渡状态，不应继续扩展。
```

迁移策略：

```text
Phase 1 可以保留这些字段避免破坏现有调用。
Phase 2 开始引入 VisualRoleControlsContract。
Phase 3 后内部服务不得再直接依赖 IPControlsContract。
Phase 5 后 IPControlsContract 只作为 legacy input adapter。
```

---

## 7. V4.1 视觉角色档案：VisualRoleProfile

当前 `IPProfile` 更多描述“它长什么样”。  
V4.1 需要从 `IPProfile` 构建运行时档案：

```text
VisualRoleProfile
视觉角色档案
```

建议结构：

```python
@dataclass(frozen=True)
class VisualRoleProfile:
    profile_id: str
    display_name: str

    identity_kernel: tuple[str, ...]
    appearance_traits: tuple[str, ...]
    action_affordances: tuple[str, ...]
    primary_role_affordances: tuple[str, ...]
    supporting_role_affordances: tuple[str, ...]
    forbidden_role_forms: tuple[str, ...]
    reference_assets: tuple[str, ...] = ()
```

字段说明：

| 字段 | 含义 |
|---|---|
| identity_kernel | 身份识别核，比如白兔、蓝领结、红嘴麻雀 |
| appearance_traits | 外观特征 |
| action_affordances | 可执行动作，比如讲解、搬运、观察、引导、操作 |
| primary_role_affordances | 可作为主角的角色 |
| supporting_role_affordances | 可作为辅助融入的形式 |
| forbidden_role_forms | 禁止形态，比如角标、水印、贴纸 |
| reference_assets | 未来可接参考图 / IP-Adapter / LoRA |

核心原则：

```text
生成服务不直接读 IPProfile。
生成服务只接收 VisualRoleProfile。
```

`IPProfile` 属于资产设计层。  
`VisualRoleProfile` 属于生成运行层。

---

### 7.1 VisualRoleProfileBuilder 降级策略

`VisualRoleProfileBuilder` 必须支持非理想输入。  
如果 `IPProfile` 字段不完整，不能直接失败，而应按规则降级。

#### identity_kernel

来源优先级：

```text
identity_lock
minimal_traits
identity_anchors
name
visual_summary
style_hint
world_hint
description
```

如果仍为空：

```text
raise VisualRoleProfileError("identity kernel is required")
```

不要再使用泛化兜底：

```text
频道视觉签名
```

因为这会导致 critic 无法判断具体 IP 是否出现。

#### appearance_traits

来源：

```text
visual_summary
minimal_traits
identity_anchors
style_hint
```

#### action_affordances

优先使用资产库显式配置。  
如果没有，则按 IP 类型推导：

| IP 类型 | 默认 action_affordances |
|---|---|
| 人类 / 数字人 | 讲解、观察、引导、演示、操作 |
| 动物 / 吉祥物 | 观察、引导、互动、搬运、指示 |
| 飞机 / 车辆 | 穿行、运输、引导视线、作为场景中心运动物 |
| 石头 / 物件 | 承载信息、作为隐喻主体、作为展品、作为场景支点 |
| 抽象标识 | 作为环境品牌装置、展板图像、投影图像、信息图指示元素 |

#### primary_role_affordances

不能只适配兔子。  
必须覆盖：

```text
人类主持人
红嘴麻雀
飞机
石头
```

这些是强制测试样例。

#### supporting_role_affordances

支持：

```text
讲解者
观察者
导览者
操作员
展板图像
投影图像
桌面摆件
墙面照片
商品演示者
信息图指示物
环境品牌装置
```

但要注意：

```text
允许桌面摆件 / 墙面照片，
前提是它必须承担场景职责，
不能只是无意义装饰。
```

#### forbidden_role_forms

默认必须包含：

```text
角标
水印
贴纸
logo
corner badge
watermark
sticker
overlay
UI overlay
floating icon
无意义装饰
```

---

## 8. V4.1 核心服务模块

### 8.1 VisualRoleProfileBuilder

职责：

```text
从 IPProfile / AssetBible 中构建 VisualRoleProfile。
```

它负责：

```text
提取身份核
提取外观特征
生成动作职责
生成主角能力
生成辅助能力
生成禁止形态
挂载参考图资产
```

输出必须是生成运行层对象，不允许把完整资产层对象继续散传给 prompt planner。

---

### 8.2 VisualExpressionClassifier

职责：

```text
判断当前图像任务的表达类型。
```

输入：

```text
用户文本
分镜 frame
BaseVisualBrief
visual_expression_mode
```

如果用户指定了表达类型：

```text
直接使用用户选择。
```

如果用户选择 auto：

```text
由规则 / LLM 综合判断。
```

输出：

```python
class VisualExpressionDecision:
    frame_id: str
    expression_mode: VisualExpressionMode
    reason: str
```

最低实现可以先规则化：

| 命中信息 | expression_mode |
|---|---|
| `流程 / 原理 / 机制 / 为什么` | explanatory_diagram |
| `对比 / vs / A 和 B` | comparison_or_debate_scene |
| `列表 / 三点 / 时间线 / 结构` | infographic_layout |
| `产品 / 商品 / 设备 / 包装` | product_or_object_scene |
| `主持 / 口播 / 人设 / 数字人` | portrait_or_host_scene |
| `品牌空间 / 系列感 / 频道统一` | environment_branding |
| 抽象观点 / 心理状态 / 方法论 | cognitive_metaphor |
| 其他 | narrative_scene |

后续可升级为 LLM 分类。

---

### 8.3 VisualRoleScenePlanner

这是 V4.1 的核心 planner。

职责：

```text
生成完整融合后的 integrated_scene_prompt。
```

输入：

```text
BaseVisualBrief
VisualRoleRequest
VisualRoleProfile
VisualExpressionDecision
```

输出：

```python
class VisualRoleIntegratedPromptPlan:
    frame_id: str
    expression_mode: VisualExpressionMode
    role_mode: VisualRoleMode
    consistency_mode: VisualConsistencyMode

    role_assignment: str
    scene_rewrite_level: str
    integration_strategy: str

    original_intent_summary: str
    retained_intent: tuple[str, ...]
    transformed_scene_logic: str

    role_action: str
    role_manifestation: str
    role_location: str

    integrated_scene_prompt: str
    quality_notes: tuple[str, ...]
```

严禁输出：

```text
hidden
suppressed
fallback
无法融合
不适合
省略视觉角色
```

---

### 8.4 VisualRolePromptCritic

职责：

```text
审核 integrated_scene_prompt 是否合格。
```

必须采用两层审核：

```text
Rule Critic
LLM Critic
```

#### Rule Critic

本地硬规则校验：

```text
不允许角标、水印、logo、sticker、overlay
不允许 hidden / suppressed / fallback
prompt 不得为空
主体代替时不能只是小物件
辅助融入时不能替代原主体
必须包含 identity_kernel
必须有 role_action 或 role_manifestation
必须保留原始画面意图摘要
```

#### LLM Critic

语义审核：

```text
是否保留原始画面意图
视觉 IP 是否参与表达
是否自然融合
是否像装饰物
是否符合表达类型
是否符合角色模式
```

---

### 8.5 VisualRoleRepairLoop

职责：

```text
失败后重写，而不是隐藏。
```

流程：

```text
Planner 输出 integrated_scene_prompt
↓
Critic 审核
↓
不合格
↓
结构化返回失败原因
↓
Repair Prompt 要求 LLM 重写
↓
最多重试 N 次
↓
仍失败则明确报错
```

不允许：

```text
修复失败后 fallback 到无角色图。
```

默认参数：

```python
max_repair_attempts = 2
```

失败错误：

```python
class VisualRoleRepairFailedError(RuntimeError):
    ...
```

---

### 8.6 VisualRolePromptProjector

职责：

```text
把最终 integrated_scene_prompt 投影给具体图像模型。
```

硬规则：

```text
如果 VisualRoleRequest.enabled = True：
    integrated_scene_prompt 必须存在
    integrated_scene_prompt 必须通过 critic
    最终 prompt 必须来自 integrated_scene_prompt
    不允许静默回 base prompt
```

否则：

```python
raise VisualRolePromptProjectionError
```

V4 projector 不再执行旧逻辑：

```text
anchor_clause 为空 → 继续 base prompt
```

而必须执行：

```text
V4 enabled + integrated_scene_prompt 缺失
→ raise VisualRolePromptProjectionError
```

---

## 9. 结构化失败原因

V4.1 的 critic / repair 不能只传字符串。  
必须结构化。

建议模型：

```python
class VisualRolePromptIssue(BaseModel):
    code: str
    severity: Literal["blocking", "warning"]
    message: str
    repair_instruction: str
```

建议 code：

```text
role_missing
identity_kernel_missing
subject_replacement_not_primary
supporting_mode_replaced_subject
overlay_like_visual_role
original_intent_lost
expression_mode_mismatch
integrated_prompt_empty
forbidden_visual_form
projector_missing_integrated_prompt
critic_not_passed
```

好处：

```text
可调试
可记录日志
可展示给 UI
可作为 repair prompt 输入
可做统计分析
```

---

## 10. V4.1 真实端到端链路

必须基于真实调用链重构：

```text
Web UI
↓
output_preview / video_params
↓
VisualRoleControlsContract
↓
VisualRoleRequest
↓
StandardPipeline
↓
ImagePromptComposer.compose()
↓
generate_styled_image_prompt_batch()
↓
VisualPromptPlanningService.plan_image_prompts()
↓
BaseVisualBriefPlanner
↓
VisualRoleProfileBuilder
↓
VisualExpressionClassifier
↓
VisualRoleScenePlanner
↓
VisualRolePromptCritic
↓
VisualRoleRepairLoop
↓
VisualRolePromptProjector
↓
RenderedMediaPrompt
↓
图像生成工作流
```

重点：

```text
StandardPipeline 不直接调用 generate_styled_image_prompt_batch。
真实中间层是 ImagePromptComposer。
```

---

## 11. V4 与 V3 旧路径的硬边界

必须新增内部标记：

```text
visual_role_pipeline = "v4_expression"
```

或：

```text
visual_role_system_version = "v4.1"
```

硬规则：

```text
如果 visual_role_request.enabled = True
且 visual_role_pipeline = "v4_expression"
则必须走 V4 VisualRoleScenePlanner
严禁进入 V3 VisualAnchorIntegrationPlanner
```

旧模块可以保留兼容：

```text
visual_anchor_integration.py
visual_anchor_integration_planner.py
visual_anchor_placement_planner.py
visual_anchor_policy.py
```

但 V4 主路径不得依赖它们。

---

### 11.1 半 V4 现有代码迁移规则

当前 dev 中已有部分能力需要迁移，而不是简单删除。

迁移表：

| 当前模块 / 对象 | 当前问题 | V4.1 处理 |
|---|---|---|
| VisualRoleStrategyControls | 名字已是 V4，可保留 | 迁到或保留在 `models/visual_role_strategy.py` |
| VisualAnchorIntegrationPlanner | 行为已接近 V4，但名字和输出仍是 anchor | 迁移核心 repair loop 到 `VisualRoleScenePlanner` |
| VisualAnchorPlacementPlan | 承载 placement，不足以表达完整 integrated prompt | 新增 `VisualRoleIntegratedPromptPlan` |
| ProviderPromptProjector | 当前可静默丢 anchor clause | 新增 `VisualRolePromptProjector` |
| visual_anchor_enabled | V3 命名 | V4 改为 `visual_role_request.enabled` |
| anchor_profile | V3 命名 | V4 改为 `visual_role_profile` |
| anchor_packages | V3 命名 | V4 主路径不依赖，必要时作为 legacy bridge |

---

## 12. 可观测性与调试产物

V4.1 必须输出可追踪 artifact。

建议每个任务输出：

```text
visual_role_request.json
visual_role_profile.json
visual_expression_decision.json
visual_role_plan_frame_001.json
visual_role_critique_frame_001.json
visual_role_repair_attempts_frame_001.json
final_integrated_prompt_frame_001.txt
```

每帧必须能回答：

```text
用户选了什么策略？
系统判断了什么表达类型？
视觉角色档案是什么？
LLM 生成了什么融合 prompt？
Critic 为什么通过或失败？
Repair 做了几次？
最终 prompt 是哪个？
```

没有这些 artifact，后续用户说“IP 没出现”，排查会继续靠猜。

---

## 13. 前端设计

### 13.1 主入口名称

```text
系列视觉角色
```

不要再叫：

```text
IP 角色融入
视觉锚点
```

---

### 13.2 核心控件

```text
启用视觉角色
选择视觉角色素材库
选择视觉角色形象
```

---

### 13.3 角色模式

```text
视觉角色模式：
- 自动
- 主体代替
- 辅助融入
```

---

### 13.4 一致性模式

```text
角色一致性：
- 关闭
- 辅助角色一致
- 主角一致
```

---

### 13.5 高级表达类型

默认折叠：

```text
表达类型：
- 自动判断
- 叙事场景
- 解释图解
- 认知隐喻
- 信息图表
- 对比 / 辩论场景
- 商品 / 物件场景
- 人物 / 主持人场景
- 环境品牌化
```

---

### 13.6 前端参数名

前端最终写入 `video_params` 的字段必须是：

```text
ip_enabled
ip_asset_bible_id
ip_profile_id
visual_expression_mode
visual_role_mode
visual_consistency_mode
```

不要新增语义重复字段，例如：

```text
role_enabled
character_enabled
visual_ip_mode
anchor_mode
```

---

## 14. 测试要求：可执行断言清单

### 14.1 Contract 测试

| 测试名 | 输入 | 断言 |
|---|---|---|
| `test_visual_role_controls_accepts_v4_fields` | 含三个 V4 字段 | 字段完整保留 |
| `test_ip_controls_remains_legacy_adapter` | 旧 IP 字段 | 只负责旧字段兼容 |
| `test_visual_expression_mode_invalid_defaults_auto` | 非法 expression mode | 归一化为 auto |
| `test_primary_character_forces_subject_replacement` | `visual_consistency_mode=primary_character` | effective role = subject_replacement |

---

### 14.2 VisualRoleRequest 测试

| 测试名 | 输入 | 断言 |
|---|---|---|
| `test_visual_role_request_disabled_does_not_trigger_v4` | enabled=false | 不进入 V4 planner |
| `test_visual_role_request_requires_asset_when_enabled` | enabled=true 无 asset id | 抛错 |
| `test_visual_role_request_requires_profile_when_enabled` | enabled=true 无 profile id | 抛错 |
| `test_visual_role_request_pipeline_version_is_v4_expression` | enabled=true | pipeline_version = v4_expression |

---

### 14.3 链路穿透测试

验证：

```text
Web UI
→ video_params
→ StandardPipeline
→ ImagePromptComposer
→ generate_styled_image_prompt_batch
→ VisualPromptPlanningService
```

字段完整传递：

```text
ip_enabled
ip_asset_bible_id
ip_profile_id
visual_expression_mode
visual_role_mode
visual_consistency_mode
generation_world_hint
```

测试名建议：

```text
test_visual_role_fields_pass_through_standard_pipeline_to_prompt_planning
```

---

### 14.4 表达类型测试

覆盖：

```text
narrative_scene
explanatory_diagram
cognitive_metaphor
infographic_layout
comparison_or_debate_scene
product_or_object_scene
portrait_or_host_scene
environment_branding
```

测试名建议：

```text
test_visual_expression_classifier_respects_user_selected_mode
test_visual_expression_classifier_auto_detects_explanatory_diagram
test_visual_expression_classifier_auto_detects_infographic_layout
test_visual_expression_classifier_auto_detects_cognitive_metaphor
```

---

### 14.5 主体代替测试

要求：

```text
视觉角色成为核心主体。
不能只是摆件 / 相框 / 小图案。
```

测试名建议：

```text
test_subject_replacement_requires_visual_role_as_primary_subject
```

断言：

```text
role_mode = subject_replacement
role_manifestation 不是 small object / poster / watermark
integrated_scene_prompt 包含 identity_kernel
critic passed
```

---

### 14.6 辅助融入测试

要求：

```text
保留原主体。
视觉角色承担场景职责。
不能隐藏。
不能角标化。
```

测试名建议：

```text
test_supporting_integration_preserves_original_subject
test_supporting_integration_rejects_subject_replacement
test_supporting_integration_rejects_overlay_like_role
```

---

### 14.7 非兔子 IP 测试

必须用：

```text
人类主持人
红嘴麻雀
飞机
石头
```

证明身份核不是硬编码兔子。

测试名建议：

```text
test_visual_role_profile_builder_supports_human_host
test_visual_role_profile_builder_supports_red_beaked_sparrow
test_visual_role_profile_builder_supports_airplane
test_visual_role_profile_builder_supports_stone_object
```

---

### 14.8 强制失败测试

如果 LLM 多次输出无视觉角色 prompt：

```text
必须抛错。
不能返回无视觉角色图。
```

测试名建议：

```text
test_repair_loop_raises_after_repeated_role_missing
```

断言：

```text
error type = VisualRoleRepairFailedError
issue code contains role_missing
final prompt is not returned
```

---

### 14.9 Projector 测试

验证：

```text
V4 enabled 时 integrated_scene_prompt 被拒绝必须报错。
不能静默回 base prompt。
```

测试名建议：

```text
test_v4_projector_raises_when_integrated_prompt_missing
test_v4_projector_raises_when_critic_not_passed
test_v4_projector_uses_integrated_scene_prompt_as_final_prompt
```

---

### 14.10 P0 回归测试

必须新增测试覆盖当前参数不匹配问题：

```text
test_visual_prompt_planning_projector_accepts_visual_role_strategy_argument
```

或在 V4 projector 完成后改成：

```text
test_visual_prompt_planning_routes_v4_to_visual_role_projector
```

断言：

```text
调用 plan_image_prompts 不因 unexpected keyword argument 失败。
```

---

## 15. 实施阶段

### Phase P0：修复当前运行风险

目标：

```text
修复 ProviderPromptProjector.project() 参数不匹配。
保证 dev 当前 image prompt planning 不因 unexpected keyword argument 中断。
```

验收：

```text
现有 image prompt planning 测试通过。
新增 P0 回归测试通过。
```

推荐策略：

```text
短期为旧 ProviderPromptProjector 增加 visual_role_strategy 可选参数。
同时标注该参数为 legacy compatibility。
V4 主路径最终不依赖该 projector。
```

---

### Phase 0：半 V4 状态审计与迁移准备

目标：

```text
审计当前 dev 中已经进入旧 anchor 模块的 V4 能力。
列出保留、迁移、废弃清单。
避免简单 git restore 丢掉可复用实现。
```

必须检查：

```text
VisualRoleStrategyControls
VisualAnchorIntegrationPlanner mandatory integration 逻辑
repair loop 逻辑
identity kernel 逻辑
ProviderPromptProjector 静默丢 anchor clause 逻辑
```

验收：

```text
迁移清单完成。
P0 已修。
现有非 V4 任务不受影响。
```

---

### Phase 1：新增 V4.1 contract + 前端控件

新增：

```text
VisualExpressionMode
VisualRoleControlsContract
VisualRoleStrategyControls
VisualRoleRequest
前端三个字段
i18n 文案
```

不改变生成行为。

验收：

```text
字段能从前端进入 video_params。
contract 测试通过。
primary_character 强制 subject_replacement 测试通过。
```

---

### Phase 2：真实链路穿透

接通：

```text
StandardPipeline
→ ImagePromptComposer
→ generate_styled_image_prompt_batch
→ VisualPromptPlanningService
```

新增字段：

```text
visual_expression_mode
visual_role_request
visual_role_profile
```

验收：

```text
链路穿透测试通过。
非 V4 任务不受影响。
```

---

### Phase 3：VisualRoleProfile + ExpressionClassifier

新增：

```text
VisualRoleProfileBuilder
VisualExpressionClassifier
```

验收：

```text
能从 IPProfile 构建 VisualRoleProfile。
能自动判断表达类型。
能处理人类主持人 / 红嘴麻雀 / 飞机 / 石头。
```

---

### Phase 4：VisualRoleScenePlanner + Critic + Repair Loop

新增：

```text
VisualRoleScenePlanner
VisualRolePromptCritic
VisualRoleRepairLoop
VisualRoleIntegratedPromptPlan
VisualRolePromptIssue
```

从旧 `VisualAnchorIntegrationPlanner` 迁移可复用能力：

```text
mandatory integration prompt 思路
repair loop 思路
identity kernel 校验思路
forbidden overlay 校验思路
```

验收：

```text
启用 V4 后每帧输出 integrated_scene_prompt。
失败进入 repair loop。
修复失败明确报错。
```

---

### Phase 5：Projector 强边界与旧路径降级

新增 / 修改：

```text
VisualRolePromptProjector
VisualPromptPlanningService V4 分支
ProviderPromptProjector legacy 分支
旧 VisualAnchor 路径降级兼容
```

验收：

```text
V4 enabled 任务不再进入旧 anchor planner。
最终 prompt 必须来自 integrated_scene_prompt。
缺失 integrated_scene_prompt 必须抛错。
不能静默回 base prompt。
```

---

### Phase 6：可观测 artifact

输出：

```text
visual_role_request.json
visual_role_profile.json
visual_expression_decision.json
visual_role_plan_frame_xxx.json
visual_role_critique_frame_xxx.json
visual_role_repair_attempts_frame_xxx.json
final_integrated_prompt_frame_xxx.txt
```

验收：

```text
每个生成任务可追踪视觉角色决策全过程。
用户反馈“IP 没出现”时能定位是哪一层失败。
```

---

## 16. 不做的事情

V4.1 明确不做：

```text
不继续在 VisualAnchorIntegrationPlanner 上打补丁作为最终方案。
不继续添加 fallback。
不继续让 LLM 坏输出变 suppressed。
不把所有场景都变成认知隐喻。
不把角色一致性完全交给 prompt。
不一次性强删旧模块造成主流程断裂。
不让 IPControlsContract 继续承载 V4 主能力。
不让 projector 静默回 base prompt。
```

---

## 17. 最终验收标准

V4.1 完成后必须满足：

```text
1. 用户不开启视觉角色，原有生成链路正常。
2. 用户开启视觉角色，最终每帧 prompt 必须包含视觉角色。
3. 主体代替模式下，视觉角色成为画面核心主体。
4. 辅助融入模式下，原主体保留，视觉角色承担场景职责。
5. 主角一致模式下，强制走主体代替。
6. 表达类型可自动判断，也可用户指定。
7. 认知锚点只是表达类型之一，不是总逻辑。
8. 不允许 hidden / suppressed / fallback 作为成功结果。
9. LLM 输出不合格时进入 repair loop。
10. repair loop 失败时明确报错。
11. V4 enabled 时严禁静默回退到无角色 prompt。
12. 每帧输出可观测 artifact。
13. V4 主路径不依赖旧 VisualAnchorIntegrationPlanner。
14. Projector 缺失 integrated_scene_prompt 必须抛错。
15. 非兔子 IP 测试通过：人类主持人、红嘴麻雀、飞机、石头。
```

---

## 18. 最终结论

V4.1 的核心不是：

```text
把视觉锚点加到图里
```

而是：

```text
让视觉角色参与画面表达。
```

它不是小黑仓库“认知锚点配图”的简单复制，而是吸收其最重要的原则：

```text
IP 不是装饰物。
IP 必须承担画面动作或场景职责。
如果去掉 IP，画面表达应该明显变弱。
```

Pixelle V4.1 要做得更通用，支持：

```text
普通插画
信息图表
认知隐喻
故事分镜
商品展示
人物主持人
环境品牌化
角色一致性
```

最终系统目标：

```text
视觉角色启用后，
不是判断适不适合出现，
而是决定如何参与表达。

失败不隐藏，
失败就重写。

重写失败不假装成功，
而是明确报错。
```

---

## 19. 本地提交建议

建议提交前执行：

```powershell
git status
git checkout dev
```

替换文件：

```powershell
Copy-Item `
  .\Pixelle_V4_1_视觉角色表达系统_端到端重构方案_review2修订版.md `
  .\docs\superpowers\Pixelle_V4_1_视觉角色表达系统_端到端重构方案.md `
  -Force
```

检查 diff：

```powershell
git diff -- docs\superpowers\Pixelle_V4_1_视觉角色表达系统_端到端重构方案.md
```

建议提交信息：

```text
docs: refine V4.1 visual role expression refactor plan
```
