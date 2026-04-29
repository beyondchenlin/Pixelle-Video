# 19 FlowGram Adapter 分方案

用途：定义 FlowGram 与 Pixelle Core 的解耦接入方式。  
上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`

---

## 1. 定位

FlowGram 是 Studio 的可视化编排外壳，不是 Pixelle 的领域核心，也不是生产执行事实源。

Pixelle Core 必须拥有自己的 WorkflowDefinition、NodeContract、Artifact 和 Trace 体系。

---

## 2. 正确关系

```text
FlowGram Canvas Schema
  -> FlowGram Adapter
  -> PixelleWorkflowDefinition
  -> Pixelle Workflow Validation
  -> WorkflowRun / NodeRun
  -> Worker / Artifact / Trace
```

反向展示：

```text
PixelleWorkflowDefinition
  -> FlowGram View Schema
  -> Studio Canvas
```

---

## 3. 边界

FlowGram 可以保存：

- layout。
- canvas viewport。
- node position。
- user-facing labels。
- visual grouping。

FlowGram 不可以保存为唯一事实源：

- executable semantics。
- provider routing。
- billing policy。
- resource permission。
- artifact dependencies。
- worker execution state。

---

## 4. Adapter 输入输出

输入：

```text
flowgram_schema
node_contract_registry
resource_resolver_snapshot
```

输出：

```text
PixelleWorkflowDefinition
validation_errors
layout_snapshot
```

所有节点必须映射到已注册 NodeContract。

---

## 5. 校验规则

- 未注册 node_type 不可执行。
- 节点输入输出类型必须匹配。
- Public API 节点必须通过权限检查。
- 资源 ID 必须通过 ResourceResolver。
- Canvas layout 变化不得改变执行语义。

---

## 6. 阶段边界

阶段 7 才接 FlowGram Adapter。

阶段 7 之前：

- 可以设计 NodeContractLite。
- 可以设计 Workflow Skeleton。
- 不接 FlowGram 到主执行路径。

阶段 7 之后：

- 支持保存和加载画布。
- 支持节点配置由后端合同渲染。
- 支持从画布创建 PixelleWorkflowDefinition。

---

## 7. 验收标准

- FlowGram schema 修改不破坏 Pixelle Core。
- 同一 PixelleWorkflowDefinition 可生成 FlowGram view schema。
- FlowGram 节点只能映射到后端已注册合同。
- FlowGram 不直接调用 Provider。
- 执行结果仍写入 Artifact / Trace。

---

## 8. 非目标

- 不照搬 FlowGram Runtime 作为 Pixelle 后端执行器。
- 不让用户画布绕过权限和资源白名单。
- 不把前端布局字段写进核心领域模型。
