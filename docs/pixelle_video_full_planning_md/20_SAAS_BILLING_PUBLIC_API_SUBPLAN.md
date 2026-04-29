# 20 SaaS / Billing / Public API 分方案

用途：定义 Pixelle 商业化后端、权限、计费和对外 API 边界。  
上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`

---

## 1. 定位

SaaS / Billing / Public API 是后期平台化能力，不能抢在工作台、Artifact、Worker、Provider 前面。

它的目标是让 Pixelle 可以安全地服务多用户、多工作区、API 客户和商业套餐。

---

## 2. 核心模型

```text
User
Workspace
Project
APIKey
PlanPolicy
UsageLedger
ResourcePolicy
BillingEvent
WebhookEndpoint
```

---

## 3. API 分层

```text
App API
  Studio Web 使用，面向登录用户。

Public API
  第三方和商业用户使用，强控制、强审计。

Admin API
  运营后台使用。

Internal API
  Worker 和内部服务使用。
```

Public API 不等同于把 App API 直接公开。

---

## 4. 强控制参数

允许：

```text
style_id
template_id
voice_id
bgm_id
workflow_preset_id
provider_preset_id
```

禁止：

```text
local file path
raw workflow file
raw provider URL
unbounded prompt_prefix
arbitrary bgm_path
```

---

## 5. 计费事件

```text
image_generation
image_regeneration
tts_generation
video_segment_generation
final_render
storage_usage
api_call
```

每个 BillingEvent 必须能追溯到 job_id、artifact_version_id、provider_id 和 workspace_id。

---

## 6. 权限策略

PlanPolicy 控制：

- 并发数。
- 队列优先级。
- 可用 Provider。
- 可用模板。
- 是否去水印。
- 最大项目数。
- 最大存储量。
- Public API 配额。

权限必须在后端执行，不能只靠前端隐藏按钮。

---

## 7. Public API 验收

- API Key 能绑定 workspace。
- Public API 请求能生成 UsageLedger。
- Public API 不能传 raw path。
- Webhook 能回传任务状态。
- 错误码稳定、可文档化。
- 每次扣费都能追踪到 Artifact / Trace。

---

## 8. 阶段边界

阶段 8 才建设 SaaS / Billing / Public API。

阶段 1 到阶段 7 只需要预留：

- resource_id 思维。
- provider cost snapshot。
- trace and artifact audit。
- permission key 字段。

---

## 9. 非目标

- 不在阶段 1 实现支付系统。
- 不在阶段 1 实现完整多租户。
- 不在阶段 1 开放 Public API。
