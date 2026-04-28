# 07 用户、权限、计费与资源策略

## 1. 为什么要提前设计

未来商业化需要：

```text
用户登录
工作区
会员套餐
API Key
生成额度
重抽卡扣费
资源白名单
并发限制
水印控制
存储期限
```

这些必须由后端控制，不能只靠前端隐藏按钮。

## 2. 用户与工作区

建议支持：

```text
User
Workspace
WorkspaceMember
APIKey
Subscription
UsageLedger
```

### User

```python
class User(BaseModel):
    user_id: str
    email: str
    name: str | None
    status: Literal["active", "disabled"]
```

### Workspace

```python
class Workspace(BaseModel):
    workspace_id: str
    owner_user_id: str
    name: str
    plan_id: str
```

## 3. 套餐策略

### Free

```text
每天 3 次
最多 5 个分镜
默认 IP
带水印
低优先级队列
不能调用 Public API
不能自定义 workflow
```

### Basic

```text
每天 30 次
最多 8 个分镜
允许创建 3 个 IP
允许基础 BGM
720p
普通队列
```

### Pro

```text
每天 300 次
最多 20 个分镜
允许创建 50 个 IP
无水印
允许 API Key
高级模板
高优先级队列
```

### Enterprise

```text
独立队列
自定义 workflow
团队空间
专属模型
Webhook
白标
更长存储
```

## 4. 权限点

```text
video.generate
video.batch_generate
video.no_watermark
video.high_resolution
video.priority_queue

ip.create
ip.max_count
ip.reference_mode

frame.regenerate_image
frame.regenerate_audio
frame.edit_prompt

api.public_access
api.webhook
api.debug_trace

workflow.custom
template.premium
provider.cloud
```

## 5. 额度和扣费

### 完整视频

```text
基础文案生成：1 credit
每张图片：1 credit
每段 TTS：0.5 credit
最终合成：1 credit
高级模型倍率：x2/x3
```

### 重抽卡

```text
重新生成一张图片：1 credit
重新生成一段音频：0.5 credit
重新生成最终视频：1 credit
重新生成文案：1 credit
```

## 6. 资源白名单

资源不要直接用本地路径暴露。

建议资源表：

```text
resource_presets
workflow_presets
template_presets
bgm_assets
voice_presets
style_presets
```

每个资源有：

```text
resource_id
resource_type
display_name
internal_path
required_plan
enabled
cost_multiplier
```

## 7. PlanPolicy

新增服务：

```text
pixelle_video/services/plan_policy.py
```

职责：

```python
validate_video_request()
validate_ip_create()
validate_regenerate_request()
resolve_allowed_resources()
estimate_credit_cost()
reserve_credits()
commit_usage()
refund_on_failure()
```

## 8. 并发限制

按套餐限制：

```text
Free: 同时 1 个任务
Basic: 同时 2 个任务
Pro: 同时 5 个任务
Enterprise: 自定义
```

按资源限制：

```text
image.high 队列只有 Pro 以上可用
cloud_provider 只有 Pro / Enterprise 可用
custom workflow 只有 Enterprise 可用
```

## 9. 水印策略

不要在前端决定是否加水印。  
后端根据套餐在合成阶段决定：

```text
Free: 强制水印
Basic: 可付费去水印
Pro: 默认无水印
Enterprise: 白标
```

## 10. Debug Trace 策略

```text
Free: 无 raw prompt
Basic: 可看最终 storyboard
Pro: 可看 final prompt
Admin: 可看 raw prompt 和 raw response
API: 根据 debug 权限
```

## 11. 计费安全

必须支持：

```text
预估 cost
预扣 credits
成功后结算
失败后按实际消耗扣费或退款
防止重复扣费
幂等 key
```
