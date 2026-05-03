# Storyboard Workbench Client Boundary 设计

日期：2026-05-03

## 1. 目标

本设计把当前 Storyboard Workbench 对 `8001` API 的直接依赖降级为部署适配细节，明确分镜产品能力依赖的是 Stage 1A / Stage 1B 服务合同，而不是某个端口。

核心结论：

```text
产品功能依赖 WorkbenchClient 合同
本地 Streamlit 默认走 in-process client
远程部署 / flowgram.ai-main 集成走 HTTP client
8001 只属于 HTTP 部署适配器，不属于产品功能边界
```

## 2. 当前问题

当前分镜功能实际分成三类能力：

1. Home 生成主链路：通过 `PixelleVideoCore.generate_video()` 在 Streamlit 进程内执行，不依赖 HTTP API。
2. Workbench 预览和字段锁定：通过 `st.session_state` 和 snapshot-scoped override draft 执行，不依赖 HTTP API。
3. Workbench 候选图、选图、重抽、依赖雷达：当前由 Streamlit 组件直接调用 `web.utils.storyboard_workbench_api` / `web.utils.stale_api`，默认走 `DEFAULT_API_BASE_URL`，即 `http://localhost:8001/api`。

第三类能力的问题不是端口默认值本身，而是 UI 组件知道了 HTTP transport。这样会导致：

- 本地只启动 Streamlit 时，生成和锁定可用，但候选图 / stale / 重抽不可用。
- 用户会误以为分镜功能依赖 `8001`。
- 未来 `flowgram.ai-main` 远程部署接入时，HTTP 形态和本地产品形态混在同一层。

## 3. 设计原则

### 3.1 产品依赖服务合同，不依赖端口

Workbench 的正式产品依赖是：

```text
StoryboardWorkbenchService
StoryboardWorkbenchStateStore
ArtifactRepository
ArtifactObjectStore
StaleDependencyReadService
TaskManager / generation task reservation
```

端口、URL、HTTP 状态码只属于远程 transport。

### 3.2 UI 只依赖 WorkbenchClient

Streamlit 组件不再直接调用 `httpx` helper，不再直接拼 endpoint，也不再把 `api_base_url` 当成功能上下文。

UI 只调用：

```text
StoryboardWorkbenchClient.list_image_candidates(...)
StoryboardWorkbenchClient.select_image_candidate(...)
StoryboardWorkbenchClient.regenerate_frame_image(...)
StoryboardWorkbenchClient.get_prompt_plan_stale_summary(...)
```

### 3.3 本地默认 in-process，远程显式 HTTP

默认本地模式：

```text
Streamlit UI
  -> InProcessStoryboardWorkbenchClient
  -> services / repositories / state store
```

远程或 flowgram 部署模式：

```text
Streamlit UI 或 flowgram.ai-main
  -> HttpStoryboardWorkbenchClient
  -> http://host:port/api
  -> FastAPI routers
  -> services / repositories / state store
```

`8001` 是 HTTP client 的默认配置，不是 Workbench 组件的默认依赖。

## 4. 新架构

```text
web/components/storyboard_preview.py
  -> render_storyboard_workbench_panel()
  -> StoryboardWorkbenchClient
      -> InProcessStoryboardWorkbenchClient
          -> PixelleVideoCore attached platform dependencies
          -> StoryboardWorkbenchService
          -> StaleDependencyReadService
          -> StoryboardWorkbenchStateStore
          -> TaskManager if configured
      -> HttpStoryboardWorkbenchClient
          -> web.utils.storyboard_workbench_api
          -> web.utils.stale_api
```

新增模块：

```text
web/workbench/client.py
web/workbench/http_client.py
web/workbench/inprocess_client.py
web/state/workbench_client.py
```

保留模块：

```text
web/utils/storyboard_workbench_api.py
web/utils/stale_api.py
```

