# Stage 1B Workbench Stale 面板设计

## Goal

把已经完成的 Stage 1B stale 依赖读取能力接入真实前端 Workbench/Storyboard Preview 区域，让用户在检查分镜计划时能看到当前 PromptPlan 是否已经被上游 AssetBible/SceneCast 改动影响。

本设计只做只读依赖雷达展示，不触发生成、不触发重抽、不保存 PromptPlan、不写 stale 状态，也不把本地路径、workflow path、provider URL 暴露到前端。

## Current State

已经完成：

- `web/components/stale_panel.py`：只读 stale summary 渲染组件，已过滤 `workflow_path`、`provider_url`、`local_path`。
- `web/utils/stale_api.py`：stale target 和 downstream 的前端 API client，已校验 public ID 和响应 shape。
- `api/routers/stale_dependencies.py`：提供按 `workspace_id + project_id + target` 查询 stale summary 的只读接口。
- `web/components/storyboard_preview.py`：当前 Storyboard Preview/Workbench 入口，基于 `planning_snapshot.storyboard_generation.frames` 渲染逐帧编辑和锁定字段。
- `web/components/storyboard_planning_controls.py`：在高级分镜规划控件中调用 preview renderer。

当前缺口：

- 前端 preview 还没有把 stale summary 挂到每帧上下文里。
- Preview renderer 目前只接收 `planning_snapshot`，无法获得 `api_base_url`、`workspace_id`、`project_id` 等 stale 查询上下文。
- Workbench API 已具备候选图和重抽接口，但当前 Web UI 尚未渲染真实候选图工作台；因此本阶段应优先接入现有 Storyboard Preview，而不是新建未闭环页面。

## Recommended Approach

采用“计划级只读依赖雷达”方案：

1. 新增一个 focused frontend component：`web/components/storyboard_workbench_stale.py`。
2. 组件从 preview rows 中读取唯一 `prompt_plan_id`，通过 `web.utils.stale_api.get_stale_target_summary()` 查询 `target_type=prompt_plan`。
3. 查询成功时复用 `render_stale_target_panel()` 渲染统一的 stale summary。
4. 查询上下文缺失或 API 异常时只显示短 caption，不抛出到顶层 UI，不阻断分镜编辑。
5. 组件不渲染按钮，不调用 regenerate/select/save/generate API，不写入 `st.session_state` 的业务状态。

放弃的备选方案：

- 逐帧 stale radar：看起来更贴近帧，但当前 stale target 是 `prompt_plan`，同一个 planning snapshot 下所有帧通常共享同一个 PromptPlan；逐帧查询会重复 HTTP 请求和重复展示，尤其 Streamlit expander 折叠时仍会执行内容。
- 后端直接把 stale summary 合并进 Workbench response：长期更干净，但当前 Web UI 还没有真实 Workbench 列表页面，会扩大后端 API contract，超出本次只读集成目标。

## Data Flow

1. 视频生成完成后，现有逻辑把 `result.storyboard.planning_snapshot` 存入 `st.session_state["storyboard_preview_snapshot"]`。
2. 左侧高级分镜控件调用 `render_storyboard_advanced_controls()`，再调用 `render_storyboard_preview()`。
3. `render_storyboard_preview()` 继续负责逐帧字段编辑和 lock override 收集。
4. 新组件在 preview expander 顶部按唯一 PromptPlan 渲染 stale radar，再渲染逐帧字段编辑区域。
5. stale radar 需要的上下文来自 session state 或调用方显式传入：
   - `api_base_url`，默认 `http://localhost:8000/api`。
   - `workspace_id`，默认从 `st.session_state["workspace_id"]` 读取。
   - `project_id`，默认从 `st.session_state["project_id"]` 读取。
   - `prompt_plan_id`，来自每帧 preview row 的 `plan_id`。

## UI Placement

Stale 面板应放在 Storyboard Preview expander 内部、逐帧卡片列表之前。

原因：

- PromptPlan stale 是计划级状态，不应在每个 frame card 里重复展示同一份结果。
- 用户在开始编辑 frame override 前先看到该 planning snapshot 是否过期。
- 避免一个 snapshot 下 N 个 frame 触发 N 次相同 HTTP 查询。
- 未来接入候选图 Workbench 时，image artifact 级 stale 面板应放到候选图区域旁边，并使用 `target_type=image_artifact`，不复用 PromptPlan 面板的 UI 位置。

视觉风格保持现有 Streamlit/Storyboard 控件体系，不引入新的大胆主题。这里的目标是明确状态和低干扰，而不是建立独立视觉品牌。

## Public Boundary And Safety

- 允许展示 public ID、target type、reason code、upstream public ID、upstream version。
- 禁止展示 `workflow_path`、`provider_url`、`local_path`、Windows 路径、provider endpoint、object store 私密路径。
- 前端必须在调用 HTTP 前验证 public ID；已有 `stale_api` 会做该校验，组件层还要对缺失上下文 fail closed。
- API 异常、shape 异常或网络异常只显示 `stale.unavailable` caption，不打印异常详情到 UI。

## Stage Boundaries

- Stage 1A 继续拥有 PromptPlan 定义和创建。
- Stage 1B 消费 PromptPlan 并展示 stale 状态。
- Stage 2 projection preview 仍然 preview-only，不保存 projected PromptPlan，不写 stale，不接主生成链路。
- 标题和字幕渲染链路继续独立，不进入 PromptPlan、AssetBible StyleProfile 或本 stale 面板。

## Tests

必须覆盖：

- 有完整上下文和 `prompt_plan_id` 时，组件调用 stale target API 并渲染 `render_stale_target_panel()`。
- 缺少 `project_id`、`workspace_id` 或 `prompt_plan_id` 时，不调用 API，只显示 caption。
- API 失败时，不泄露异常详情，不阻断 preview。
- `render_storyboard_preview()` 能把当前唯一 `plan_id` 传给 stale renderer，且不影响原有 override payload。
- 同一个 preview snapshot 只对同一个 `prompt_plan_id` 渲染一次 stale radar。
- UI 渲染结果不包含 regenerate/generate/save 按钮，也不包含本地路径、workflow path、provider URL。

## Out Of Scope

- 不新增自动重抽按钮。
- 不接入 candidate image gallery。
- 不写入 stale mark。
- 不修改 PromptPlan schema。
- 不修改 Stage 2 projection persistence 边界。
- 不修改标题/字幕相关实现。

## Self Review

- Spec coverage：覆盖真实 UI 挂载点、数据流、安全边界、失败语义、Stage 边界和测试要求。
- Placeholder scan：无 TBD、TODO 或未定项。
- Scope check：本设计只做 Stage 1B 前端只读 stale 展示，不扩大到生成、重抽、保存或 Stage 2 persistence。
- Ambiguity check：明确使用 `prompt_plan` stale target，明确面板位置在 preview expander 顶部且按唯一 PromptPlan 渲染一次，明确上下文缺失时 fail closed。
