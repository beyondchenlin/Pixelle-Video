# 16 Workflow Skeleton 分方案

用途：定义 Pixelle 最小工作流骨架，避免过早建设完整 Workflow 平台。  
上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`

---

## 1. 定位

Workflow Skeleton 的目标不是马上做用户自定义 DAG，也不是接 FlowGram Runtime。

它的目标是把已经稳定的工作台流程整理成可记录、可测试、可扩展的系统预设流程。

---

## 2. 核心原则

```text
系统预设先于用户自定义
NodeContractLite 先于完整 NodeContract
WorkflowRunLite 先于完整 Workflow Engine
兼容现有 StandardPipeline
```

---

## 3. 最小模型

```text
NodeContractLite
  node_type
  input_artifact_types
  output_artifact_types
  executor_key
  required_permission_keys
  idempotency_scope
  trace_stage

SystemWorkflowPreset
  preset_id
  name
  node_sequence
  version

WorkflowRunLite
  run_id
  preset_id
  project_id
  status
  node_runs

NodeRunLite
  node_run_id
  node_type
  input_artifact_refs
  output_artifact_refs
  status
  trace_event_ids
```

---

## 4. 阶段边界

阶段 4 只做：

- NodeContractLite。
- SystemWorkflowPreset。
- WorkflowRunLite / NodeRunLite。
- in-process executor。
- StandardPipeline compatibility workflow。

阶段 4 不做：

- FlowGram Canvas。
- 用户自定义节点。
- 完整 DAG 调度。
- 分布式 NodeRun 队列。
- 复杂条件分支。

---

## 5. 数据流

```text
Storyboard Workbench
  -> SystemWorkflowPreset
  -> WorkflowRunLite
  -> NodeRunLite
  -> ArtifactVersion
  -> GenerationTrace
```

Workflow 不直接保存二进制产物，只引用 ArtifactRef。

---

## 6. 错误处理

NodeRunLite 失败时：

- 写入 GenerationTrace。
- 标记输出 ArtifactVersion 为 failed。
- 保留 input snapshot。
- 不自动覆盖用户锁定的产物。

---

## 7. 验收标准

- 能用 SystemWorkflowPreset 描述阶段 1 工作台流程。
- 能执行一个 in-process 测试 workflow。
- 每个 NodeRunLite 都能产生 Trace。
- 现有 StandardPipeline 可作为 compatibility workflow 被记录。
- 没有引入 FlowGram 运行时依赖。

---

## 8. 后续升级

阶段 5 接 Worker / Queue。  
阶段 7 接 FlowGram Adapter。  
阶段 8 之后再考虑用户自定义 Public Workflow。