这些 HTTP helper 会成为 `HttpStoryboardWorkbenchClient` 的内部实现，不再由 UI 组件直接依赖。

## 5. Client 合同

`StoryboardWorkbenchClient` 使用同步方法，适配 Streamlit 当前同步渲染模型：

```python
class StoryboardWorkbenchClient(Protocol):
    def list_image_candidates(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
    ) -> dict: ...

    def select_image_candidate(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
        version_id: str,
        actor_id: str | None = None,
    ) -> dict: ...

    def regenerate_frame_image(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
    ) -> dict: ...

    def get_prompt_plan_stale_summary(
        self,
        *,
        workspace_id: str,
        project_id: str,
        prompt_plan_id: str,
    ) -> dict: ...
```

返回 shape 保持和当前 UI 需要的一致：

- `list_image_candidates()` 返回 `{workspace_id, storyboard_id, frame_id, artifact_id, candidates}`。
- `select_image_candidate()` 返回 `{success, workspace_id, storyboard_id, frame_id, state}`。
- `regenerate_frame_image()` 返回 `{success, task_id, task_type, created, ...}`；如果本地没有 task manager，则返回安全的不可用结果或抛出可捕获异常，由 UI 显示不可用。
- `get_prompt_plan_stale_summary()` 返回 `{success, stale_summary}`。

## 6. In-process Client

`InProcessStoryboardWorkbenchClient` 从本地 Streamlit session 中的 `PixelleVideoCore` 或 platform dependencies 读取依赖。

职责：

- 调用 `StoryboardWorkbenchService.list_image_candidates()`。
- 加载 / 保存 `StoryboardFrameWorkbenchState`。
- 调用 `StoryboardWorkbenchService.select_image_version()`。
- 调用 `StoryboardWorkbenchService.build_frame_image_regeneration_task_request()`，并通过 task manager reserve/reuse；如果 task manager 不存在，则 fail closed。
- 调用 `StaleDependencyReadService.get_target_summary()`。

它不得：

- 拼 HTTP endpoint。
- 依赖 `api_base_url`。
- 暴露本地文件路径。
- 绕过现有 service validation。

## 7. HTTP Client

`HttpStoryboardWorkbenchClient` 保留当前远程能力，内部复用：

```text
web.utils.storyboard_workbench_api
web.utils.stale_api
```

使用场景：

- `flowgram.ai-main` 工作流前端调用 Pixelle 后端。
- 远程部署。
- Streamlit 与 API 服务分进程 / 分机器部署。

配置：

```text
PIXELLE_WORKBENCH_CLIENT_MODE=http
PIXELLE_API_BASE_URL=http://host:8001/api
```

未显式配置时，本地 Streamlit 不应默认走 HTTP。

## 8. Client Factory

新增 `web/state/workbench_client.py`：

```text
resolve_storyboard_workbench_client(session_state)
```

解析规则：

1. `session_state["workbench_client"]` 已有可用 client，则复用。
2. `PIXELLE_WORKBENCH_CLIENT_MODE=http`，返回 HTTP client。
3. `session_state["workbench_client_mode"] == "http"`，返回 HTTP client。
4. 默认返回 in-process client。

HTTP 模式才读取 `api_base_url`。

in-process 模式优先使用当前 Streamlit 已初始化的 `PixelleVideoCore` 及其 attached platform dependencies。

## 9. UI 改造

### 9.1 Storyboard Workbench Panel

当前：

```text
render_storyboard_workbench_panel(..., api_base_url, candidate_loader, candidate_selector, frame_regenerator)
```

改为：

```text
render_storyboard_workbench_panel(..., workbench_client=None)
```

组件内部：

- 用 `resolve_storyboard_workbench_client(ui.session_state)` 获取 client。
- 调用 client 方法。
- 不再接收或传递 `api_base_url`。

测试可传 fake client。

### 9.2 Stale Panel

当前：

