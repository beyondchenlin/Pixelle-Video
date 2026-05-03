# Storyboard Workbench Client Boundary 设计

日期：2026-05-03

## 1. 目标

本设计把当前 Storyboard Workbench 对 `8001` API 的直接依赖降级为部署适配细节，明确分镜产品能力依赖的是 Workbench 服务合同，而不是某个端口、某个 URL 拼接规则或某个前端 helper。

核心结论：

```text
产品功能依赖 StoryboardWorkbenchClient 合同
本地 Streamlit 默认走 in-process client
远程部署 / flowgram.ai-main 集成走 HTTP client
8001 只属于 HTTP 部署适配器，不属于产品功能边界
```

本次设计同时修正 3 个此前遗漏的边界：

1. `client factory` 不能缓存未配置完成的本地 client。
2. `artifact` 显示合同不能再间接依赖 `/api/files/...` 和 `api_base_url`。
3. `regenerate` 不能再假设本地一定挂了 `task_manager`；必须转成显式 capability。

## 2. 当前根因

当前分镜功能实际分成四类能力：

1. Home 生成主链路：通过 `PixelleVideoCore.generate_video()` 在 Streamlit 进程内执行，不依赖 HTTP API。
2. Workbench 预览和字段锁定：通过 `st.session_state` 和 snapshot-scoped override draft 执行，不依赖 HTTP API。
3. Workbench 候选图、选图、stale 查询：当前由 Streamlit 组件直接调用 `web.utils.storyboard_workbench_api` / `web.utils.stale_api`，默认走 `DEFAULT_API_BASE_URL`，即 `http://localhost:8001/api`。
4. Workbench 图片显示：当前 UI 通过 `artifact_url_for_streamlit(url, api_base_url=...)` 把相对 URL 拼成展示 URL，因此即使操作走本地，图片显示仍可能绕回 API origin。

现有问题不是“默认端口写成了 8001”，而是 UI 组件知道了 transport 和显示细节，导致：

- 本地只启动 Streamlit 时，分镜能力呈现为“部分可用、部分隐式依赖 API”。
- 用户会误以为分镜功能依赖 `8001`。
- `flowgram.ai-main` 远程形态和本地产品形态混在同一层。
- `resolve_storyboard_workbench_client()` 如果在 `PixelleVideoCore` 就绪前被调用，可能缓存一个后续不会自动恢复的坏 client。
- `regenerate` 在本地模式下可能根本没有执行通道，但 UI 仍展示可点击动作。

## 3. 设计原则

### 3.1 产品依赖服务合同，不依赖端口

Workbench 的正式产品依赖是：

```text
StoryboardWorkbenchService
StoryboardWorkbenchStateStore
ArtifactRepository
ArtifactObjectStore 或其本地可读适配器
StaleDependencyReadService
StoryboardWorkbenchTaskSubmitter（可选能力）
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
  -> PixelleVideoCore attached dependencies
```

远程或 flowgram 部署模式：

```text
Streamlit UI / flowgram.ai-main
  -> HttpStoryboardWorkbenchClient
  -> http://host:port/api
  -> FastAPI routers
  -> services / repositories / state store
```

`8001` 是 HTTP client 的默认配置，不是 Workbench 组件的默认依赖。

### 3.4 不缓存未配置完成的 client

factory 必须把“模式解析”和“实例缓存”拆开处理：

- HTTP client 可以按 `mode + api_base_url` 缓存。
- in-process client 只能在拿到真实 `PixelleVideoCore` 后缓存。
- 没有 `pixelle_video` 时，不得缓存一个“稍后再补”的本地 client。
- 如果 `PixelleVideoCore` 因配置变化被重建，factory 必须感知 identity 变化并重建 client。

### 3.5 能力必须诚实暴露，不能保留假按钮

`regenerate` 属于可选能力，不应通过“点击后报错”表达。

规则：

- client 提供明确 capability。
- UI 根据 capability 禁用不可用动作，并展示简短原因。
- 如果仍有直接调用，client 返回结构化的 unavailable 结果或抛出可捕获的配置异常，但这属于兜底，不是主路径。

## 4. 目标架构

