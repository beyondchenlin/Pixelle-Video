# IP Workbench Apply Contract 设计

日期：2026-05-03

## 1. 结论

当前 IP 总方向正确，但旧 Stage 2 计划不能继续作为执行依据。

`AssetBible`、`SceneCast`、验证、草稿 API、stale-aware 写入和 preview-only PromptPlan projection 已经在 `dev` 上存在。后续如果继续扩展 `Stage 2 Projection Preview`，会把调试入口伪装成正式产品功能，留下第二套 Workbench 边界和第二套 PromptPlan 事实源。

新的执行方向是：

```text
AssetBible / SceneCast
  -> Storyboard IP Workbench client boundary
  -> explicit apply contract
  -> StaleAwarePromptPlanWriteService
  -> persisted applied PromptPlanBundle
  -> existing Workbench stale / regenerate / artifact flow
```

旧 preview 继续保留为只读调试入口，但不得承担保存、stale 写入、重抽或主生成职责。

## 2. 当前状态

已经完成：

- `pixelle_video/models/asset_bible.py`
- `pixelle_video/models/scene_cast.py`
- `pixelle_video/services/scene_casting.py`
- `pixelle_video/services/prompt_composer.py`
- `pixelle_video/services/asset_prompt_plan_composer.py`
- `api/routers/asset_bible.py`
- `api/schemas/asset_bible.py`
- `pixelle_video/services/stale_write_integration.py`
- `web/components/asset_prompt_plan_projection.py`
- `web/pipelines/stage2_projection.py`

验证结果：

```text
python -m pytest -q tests/test_asset_bible_models.py tests/test_scene_cast_model.py tests/test_scene_casting_validation.py tests/test_prompt_composer_asset_projection.py tests/test_asset_prompt_plan_composer.py tests/test_asset_bible_api.py tests/test_asset_prompt_plan_projection_ui.py tests/test_stage2_projection_pipeline_ui.py tests/test_stale_write_integration.py
124 passed
```

关键缺口：

- 没有正式 IP Workbench。
- Stage 2 UI 仍直接依赖 `httpx`、`DEFAULT_API_BASE_URL` 和 `web.utils.asset_bible_api`。
- preview endpoint 只返回投影结果，不保存、不标记 stale、不触发生成。
- 主生成和单帧重抽只消费已保存的 `PromptPlan.final_prompt`，不会从 SceneCast 选择中获得 IP 约束。
- `StaleAwarePromptPlanWriteService` 已存在，但当前主线没有用 apply contract 把 SceneCast 结果写回正式 PromptPlanBundle。

## 3. 设计目标

1. 建立正式的 IP Workbench 产品边界。
2. 让 UI 只依赖 client contract，不直接调用 HTTP helper、端口、URL 拼接或 repository。
3. 新增明确的 apply contract，将一个已验证的 `SceneCast` 应用到已有 `PromptPlanBundle`。
4. apply 必须通过 `StaleAwarePromptPlanWriteService` 保存，从源头写入依赖边和 stale 传播。
5. Workbench 重抽和候选图流程只消费正式保存后的 PromptPlan，不消费 preview/session 临时状态。
6. 保持 preview-only 入口的边界，不在 preview 上偷偷加保存能力。

## 4. 非目标

本阶段不做：

- Reference image 管理。
- LoRA 管理。
- image-to-image 一致性。
- Provider routing。
- ComfyUI workflow/path 暴露。
- 自动替换用户已选候选图。
- 从 preview response 直接触发图片或视频生成。
- 在 `StyleProfile` 或 `PromptPlan.metadata` 中混入标题、字幕、字体、workflow、provider 参数。

## 5. 边界原则

### 5.1 Preview 仍然只读

保留现有：

```text
POST /api/projects/{project_id}/asset-bible/{asset_bible_id}/scene-casts/{scene_cast_id}/prompt-plan-projection
```

该 endpoint 永远只返回 preview：

- 不调用 `PromptPlanRepository.save_prompt_plan_bundle()`。
- 不调用 `StaleAwarePromptPlanWriteService`。
- 不创建依赖边。
- 不标记 stale。
- 不触发生成。

### 5.2 Apply 是独立合同

新增 apply endpoint：

```text
POST /api/projects/{project_id}/asset-bible/{asset_bible_id}/scene-casts/{scene_cast_id}/prompt-plan-apply
```

请求：

