# Storyboard Workbench Client Boundary 设计

日期：2026-05-03

## 1. 目标

本设计把 Storyboard Workbench 对 `8001` API 的直接依赖降级为部署适配细节，明确分镜产品能力依赖的是 Workbench 服务合同，而不是某个端口、某个 URL 拼接规则或某个前端 helper。

核心结论：

```text
产品功能依赖 StoryboardWorkbenchClient 合同
本地 Streamlit 默认走 in-process client
远程部署 / flowgram.ai-main 集成走 HTTP client
8001 只属于 HTTP 部署适配器，不属于产品功能边界
```

本次设计必须从源头解决 4 个边界问题：

1. `client factory` 不能缓存未配置完成的本地 client。
2. `artifact` 显示合同不能再间接依赖 `/api/files/...` 和 `api_base_url`。
3. `regenerate` 不能再假设本地或 HTTP 后端一定有 `task_manager`；必须转成显式 capability。
4. FastAPI router 不能再直接 reach-through 到 `request.app.state.task_manager`；再生成任务提交必须通过一等依赖 `StoryboardWorkbenchTaskSubmitter`。

本设计不接受“本地重抽图先禁用，以后再接”的过渡方案。可执行目标是：本地和 HTTP 都通过同一个窄的 task submitter 抽象提交 frame image regeneration；只有运行时确实未配置 submitter 时，capability 才报告不可用。

通俗地说：不是把坏掉的按钮藏起来，而是把按钮真正接到正确的电路上；如果电路没有装，系统要明确说“没装”，不能假装能用。

## 2. 当前根因

当前分镜功能实际分成四类能力：

1. Home 生成主链路：通过 `PixelleVideoCore.generate_video()` 在 Streamlit 进程内执行，不依赖 HTTP API。
2. Workbench 预览和字段锁定：通过 `st.session_state` 和 snapshot-scoped override draft 执行，不依赖 HTTP API。
3. Workbench 候选图、选图、stale 查询：当前由 Streamlit 组件直接调用 `web.utils.storyboard_workbench_api` / `web.utils.stale_api`，默认走 `DEFAULT_API_BASE_URL`，即 `http://localhost:8001/api`。
4. Workbench 图片显示：当前 UI 通过 `artifact_url_for_streamlit(url, api_base_url=...)` 把相对 URL 拼成展示 URL，因此即使操作走本地，图片显示仍可能绕回 API origin。

现有问题不是“默认端口写成了 8001”，而是 UI、transport、显示、安全过滤、任务提交混在同一层，导致：

- 本地只启动 Streamlit 时，分镜能力呈现为“部分可用、部分隐式依赖 API”。
- 用户会误以为分镜功能依赖 `8001`。
- `flowgram.ai-main` 远程形态和本地产品形态混在同一层。
- `resolve_storyboard_workbench_client()` 如果在 `PixelleVideoCore` 就绪前被调用，可能缓存一个后续不会自动恢复的坏 client。
- `regenerate` 在本地模式下可能根本没有执行通道，但 UI 仍展示可点击动作。
- HTTP client 如果硬编码 `can_regenerate_frame_image=True`，会在后端 task submitter 缺失时制造另一个假能力。
- FastAPI router 直接读取 `request.app.state.task_manager`，使任务系统成为隐藏依赖，无法被本地 in-process client 和 capability 查询一致复用。

## 3. 设计原则

### 3.1 产品依赖服务合同，不依赖端口

Workbench 的正式产品依赖是：

```text
StoryboardWorkbenchService
StoryboardWorkbenchStateStore
ArtifactRepository
ArtifactObjectStore 或其本地可读适配器
StaleDependencyReadService
StoryboardWorkbenchTaskSubmitter
```

端口、URL、HTTP 状态码只属于远程 transport。

### 3.2 UI 只依赖 WorkbenchClient 合同和显示合同

Streamlit 组件不再直接调用 `httpx` helper，不再直接拼 endpoint，也不再把 `api_base_url` 当成功能上下文。

UI 只调用：

```text
StoryboardWorkbenchClient.get_capabilities(...)
StoryboardWorkbenchClient.list_image_candidates(...)
StoryboardWorkbenchClient.select_image_candidate(...)
StoryboardWorkbenchClient.regenerate_frame_image(...)
StoryboardWorkbenchClient.get_prompt_plan_stale_summary(...)
```