```text
web/pages/3_🧭_Storyboard_Workbench.py
  -> resolve_workbench_client_mode(...)
  -> if in-process: get_pixelle_video()
  -> resolve_storyboard_workbench_client(...)
  -> render_storyboard_preview(..., workbench_client=client)

web/components/storyboard_preview.py
  -> render_prompt_plan_stale_panel(..., workbench_client=client)
  -> render_storyboard_workbench_panel(..., workbench_client=client)

web/workbench/http_client.py
  -> web.utils.storyboard_workbench_api
  -> web.utils.stale_api
  -> convert remote artifact url -> display payload

web/workbench/inprocess_client.py
  -> StoryboardWorkbenchService
  -> StoryboardWorkbenchStateStore
  -> StaleDependencyReadService
  -> LocalReadableArtifactSource
  -> StoryboardWorkbenchTaskSubmitter (optional)
```

现有 Stage 1 生成链路已经通过 `StoryboardWorkbenchArtifactBridge` 把生成出的 frame media 注册为 Workbench artifact，并把 `workbench_state` 写回 snapshot / state store。`InProcessStoryboardWorkbenchClient` 是这些已注册 artifact 的消费方，不重新实现 artifact 注册语义。

新增模块：

```text
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

## 5. Client 合同

### 5.1 能力合同

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

### 5.2 显示合同

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

### 5.3 操作合同

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
- `regenerate_frame_image()` 在可用时返回 `{success, task_id, task_type, created, ...}`；在预期不可用时返回 `{success: False, code: "regenerate_unavailable", reason: ...}`。
- `get_prompt_plan_stale_summary()` 返回 `{success, stale_summary}`。

## 6. In-process Client

`InProcessStoryboardWorkbenchClient` 从当前 Streamlit session 的 `PixelleVideoCore` 读取依赖。

职责：

- 调用 `StoryboardWorkbenchService.list_image_candidates()`。
- 消费 `StoryboardWorkbenchArtifactBridge` 已注册的 artifact / version / storage key，不重复创建 Workbench artifact。
- 通过 `LocalReadableArtifactSource` 把 `storage_key` 解析成可直接供 Streamlit 展示的安全 payload。
- 加载 / 保存 `StoryboardFrameWorkbenchState`。
- 调用 `StoryboardWorkbenchService.select_image_version()`。
- 调用 `StaleDependencyReadService.get_target_summary()`。
- 如果存在 `StoryboardWorkbenchTaskSubmitter`，则提交 `regenerate` 任务；否则 capability 明确报告不可用。

它不得：

- 拼 HTTP endpoint。
- 依赖 `api_base_url`。
- 暴露本地文件路径给 UI。
- 直接 reach-through 到 `core.task_manager`。

### 6.1 本地显示依赖

本地显示不再依赖通用 `ArtifactObjectStore.get_file_url()`。

新增一个窄协议，供 in-process client 使用：

```python
class LocalReadableArtifactSource(Protocol):
    async def get_local_file_uri(self, storage_key: str) -> str: ...
