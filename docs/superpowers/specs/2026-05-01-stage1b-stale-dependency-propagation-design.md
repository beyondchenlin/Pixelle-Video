# Stage 1B Stale 依赖失效传播设计

## Goal

为 Stage 1B 建立可测试、幂等、可审计的 stale 依赖失效机制，使 AssetBible、SceneCast、PromptPlan 的上游变更能够稳定传播到下游规划、图片产物、视频片段和最终视频状态。该机制只负责记录依赖边与标记 stale，不自动重写内容、不触发生成、不接入 Stage 2 projection persistence，也不接入 main generation provider routing。

## 背景

现有 Stage 1A 已建立 `PromptPlan`、`ImagePromptDraft` 和 LLM trace 的核心契约。Stage 2 当前只提供 `SceneCast` 投影到 `PromptPlan` 的非持久化预览，并明确不做 PromptPlan 持久化、不标记 stale、不触发图片生成。Stage 1B 需要补齐中间工作台、候选图、Artifact 与 Trace 之间的依赖失效基础，使后续局部重生成有稳定依据。

## 范围

本设计覆盖：

- AssetBible 变更后，相关 SceneCast、PromptPlan、image artifact 的 stale 标记。
- SceneCast 变更后，相关 PromptPlan、image artifact 的 stale 标记。
- PromptPlan 变更后，相关 image artifact、video segment、final video 的 stale 标记。
- 依赖边记录与公开 ID 原则。
- lock 与 stale 的关系。
- 幂等与审计记录。
- Stage 1B 与 Stage 2 / 主生成链路的边界。

本设计不覆盖：

- Stage 2 projection persistence。
- 将 Stage 2 预览结果写回 PromptPlan。
- main generation provider routing。
- Provider 级 PromptProjection、ComfyUI workflow routing、LoRA / reference image 路由。
- 自动重生成、自动改写 PromptPlan、自动替换用户已选产物。
- UI 交互样式与前端状态管理。

## 核心概念

### Dependency Edge

依赖边表示一个下游对象依赖某个上游对象的某个版本或修订快照。依赖边本身只使用公开 ID 和版本信息，不把本地路径、workflow path、provider URL 当作公开契约。

推荐字段：

```json
{
  "edge_id": "dep_edge_001",
  "workspace_id": "workspace_1",
  "project_id": "project_1",
  "upstream_type": "asset_bible",
  "upstream_id": "bible_demo",
  "upstream_version": "asset_bible_rev_3",
  "downstream_type": "scene_cast",
  "downstream_id": "cast_frame_0001",
  "relation": "scene_cast.references_asset_bible",
  "created_at": "2026-05-01T10:00:00Z",
  "metadata": {
    "storyboard_plan_id": "storyboard_plan_1",
    "frame_id": "frame_0001"
  }
}
```

`upstream_type` 与 `downstream_type` 使用领域类型，不使用 Python 类名、数据库表名或存储目录名作为长期公开契约。第一阶段允许的类型为：

- `asset_bible`
- `scene_cast`
- `prompt_plan`
- `image_artifact`
- `video_segment`
- `final_video`

### Stale Mark

stale 标记表示下游对象仍可被查看和审计，但它依赖的上游对象已经发生变更，需要用户确认、重新投影或重新生成。stale 不是失败状态，也不是删除或覆盖。

推荐字段：

```json
{
  "stale_id": "stale_001",
  "workspace_id": "workspace_1",
  "project_id": "project_1",
  "target_type": "prompt_plan",
  "target_id": "prompt_plan_001",
  "reason_code": "scene_cast_changed",
  "upstream_type": "scene_cast",
  "upstream_id": "cast_frame_0001",
  "upstream_version": "scene_cast_rev_4",
  "marked_at": "2026-05-01T10:03:00Z",
  "message": "SceneCast cast_frame_0001 changed after PromptPlan prompt_plan_001 was composed."
}
```

同一个 `workspace_id + project_id + target_type + target_id + reason_code + upstream_type + upstream_id + upstream_version` 重复标记必须幂等，不得重复写入同义审计记录。`project_id` 是 stale 标记的一等身份字段；项目级 API 查询 stale target 或 upstream downstream 时，仓储必须同时按 `workspace_id` 和 `project_id` 过滤，避免同一工作区下不同项目的同名对象互相污染。

### Version Token