并只消费 client 产出的安全显示 payload，而不是自己解析相对 URL。

### 3.3 本地默认 in-process，远程显式 HTTP

默认本地模式：

```text
Streamlit UI
  -> InProcessStoryboardWorkbenchClient
  -> PixelleVideoCore attached platform dependencies
  -> StoryboardWorkbenchTaskSubmitter
  -> TaskManager.reserve_or_reuse_generation_task(...)
```

远程或 flowgram 部署模式：

```text
Streamlit UI / flowgram.ai-main
  -> HttpStoryboardWorkbenchClient
  -> http://host:port/api
  -> FastAPI routers
  -> StoryboardWorkbenchTaskSubmitter
  -> TaskManager.reserve_or_reuse_generation_task(...)
```

`8001` 是 HTTP client 的默认配置，不是 Workbench 组件的默认依赖。

### 3.4 不缓存未配置完成的 client

factory 必须把“模式解析”和“实例缓存”拆开处理：

- HTTP client 可以按 `mode + api_base_url` 缓存。
- in-process client 只能在拿到真实 `PixelleVideoCore` 后缓存。
- 没有 `pixelle_video` 时，不得缓存一个“稍后再补”的本地 client。
- 如果 `PixelleVideoCore` 因配置变化被重建，factory 必须感知 identity 变化并重建 client。

### 3.5 能力必须由真实后端依赖产生，不能硬编码

`regenerate` 属于运行时能力，不应通过“按钮一直可点，点击后报错”表达。

规则：

- client 提供明确 capability。
- in-process client 从 `PixelleVideoCore.storyboard_workbench_task_submitter` 判断能力。
- HTTP client 从 FastAPI capability endpoint 判断能力，不得硬编码为 true。
- UI 根据 capability 禁用不可用动作，并展示简短原因。
- 如果调用时 submitter 消失，client 返回结构化 unavailable 结果或 router 返回 503；这是并发兜底，不是主路径。

## 4. 目标架构

```text
api/workbench/task_submitter.py
  -> StoryboardWorkbenchTaskSubmitter
  -> TaskManagerStoryboardWorkbenchTaskSubmitter
  -> StoryboardWorkbenchCapabilities

api/app.py
  -> build_task_manager(...)
  -> configure_platform_dependencies(..., task_manager=manager)
  -> attach storyboard_workbench_task_submitter to app.state

web/state/session.py
  -> get_or_create_platform_dependencies()
  -> attach storyboard_workbench_task_submitter to PixelleVideoCore

api/routers/storyboard_workbench.py
  -> get_storyboard_workbench_capabilities()
  -> request_frame_image_regeneration(..., submitter=...)

web/pages/3_🧭_Storyboard_Workbench.py
  -> resolve_workbench_client_mode(...)
  -> if in-process: get_pixelle_video()
  -> resolve_storyboard_workbench_client(...)
  -> render_storyboard_preview(..., workbench_client=client)

web/components/storyboard_preview.py
  -> render_prompt_plan_stale_panel(..., workbench_client=client)
  -> render_storyboard_workbench_panel(..., workbench_client=client)

web/workbench/http_client.py
  -> capability endpoint
  -> web.utils.storyboard_workbench_api
  -> web.utils.stale_api
  -> convert remote artifact url -> display payload

web/workbench/inprocess_client.py
  -> StoryboardWorkbenchService
  -> StoryboardWorkbenchStateStore
  -> StaleDependencyReadService
  -> LocalReadableArtifactSource
  -> StoryboardWorkbenchTaskSubmitter
```

现有 Stage 1 生成链路已经通过 `StoryboardWorkbenchArtifactBridge` 把生成出的 frame media 注册为 Workbench artifact，并把 `workbench_state` 写回 snapshot / state store。`InProcessStoryboardWorkbenchClient` 是这些已注册 artifact 的消费方，不重新实现 artifact 注册语义。

新增模块：

```text
api/workbench/__init__.py
api/workbench/task_submitter.py
web/workbench/client.py
web/workbench/display.py
web/workbench/http_client.py
web/workbench/inprocess_client.py
web/workbench/inprocess_protocols.py
web/state/workbench_client.py
```

