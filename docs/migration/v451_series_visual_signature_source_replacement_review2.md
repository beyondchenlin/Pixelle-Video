# V4.5 系列视觉签名源替换：两轮对抗式审查记录

> 状态：**阻塞合并 / PR 保持 Draft**
>
> 本文是 `v451_series_visual_signature_source_replacement.md` 的第二轮审查附录。若旧文档中的“影子验收完成 / 可进入切换阶段”与本文冲突，以本文和当前代码门禁为准。当前不能把该迁移描述为“全部完成”或“零技术债终态”。

## 1. 第一性原理

视觉签名不是贴纸、角标、Logo 或后处理装饰。它是一个**受正文主体约束的、场景内参与的、可识别的系列视觉身份**。

生产链必须满足五个不可妥协的不变量：

1. **单一事实源**：视觉签名请求、角色决策、身份档案、最终契约、最终编译都只能有一个生产事实源。
2. **正文优先**：视觉签名不能替代、遮挡、合并、吞掉正文必需主体。
3. **身份完整**：配置为 required identity traits 的每一条身份特征都必须进入最终提示词并通过最终门禁。
4. **边界清晰**：Visual Story 只负责正文视觉路线；Article Concretization 只负责正文锚点/图解/布局/文字；视觉签名只能在最终 canonical V4.5 projection 阶段参与。
5. **失败显式**：档案缺失、主体缺失、角色面积超限、保护语义超预算、身份特征丢失都必须 fail closed，不能静默降级成“看起来还能出图”。

## 2. Review 1：数据流 / 控制流 / 契约审查

### P0-1：旧 shadow 不是独立候选链

旧 shadow candidate 复用了已经经过旧签名路径生成的 production prompt 作为候选基础，因此可能形成“旧签名 + 新签名”的叠加，而不是干净的 V4.5 候选。这使 shadow coverage/pass rate 不能证明新链可独立替代旧链。

**处理：**
- 物理删除 `series_visual_signature_shadow_comparison.py` 及其旧测试。
- 不再以 shadow report 作为切换资格事实源。
- 新生产链先生成 signature-free base prompt，再由唯一 `SeriesVisualSignatureProjectionService` 投影视觉签名。

### P0-2：生产执行曾是双轨

旧 `VisualPromptPlanningService` / IP 融合语义与 canonical V4.5 同时存在，导致改动可能命中一条路径而生产使用另一条路径。

**处理：**
- 新增 `VisualPromptComposer` 作为图片/视频共用的真实编排实现。
- `ImagePromptComposer` 降为兼容别名，不再拥有第二套实现。
- 基础生成器的旧视觉签名/IP 参数被硬编码为 `False/None`，防止兼容字段重新激活旧执行器。
- 视觉签名只在最终 canonical projection 阶段注入。

### P0-3：Visual Story 会让旧 IP 影响路线和成本

旧 Visual Story 会：
- 将 IP 档案放入路线分析模型上下文；
- 单独做 IP route compatibility 推理；
- 单独做 IP style harmonization；
- 做逐帧 IP fusion；
- 让 IP compatibility 参与 route ranking。

这不仅改变正文路线，还增加模型调用、延迟和费用。

**处理：**
- Visual Story 改成 content-only。
- 路线分析模板删除 IP 输入/输出字段。
- 物理删除 IP route compatibility、style harmonization、frame IP fusion、frame IP fusion batch 四套模板。
- `FrameVisualPlanBatchService` 不再运行 `ContentBoundIPPlanner`。
- Visual Story 批次循环不再运行旧 IP 模型推理。
- 质量门禁把任何 active old IP runtime 判为 `legacy_ip_runtime_reintroduced`。

### P0-4：模型自评分可绕过确定性路线评分

旧 `VisualRouteScores.final_score` 可直接信任模型传入的 `final`，并且默认公式包含 22% `ip_compatibility` 权重。即使服务层想做 content-only，旧 `final` 仍可能把 IP 偏好的路线带回排序。

**当前状态：仍是合并阻塞项。**

服务层已重建 content-only score 并丢弃模型 `final` / `ip_compatibility`，但共享 `VisualRouteScores` 模型本身仍保留历史危险语义。最终零债版本必须让共享模型的 `final_score` 本身不再信任外部 `final`，也不再使用 IP 权重；历史字段只能做反序列化兼容。

### P1-1：Article Concretization 曾是第二角色决策中心