```json
{
  "workspace_id": "workspace_1",
  "storyboard_plan_id": "storyboard_plan_1",
  "frame_id": "frame_0001",
  "actor_id": "user"
}
```

响应：

```json
{
  "success": true,
  "message": "Success",
  "application": {
    "prompt_plan": {
      "prompt_plan_id": "prompt_plan_1",
      "storyboard_plan_id": "storyboard_plan_1",
      "frame_id": "frame_0001",
      "image_prompt_draft_id": "image_prompt_draft_1",
      "prompt_sections": {"subject": "Luna studies the compass"},
      "final_prompt": "Luna studies the compass in the warm comic lab.",
      "source_trace_id": "trace_prompt_1",
      "character_ids": ["char_luna"],
      "scene_id": "scene_lab",
      "prop_ids": ["prop_compass"],
      "style_id": "style_warm_comic",
      "metadata": {
        "scene_cast_id": "cast_frame_1",
        "asset_bible_id": "bible_demo"
      }
    },
    "source": {
      "asset_bible_id": "bible_demo",
      "scene_cast_id": "cast_frame_1",
      "prompt_plan_id": "prompt_plan_1"
    },
    "write": {
      "version_tokens": ["prompt_plan_rev_abc123"],
      "dependency_edge_count": 1,
      "stale_mark_count": 0
    }
  }
}
```

### 5.3 Apply 保存整个 bundle

当前 `PromptPlanRepository` 是 bundle-oriented：

```python
save_prompt_plan_bundle(workspace_id, bundle)
load_prompt_plans_by_storyboard(workspace_id, storyboard_id)
```

因此 apply service 不新增单帧 repository patch 接口。它必须：

1. 加载当前 storyboard 的 PromptPlan 列表。
2. 找到目标 `frame_id` 的 PromptPlan。
3. 调用现有 `apply_scene_cast_to_prompt_plan()` 得到新 PromptPlan。
4. 用新 PromptPlan 替换 bundle 中对应项。
5. 通过 `StaleAwarePromptPlanWriteService.save_prompt_plan_bundle()` 保存整个 bundle。

这样不会绕过现有 repository 合同，也不会把单帧 patch 私货塞进 storage adapter。

### 5.4 Workbench client 是 UI 唯一入口

新增 `StoryboardIPWorkbenchClient` 合同：

```python
class StoryboardIPWorkbenchClient(Protocol):
    def list_asset_bibles(
        self,
        *,
        workspace_id: str,
        project_id: str,
    ) -> dict[str, Any]: ...

    def list_scene_casts(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> dict[str, Any]: ...

    def apply_scene_cast_to_prompt_plan(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
        storyboard_plan_id: str,
        frame_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]: ...
```

UI 不得直接导入：

- `web.utils.asset_bible_api`
- `httpx`
- `DEFAULT_API_BASE_URL`
- `localhost:8001`

HTTP helper 可以保留，但只能作为 `HttpStoryboardIPWorkbenchClient` 的内部实现。Local Streamlit 默认走 in-process client。

### 5.5 SceneCast 绑定必须有分镜语义

正式 Workbench 中，SceneCast 不是裸 ID 输入框。用户应该在当前 storyboard/frame 上看到：

- 当前 AssetBible。
- 可用于当前 frame 的 SceneCast。
- SceneCast 引用的 characters / scene / props / style。
- apply 后的 PromptPlan 资产锁定字段。
- apply 后 stale 状态。

如果缺少 AssetBible 或 SceneCast，UI 明确显示缺口，不允许把 debug ID 当作产品流程。

### 5.6 生成只消费保存后的 PromptPlan

单帧重抽继续使用：

```text
PromptPlanRepository.load_prompt_plans_by_storyboard()
-> PromptPlan.final_prompt
```

但前提是 IP apply 已经把 SceneCast 写入正式 PromptPlanBundle。重抽不读取 session state、不读取 preview result、不读取 `projection_preview_result`。

## 6. 后端服务

新增服务：

```python
class AssetPromptPlanApplyService:
    async def apply_scene_cast_to_prompt_plan_bundle(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
        storyboard_plan_id: str,
        frame_id: str,
        actor_id: str | None = None,
    ) -> PromptPlanApplyResult:
        ...
```

依赖：

- `AssetBibleRepository`
- `PromptPlanRepository`
- `StaleAwarePromptPlanWriteService`

职责：