保留模块：

```text
web/utils/storyboard_workbench_api.py
web/utils/stale_api.py
web/utils/artifact_display_urls.py
```

这些 helper 只作为 `HttpStoryboardWorkbenchClient` 的内部实现，不再由 UI 组件直接依赖。

Client 生命周期边界只存在于 `web/pages/3_🧭_Storyboard_Workbench.py` 与 `web/state/workbench_client.py`。`web/components/storyboard_preview.py`、`web/components/storyboard_workbench_panel.py`、`web/components/storyboard_workbench_stale.py` 只接收并使用传入的 `workbench_client`，不再调用 factory。

## 5. Task Submitter 合同

新增一等后端抽象：

```python
class StoryboardWorkbenchTaskSubmitter(Protocol):
    async def reserve_frame_image_regeneration(
        self,
        *,
        generation_fingerprint: str,
        request_params: Mapping[str, Any],
    ) -> StoryboardWorkbenchTaskSubmission: ...
```

返回对象使用明确字段，不让 web/client 层理解 `TaskManager` 的内部 outcome：

```python
@dataclass(frozen=True)
class StoryboardWorkbenchTaskSubmission:
    task_id: str
    task_type: str
    created: bool
    reused_reason: str | None = None
```

标准实现：

```python
class TaskManagerStoryboardWorkbenchTaskSubmitter:
    def __init__(self, task_manager: TaskManager) -> None: ...
```

职责：

- 唯一了解 `TaskType.FRAME_IMAGE_REGENERATION`。
- 唯一调用 `TaskManager.reserve_or_reuse_generation_task(...)`。
- 给 FastAPI router 和 Streamlit in-process client 复用。

通俗地说：`task_manager` 是“发动机”，`StoryboardWorkbenchTaskSubmitter` 是“这辆车允许 Workbench 使用的油门踏板”。页面、client、router 都不应该直接摸发动机。

## 6. Capability 合同

新增 capability 数据结构：

```python
@dataclass(frozen=True)
class StoryboardWorkbenchCapabilities:
    can_regenerate_frame_image: bool
    regenerate_unavailable_reason: str | None = None
```

HTTP schema：

```python
class StoryboardWorkbenchCapabilitiesResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    can_regenerate_frame_image: bool
    regenerate_unavailable_reason: str | None = None
```

新增 endpoint：

```text
GET /api/storyboards/workbench/capabilities
```

规则：

- FastAPI 通过 `request.app.state.storyboard_workbench_task_submitter` 判断 `can_regenerate_frame_image`。
- HTTP client 每次或带短生命周期缓存查询 capability endpoint；本计划采用无缓存查询，先保证行为真实。
- in-process client 通过 `pixelle_video.storyboard_workbench_task_submitter` 判断 capability。
- 缺少 submitter 时返回：

```python
{
    "can_regenerate_frame_image": False,
    "regenerate_unavailable_reason": "task submitter is not configured",
}
```

## 7. Client 合同

### 7.1 能力合同

`StoryboardWorkbenchClient` 需要显式暴露 capability：

```python
class StoryboardWorkbenchClient(Protocol):
    def get_capabilities(self) -> dict[str, Any]: ...
```

当前最少包含：

```python
{
    "can_regenerate_frame_image": bool,
    "regenerate_unavailable_reason": str | None,
}
```

### 7.2 显示合同

候选图不能再把“原始 URL”直接暴露给 UI。client 必须返回安全显示 payload：

```python
{
    "kind": "url" | "bytes",
    "url": "https://..." ,        # kind=url 时必填，必须是可直接展示的绝对 URL
    "data": b"...",               # kind=bytes 时必填
    "mime_type": "image/png",     # kind=bytes 时必填
}
```

约束：

- HTTP client 可以返回 `kind=url`。
- in-process client 必须返回 `kind=bytes` 或其他无需 API origin 的本地可显示 payload。
- in-process client 不得把 `/api/files/...`、`localhost:8001`、Windows 路径、workflow path 暴露给 UI。
- UI 不再读取 `candidate["url"]`，只读取 `candidate["image_display"]`。

### 7.3 操作合同

