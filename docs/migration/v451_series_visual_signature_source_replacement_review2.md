# V4.5 系列视觉签名源替换：两轮对抗式审查记录

> 状态：**代码与文档已按两轮审查收口；最终 HEAD 的 CI 通过前保持 Draft**
>
> 本文记录本次源替换的两轮第一性原理 / 对抗式审查。合并判定以当前代码门禁、本文和主迁移文档为准；早期“影子链切换”方案已经被否决并物理删除。

## 1. 第一性原理

视觉签名不是贴纸、角标、Logo 或后处理装饰，而是一个受正文主体约束、在场景内参与、可持续识别的系列视觉身份。

生产链必须同时满足以下不变量：

1. **单一事实源**：请求、身份档案、角色决策、最终契约和最终编译只能各有一个生产事实源。
2. **正文优先**：视觉签名不能替代、吞掉、遮挡或合并正文必需主体。
3. **身份完整**：每一条 required identity trait 都必须进入最终提示词并通过最终门禁。
4. **职责隔离**：Visual Story 只做正文视觉路线；Article Concretization 只做正文锚点/图解/布局/文字；重复身份只能在 canonical V4.5 final projection 阶段进入最终提示词。
5. **失败显式**：档案缺失、主体缺失、角色面积越界、保护语义超预算、身份特征丢失都必须 fail closed。
6. **兼容不等于双运行时**：历史字段可以在协议边界被归一化，但不能拥有第二套生成、评分、角色解析或投影语义。
7. **观测不能成为第二数据湖**：运行审计不能复制原始提示词、主体、身份特征或用户私有 hint。

当前目标链：

```text
Article / Storyboard
  -> VisualStoryEngine                    # content-only route
  -> FrameVisualPlanBatchService          # content-only frame facts
  -> VisualPromptComposer                 # canonical core
       -> signature-free base prompt
       -> VisualSignatureProfileSnapshot
       -> canonical role resolver
       -> SeriesVisualSignatureContract
       -> FinalVisualPromptContractV45
       -> FinalVisualPromptCompiler
       -> final prompt gate
       -> provider/media adapter
```

---

## 2. Review 1：架构 / 数据流 / 兼容性

### P0-1：模型自带 `final` 与 `ip_compatibility` 可污染正文路线排序

**风险**

旧 `VisualRouteScores` 可以接受模型给出的 `final`，且历史公式让 `ip_compatibility` 参与正文路线选择。即使服务层重算一次，模型层仍然保留未来回归入口。

**根因修复**

`VisualRouteScores.computed_final()` 现在是唯一排序公式，只读取：

```text
content_fit
memorability
channel_consistency
production_reliability
risk
```

历史 `final` 与 `ip_compatibility` 仍可反序列化以兼容旧协议，但不再拥有决策权；`to_dict()` 输出确定性重算后的 final。

`VisualStoryEngineService` 不再保留第二份 `_content_route_score` 公式。

**门禁**

- 单测证明修改外部 `final` 不改变排序。
- 单测证明修改 `ip_compatibility` 不改变排序。
- AST 架构门禁禁止 `computed_final()` 重新读取这两个字段。
- AST 架构门禁禁止服务层重新出现第二份评分公式。

状态：**P0 已从共享模型源头解决。**

### P0-2：Article Concretization 曾是第二视觉签名角色 / 契约中心

**风险**

文章具象化层曾定义自己的 `SeriesVisualSignatureRole` / `SeriesVisualSignatureContract`，并依据文章结构选择 operator / guide / silent witness。这样 canonical final projection 与文章层都可以决定重复身份。

**根因修复**

- 删除文章层本地同名 role / contract 类定义。
- `models/article_concretization.py` 只 re-export canonical 类型。
- 文章 resolution 的历史 role/profile/strategy 输入只产生弃用诊断，不改变结果。
- `effective_signature_role` 只返回兼容值 `NONE`。
- `ArticleConcretizationPlanner` 即使收到历史身份档案或旧角色，也只携带 canonical disabled contract。
- active role/profile/participation 只在最终 canonical projection 创建。

