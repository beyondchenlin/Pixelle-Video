# 24 Platform Foundation / Zero Technical Debt 分方案

用途：在 Stage 1A、Stage 1B 和 Stage 2 并行开发前，先建立平台级事实源、存储抽象、资源解析和零技术债闸门。  
上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`

---

## 1. 定位

本分方案是 Stage 0.5。它不是一个可跳过的“基础设施优化”，而是 Stage 1 / Stage 2 并行开发的前置合同。

Pixelle 后续所有创作能力必须先回答四个问题：

```text
领域事实写到哪里？
raw payload 和二进制产物写到哪里？
Public/App API 如何把用户输入解析成平台资源 ID？
本地开发适配器是否被隔离在正式合同之外？
```

如果这些问题没有先解决，Stage 1A、Stage 1B 和 Stage 2 会各自实现本地 JSON、JSONL、`_runtime`、legacy 字段和临时 fallback，最终形成系统性迁移债。

---

## 2. 零技术债红线

必须遵守：

- PostgreSQL 是领域元数据的生产级事实源。
- 对象存储是 raw payload、图片、音频、视频、debug payload 的生产级事实源。
- 本地文件系统只能作为 `dev/test adapter`，不能作为领域服务的默认命名、默认合同或长期执行路径。
- 业务服务只能依赖 Repository / Store / Resolver 接口，不能依赖 `output/{task_id}`、`_runtime`、JSONL 文件名或本地路径布局。
- App API 和 Public API 只能接受资源 ID、preset ID、策略 ID 或受控 debug token，不能接受任意本地路径、workflow 路径、provider URL 或 arbitrary prompt prefix。
- 字体、模板、预览图片、真实预览帧和生成图片引用都必须表达为资源 ID、storage key 或 artifact/version ID；不得把本地字体路径、模板路径、预览帧路径暴露为正式合同。
- 旧 raw 字段不能只标记 deprecated 后继续作为主入口；必须迁移到明确的 Internal/Debug API 边界。

禁止：

- 在 Stage 1A 中创建 `LocalLLMTraceStore` 作为正式服务。
- 在 Stage 1B 中创建 `LocalJsonArtifactService` 或 `LocalJsonGenerationTraceService` 作为正式服务。
- 在 Stage 2 中创建 `LocalAssetBibleService` 作为正式服务。
- 使用 `_runtime/trace/{request_id}` 作为任何可执行计划的默认路径。
- 使用 `_runtime/preview`、`output/{task_id}/preview` 或本地绝对路径作为实施预览、真实预览帧、字体资源的正式返回值。
- 用“后续迁移到数据库”替代当前阶段的接口、schema 和 fail-fast 策略。
- 让兼容字段继续参与新功能设计。

---

## 3. 平台级接口

Stage 0.5 必须先定义这些接口，后续阶段只能消费它们：

```text
TraceRepository
  append_llm_interaction()
  list_llm_interactions()
  append_generation_event()
  list_generation_events()

RawPayloadStore
  put_json()
  get_json()
  exists()

ArtifactRepository
  create_artifact()
  create_artifact_version()
  select_artifact_version()
  list_artifact_versions()
  mark_artifact_failed()

ArtifactObjectStore
  put_file()
  get_file_url()
  exists()

AssetBibleRepository
  save_asset_bible()
  load_asset_bible()
  save_scene_cast()
  load_scene_cast()

PromptPlanRepository
  save_prompt_plan_bundle()
  load_prompt_plans_by_storyboard()
  mark_prompt_plan_stale()

ResourceResolver
  resolve_style_id()
  resolve_template_id()
  resolve_font_asset_id()
  resolve_voice_id()
  resolve_bgm_id()
  resolve_workflow_preset_id()
  resolve_provider_preset_id()