```python
class StoryboardWorkbenchClient(Protocol):
    def get_capabilities(self) -> dict[str, Any]: ...

    def list_image_candidates(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
    ) -> dict[str, Any]: ...

    def select_image_candidate(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
        version_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]: ...

    def regenerate_frame_image(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
    ) -> dict[str, Any]: ...

    def get_prompt_plan_stale_summary(
        self,
        *,
        workspace_id: str,
        project_id: str,
        prompt_plan_id: str,
    ) -> dict[str, Any]: ...
```

返回 shape：

- `list_image_candidates()` 返回 `{workspace_id, storyboard_id, frame_id, artifact_id, candidates}`，其中每个 candidate 包含 `image_display`。
- `select_image_candidate()` 返回 `{success, workspace_id, storyboard_id, frame_id, state}`。
- `regenerate_frame_image()` 在可用时返回 `{success, task_id, task_type, created, ...}`；在运行时依赖消失时返回 `{success: False, code: "regenerate_unavailable", reason: ...}`。
- `get_prompt_plan_stale_summary()` 返回 `{success, stale_summary}`。

## 8. Platform Dependencies 与生命周期

`PlatformDependencies` 必须新增：

```python
storyboard_workbench_task_submitter: StoryboardWorkbenchTaskSubmitter | None = None
```

构建规则：

- `build_platform_dependencies(config, task_manager=None)` 接收可选 `task_manager`。
- 有 `task_manager` 时构造 `TaskManagerStoryboardWorkbenchTaskSubmitter(task_manager)`。
- 没有 `task_manager` 时不直接创建隐藏全局 task manager；返回 submitter 为 `None`，并由 capability 明确暴露不可用。
- `configure_platform_dependencies(app, config, task_manager=manager)` 在 API lifespan 中接收已启动前的 manager，并把 submitter 挂到 `app.state`。
- `web.state.session.get_pixelle_video()` 使用 `get_or_create_local_platform_dependencies()`。为了本地 Streamlit 也具备一等 regenerate 能力，该入口必须显式创建并持有本地 `TaskManager` 与 submitter，并注册 session 清理或进程级清理。

本地 Streamlit 的最佳实践不是从 `PixelleVideoCore` 偷读 `task_manager`，而是在平台依赖层显式注入 `storyboard_workbench_task_submitter`。这样 UI、client、service 都只看自己的合同。

## 9. In-process Client

`InProcessStoryboardWorkbenchClient` 从当前 Streamlit session 的 `PixelleVideoCore` 读取依赖。

职责：

- 调用 `StoryboardWorkbenchService.list_image_candidates()`。
- 消费 `StoryboardWorkbenchArtifactBridge` 已注册的 artifact / version / storage key，不重复创建 Workbench artifact。
- 通过 `LocalReadableArtifactSource` 把 `storage_key` 解析成可直接供 Streamlit 展示的安全 payload。
- 加载 / 保存 `StoryboardFrameWorkbenchState`。
- 调用 `StoryboardWorkbenchService.select_image_version()`。
- 调用 `StaleDependencyReadService.get_target_summary()`。
- 通过 `StoryboardWorkbenchTaskSubmitter` 提交 `regenerate` 任务。

它不得：

- 拼 HTTP endpoint。
- 依赖 `api_base_url`。
- 暴露本地文件路径给 UI。
- 直接 reach-through 到 `core.task_manager`。

### 9.1 本地显示依赖

本地显示路径不再消费通用 `ArtifactObjectStore.get_file_url()` 产出的 URL。

当前 `StoryboardWorkbenchService.list_image_candidates()` 仍会为了既有服务合同生成受控 `url` 字段；这个字段保留在 service / HTTP 适配层，不再进入本地 UI 显示合同。in-process client 必须丢弃该 `url`，只从 candidate 的 `storage_key` 通过本地可读协议加载 bytes，从边界上保证 UI 不回落到 API origin。

新增一个窄协议，供 in-process client 使用：

```python
class LocalReadableArtifactSource(Protocol):
    async def get_local_file_uri(self, storage_key: str) -> str: ...
```

client 通过该协议读取受控对象，再转成 bytes payload。这样本地显示依赖的是“受控本地对象可读能力”，不是 API origin。

### 9.2 regenerate 依赖

本地 regenerate 不再假设 `PixelleVideoCore` 上挂了 `task_manager`。它只读取：