**门禁**

- AST 禁止文章层重新定义 role/contract。
- AST 禁止文章层出现自动角色映射 / 角色解析函数。
- resolution / planner 测试覆盖严格与非严格历史输入，证明其不再具有运行时决策权。

状态：**P0 已在模型、resolution 和 planner 三层收口。**

### P0-3：兼容编排器不能成为第二套提示词运行时

**风险**

兼容层如果只是模糊 alias，会让职责不清；如果复制实现，则形成第二运行时。真正需要的是“可兼容旧输入，但不拥有语义”的 adapter。

**根因修复**

`VisualPromptComposer` 是唯一 canonical core：

- 只接受 canonical `SeriesVisualSignatureRequest`；
- 可接受预解析的 `VisualSignatureProfileSnapshot`；
- 不接受历史 expression / structure / participation / mode / fallback 控制。

`ImagePromptComposer` 是受限兼容 adapter：

- 接收历史调用形态；
- 一次性归一化成 canonical request / profile snapshot；
- canonical request 与历史字段同时存在时，canonical request 拥有最终解释权；
- 字符串 `"false"` 等布尔值由 canonical parser 解析，不能用 Python truthiness 误判；
- 旧 scene cast 参数在兼容边界被丢弃；
- adapter 自身不生成 base prompt、不投影视觉签名。

**门禁**

- AST 验证 core API 不得重新出现历史签名参数。
- AST 验证 adapter 不得定义第二个 `VisualPromptComposer`。
- AST 验证 adapter 不能调用 base generator / projection service。
- 集成测试覆盖 canonical-over-legacy 优先级和字符串布尔边界。

状态：**P0 已收口为单 core + 受限输入 adapter。**

### P0-4：旧 shadow 不能证明新链独立拥有身份

**风险**

旧 shadow candidate 复用了可能已经经过旧签名链生成的 production prompt，因此可能形成“旧签名 + 新签名”叠加。它能比较字符串，却不能证明 V4.5 能独立替换旧链，还额外制造第二运行时与第二快照 schema。

**根因修复**

- 物理删除 shadow runtime 与其测试。
- 不再维护 `series_visual_signature_shadow_comparison` 事实源。
- 生产先生成 signature-free base prompt，再由唯一 canonical projection 注入身份。

状态：**P0 已物理删除，不是 suppress / ignore。**

### P0-5：上游 Visual Story / 旧 IP 上下文可能旁路渗透进 signature-free base

**风险**

即使最终调用关闭旧签名，上游 route、frame fusion、style harmonization、channel memory 若携带 IP 语义，base prompt 仍可能提前包含身份，最终再次投影时形成双注入。

**根因修复**

`VisualPromptComposer` 对 Visual Story context 使用 whitelist content projection：

- 只允许正文 route facts；
- 只允许正文 frame facts；
- 允许参考图事实；
- 排除 recommended IP role / IP fit / IP compatibility / active IP fusion / 旧身份场景 affordance 等字段。

下层 base generator 的所有旧 visual-signature / IP 参数继续被硬编码为 `False/None`。

状态：**P0 已通过白名单 + hard-disable 双门禁收口。**

---

## 3. Review 2：失败语义 / 性能 / 安全 / 未来维护

### P1-1：成功覆盖率没有严格分母

**风险**

“100% coverage” 如果没有 expected / attempted / unique / duplicate / failed / not-attempted，就无法证明没有漏帧、重复帧或静默跳过。

**根因修复**

canonical projection success audit 明确记录：

```text
expected_frame_count
attempted_frame_count
projected_frame_count
unique_frame_count
duplicate_frame_count
failed_frame_count
not_attempted_frame_count
coverage_rate
all_frames_passed
```

成功批次只有在：

```text
attempted == expected
projected == expected
unique == expected
duplicate == 0
failed == 0
not_attempted == 0
coverage_rate == 1.0
```

时才可返回；重复 frame id 与空 batch 预先拒绝。

状态：**P1 已解决。**

