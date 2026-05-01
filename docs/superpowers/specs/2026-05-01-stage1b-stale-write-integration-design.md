# Stage 1B Stale 写入点集成设计

## Goal

把已经完成的 Stage 1B stale 依赖传播机制接入真实写入点，让 AssetBible、SceneCast、PromptPlan 和 image artifact 的保存/生成结果能够记录依赖边，并基于 public ID 与版本 token 触发下游 stale 标记。

本设计只负责写入点集成和依赖审计，不持久化 Stage 2 投影预览，不触发主生成链路，不接入 provider routing，也不把本地路径、workflow path、provider URL 暴露为公开契约。

## Current State

已完成：

- `pixelle_video.models.stale_dependency`：`DependencyEdge`、`StaleMark`、`UpstreamChangeEvent`、`StalePropagationSummary`。
- `pixelle_video.repositories.stale_dependencies`：依赖边仓储与 stale 标记仓储 Protocol。
- `pixelle_video.services.stale_dependency_propagation`：edge-driven 递归 stale 传播服务。
- Stage 2 投影预览保持 preview-only：不调用 `save_prompt_plan_bundle()`，不标记 stale，不接主生成链路。

当前缺口：

- `api/routers/asset_bible.py` 仍直接调用 `AssetBibleRepository.save_asset_bible()` 和 `save_scene_cast()`，没有写依赖边，也没有触发 Stage 1B stale 传播。
- `PromptPlanRepository.save_prompt_plan_bundle()` 只有 Protocol 契约，尚未有统一的 stale-aware 写入协调层。
- `StoryboardWorkbenchService.record_frame_image_regeneration_result()` 创建 image artifact version，但没有写 `image_artifact.generated_from_prompt_plan` 依赖边。
- `StoryboardWorkbenchService.mark_prompt_plan_change_stale()` 仍是旧的 PromptPlan 单类型 stale 兼容路径，不应成为新的统一传播机制。

## Design Principles

- **应用服务编排，不污染仓储语义**：仓储继续负责保存/加载数据；新增 stale-aware 写入协调服务负责版本 token、依赖边和传播编排。
- **edge-driven，避免路径扫描**：所有传播都从 `DependencyEdgeRepository.list_downstream_edges()` 出发，不扫描文件路径、workflow、provider metadata 或生成目录。
- **保存后始终触发传播**：写入协调服务在保存上游对象后始终触发对应 `UpstreamChangeEvent`。是否真正产生 stale 标记由传播服务根据依赖边版本过滤决定。这样即使上一次保存成功但传播失败，重试同一保存仍能补齐传播，不会因为“内容未变化”而跳过。
- **重试安全**：依赖边保存必须按 `edge_id` 幂等 upsert；stale 标记已按 `workspace_id + target + reason + upstream` 幂等。
- **版本 token 是公开 token，不是路径**：如果当前模型没有显式 revision 字段，使用 canonical public payload hash 生成稳定 token，例如 `asset_bible_rev_8f3a1c2d4e6b`。
- **Stage 2 边界不变**：Stage 2 projection preview 不创建依赖边，不保存 projected PromptPlan，不触发 stale，不调用生成或 provider routing。
- **锁定语义不变**：lock 只阻止自动改写/自动替换，不阻止 stale 标记；stale metadata 继续保留 `auto_rewrite_allowed: False`。

## New Components

### `DependencyVersionService`

职责：

- 接收已通过领域模型解析的 payload。
- 使用 sorted-key canonical JSON 和 SHA-256 短 hash 生成稳定 token。
- 只输出形如 `<entity_type>_rev_<hash>` 的公开 token。
- 生成 hash 时排除 transient / audit 字段，例如 `created_at`、`updated_at`、`metadata.generated_at`、`metadata.last_saved_by`，避免无业务变化导致版本抖动。

公开方法：