```python
pixelle_video.storyboard_workbench_task_submitter
```

规则：

- 有 submitter：`can_regenerate_frame_image=True`，调用 submitter。
- 无 submitter：`can_regenerate_frame_image=False`，UI 禁用按钮，直接调用返回结构化 unavailable。
- 禁止通过 `api.tasks.manager.task_manager` 全局变量或 `core.task_manager` 临时接线。

## 10. HTTP Client

`HttpStoryboardWorkbenchClient` 保留当前远程能力，内部复用：

```text
web.utils.storyboard_workbench_api
web.utils.stale_api
web.utils.artifact_display_urls
```

职责变化：

- UI 不再调用 `artifact_url_for_streamlit()`。
- HTTP client 在内部把 API 返回的 URL 规范化为绝对展示 URL，然后写入 `image_display={"kind":"url", ...}`。
- HTTP client 通过 `GET /api/storyboards/workbench/capabilities` 获取 `regenerate` 能力，不硬编码。
- UI 只消费 client 处理后的显示 payload。

使用场景：

- `flowgram.ai-main` 调用 Pixelle 后端。
- 远程部署。
- Streamlit 与 API 分进程 / 分机器部署。

配置：

```text
PIXELLE_WORKBENCH_CLIENT_MODE=http
PIXELLE_API_BASE_URL=http://host:8001/api
```

未显式配置时，本地 Streamlit 不应默认走 HTTP。

## 11. Client Factory 与生命周期

新增 `web/state/workbench_client.py`：

```text
resolve_workbench_client_mode(session_state)
resolve_storyboard_workbench_client(session_state, pixelle_video=None)
```

解析规则：

1. `PIXELLE_WORKBENCH_CLIENT_MODE=http` 或 `session_state["workbench_client_mode"] == "http"` 时返回 HTTP mode。
2. 否则默认返回 in-process mode。

缓存规则：

1. HTTP client 按 `mode + api_base_url` 缓存。
2. in-process client 按 `mode + id(pixelle_video)` 缓存。
3. `pixelle_video is None` 时不得缓存 in-process client。
4. 已缓存 client 与当前 cache key 不一致时，必须丢弃并重建。

页面规则：

- Workbench page 先解析 mode。
- mode 为 `inprocess` 时，先调用 `get_pixelle_video()`，再交给 factory。
- 这样可以从源头避免“未配置完成的本地 client 被缓存”。

## 12. UI 改造

### 12.1 Storyboard Workbench Panel

当前：

```text
render_storyboard_workbench_panel(..., api_base_url, candidate_loader, candidate_selector, frame_regenerator)
```

改为：

```text
render_storyboard_workbench_panel(..., workbench_client=None)
```

组件内部：

- 接收 page / preview 注入的 `workbench_client`。
- 如果缺少 client，则 fail closed：显示不可用提示，不直接回退到 HTTP helper。
- 调用 client 方法。
- 渲染 `candidate["image_display"]`。
- 根据 `client.get_capabilities()` 禁用或启用 regenerate。
- 不再接收或传递 `api_base_url`。

### 12.2 Stale Panel

当前：

```text
render_prompt_plan_stale_panel(..., api_base_url, stale_summary_loader)
```

改为：

```text
render_prompt_plan_stale_panel(..., workbench_client=None)
```

只通过 client 查询 stale summary。

### 12.3 Storyboard Preview / Page

`render_storyboard_preview()` 和 `3_🧭_Storyboard_Workbench.py` 只负责：

- 预览布局
- 锁定字段收集
- 解析本地 / 远程 mode
- 注入 `workbench_client`

它们不再传递 `api_base_url` 给 Workbench 子组件。

## 13. flowgram.ai-main 边界

`D:\demo1\Pixelle\Pixelle\flowgram.ai-main` 属于未来工作流编排或远程部署调用方。

它应接入：

```text
HttpStoryboardWorkbenchClient / FastAPI API
```

而不是影响本地 Streamlit 默认实现。

因此：

- flowgram 使用 `8001` 或其他 API endpoint 是合理的。
- 本地 Pixelle 产品体验不应因为没有 `8001` 服务而丢失候选图、选图、stale 和 regenerate 核心能力。
- 同一套 `StoryboardWorkbenchClient` 合同保证本地和远程形态行为一致。

