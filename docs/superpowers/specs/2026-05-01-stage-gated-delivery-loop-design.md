# 阶段门控交付循环设计

## 目标

建立一个固定的交付循环：先完成真实前后端集成体验验收，再进入下一个功能开发；每完成一个功能单元后，必须回到集成体验验收。这个循环用于防止 Stage1 / Stage2 已收口成果在后续开发中被破坏，也避免只看自动化测试而忽略真实前端体验。

## 背景

当前 Stage1 / Stage2 收口 runner 已经完成并通过：

- `stage1a-contract`
- `stage1b-workbench-stale-artifact`
- `stage2-assetbible-scenecast-projection`
- `stage1-stage2-boundary`

这些任务证明 Stage1 / Stage2 的自动化合同和跨阶段边界已经通过。但用户侧仍然需要确认真实前端页面、真实 API 调用、真实状态流转和可见体验是否成立。因此后续不能直接无条件进入新功能开发，必须先加一个真实体验验收门。

## 循环总览

循环由两个阶段组成：

```text
Integration Acceptance -> Review Gate 1 -> Review Gate 2 -> Feature Delivery -> Review Gate 1 -> Review Gate 2 -> Integration Acceptance
```

中文表达：

```text
集成体验验收 -> 两次全局 review -> 单功能开发 -> 两次全局 review -> 回到集成体验验收
```

每次循环只允许推进一个明确目标。任何阶段失败，都必须停在当前阶段，先从源头修复问题，不允许跳到下一阶段。

## 阶段一：集成体验验收

### 目的

验证当前系统在真实前后端体验中是否可用，而不是只验证单元测试或合同测试。

### 输入

- 当前 `dev` 分支。
- 已通过的 Stage1 / Stage2 closeout 报告。
- 当前前端、后端、API、运行时配置。
- 用户指定的重点观察点，例如标题、字幕、Stage2 projection preview、Workbench stale 状态。

### 执行内容

集成体验验收应至少覆盖：

- 后端服务能启动，基础健康状态正常。
- 前端服务能启动，核心页面可打开。
- Stage1A 相关能力在真实入口中可被触达，包括 PromptPlan、LLM trace、ImagePromptComposer、StandardPipeline 规划合同。
- Stage1B 相关能力在真实入口中可被触达，包括 Workbench、stale 状态、artifact bridge、frame regeneration。
- Stage2 相关能力在真实入口中可被触达，包括 AssetBible、SceneCast、PromptPlan projection preview。
- Stage2 projection preview 仍然是 preview-only，不保存投影后的 PromptPlan，不触发图片或视频生成，不进入主生成链路。
- 标题、字幕、text rendering 相关改动没有破坏 Stage1 / Stage2 数据流。
- 前端页面应提供截图或明确的观察记录，不能只报告“测试通过”。

### 输出

每次验收应输出一份本地报告，建议路径为：

```text
_runtime/integration_acceptance/YYYYMMDD_HHMMSS_<cycle_id>.md
```

报告至少包含：

- 当前分支和 commit。
- 启动命令和结果。
- 前端页面或流程截图路径。
- 已验证的用户流程清单。
- 失败项、疑点和阻塞项。
- Review Gate 1 和 Review Gate 2 的结论。

报告默认不提交到 git，除非后续明确决定归档。

### 通过条件

阶段一只有在以下条件全部满足时才算通过：

- 后端和前端核心入口可启动。
- Stage1A、Stage1B、Stage2 的用户可见入口没有明显断链。
- Stage2 projection preview 没有越过 preview-only 边界。
- 标题、字幕、text rendering 没有引入跨阶段冲突。
- 没有暴露本地路径、provider URL、workflow path、raw prompt 或 raw response。
- 两次全局 review 都通过。

## 阶段二：单功能开发

### 目的

在已有 Stage1 / Stage2 基础上继续扩展产品能力，但每轮只做一个功能单元，避免把多个目标混在一个提交或一个 review 中。

### 输入

- 阶段一已通过的集成体验验收报告。
- 一个明确的功能目标。
- 对应 spec 和 implementation plan。
- 当前干净的 `dev` 分支或隔离 worktree。

### 可选功能方向

后续功能可以包括但不限于：