- 加载 AssetBible。
- 加载 SceneCast。
- 校验 SceneCast 归属和引用。
- 加载 PromptPlanBundle。
- 替换目标 PromptPlan。
- 通过 stale-aware write service 保存。
- 返回应用后的 PromptPlan 和写入摘要。

不做：

- 不读写本地路径。
- 不知道 FastAPI。
- 不知道 Streamlit。
- 不生成图片。
- 不处理 provider routing。

## 7. 前端集成

新增正式面板：

```text
web/components/ip_workbench_panel.py
```

接入位置：

- `web/components/storyboard_preview.py`
- `web/pages/3_🧭_Storyboard_Workbench.py`

面板显示在每个 frame 的 Workbench 上下文中，和候选图、stale panel 使用同一组 project/workspace/storyboard/frame 上下文。

交互：

1. 加载当前项目的 AssetBible。
2. 选择 AssetBible。
3. 加载该 AssetBible 下 SceneCast。
4. 按当前 `storyboard_plan_id + frame_id` 过滤或优先排序 SceneCast。
5. 展示资产引用摘要。
6. 用户点击 apply。
7. 调用 `StoryboardIPWorkbenchClient.apply_scene_cast_to_prompt_plan()`。
8. 刷新 stale summary / prompt plan display。

## 8. 数据流

```text
Workbench page
  -> resolve StoryboardIPWorkbenchClient
  -> IP Workbench panel
  -> list AssetBible / SceneCast
  -> apply SceneCast
  -> HTTP or in-process adapter
  -> AssetPromptPlanApplyService
  -> AssetBibleRepository
  -> PromptPlanRepository
  -> apply_scene_cast_to_prompt_plan()
  -> StaleAwarePromptPlanWriteService
  -> dependency edges / propagation
  -> persisted applied PromptPlanBundle
  -> Workbench stale and regenerate read official PromptPlan
```

## 9. 错误语义

- 缺少 AssetBible：`404`
- 缺少 SceneCast：`404`
- 缺少 PromptPlan：`404`
- SceneCast 引用非法：`422`
- SceneCast 与请求 frame/storyboard 不匹配：`422`
- repository payload 身份不一致：`502`
- stale write dependency 缺失：`404`
- stale write infrastructure 缺失：`503`
- client 未配置：UI fail closed，不回退到 HTTP helper

所有公开错误不得包含本地路径、workflow path、provider URL 或 storage key。

## 10. 测试策略

后端：

- apply service 保存整个 bundle。
- apply service 不变更非目标 frame。
- apply service 写入 `scene_cast_id` / `asset_bible_id` metadata。
- apply service 通过 `StaleAwarePromptPlanWriteService` 写依赖边。
- preview endpoint 仍不保存。
- apply endpoint 拒绝 path-like ID。

客户端边界：

- HTTP client 内部调用 helper。
- in-process client 直接调用 repository/service。
- UI 不 import `httpx`、`web.utils.asset_bible_api`、`DEFAULT_API_BASE_URL`。
- factory 默认 in-process，不缓存未配置 client。

UI：

- 有 client 时渲染 AssetBible/SceneCast 选择。
- 无 client 时 fail closed。
- apply 成功后显示应用后的 PromptPlan asset refs。
- frame 不匹配时禁用 apply。

回归：

- Stage2 preview tests 保持通过。
- Storyboard Workbench client boundary tests 保持通过。
- Stale write tests 保持通过。

## 11. 验收标准

1. 旧 Stage2/IP 计划明确标记为历史计划，不再作为新执行依据。
2. IP Workbench UI 不直接依赖 HTTP helper 或 `api_base_url`。
3. preview endpoint 仍然 preview-only。
4. apply endpoint 独立存在，并通过 stale-aware write service 保存 PromptPlanBundle。
5. apply 后的 PromptPlan 是重抽和候选图生成的唯一输入。
6. SceneCast 在 Workbench 中按 storyboard/frame 语义绑定，不再依赖裸 ID 调试。
7. 没有新增第二套 PromptPlan 事实源。
8. 没有新增 provider/workflow/path 泄漏。
9. 聚焦测试和文档边界检查通过。

## 12. 自检

- Scope check：本设计只修复 IP Workbench 与 apply 合同，不扩展 LoRA、参考图或 provider routing。
- Boundary check：preview 和 apply 明确分离。
- Source-of-truth check：正式保存仍走 PromptPlanRepository 和 stale-aware write service。
- UI check：正式 UI 只依赖 client contract。
- Debt check：不把 debug preview 扩成产品流程，不新增第二套 PromptPlan。