## 14. 测试策略

必须新增 / 调整测试：

1. `TaskManagerStoryboardWorkbenchTaskSubmitter` 把 frame image regeneration 请求提交到 `TaskManager.reserve_or_reuse_generation_task(...)`，并返回稳定 submission shape。
2. `PlatformDependencies` 在 API lifespan 和 Streamlit session 中都挂载 `storyboard_workbench_task_submitter`。
3. FastAPI capability endpoint 根据 submitter 是否存在返回真实能力。
4. FastAPI regenerate endpoint 通过 submitter，不再直接读取 `request.app.state.task_manager`。
5. HTTP client 从 capability endpoint 读取能力，不硬编码 true。
6. HTTP client 把 API 返回的相对 URL 规范化为 `image_display={"kind":"url", ...}`，UI 不再自己拼 URL。
7. client factory 默认返回 in-process mode，但在 `pixelle_video` 缺失时不缓存坏 client。
8. client factory 在 `PixelleVideoCore` identity 变化时重建 in-process client。
9. Workbench page 在本地 mode 下先 `get_pixelle_video()`，再 resolve client。
10. `render_storyboard_workbench_panel()` 不再需要 `api_base_url`，使用 fake client 和 `image_display={"kind":"bytes"}` 能渲染候选图。
11. `render_prompt_plan_stale_panel()` 不再需要 `api_base_url`，使用 fake client 能渲染 stale panel。
12. 本地 client 调用 service / state store / local-readable artifact source / submitter，不调用 `httpx`。
13. source-level regression 确认 Workbench UI 组件不再 import：
    - `web.utils.storyboard_workbench_api`
    - `web.utils.stale_api`
    - `web.utils.artifact_display_urls`
    - `httpx`
    - `localhost:8001`
14. 本地 mode 的 Workbench UI 源码和测试不再把 `api_base_url` 当能力输入；`api_base_url` 只能出现在 HTTP client / HTTP helper / 显式 HTTP mode 测试中。

## 15. 非目标

本设计不做：

- 移除 HTTP API。
- 重写 `flowgram.ai-main`。
- 顺手改动 AssetBible / Stage2 所有 HTTP client。
- 通过 reach-through `task_manager` 临时打通本地 regenerate。
- 重写整个任务系统或引入新的队列后端。

本设计只收敛 Storyboard Workbench 的产品边界，并把 regenerate 的依赖关系转成显式、可复用、可测试的能力模型。

## 16. 验收标准

完成后必须满足：

1. Storyboard Workbench UI 默认不依赖 `8001`。
2. UI 组件不直接调用 HTTP helper，也不直接处理 `artifact_url_for_streamlit()`。
3. HTTP 模式仍可通过 `PIXELLE_API_BASE_URL` 使用 `8001` 或远程 API。
4. 本地模式候选图、选图、stale 查询通过 in-process client 调用服务合同。
5. 本地模式候选图展示不依赖 `api_base_url`，不依赖 `/api/files/...`。
6. factory 不缓存未配置完成的 in-process client。
7. 本地与 HTTP regenerate 都通过 `StoryboardWorkbenchTaskSubmitter`，不直接读取 task manager。
8. capability 来自真实 submitter 配置；HTTP client 不硬编码 regenerate 可用。
9. 所有返回到 UI 的 artifact 显示数据仍经过安全过滤。
10. 测试覆盖本地模式、HTTP 模式、client 生命周期、显示合同、submitter 注入、capability endpoint、缺失依赖和无端口硬编码回归。

## 17. 自检

- Placeholder scan：无未完成占位内容。
- Scope check：只处理 Storyboard Workbench client boundary，不扩展到 AssetBible / Stage2。
- Boundary check：`8001` 被限定为 HTTP client 配置，不再是 UI 产品功能依赖。
- Lifecycle check：factory 不缓存未初始化完成的 in-process client。
- Display check：本地显示合同不再回落到 `api_base_url`。
- Capability check：regenerate 通过真实 submitter 和 capability endpoint 暴露，不再保留假按钮。
- Debt check：不接受“本地 regenerate 本期先禁用”的过渡债；本地和 HTTP 都走同一 submitter 抽象。