### P1-2：失败批次只抛异常会丢失分母和未尝试帧

**风险**

如果 100 帧在第 2 帧失败，只记录异常字符串，无法区分已成功、已失败和未尝试帧，也容易产生错误运营判断。

**根因修复**

`SeriesVisualSignatureProjectionError` 携带受限失败 audit：

- expected / attempted / projected / unique；
- failed / not-attempted；
- failed frame id / index；
- stable reason code；
- exception type。

部分成功帧永远不会被包装成成功 batch 返回。

状态：**P1 已解决，失败路径同样有明确分母。**

### P1-3：Projection observability 可能变成第二份原始提示词 / 身份数据仓库

**风险**

如果 planning snapshot 每帧复制原始 prompt、主体、identity traits、request hints，会产生隐私、存储和长期生命周期技术债。

第一轮修复后又发现 core composer 仍把完整 canonical request 与完整 profile snapshot 复制进 planning snapshot，构成绕过 audit policy 的旁路。

第二轮收口后再次对抗检查发现：`compatibility_options` 接受兼容协议输入，而旧 request audit 会直接持久化全部 option key 名称。未知 key 名称本身属于用户可控输入，攻击者可以把受保护文本编码进 key 名称，形成“只存 key 不存 value”仍然泄漏的旁路。

**根因修复**

projection audit 固定为：

```text
payload_class = bounded_hash_count_only
retention_owner = planning_snapshot_lifecycle
raw_prompt_retention = forbidden
raw_subject_retention = forbidden
raw_identity_trait_retention = forbidden
raw_request_hint_retention = forbidden
```

允许保存：

- prompt 字符数；
- SHA-256 fingerprint；
- role；
- subject / trait 数量；
- final gate 状态；
- frame / contract id；
- 稳定失败 reason code；
- 固定白名单中的 compatibility option key；
- compatibility option 总数与未知 option 数量。

禁止保存：

- 原始正/负提示词；
- 原始 required subjects；
- 原始 identity traits；
- 原始 user hint / world hint；
- 原始异常 cause message；
- 未识别、用户可控的 compatibility option key 名称和值。

`VisualPromptComposer` 现在只写：

```text
series_visual_signature_request_audit
series_visual_signature_profile_ref
series_visual_signature_projection_audit
series_visual_signature_contract_by_frame   # bounded summary
```

不再复制完整 request / profile snapshot。

`SeriesVisualSignatureProjectionAuditPolicy.request_audit_dict()` 将“运行时可接受的兼容协议”与“可持久化审计协议”分离：未知兼容 key 仍可在迁移边界存在，但审计只能记录固定协议白名单 key；未知 key 只计数，不记录名称和值。

这里不新增独立数据库 / TTL 系统，而是复用既有 planning snapshot 生命周期；由于没有新增原始 prompt/identity corpus，保留风险被限制在已有工件生命周期内。

状态：**P1 已从持久化源头解决，并封堵用户可控 key 名称旁路。**

### P1-4：受保护身份 / 主体文本会通过异常日志旁路泄漏

**风险**

即使 audit 不保存原文，如果 profile validation 或 final gate 把无效 trait / missing subject 原文拼进异常消息，上层日志仍会捕获敏感数据。

**Review 2 发现并修复的旁路**

- profile snapshot builder 错误不再回显 trait 原文，只报 index / reason；
- canonical profile model 自身也做相同修复，避免未来新调用者绕过 builder；
- final prompt gate 缺主体时只报 subject index；
- final prompt gate 缺身份特征时只报 trait index；
- projection failure audit 只保存稳定 reason code + exception type，不保存原始 cause message。

新增 sentinel 测试证明受保护文本不会出现在这些异常字符串中。

状态：**P1 已在错误源头解决，而不是仅在日志层打码。**

### P1-5：Projection 没有确定性的运行 / 持久化预算

**风险**

无上限的帧数、提示词、主体、traits 与 audit 大小会带来 CPU、内存、序列化和存储风险。