```

接口命名必须表达领域责任，不表达本地实现方式。允许存在 `FilesystemDevTraceRepository`、`FilesystemDevArtifactObjectStore` 这类 dev adapter，但业务代码不能直接 new 这些实现。

---

## 4. 生产与本地适配

生产模式：

```text
PostgresTraceRepository
PostgresArtifactRepository
PostgresAssetBibleRepository
PostgresPromptPlanRepository
S3RawPayloadStore / MinIORawPayloadStore
S3ArtifactObjectStore / MinIOArtifactObjectStore
DatabaseResourceResolver
```

本地开发 / 单元测试模式：

```text
InMemoryTraceRepository
InMemoryArtifactRepository
InMemoryAssetBibleRepository
InMemoryPromptPlanRepository
FilesystemDevRawPayloadStore
FilesystemDevArtifactObjectStore
StaticResourceResolver
```

约束：

- `dev/test adapter` 必须由配置工厂注入，不能在业务服务里硬编码。
- `production` profile 缺少 PostgreSQL 或对象存储配置时必须 fail fast。
- `dev` profile 可以使用内存或本地文件，但返回值仍必须是平台 storage key，不允许把 Windows/Linux 本地路径暴露为合同。
- 测试优先使用 fake/in-memory repository，避免把本地文件布局写进领域测试。

---

## 5. API 边界

正式 App/Public API 输入应收敛为：

```text
style_id
template_id
font_asset_id
voice_id
bgm_id
workflow_preset_id
provider_preset_id
asset_bible_id
scene_cast_id
prompt_plan_id
```

Internal/Debug API 可以在受控条件下接受：

```text
debug_prompt_prefix
debug_workflow_key
debug_provider_id
debug_raw_payload_object_key
debug_font_file
```

但必须满足：

- 只能在 Admin / Local Debug / Internal route 中启用。
- OpenAPI schema 必须把 App/Public schema 和 Internal/Debug schema 分开。
- 新功能不得依赖 legacy raw 字段。
- 兼容读取必须集中在 adapter 或 migration 层，不得散落在业务服务。

---

## 6. Stage 1 / Stage 2 影响

Stage 1A：

- `LLMInteractionRecorder` 依赖 `TraceRepository` 和 `RawPayloadStore`。
- `PromptPlanBuilder` 输出 `PromptPlanBundle`，并可通过 `PromptPlanRepository` 保存。
- 不再实现本地 JSONL trace store。
- 不再把 Prompt-only IP hint 作为长期事实源；只允许引用 Stage 2 产出的资源 ID 或草稿 asset profile ID。
- `text_rendering.image_text` 只能表达图中文字抑制和渲染策略，不能成为第二套图片提示词或 PromptPlan 事实源。

Stage 1B：

- `Artifact`、`ArtifactVersion`、`GenerationEvent` 依赖 `ArtifactRepository`、`ArtifactObjectStore` 和 `TraceRepository`。
- 分镜工作台只读取 Stage 1A 的 `PromptPlan` 合同，不重新定义。
- raw 参数治理必须拆出 App/Public schema 与 Internal/Debug schema，不再只做 deprecated 标记。
- 实施预览区消费 selected/candidate `ArtifactVersion`，不能创建独立图片事实源；真实预览帧如需持久化，必须进入 `ArtifactObjectStore` 或受控预览 artifact key。

Stage 2：

- `AssetBible`、`IPProfile`、`CharacterProfile`、`SceneCast` 依赖 `AssetBibleRepository`。
- IP 形象设计从 Stage 2A 开始并行推进，先定义角色、世界观、风格事实源，再接 PromptComposer。
- Stage 2 在 Gate A 前只能产出合同、校验器和 repository 测试，不能写入主生成链路。
- Stage 2 的 `StyleProfile` 是视觉 / IP 风格事实源，不是标题或字幕 `TextStyleProfile`；不得接管 `caption_style` 或 `title_style` 默认值。

---

## 7. 集成闸门

Gate 0.5：平台基础合同稳定。

满足条件：

- Repository / Store / Resolver 接口存在，并有 fake/in-memory 测试。
- 生产 profile 缺少 PostgreSQL / 对象存储配置时 fail fast。
- dev/test adapter 不向领域模型返回本地绝对路径。
- `rg "LocalJson|LocalLLMTraceStore|LocalAssetBibleService|_runtime/trace"` 不命中 active implementation plan。
- App/Public API schema 不再把 raw workflow path、raw local path、arbitrary prompt prefix 作为新能力入口。
- App/Public API schema 不再把 raw font path、raw preview image path、raw rendered preview frame path 作为新能力入口。

未通过 Gate 0.5 时：

- Stage 1A 只能写领域模型测试，不能接入 LLMService trace。
- Stage 1B 只能写 Artifact / GenerationEvent 纯模型测试，不能写持久化服务。
- Stage 2 只能写 AssetBible / SceneCast 纯模型测试，不能写 API 或持久化服务。

---

## 8. 后续实施入口

对应平台基础实施计划：

`../superpowers/plans/2026-04-30-platform-foundation-zero-technical-debt-implementation.md`

该计划必须先于 Stage 1A、Stage 1B 和 Stage 2 的主动执行入口完成。