```

client 通过该协议读取受控对象，再转成 bytes payload。这样本地显示依赖的是“受控本地对象可读能力”，不是 API origin。

### 6.2 regenerate 依赖

本地 regenerate 不再假设 `PixelleVideoCore` 上挂了 `task_manager`。

新增一个窄协议：

```python
class StoryboardWorkbenchTaskSubmitter(Protocol):
    async def reserve_frame_image_regeneration(
        self,
        *,
        generation_fingerprint: str,
        request_params: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...
```

规则：

- 有 submitter：`can_regenerate_frame_image=True`。
- 无 submitter：`can_regenerate_frame_image=False`，UI 禁用按钮。
- 本次 client boundary 设计不通过 reach-through `task_manager` 来“硬接通”本地 regenerate。

## 7. HTTP Client

`HttpStoryboardWorkbenchClient` 保留当前远程能力，内部复用：

```text
web.utils.storyboard_workbench_api
web.utils.stale_api
web.utils.artifact_display_urls
```

职责变化：

- UI 不再调用 `artifact_url_for_streamlit()`。
- HTTP client 在内部把 API 返回的 URL 规范化为绝对展示 URL，然后写入 `image_display={"kind":"url", ...}`。
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

## 8. Client Factory 与生命周期

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

- 通过 `resolve_storyboard_workbench_client(...)` 获取 client。
- 调用 client 方法。
- 渲染 `candidate["image_display"]`。
- 根据 `client.get_capabilities()` 禁用或启用 regenerate。
- 不再接收或传递 `api_base_url`。

### 9.2 Stale Panel

当前：

```text
render_prompt_plan_stale_panel(..., api_base_url, stale_summary_loader)
```

改为：

```text
render_prompt_plan_stale_panel(..., workbench_client=None)
```

只通过 client 查询 stale summary。

### 9.3 Storyboard Preview / Page

`render_storyboard_preview()` 和 `3_🧭_Storyboard_Workbench.py` 只负责：

- 预览布局
- 锁定字段收集
- 解析本地 / 远程 mode
- 注入 `workbench_client`

它们不再传递 `api_base_url` 给 Workbench 子组件。

## 10. flowgram.ai-main 边界

`D:\demo1\Pixelle\Pixelle\flowgram.ai-main` 属于未来工作流编排或远程部署调用方。

它应接入：

```text
HttpStoryboardWorkbenchClient / FastAPI API
```

而不是影响本地 Streamlit 默认实现。

因此：

- flowgram 使用 `8001` 或其他 API endpoint 是合理的。
- 本地 Pixelle 产品体验不应因为没有 `8001` 服务而丢失候选图、选图、stale 核心能力。
- 同一套 `StoryboardWorkbenchClient` 合同保证本地和远程形态行为一致。

## 11. 测试策略

必须新增 / 调整测试：

1. HTTP client 把 API 返回的相对 URL 规范化为 `image_display={"kind":"url", ...}`，UI 不再自己拼 URL。
2. client factory 默认返回 in-process mode，但在 `pixelle_video` 缺失时不缓存坏 client。
3. client factory 在 `PixelleVideoCore` identity 变化时重建 in-process client。
4. Workbench page 在本地 mode 下先 `get_pixelle_video()`，再 resolve client。
5. `render_storyboard_workbench_panel()` 不再需要 `api_base_url`，使用 fake client 和 `image_display={"kind":"bytes"}` 能渲染候选图。
6. `render_prompt_plan_stale_panel()` 不再需要 `api_base_url`，使用 fake client 能渲染 stale panel。
7. 本地 client 调用 service / state store / local-readable artifact source，不调用 `httpx`。
8. 本地 client 缺少 `StoryboardWorkbenchTaskSubmitter` 时，`capabilities` 明确报告 regenerate 不可用，UI 按 disabled 处理，不崩溃。
9. source-level regression 确认 Workbench UI 组件不再 import：
   - `web.utils.storyboard_workbench_api`
   - `web.utils.stale_api`
   - `web.utils.artifact_display_urls`
   - `httpx`
   - `localhost:8001`
10. 本地 mode 的 Workbench UI 源码和测试不再把 `api_base_url` 当能力输入。

## 12. 非目标

本设计不做：

- 重写 FastAPI router。
- 移除 HTTP API。
- 重写 `flowgram.ai-main`。
- 顺手改动 AssetBible / Stage2 所有 HTTP client。
- 通过 reach-through `task_manager` 临时打通本地 regenerate。

本设计只收敛 Storyboard Workbench 的产品边界，并把 regenerate 的依赖关系转成显式能力模型。

## 13. 验收标准

完成后必须满足：

1. Storyboard Workbench UI 默认不依赖 `8001`。
2. UI 组件不直接调用 HTTP helper，也不直接处理 `artifact_url_for_streamlit()`。
3. HTTP 模式仍可通过 `PIXELLE_API_BASE_URL` 使用 `8001` 或远程 API。
4. 本地模式候选图、选图、stale 查询通过 in-process client 调用服务合同。
5. 本地模式候选图展示不依赖 `api_base_url`，不依赖 `/api/files/...`。
6. factory 不缓存未配置完成的 in-process client。
7. regenerate 在 capability 缺失时表现为 disabled / unavailable，而不是假可用。
8. 所有返回到 UI 的 artifact 显示数据仍经过安全过滤。
9. 测试覆盖本地模式、HTTP 模式、client 生命周期、显示合同、缺失依赖和无端口硬编码回归。

## 14. 自检

- Placeholder scan：无未完成占位内容。
- Scope check：只处理 Storyboard Workbench client boundary，不扩展到 AssetBible / Stage2。
- Boundary check：`8001` 被限定为 HTTP client 配置，不再是 UI 产品功能依赖。
- Lifecycle check：factory 不缓存未初始化完成的 in-process client。
- Display check：本地显示合同不再回落到 `api_base_url`。
- Capability check：regenerate 通过显式 capability 暴露，不再保留假按钮。