墙钟 timeout 不能作为正确性边界，因为宿主机负载具有非确定性。

**根因修复**

`SeriesVisualSignatureProjectionBudget` 使用确定性复杂度预算：

```text
max frames per batch             = 512
max base prompt chars / frame    = 20,000
max negative prompt chars/frame  = 12,000
max required subjects/frame      = 64
max required subject chars       = 256
max identity traits              = 32
max projection audit bytes       = 512 KiB
```

超预算明确失败；不允许为了“能生成”而静默删除 protected semantics。

状态：**P1 已解决。**

### P1-6：迁移状态机若可切 old/new/shadow，会重新制造双运行时

**风险**

新增一个可切换的 migration feature flag 看似方便回滚，实际上会永久保留 old/new/shadow 多种语义，违背源替换目标。

**根因修复**

迁移状态不做行为开关，而写成 machine-readable runtime invariants：

```text
production_identity_owner      = canonical_v45_projection
compatibility_adapter_scope    = input_normalization_only
legacy_prompt_runtime_allowed  = false
shadow_runtime_allowed         = false
```

它们进入 bounded projection audit policy，仅用于审计当前部署契约，不能激活第二运行时。

状态：**P1 已以不可变 ownership policy 解决。**

---

## 4. 支持的兼容协议面与维护性收口，不视为第二运行时

### P2-1：历史输入字段仍在 API / adapter 边界存在

立即删除历史字段会变成有意 breaking API change，而不是架构优化。

当前允许保留的原因：

- 历史字段终止于 `ImagePromptComposer` adapter；
- canonical request 拥有最终解释权；
- adapter 不执行 base prompt generation / signature projection；
- core API 不暴露这些字段；
- AST + 集成测试锁定此边界；
- runtime policy 明确 `compatibility_adapter_scope = input_normalization_only`。

**退出条件**

当受支持的第一方 / 外部调用契约都不再发送历史字段时，物理删除 adapter 与历史字段。删除时不能把旧行为迁到新的地方重新形成第二语义。

### P2-2：Visual Story 仍有 neutral IP-shaped protocol shell

部分旧序列化结构仍含 compatibility reports / frame IP fusion placeholder 等字段，但生产服务已经将其约束为 non-operative：

- IP/profile 输入在内容路线分析前丢弃；
- route score 不读取 IP compatibility；
- content route 的 identity role 为 NONE；
- frame IP fusion 为 neutral / disabled；
- signature-free base prompt 的 whitelist 不接收 active IP fusion。

只要上述门禁成立，这些是协议壳，不是第二运行时。

### P2-3：CI 路径过滤可能让新增运行时文件绕过架构门禁

**风险**

架构测试本身会递归扫描 `api`、`pixelle_video`、`web` 运行时根目录，但旧 CI workflow 对触发文件使用人工维护的 `paths` 清单。新增视觉签名相关文件如果没有命中清单，架构扫描器本身就没有机会执行，形成“扫描能力正确、触发入口可绕过”的维护漏洞。

**根因修复**

- 删除 Visual Signature CI 在 `pull_request` / `push` 上的 `paths` 过滤；
- 所有进入 `dev` / `main` 的变更都会执行视觉签名架构门禁；
- 继续保留 concurrency cancellation，同一 PR 只执行最新有效运行，控制重复成本；
- 新文件不能再通过文件名或目录命名绕过全仓 runtime scanner。

状态：**P2 已从触发机制根修，不再依赖人工维护路径清单。**

---

## 5. Review 1 总结

第一轮专门检查架构职责、数据流、兼容权威和隐藏双注入。

第一轮发现并修复：

1. 外部 final / IP compatibility 可污染 route ranking；
2. Article Concretization 仍有第二 role / contract；
3. compatibility composer 需要成为真正受限 adapter；
4. success coverage 缺少严格分母；
5. planning snapshot 仍复制完整 request / profile；
6. 上游 Visual Story / IP context 可旁路进入 base prompt 的风险需要白名单锁死；
7. CI 的人工 `paths` 过滤可让新增文件绕过全仓架构扫描，因此改成对 `dev` / `main` 无路径过滤触发。