```text
render_prompt_plan_stale_panel(..., api_base_url, stale_summary_loader)
```

改为：

```text
render_prompt_plan_stale_panel(..., workbench_client=None)
```

组件内部通过 client 查询 stale summary。

### 9.3 Storyboard Preview

`render_storyboard_preview()` 仍然只负责布局和收集 override。

它传给子组件的是 `workbench_client` 或 context，不传 HTTP base URL。

## 10. Artifact 显示

当前 HTTP 返回 URL，UI 通过 `artifact_url_for_streamlit(url, api_base_url=...)` 转成显示 URL。

新方案：

- HTTP client 返回 remote display URL，仍可使用 `artifact_url_for_streamlit()`。
- In-process client 可返回受控 relative URL 或可显示对象。
- 第一阶段为避免扩大范围，in-process client 可以继续返回 service 生成的受控 URL；如果 object store 返回 relative `/api/files/...`，UI 在本地模式可把它作为相对资源交给后续 artifact display adapter 处理。

注意：不得把 Windows 本地路径、workflow path、provider URL 暴露给 UI。

## 11. flowgram.ai-main 边界

`D:\demo1\Pixelle\Pixelle\flowgram.ai-main` 属于未来工作流编排或远程部署调用方。

它应接入：

```text
HttpStoryboardWorkbenchClient / FastAPI API
```

而不是影响本地 Streamlit 默认实现。

因此：

- flowgram 使用 `8001` 或其他 API endpoint 是合理的。
- 本地 Pixelle 产品体验不应因为没有 `8001` 服务而丢失 Workbench 核心能力。
- 同一套 WorkbenchClient 合同保证两种部署形态行为一致。

## 12. 测试策略

必须新增 / 调整测试：

1. Client factory 默认返回 in-process client。
2. 配置 `PIXELLE_WORKBENCH_CLIENT_MODE=http` 时返回 HTTP client。
3. `render_storyboard_workbench_panel()` 不再需要 `api_base_url`，使用 fake client 能渲染候选图。
4. `render_prompt_plan_stale_panel()` 不再需要 `api_base_url`，使用 fake client 能渲染 stale panel。
5. HTTP client 复用现有 endpoint builder 和 response validation。
6. In-process client 调用 service / state store，不调用 `httpx`。
7. 本地 client 缺少 task manager 时，重抽 fail closed，UI 显示不可用，不崩溃。
8. `rg` 或源码测试确认 Workbench UI 组件不直接 import `web.utils.storyboard_workbench_api` / `web.utils.stale_api`。

## 13. 非目标

本设计不做：

- 重写 FastAPI router。
- 移除 HTTP API。
- 实现 production repository adapters。
- 修改 Stage 2 preview/apply 合同。
- 把 flowgram.ai-main 纳入当前仓库编译或运行链路。
- 立刻重写 AssetBible / Stage2 所有 HTTP client；本设计先收敛 Storyboard Workbench。

## 14. 验收标准

完成后必须满足：

1. Storyboard Workbench UI 默认不依赖 `8001`。
2. UI 组件不直接调用 HTTP helper。
3. HTTP 模式仍可通过 `PIXELLE_API_BASE_URL` 使用 `8001` 或远程 API。
4. 本地模式候选图、选图、stale 查询通过 in-process client 调用服务合同。
5. 所有返回到 UI 的 artifact URL / metadata 仍经过安全过滤。
6. 测试覆盖本地模式、HTTP 模式、缺失依赖、无端口硬编码回归。

## 15. 自检

- Placeholder scan：无 TBD / TODO / 未定项。
- Scope check：只处理 Storyboard Workbench client boundary，不扩展到 Stage2 apply 或 flowgram 实现。
- Boundary check：`8001` 被限定为 HTTP client 配置，不再是 UI 产品功能依赖。
- Consistency check：本地和远程都通过同一个 `StoryboardWorkbenchClient` 合同进入 Workbench 能力。