上游版本使用稳定公开版本 token，例如 `asset_bible_rev_3`、`scene_cast_rev_4`、`prompt_plan_rev_9`。如果当前仓储尚无显式版本字段，Stage 1B 实施时先通过仓储返回的 `updated_at` 或内容哈希生成内部 version token，但公开 stale 原因仍只暴露 `upstream_version`，不暴露本地文件路径、workflow path 或 provider URL。

当传播入口收到某个上游对象的新 `upstream_version` 时，直接依赖该对象且 `edge.upstream_version == event.upstream_version` 的下游视为已经基于当前版本建立，不应被标记 stale。直接依赖边中 `edge.upstream_version != event.upstream_version` 的下游才需要 stale 标记。递归传播表示“中间对象已经 stale”，例如 AssetBible 变更导致 SceneCast stale 后，依赖该 SceneCast 的 PromptPlan 也需要 stale；该递归传播不再把原始 AssetBible 版本 token 与 SceneCast 边版本做等值比较。

## 传播规则

### AssetBible Changed

触发条件：

- `AssetBibleRepository.save_asset_bible()` 保存了同一 `asset_bible_id` 的新版本。
- 变更可能来自角色、场景、道具、风格或 IP profile。

传播路径：

```text
AssetBible changed
  -> SceneCast stale
  -> PromptPlan stale
  -> image artifact stale
```

规则：

- 依赖该 AssetBible 的 SceneCast 标记 stale，原因 `asset_bible_changed`。
- 依赖这些 SceneCast 的 PromptPlan 标记 stale，原因 `asset_bible_changed_via_scene_cast`。
- 依赖这些 PromptPlan 的 image artifact 标记 stale，原因 `asset_bible_changed_via_prompt_plan`。
- 如果某个 PromptPlan 直接记录了 `asset_bible_id` 或 `metadata.asset_bible_id`，也可以直接通过 `prompt_plan.references_asset_bible` 边命中，但不得依赖路径扫描或 provider metadata。

示例：

```text
bible_demo@rev_3 -> cast_frame_0001
cast_frame_0001 -> prompt_plan_0001
prompt_plan_0001 -> image_artifact_frame_0001
```

当 `bible_demo` 保存为 `rev_4` 后，三类下游对象都应被标记 stale。

### SceneCast Changed

触发条件：

- `AssetBibleRepository.save_scene_cast()` 保存了同一 `scene_cast_id` 的新版本。
- 变更可能来自 `character_ids`、`scene_id`、`prop_ids`、`style_id` 或 `continuity_notes`。

传播路径：

```text
SceneCast changed
  -> PromptPlan stale
  -> image artifact stale
```

规则：

- 依赖该 SceneCast 的 PromptPlan 标记 stale，原因 `scene_cast_changed`。
- 依赖这些 PromptPlan 的 image artifact 标记 stale，原因 `scene_cast_changed_via_prompt_plan`。
- 如果 image artifact 直接记录了 `source_scene_cast_id`，可以额外通过直接边命中，但该直接边不能替代 PromptPlan 依赖边。

### PromptPlan Changed

触发条件：

- `PromptPlanRepository.save_prompt_plan_bundle()` 保存了包含同一 `prompt_plan_id` 的新版本。
- 后续单帧 PromptPlan update 接口如被引入，也必须触发同一传播入口。

传播路径：

```text
PromptPlan changed
  -> image artifact stale
  -> video segment stale
  -> final video stale
```

规则：

- 依赖该 PromptPlan 的 image artifact 标记 stale，原因 `prompt_plan_changed`。
- 依赖该 PromptPlan 或其 image artifact 的 video segment 标记 stale，原因 `prompt_plan_changed_via_image_artifact`。
- 依赖 stale video segment 的 final video 标记 stale，原因 `prompt_plan_changed_via_video_segment`。
- 若当前阶段尚未实现 video segment / final video 仓储，Stage 1B 仍应在依赖边模型和服务中保留类型与测试 fake，避免以后通过路径或渲染文件名补推依赖。

## Public ID 原则

所有依赖边、stale 标记、API 响应和审计记录必须使用公开 ID：

- 可以使用：`workspace_id`、`project_id`、`asset_bible_id`、`scene_cast_id`、`storyboard_plan_id`、`frame_id`、`prompt_plan_id`、`artifact_id`、`version_id`、`segment_id`、`final_video_id`。
- 可以使用：对象存储 key 作为 ArtifactVersion 的二进制定位字段，但它不是依赖边 ID，不作为上游或下游公开契约。
- 不可以使用：本地绝对路径，例如 `D:\demo1\Pixelle\output\frame.png`。
- 不可以使用：相对路径逃逸，例如 `../output/frame.png`。
- 不可以使用：ComfyUI workflow path，例如 `workflows/selfhost/storyboard.json`。
- 不可以使用：provider URL，例如 `https://provider.example/jobs/123`。
- 不可以使用：Python import path、类名、临时目录、worker 机器名作为公开依赖 ID。