**第一轮结论**

当前生产身份拥有者收口为 canonical V4.5 projection；route score 与 core composer 也各只有一个语义事实源；架构扫描不再受新增文件路径清单约束。

---

## 6. Review 2 总结

第二轮不再重复看语法，而是主动寻找失败路径、安全旁路、性能上限和维护性回归入口。

第二轮发现并修复：

1. 失败批次缺少 attempted / projected / not-attempted 分母；
2. profile builder 会在错误消息中回显 identity trait；
3. canonical profile model 自己也存在相同回显旁路；
4. final gate 会在错误消息中回显 missing subject / trait；
5. projection 缺少确定性运行 / audit 大小预算；
6. 可切换 migration state 会重新制造双运行时，因此改成不可变 ownership policy；
7. architecture gate 继续扩大，防止完整 request/profile 回到 planning snapshot；
8. compatibility option 的未知 key 名称可编码受保护文本并进入审计，因此改成固定白名单 key + 未知 key 只计数。

**第二轮结论**

在已审查生产路径中，没有再发现新的 source-level 双身份运行时阻塞。剩余历史字段属于有明确 authority、门禁和退出条件的兼容协议面，不具备独立运行语义；运行时兼容输入与可持久化审计字段也已经分离。

---

## 7. 测试 / CI 门禁

Visual Signature CI 必须覆盖并 lint：

- canonical request/profile/contract；
- deterministic route-score authority；
- Article Concretization no-role ownership；
- signature-neutral Article Concretization planner；
- canonical projection success / failure denominator；
- projection privacy / retention policy；
- projection deterministic budgets；
- profile validation security；
- final prompt gate protected-data security；
- canonical core composer；
- historical compatibility adapter；
- source-replacement AST architecture gates；
- provider projection；
- Visual Story content-only source replacement；
- compatibility option audit key 白名单与未知 key 计数行为；
- 两份 migration/review 文档与 workflow 自身。

触发策略：Visual Signature CI 对进入 `dev` / `main` 的 `pull_request` / `push` **不使用 `paths` 过滤**。架构测试会自行扫描运行时根目录，因此新增文件不能通过遗漏路径清单跳过门禁。

重点边界测试包括：

- external final score poisoning；
- IP compatibility poisoning；
- canonical-over-legacy precedence；
- string boolean `"false"`；
- duplicate frame id；
- empty required subjects；
- success denominator；
- failure denominator / not-attempted；
- oversized frame/prompt/subject/traits/audit；
- raw prompt/subject/trait/hint 不进入 projection observability；
- raw protected term 不进入 profile/final-gate error message；
- user-controlled compatibility option key 名称不进入持久化 audit，只记录固定白名单 key 和未知 key 数量。

---

## 8. 最终合并门禁

本次 Review 2 完成后，仍然只认 **最终 PR HEAD**：

```text
Visual Signature CI = success
Reference Image CI  = success
PR mergeable         = true
unresolved blocking review threads = 0
```

任何更早提交的绿灯，在最终代码或文档继续变化后都失效。

最终 HEAD 满足以上条件后，才可从 Draft 切为 Ready for review；本文不授权自动 merge。

## 9. 最终评价

- 架构：**单一 production identity owner，源级收口。**
- 兼容：**仅输入归一化；canonical request 永远权威。**
- 失败：**fail closed，成功与失败都有明确分母。**
- 性能：**确定性复杂度 / 持久化预算。**
- 安全与隐私：**projection observability 不保存受保护原文；未知用户可控 compatibility key 名称不持久化；已审查错误源不回显受保护主体/trait。**
- 维护性：**AST 门禁 + 可执行测试防止主要双运行时、双评分、原始快照复制和兼容层越权回归；CI 不再允许新运行时文件通过路径过滤遗漏绕过架构扫描。**

合并建议：**仅在最终 HEAD 两套 CI 全绿、可合并且无阻塞 review thread 后恢复 Ready for review。**
