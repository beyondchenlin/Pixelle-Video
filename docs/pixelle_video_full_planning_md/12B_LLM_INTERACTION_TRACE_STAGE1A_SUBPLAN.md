# 12B Stage 1A 大模型交互追踪分方案

用途：定义 Stage 1A 必须具备的平台级 LLM 输入输出追踪能力，确保文案、分镜规划、图片提示词和 PromptPlan 的每一次大模型调用都可查看、可审计、可定位错误。
上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`
设计规格：`../superpowers/specs/2026-04-29-llm-interaction-trace-design.md`

---

## 1. 定位

这个分方案不是“增加一个日志框”，而是从源头把大模型调用变成 Pixelle 的生产事实源。

Stage 1A 的完整链路应变成：

```text
用户主题/文案
  -> ScriptDraft
  -> StoryboardPlan
  -> ImagePromptDraft
  -> PromptPlan
  -> LLMInteractionTrace
```

左侧展示区只是读取这些结构化 Trace 的产品界面。终端日志、stdout 和普通 logger 不能再承担“大模型输入输出事实源”的角色。

---

## 2. BettaFish 参考判断

参考项目：`https://github.com/666ghj/BettaFish`

BettaFish 的前端日志系统值得参考的地方：

- 结果区旁边常驻一个运行过程展示区。
- 多个 Engine 用 tab 区分。
- 每个 Engine 有运行状态点。
- 日志实时追加，用户能看到系统是否还在工作。
- 前端在页面恢复可见时会刷新历史日志，补齐遗漏内容。
- 用户滚动查看历史时，自动滚动不会强行打断。

Pixelle 应该吸收的是“运行过程可见性”和“多阶段 tab 化体验”。

Pixelle 不应该照搬的是：

- 把文本日志文件当成事实源。
- 让前端从原始日志文本里解析大模型调用。
- 默认展示所有 raw prompt / raw response。
- 把进程日志、工程日志和领域 Trace 混在一起。

Pixelle 的追踪系统必须是结构化、领域化、权限可控的。

---

## 3. 范围

Stage 1A 必须包含：

- `LLMInteractionTrace` 领域模型。
- `LLMTraceContext` 语义上下文。
- `LLMInteractionRecorder` 记录器。
- `LocalLLMTraceStore` 本地落盘实现。
- `LLMService` 网关级追踪接入。
- ScriptDraft / StoryboardPlan / ImagePromptDraft / PromptPlan 生成服务传入 trace context。
- Trace API 或内部读取接口。
- Studio 左侧 LLM Trace Panel 的数据合同。
- raw request / raw response 的权限隔离策略。

Stage 1A 不包含：

- 完整 SaaS 权限系统。
- 跨租户审计后台。
- OpenTelemetry / ELK / Loki 等外部观测平台。
- 完整 Worker Trace Dashboard。
- 让普通用户查看内部 system/developer prompt。

---

## 4. 领域模型

建议模型边界：

```text
LLMInteractionTrace
  interaction_id
  task_id
  request_id
  session_id
  project_id
  stage
  purpose
  source_entity_type
  source_entity_id
  frame_id
  provider
  model
  temperature
  max_tokens
  response_type
  request_messages_preview
  request_hash
  response_preview
  response_hash
  parsed_output_preview
  raw_request_object_key
  raw_response_object_key
  status
  attempt
  latency_ms
  token_usage
  parse_error
  validation_error
  error_message
  created_at
  completed_at
  visibility

LLMTraceContext
  task_id
  request_id
  session_id
  project_id
  stage
  purpose
  source_entity_type
  source_entity_id
  frame_id
  visibility
```

`LLMTraceContext` 由业务服务提供语义，`LLMInteractionRecorder` 负责保存请求、响应、解析结果和错误。

---

## 5. 本地存储结构

Stage 1A 本地 MVP 落盘：

```text
output/{task_id}/trace/
  events.jsonl
  llm_interactions.jsonl
  raw/
    {interaction_id}_request.json
    {interaction_id}_response.json
    {interaction_id}_parsed.json
    {interaction_id}_error.json
```