provider URL、workflow path、本地临时路径如果确实需要调试，只能留在受权限保护的 debug payload 或 provider metadata 中，不能进入依赖边主键、stale 主键或公开响应。

## Lock 语义

lock 阻止自动重写，不阻止 stale 标记。

规则：

- `locked_content`：阻止自动改写内容字段，但上游变更仍然标记 stale。
- `locked_prompt`：阻止自动重组 PromptPlan 或 final prompt，但 PromptPlan 和下游 artifact 仍然标记 stale。
- `locked_artifact`：阻止自动替换已选 artifact version，但 artifact 仍然标记 stale。
- `locked_all`：阻止自动重写和自动替换所有下游结果，但 stale 标记和审计记录仍然写入。

用户锁定的对象被标记 stale 时，应保留锁定状态，并在 reason 中写明 `lock_policy`，方便后续 UI 显示“已锁定但依赖已过期”。

## 幂等与可审计

幂等要求：

- 重复调用同一传播入口不得创建重复 stale 标记。
- 重复标记同一目标、同一上游版本、同一原因时，返回已有记录。
- 如果同一目标因为新的上游版本再次失效，应创建新的 stale 记录，例如 `asset_bible_rev_4` 与 `asset_bible_rev_5` 是两条不同审计事实。

审计要求：

- 每条 stale 记录必须包含 `reason_code`、`upstream_type`、`upstream_id`、`upstream_version`、`marked_at`。
- 每次传播入口应返回 propagation summary，包含尝试数、实际新增数、已存在数和被命中的依赖边数。
- 记录时间戳使用 UTC ISO-8601 字符串。
- 审计记录不得包含本地路径、workflow path、provider URL。

## 仓储与服务边界

建议新增 focused repository protocols：

- `DependencyEdgeRepository`：保存、查询依赖边；`list_downstream_edges()` 必须按 `workspace_id + project_id + upstream_type + upstream_id` 查询。
- `StaleMarkRepository`：幂等写入和读取 stale 标记；`list_stale_marks()` 必须按 `workspace_id + project_id + target_type + target_id` 查询。

建议新增 focused service：

- `StaleDependencyPropagationService`：接收上游变更事件，查询依赖边，递归或分层标记下游 stale。

现有仓储扩展：

- `PromptPlanRepository.mark_prompt_plan_stale()` 已存在，可由实现适配到新的 `StaleMarkRepository`，但服务层不应只依赖 PromptPlan 单类型接口。
- `ArtifactRepository` 后续需要补充 `mark_artifact_stale()` 或通过 `StaleMarkRepository` 统一表达 artifact stale。Stage 1B 推荐统一 stale mark 仓储，避免每个领域仓储重复实现 stale 审计逻辑。

## 阶段边界

Stage 1B 本次计划只准备 stale 机制：

- 建立依赖边与 stale 标记领域模型。
- 建立 repository protocol。
- 建立传播服务。
- 补充针对 AssetBible / SceneCast / PromptPlan 变更的测试。

Stage 1B 不做：

- 不接入 Stage 2 projection persistence。
- 不把 Stage 2 projection preview 写回 PromptPlan。
- 不触发 main generation provider routing。
- 不自动重新调用 LLM、ComfyUI、TTS、HyperFrames。
- 不修改主视频生成 pipeline 的 provider 选择。
- 不在本轮实现查询 API；如需要 Studio 查询入口，必须后续单独设计只读 API 和权限边界。

## 验收标准

- AssetBible 新版本能把依赖 SceneCast、PromptPlan、image artifact 标记 stale。
- SceneCast 新版本能把依赖 PromptPlan、image artifact 标记 stale。
- PromptPlan 新版本能把依赖 image artifact、video segment、final video 标记 stale。
- 锁定对象仍被标记 stale，且不会被自动改写或替换。
- 重复传播同一上游版本不重复写 stale 记录。
- stale 记录包含原因、上游版本、时间戳。
- 依赖边和 stale 记录不包含本地路径、workflow path、provider URL。
- 实现测试不依赖真实文件系统路径、真实 provider URL 或真实 ComfyUI workflow path。