文章具象化曾独立选择 operator / guide / silent_witness 等角色，与 canonical role resolver 形成双决策中心。

**处理：**
- `article_concretization_resolution.py` 不再解析视觉签名角色。
- 历史 role/profile/strategy 输入只允许产生弃用诊断，不改变文章具象化结果。
- `effective_signature_role` 只返回 `none` 兼容值。
- 新架构测试禁止文章层重新出现自动角色映射和角色解析函数。

**当前剩余：** `models/article_concretization.py` 仍有历史同名 `SeriesVisualSignatureRole` / `SeriesVisualSignatureContract` 数据结构。它们已不应参与生产决策，但为了达到“一个运行时类定义”的零债标准，仍需进一步并入 canonical 模型或迁移持久化结构。

### P1-2：编译器/provider 命名与真实能力不一致

旧实现把最终语义编译和 Z-Image 绑定，且 `ImagePromptComposer` 实际服务 image/video 两类路径。

**处理：**
- 新增 provider/media neutral 的 `FinalVisualPromptBundle`。
- 新增唯一 `FinalVisualPromptCompiler`。
- Z-Image 仅保留 provider adapter 入口。
- 核心实现迁移到 `VisualPromptComposer`；`ImagePromptComposer` 仅为兼容别名。
- 提示词语义使用 `frame area`，不再写 image-only 的面积表述。

### P1-3：身份特征只检查前三条

旧链只把前三条 identity traits 写入/检查，第四条及以后实际上可能成为死配置。

**处理：** 所有 required identity traits 必须全部编译、全部通过最终门禁。

### P1-4：max_area_ratio 可绕过角色语义上限

旧请求允许用户把 guide/silent witness 等从属角色显式放大到接近满画面。

**处理：** 每个角色有硬语义上限；请求只能调小，不能调大，超限显式失败。

## 3. Review 2：隐藏副作用 / 兼容 / 性能 / 安全 / 维护性

### P0-5：旧 IP 信息会从上游视觉上下文渗透

仅在最终调用关闭旧签名不够，因为 Visual Story 的 `frame_visual_plans`、`frame_ip_fusion_plans`、style harmonization、channel memory 已可能包含旧 IP 语义。

**处理：** `VisualPromptComposer` 使用 whitelist content projection，只允许正文路线、正文逐帧视觉事实和参考图事实进入 signature-free base prompt。新增加的 IP 字段默认不能穿过白名单。

### P1-5：身份档案是模型输入，存在提示词注入风险

Asset Bible 中的身份字段最终进入模型提示词，不能被当成无条件可信文本。

**处理：**
- 只接受显式身份锁/最小特征/身份锚点；不从 profile id、display name、world hint 或自由文本推断身份。
- 身份特征有长度上限。
- 拒绝 `ignore previous instructions`、`system prompt`、`must render` 等指令式身份字符串。
- 对异常档案显式失败，不做静默清洗。

### P1-6：规划快照复制完整新旧提示词造成膨胀和隐私风险

旧 shadow report 每帧复制 production/candidate 正负提示词和契约，会放大持久化体积，并把业务正文/生成提示重复散落到 metadata。

**处理：** 新 projection audit 只保留长度、SHA256、角色、主体数量、身份特征数量和门禁结果；完整提示词继续由既有 prompt trace/artifact 负责。

### P1-7：不可变契约只做浅冻结

只冻结 dataclass 或顶层 mapping 不够，嵌套 list/dict 仍可在最终门禁后被外部修改。

**处理：** `FinalVisualPromptBundle` 和 V4.5 final contract 对嵌套 JSON 做递归只读冻结，序列化时再深解冻。

### P1-8：视频路径兼容风险

`ImagePromptComposer` 实际被 video template 调用。若把 canonical projection 限定为 image 会造成现有视频路径回归。

**处理：** 提升为 `VisualPromptComposer` + media-neutral final bundle；图片和视频共用最终视觉签名语义边界。

### P1-9：现有文章具象化旧测试与新职责冲突

扩大后的 CI 当前有 6 个旧 `test_article_concretization_resolution.py` 测试失败。这些测试仍要求文章层根据视觉签名角色/档案做 raise/fallback/role resolution，锁定的正是本次要删除的第二决策中心。

**当前状态：合并阻塞。**

不能为了绿灯恢复旧行为。必须把这些测试迁移为新的职责测试：文章层忽略旧视觉签名行为开关，只给弃用诊断；canonical final projection 才决定角色。