- `version_for_asset_bible(asset_bible: AssetBible) -> str`
- `version_for_scene_cast(scene_cast: SceneCast) -> str`
- `version_for_prompt_plan(prompt_plan: PromptPlan) -> str`
- `version_for_artifact_version(version: ArtifactVersion) -> str`

### `StaleAwareAssetBibleWriteService`

职责：

- 保存 AssetBible draft。
- 保存 SceneCast draft。
- 生成当前上游版本 token。
- 对 SceneCast 写入 `scene_cast.references_asset_bible` 依赖边。
- 对 AssetBible / SceneCast 保存结果触发 stale 传播。

方法：

- `save_asset_bible(workspace_id, asset_bible) -> StaleAwareWriteResult`
- `save_scene_cast(workspace_id, scene_cast) -> StaleAwareWriteResult`

AssetBible 保存流程：

1. 领域模型校验 public ID 和 payload。
2. 调用 `AssetBibleRepository.save_asset_bible()`。
3. 基于保存后的 AssetBible payload 生成 `asset_bible_rev_<hash>`。
4. 触发 `UpstreamChangeEvent(reason_code="asset_bible_changed")`。
5. 返回保存 payload、版本 token 和传播 summary。

SceneCast 保存流程：

1. 领域模型校验 SceneCast。
2. 保存前加载对应 AssetBible，生成当前 `asset_bible_rev_<hash>`。
3. 调用 `AssetBibleRepository.save_scene_cast()`。
4. 基于保存后的 SceneCast payload 生成 `scene_cast_rev_<hash>`。
5. upsert 依赖边：
   - `edge_id = dep_scene_cast_<scene_cast_id>_asset_bible_<asset_bible_id>`
   - `upstream_type = asset_bible`
   - `upstream_id = <asset_bible_id>`
   - `upstream_version = <asset_bible_rev>`
   - `downstream_type = scene_cast`
   - `downstream_id = <scene_cast_id>`
   - `relation = scene_cast.references_asset_bible`
6. 触发 `UpstreamChangeEvent(reason_code="scene_cast_changed")`。
7. 返回保存 payload、版本 token、保存的依赖边和传播 summary。

### `StaleAwarePromptPlanWriteService`

职责：

- 保存 PromptPlan bundle。
- 为每个 PromptPlan 写入对 SceneCast 或 AssetBible 的依赖边。
- 对 PromptPlan 保存结果触发 stale 传播。

方法：

- `save_prompt_plan_bundle(workspace_id, project_id, bundle) -> StaleAwareWriteResult`

依赖来源：

- 首选 `PromptPlan.metadata.scene_cast_id`，写入 `prompt_plan.uses_scene_cast`。
- 如果没有 SceneCast 但有 `PromptPlan.metadata.asset_bible_id`，写入 `prompt_plan.references_asset_bible`。
- 如果两者都没有，本服务仍保存 bundle，但不猜测依赖，不扫描 Stage 2 projection preview，不从 provider metadata 反推。

PromptPlan 保存流程：

1. 解析 `PromptPlanBundle`，并从调用方接收当前路由或应用上下文中的 `project_id`。
2. 从每个 PromptPlan 的 public metadata 提取 `scene_cast_id` 或 `asset_bible_id`。
3. 对有依赖来源的 PromptPlan，加载对应 SceneCast 或 AssetBible，生成上游版本 token。
4. 调用 `PromptPlanRepository.save_prompt_plan_bundle()`。
5. 对每个保存后的 PromptPlan 生成 `prompt_plan_rev_<hash>`。
6. upsert 依赖边。
7. 对每个 PromptPlan 触发 `UpstreamChangeEvent(reason_code="prompt_plan_changed")`。

### `StaleAwareArtifactWriteService`

职责：

- 在 image artifact version 创建成功后写入 `image_artifact.generated_from_prompt_plan` 依赖边。
- 不改变 artifact storage key、object store URL 或 provider metadata 的公开语义。

方法：

- `record_image_artifact_dependency(workspace_id, project_id, artifact_version, prompt_plan) -> DependencyEdge`

流程：