没有 `task_id` 的内容 API 调用，可以临时使用：

```text
_runtime/trace/{request_id}/
```

这个 fallback 只用于本地开发和无任务上下文的调试入口，不能成为长期产品合同。

---

## 6. 必须追踪的 Stage 1A 调用

```text
script_draft.generate
script_draft.repair
storyboard_plan.generate
storyboard_plan.validate_or_repair
image_prompt.generate_batch
image_prompt.repair
prompt_plan.build
prompt_plan.validate_or_repair
```

每次调用至少记录：

- 提交给模型的 messages 或 prompt 快照。
- model / provider / temperature / max_tokens / response_type。
- 原始 response。
- 解析后的结构化结果。
- JSON 解析错误。
- Pydantic / schema 校验错误。
- retry attempt。
- latency。
- token usage，如果 provider 返回。
- 关联的 ScriptDraft / StoryboardPlan / frame / PromptPlan。

---

## 7. API 边界

建议 Stage 1A App API：

```http
GET /api/content/tasks/{task_id}/llm-interactions
GET /api/content/tasks/{task_id}/llm-interactions/{interaction_id}
GET /api/content/tasks/{task_id}/llm-interactions/{interaction_id}/raw-request
GET /api/content/tasks/{task_id}/llm-interactions/{interaction_id}/raw-response
GET /api/content/tasks/{task_id}/llm-interactions/stream
```

Streamlit 阶段可以先用轮询读取；API-first Studio 阶段再升级为 SSE 或 WebSocket。

---

## 8. Studio 展示方式

左侧或侧边 Trace Panel 推荐结构：

```text
Tabs:
  Script
  Storyboard
  Image Prompts
  PromptPlan
  Provider
  Errors

Timeline Row:
  time
  stage
  purpose
  model
  status
  latency
  source entity

Expanded Detail:
  submitted messages
  raw response preview
  parsed output
  validation error
  retry chain
  raw payload links
```

默认自动滚动到最新记录；用户向上滚动查看历史时暂停自动滚动；页面刷新或重连后从 Trace Store 补齐历史记录。

---

## 9. 权限与安全

默认策略：

```text
普通用户：进度、摘要、最终可见产物
创作者/高级用户：StoryboardPlan、最终图片提示词、PromptPlan 摘要
Admin / Local Debug：raw request、raw response、stacktrace、provider payload
```

必须脱敏：

- API key。
- bearer token。
- password / secret。
- 私有 provider URL。
- 内部 system/developer prompt。
- 内部 workflow payload。

raw payload 必须保存，但不默认展示。

---

## 10. 和现有 GenerationTrace 的关系

`GenerationTrace` 记录生成过程事件：

```text
stage started
LLM prompt sent
LLM response received
validation result
stage failed
```

`LLMInteractionTrace` 记录一次具体模型交互：

```text
request payload
response payload
parsed output
schema validation
retry attempt
provider metadata
```

两者通过 `interaction_id` 关联。GenerationTrace 是时间线，LLMInteractionTrace 是可展开的模型输入输出证据。

---

## 11. 验收标准

- Stage 1A 的每一次 LLM 调用都有 `LLMInteractionTrace`。
- 失败时能看到具体是哪一次 prompt、response、parse 或 schema 校验失败。
- UI 能展示结构化时间线，不依赖终端日志。
- raw request / raw response 能被保存，但只在 Admin / Local Debug 可见。
- ScriptDraft、StoryboardPlan、ImagePromptDraft、PromptPlan 能反查生成它们的大模型交互记录。
- Stage 1B 的图片候选、重抽、ArtifactVersion 能继续关联上游 PromptPlan 的 LLMInteractionTrace。

---

## 12. 非目标

- 不把 BettaFish 的 stdout 日志架构照搬进 Pixelle。
- 不让前端解析普通文本日志来推断模型调用。
- 不默认向所有用户展示系统提示词。
- 不把 Trace 做成只能本地调试、无法迁移 SaaS 的临时功能。
- 不用终端日志替代领域 Trace。
