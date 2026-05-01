# Stage1 / Stage2 收口验证运行器设计

## 目标

为 Stage1 和 Stage2 剩余收口工作提供一个可重复执行的验证与状态推进工具。工具只负责执行检查、生成报告和标记下一步，不自动修改业务代码、不自动提交、不自动调用 agent 实施功能。

核心目的：

- 明确 Stage1 / Stage2 还剩哪些收口任务。
- 每完成一个任务后强制执行两轮全局 review。
- 只有验证和两轮 review 都通过，才允许推进到下一项任务。
- 避免人工记忆任务状态，降低重复确认成本。

## 范围

包含：

- Stage1A / Stage1B / Stage2 的 closeout 任务清单。
- 每项任务对应的验证命令。
- 每项任务完成后的双 review gate。
- 本地运行报告输出。
- 失败时停止并给出失败命令、失败阶段和下一步建议。

不包含：

- 自动修改业务代码。
- 自动调用 Codex、subagent 或外部 LLM。
- 自动提交或推送。
- 真实生产资源下载、模型下载或长时间媒体生成。
- 替代人工架构判断。

## 任务队列

初始任务队列包含四类收口任务：

1. Stage1 全链路合同验收
2. Stage1B Workbench / stale / Artifact 验收
3. Stage2 AssetBible / SceneCast / projection preview 验收
4. Stage1 + Stage2 跨边界一致性验收

每个任务都有以下字段：

```text
id
title
stage
description
verification_commands
review_gate_1
review_gate_2
status
last_run_at
last_report_path
```

`status` 只能是：

```text
pending
running
verification_failed
needs_review
review_failed
passed
blocked
```

## 双 Review Gate

每完成一项任务后必须执行两次全局 review。

Review Gate 1：架构和计划一致性

- 是否符合 Stage1 / Stage2 原始边界。
- 是否引入第二事实源。
- 是否把 preview-only 功能接入主生成链路。
- 是否暴露本地路径、provider URL、workflow path、raw prompt 或 raw response。
- 是否和标题/字幕/文本渲染相关改动冲突。

Review Gate 2：实现质量和回归风险

- 相关测试是否覆盖核心风险。
- 失败时是否能定位到具体任务和命令。
- 是否有隐藏的持久化副作用。
- 是否有跨模块耦合或重复状态。
- 是否需要拆分后续任务，而不是继续推进。

两个 gate 任意一个失败，任务状态变为 `review_failed`，运行器停止。

## 运行器行为

建议新增：

```text
scripts/run_stage_closeout.ps1
```

默认行为：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_stage_closeout.ps1
```

执行流程：

1. 检查当前 git 工作区是否干净。
2. 读取内置任务队列。
3. 从第一个未通过任务开始执行。
4. 运行该任务的验证命令。
5. 生成 Markdown 报告到 `_runtime/stage_closeout/`。
6. 如果验证失败，停止。
7. 如果验证通过，报告进入 `needs_review` 状态。
8. 人工完成两次全局 review 后，再继续下一项。

为了满足“每一步完成后 review 两次”的要求，脚本默认不会自动连跑所有任务。它每次只推进一个任务，除非显式传入 `-ContinueAfterReviewed` 并且上一个任务的报告已标记两个 review gate 通过。

## 报告格式

每次运行生成一份报告：

```text
_runtime/stage_closeout/YYYYMMDD_HHMMSS_<task_id>.md
```

报告包含：

- 当前 commit。
- 当前分支。
- 工作区是否干净。
- 执行的任务。
- 执行的验证命令。
- 每条命令的 exit code。
- 失败摘要。
- Review Gate 1 checklist。
- Review Gate 2 checklist。
- 下一步建议。

报告不写入 git，除非后续明确决定要归档。

## 验证命令分组

Stage1A 合同验收：

```powershell
python -m pytest -q tests/test_llm_interaction_trace_model.py tests/test_llm_interaction_recorder.py tests/test_llm_service_trace_capture.py tests/test_llm_trace_api.py tests/test_prompt_plan_model.py tests/test_prompt_plan_service.py tests/test_image_prompt_composer.py tests/test_standard_pipeline_storyboard_generation.py
```

Stage1B Workbench / stale / Artifact 验收：

```powershell
python -m pytest -q tests/test_storyboard_workbench_artifact_bridge.py tests/test_storyboard_workbench_api.py tests/test_storyboard_workbench_service.py tests/test_storyboard_workbench_frontend_api.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_frame_regeneration.py tests/test_stale_dependency_models.py tests/test_stale_dependency_repository_contract.py tests/test_stale_dependency_read_model.py tests/test_stale_dependency_propagation.py tests/test_stale_dependency_api.py tests/test_stale_write_integration.py
```

Stage2 AssetBible / SceneCast / projection preview 验收：

```powershell
python -m pytest -q tests/test_asset_bible_models.py tests/test_scene_cast_model.py tests/test_scene_casting_validation.py tests/test_prompt_composer_asset_projection.py tests/test_asset_prompt_plan_composer.py tests/test_asset_bible_api.py tests/test_asset_prompt_plan_projection_ui.py tests/test_stage2_projection_pipeline_ui.py
```

跨边界一致性验收：

```powershell
python -m ruff check pixelle_video api web tests
python -m pytest -q tests/test_standard_pipeline_staged_mode.py tests/test_standard_pipeline_hyperframes_mode.py tests/test_pipeline_text_rendering_contract.py tests/test_text_rendering_preview_service.py tests/test_text_rendering_preview_api.py
git diff --check
```

## 错误处理

运行器遇到以下情况必须停止：

- git 工作区不干净。
- 任一验证命令失败。
- 找不到测试文件。
- Python / pytest / ruff 不可用。
- 上一任务报告未完成两个 review gate。

停止时必须输出：

- 失败任务 ID。
- 失败命令。
- exit code。
- 报告路径。
- 建议下一步。

## 不留技术债约束

- 运行器本身不能修改业务代码。
- 运行器不能把 `planning_snapshot`、Stage2 projection preview 或 stale 状态作为新的事实源。
- 运行器不能绕过人工 review gate。
- 运行器不能使用隐藏全局状态；状态只能来自 git、报告文件和显式参数。
- 报告输出必须在 `_runtime/` 下，避免污染仓库文档。

## 验收标准

- 脚本在工作区干净时能执行第一个 pending 任务并生成报告。
- 脚本在工作区不干净时 fail-fast。
- 任一验证命令失败时 fail-fast，并保留报告。
- 报告包含两轮全局 review checklist。
- 默认模式不会自动越过 review gate。
- 不产生业务代码 diff。
