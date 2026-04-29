# 18 Provider / ResourceResolver 分方案

用途：定义模型 Provider、能力矩阵、资源解析和强控制参数体系。  
上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`

---

## 1. 定位

Provider 是生成能力的实现方，不是 Pixelle 的业务事实源。

ResourceResolver 负责把用户可选择的资源 ID 转换为后端可执行配置，并执行权限、套餐、白名单和安全检查。

---

## 2. Provider 类型

```text
LLMProvider
ImageProvider
TTSProvider
VideoProvider
RenderProvider
StorageProvider
```

Provider 只暴露能力和执行接口，不直接决定业务流程。

---

## 3. ResourceResolver

Public API 和 App API 应接受：

```text
style_id
template_id
voice_id
bgm_id
workflow_preset_id
provider_preset_id
```

不应接受：

```text
raw workflow path
raw local file path
raw provider URL
arbitrary prompt_prefix
```

Resolver 输出后端内部配置：

```text
resolved_provider_id
resolved_workflow_key
resolved_template_path
resolved_voice_profile
billing_multiplier
permission_snapshot
```

---

## 4. ProviderCapability

```text
ProviderCapability
  provider_id
  modality
  supported_sizes
  supported_styles
  supports_seed
  supports_negative_prompt
  supports_reference_image
  max_concurrency
  cost_weight
```

阶段 6 开始系统化建设。阶段 1 只需要支持当前 z-image / ComfyUI 能力的最小描述。

---

## 5. 路由策略

ProviderRouter 输入：

```text
task_type
resource_requirements
plan_policy
queue_priority
capability_requirement
```

输出：

```text
provider_id
provider_params
queue_name
cost_policy
```

---

## 6. 安全边界

- Public API 不允许指定任意本地文件。
- 用户不能绕过套餐直接指定高成本 Provider。
- workflow_preset_id 必须来自白名单。
- Provider 返回内容必须写入 ArtifactVersion，不直接暴露为事实源。

---

## 7. 验收标准

- App API 可通过资源 ID 解析后端配置。
- raw 参数有清晰降级路径。
- 业务层依赖 Provider 接口，不依赖 ComfyUI 文件名。
- ProviderCapability 能参与路由和权限判断。
- Usage / Billing 可以读取 provider cost snapshot。

---

## 8. 非目标

- 阶段 6 之前不做完整 Capability 管理后台。
- 不把 Provider schema 暴露为 Public API 合同。
- 不承诺所有 Provider 具备同等能力。