1. 解析 `ArtifactVersion`，并从调用方接收当前项目 `project_id`。
2. 使用 `source_prompt_plan_id` 加载或接收对应 PromptPlan public payload。
3. 生成 `prompt_plan_rev_<hash>`。
4. upsert 依赖边：
   - `edge_id = dep_image_artifact_<artifact_id>_prompt_plan_<prompt_plan_id>`
   - `upstream_type = prompt_plan`
   - `upstream_id = <prompt_plan_id>`
   - `upstream_version = <prompt_plan_rev>`
   - `downstream_type = image_artifact`
   - `downstream_id = <artifact_id>`
   - `relation = image_artifact.generated_from_prompt_plan`

本阶段不要求实现 video segment / final video 仓储；stale 服务已经保留类型和测试 fake，后续真实仓储出现时再接 `video_segment.uses_image_artifact` 与 `final_video.uses_video_segment` 边。

## API Integration

`api/routers/asset_bible.py` 的 create/update AssetBible 与 create/update SceneCast 入口应从直接调用仓储改为调用 `StaleAwareAssetBibleWriteService`。

API 响应继续保持当前 shape：

- AssetBible 接口仍返回 `AssetBibleResponse`。
- SceneCast 接口仍返回 `SceneCastResponse`。
- stale 传播 summary 暂不暴露在已有 API 响应里，避免破坏现有前端契约。

后续如果 Studio 需要显示“保存后影响了多少下游对象”，应新增只读查询或扩展响应字段，并单独设计前端展示，不在本集成阶段混入。

## Failure Semantics

- 保存前校验失败：不调用仓储，不写依赖边，不触发传播。
- 主对象保存失败：不写依赖边，不触发传播。
- 主对象保存成功但依赖边写入失败：抛出 503/500 级错误，调用方可重试；因为保存后总是重新触发传播，重试可补齐边和 stale 标记。
- 依赖边写入成功但 stale 传播失败：抛出错误，调用方可重试；stale 标记幂等。
- `StaleDependencyPropagationService` 不应吞掉仓储异常；应用层负责把异常映射为 API 错误。

## Tests

必须覆盖：

- AssetBible 保存后触发 `asset_bible_changed`，并返回 propagation summary。
- SceneCast 保存后写入 `scene_cast.references_asset_bible`，并触发 `scene_cast_changed`。
- PromptPlan bundle 保存后写入 `prompt_plan.uses_scene_cast` 或 `prompt_plan.references_asset_bible`，并触发 `prompt_plan_changed`。
- ArtifactVersion 记录后写入 `image_artifact.generated_from_prompt_plan`。
- 同一保存重试不会产生重复边或重复 stale 标记。
- Stage 2 projection preview 不调用 stale-aware write service，不保存 projected PromptPlan，不触发 stale。
- public ID 边界：依赖边和 version token 不包含 `D:\`、`://`、`workflows/`、`workflow_path`、`provider_url`。
- lock 语义：locked 下游对象仍会被标记 stale，且 `auto_rewrite_allowed` 为 `False`。

## Out Of Scope

- 不实现 Stage 2 projection persistence。
- 不让 Stage 2 projection preview 写依赖边或 stale。
- 不接 provider routing / ComfyUI workflow routing。
- 不实现自动重写 PromptPlan。
- 不自动替换用户已选 artifact version。
- 不实现 video segment / final video 真实仓储。
- 不在本阶段新增前端 stale 面板或 UI 交互。

## Self Review

- Spec coverage: 覆盖 AssetBible、SceneCast、PromptPlan、image artifact 写入点，覆盖依赖边、版本 token、传播触发、失败语义和 Stage 2 边界。
- Placeholder scan: 无未定项、未完成项或临时说明。
- Scope check: 本设计只做应用服务与写入点集成，不混入前端、provider routing、自动生成或 Stage 2 persistence。
- Ambiguity check: 明确保存后始终触发传播，依赖边幂等 upsert，API 响应暂不暴露 propagation summary。