## 4. 当前生产目标链

```text
Article / Storyboard
  -> VisualStoryEngine (content-only route)
  -> FrameVisualPlanBatchService (content-only frame facts)
  -> VisualPromptComposer
       -> signature-free base prompt generation
       -> canonical profile snapshot
       -> canonical role resolver
       -> canonical SeriesVisualSignatureContract
       -> FinalVisualPromptContractV45
       -> FinalVisualPromptCompiler
       -> final prompt gate
       -> provider/media adapter
```

任何 recurring IP / series visual signature 语义不得在 `FinalVisualPromptCompiler` 之前的 content planning 阶段参与路线评分或模型推理。

## 5. 已物理删除

- 旧 shadow comparison runtime 与旧 shadow tests。
- `ip_route_compatibility.md`
- `style_harmonization.md`
- `frame_ip_fusion.md`
- `frame_ip_fusion_batch.md`
- Visual Story prompt module 中旧 IP compatibility/style/fusion renderer。
- Frame visual service 中旧 IP fusion batch service / content-bound IP enrichment 调用。

## 6. CI / 架构门禁

专用 Visual Signature CI 现应覆盖：

- canonical request / contract / role resolver；
- provider/media-neutral final bundle + compiler；
- profile snapshot security boundary；
- final prompt gate；
- canonical production projection；
- VisualPromptComposer content-only boundary；
- Visual Story content-only route + frame planning；
- Article Concretization no-role-decision boundary；
- Reference Image regression；
- `test_no_legacy_ip_runtime.py`；
- `test_visual_signature_source_replacement.py`；
- `test_visual_story_source_replacement.py`。

架构测试必须阻止：
- shadow runtime 复活；
- 旧四套 IP prompt template 复活；
- Visual Story 重新出现 IP 模型 prompt renderer；
- Article Concretization 重新出现自动签名角色解析；
- base prompt generator 重新接入旧 visual-signature/IP 参数；
- 第二份 FinalVisualPromptCompiler / VisualPromptComposer 实现。

## 7. 当前严重程度排序与合并阻塞

### P0 — 必须在恢复 Ready 前完成

1. **共享 `VisualRouteScores.final_score` 仍保留历史 `final` 信任和 IP 权重语义。** 服务层已经防住，但模型层仍是未来回归入口。
2. **扩大版 Visual Signature CI 当前红灯。** 已确认 177 passed / 6 failed；6 个失败全部来自旧 Article Concretization 角色测试，必须迁移测试而不是恢复旧行为。
3. **最终 HEAD 必须重新跑扩大版 CI，且 Visual Signature CI + Reference Image CI 都成功。** 旧提交绿灯无效。

### P1 — 零技术债终态必须完成

4. `models/article_concretization.py` 中历史同名视觉签名 role/contract 仍需并入 canonical 模型或完成持久化迁移，不能长期保留第二运行时类定义。
5. `StandardPipeline` 仍通过兼容 import / 历史视觉签名控制字段调用编排边界；这些字段目前已无法激活旧执行器，但最终应只停留在 API compatibility adapter，不进入核心 pipeline/service 接口。
6. 旧 Visual Story 数据模型仍保留 neutral compatibility fields（compatibility reports / frame IP fusion placeholders 等）。如果持久化/外部协议必须兼容，可以保留字段，但必须明确为 non-operative compatibility payload，并由架构门禁禁止 active semantics。

## 8. 最终 Done Definition

只有以下条件全部成立，PR 才允许从 Draft 恢复 Ready：

- [ ] `VisualRouteScores.final_score` 从共享模型层去掉外部 final/IP 影响。
- [ ] Article Concretization 旧角色测试完成职责迁移，且不恢复第二角色决策。
- [ ] 同名 article-local role/contract 第二事实源完成清理或被证明只存在于持久化兼容层且无第二类定义。
- [ ] StandardPipeline 核心调用只使用 canonical visual-signature contract；历史字段只在边界适配。
- [ ] source-replacement architecture tests 被 CI 强制执行。
- [ ] 当前最终 HEAD 的 Visual Signature CI 成功。
- [ ] 当前最终 HEAD 的 Reference Image CI 成功。
- [ ] PR 仍可合并且没有 unresolved blocking review thread。

在以上条件满足前，**不得使用“全部完成”“最佳实践终态”“零技术债完成”描述本 PR，也不得合并。**