- IP 形象设计链路落地。
- Stage2 projection preview 的前端体验优化。
- AssetBible / SceneCast 的编辑、版本、复用能力。
- Workbench 更完整的生成、再生成、stale 恢复闭环。
- 标题、字幕、text rendering 的下一阶段集成。

这些方向不能在同一轮混做。每轮必须选定一个功能单元。

### 执行内容

单功能开发应遵循：

- 先写或更新 spec。
- 再写 implementation plan。
- 使用 TDD：先写失败测试，再实现，再验证。
- 每个原子变更单元单独 commit。
- commit message 使用中文 conventional commit 格式。
- 每次 commit 后立即推送到 GitHub，除非用户明确要求不推送。
- 完成后执行两次全局 review。

### 通过条件

阶段二只有在以下条件全部满足时才算通过：

- 功能目标全部实现。
- 自动化测试通过。
- 相关 lint / format / diff check 通过。
- 没有混入无关改动。
- 没有新增第二事实源。
- 没有绕过 Stage1 / Stage2 边界。
- 已提交并推送。
- 两次全局 review 都通过。

阶段二通过后，不允许直接开始下一个功能。必须回到阶段一，重新做集成体验验收。

## 双重 Review Gate

每个阶段完成后都必须执行两次全局 review。

### Review Gate 1：架构与计划一致性

检查：

- 是否仍符合 Stage1 / Stage2 原始边界。
- 是否引入第二事实源。
- 是否把 preview-only 功能接入主生成链路。
- 是否暴露本地路径、provider URL、workflow path、raw prompt 或 raw response。
- 是否和标题、字幕、text rendering 相关改动冲突。
- 是否偏离当前 spec 和 plan。

### Review Gate 2：实现质量与回归风险

检查：

- 测试是否覆盖核心风险。
- 失败是否能定位到具体任务、命令或页面。
- 是否引入隐藏持久化副作用。
- 是否引入跨模块重复状态。
- 是否需要拆分后续任务，而不是继续推进。
- 是否需要更新 spec 或 plan 才能继续。

任一 gate 失败时，当前阶段状态为 `review_failed`，必须修复后重跑该阶段，不允许继续下一阶段。

## 失败处理

### 阶段一失败

如果集成体验验收失败：

- 停止进入功能开发。
- 记录失败页面、命令、截图和日志。
- 判断失败属于前端、后端、数据契约、运行配置还是文档偏差。
- 从源头修复。
- 修复后重新执行阶段一。

### 阶段二失败

如果功能开发失败：

- 停止继续开发更多功能。
- 保留失败测试或失败报告。
- 从源头修复当前功能单元。
- 修复后重新执行阶段二验证。
- 阶段二通过后，再回到阶段一。

### 发现计划偏差

如果 review 发现原 spec 或 plan 不合理：

- 不继续执行旧计划。
- 更新 spec。
- 更新 implementation plan。
- 提交并推送文档修正。
- 从修正后的计划重新开始。

## 自动化边界

该循环可以被脚本辅助，但不能变成无条件自动执行。

允许自动化：

- 列出当前阶段。
- 执行验证命令。
- 生成本地报告。
- 检查 git 状态。
- 阻止未通过 review 的阶段继续推进。

禁止自动化：

- 自动修复业务代码。
- 自动跳过 review。
- 自动进入下一个功能。
- 自动把多个功能合并到同一轮。
- 自动调用 subagent 实施未确认的功能。
- 自动提交或推送未 review 的改动。

## 建议实施形态

后续可以新增一个门控循环运行器，例如：

```text
scripts/run_delivery_loop.ps1
```

该运行器只负责：

- 管理阶段状态。
- 调用已有 `scripts/run_stage_closeout.ps1`。
- 执行前后端集成验收命令。
- 生成 `_runtime/integration_acceptance/` 报告。
- 阻止未通过双 review 的阶段继续推进。

它不负责：

- 写业务代码。
- 创建功能实现。
- 自动调用 agent。
- 自动提交或推送。

## 验收标准

该循环设计只有在以下条件满足时才算可实施：

- spec 明确区分阶段一和阶段二。
- 阶段一失败时不能进入阶段二。
- 阶段二完成后必须回到阶段一。
- 每个阶段都有两次全局 review。
- 每轮只允许一个明确目标。
- 报告输出在 `_runtime/` 下，不污染仓库文档。
- git 提交仍遵守仓库原子提交和立即推送规则。

