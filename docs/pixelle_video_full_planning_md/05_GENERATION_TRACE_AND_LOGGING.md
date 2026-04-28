# 05 生成过程 Trace 与日志系统

## 1. 当前问题

当前系统主要依赖普通 logger 和任务状态，用户难以知道：

```text
哪一步失败
大模型 prompt 是什么
原始 response 是什么
JSON 解析哪里失败
第几帧出错
第几次 retry 成功
最终 prompt 为什么这样拼
```

这对产品化和调试都不够。

## 2. 目标

新增 Generation Trace 系统，使整个生成过程像“大模型对话流 + 工程日志”一样可视化。

前端可以展示：

```text
用户输入主题
系统生成视频策划
LLM 返回文案
质检发现问题
自动修复
生成图片提示词
组装 IP prompt
生成图片
重抽卡
合成视频
```

## 3. GenerationEvent 模型

```python
class GenerationEvent(BaseModel):
    event_id: str
    task_id: str
    project_id: str | None = None
    storyboard_id: str | None = None
    frame_id: str | None = None
    timestamp: datetime
    stage: str
    role: Literal["user", "system", "llm", "validator", "worker", "tool", "error"]
    title: str
    content: str | dict
    status: Literal["started", "success", "warning", "failed", "retrying"]
    attempt: int = 1
    raw_prompt_object_key: str | None = None
    raw_response_object_key: str | None = None
    error_message: str | None = None
    debug: dict = {}
```

## 4. Trace 文件结构

本地 MVP 可以先落盘：

```text
output/{task_id}/trace/
  events.jsonl
  001_video_plan_prompt.txt
  001_video_plan_response.json
  002_script_prompt.txt
  002_script_response.json
  003_script_validation.json
  004_image_prompt_prompt.txt
  004_image_prompt_response.json
  005_prompt_composer_debug.json
```

SaaS 阶段转成：

```text
PostgreSQL: generation_events
Object Storage: raw prompt / raw response / debug payload
```

## 5. API

```http
GET /api/v1/app/jobs/{job_id}/events
GET /api/v1/app/jobs/{job_id}/trace
GET /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/trace
```

实时流：

```http
GET /api/v1/app/jobs/{job_id}/events/stream
```

第一阶段可用轮询，后面再加 SSE / WebSocket。

## 6. 前端显示方式

推荐分三层：

### 6.1 普通用户视图

```text
正在生成文案
正在生成第 3 张图片
正在合成视频
```

### 6.2 高级用户视图

```text
每段旁白
每帧图片提示词
角色与道具分配
重抽卡历史
```

### 6.3 管理员 Debug 视图

```text
raw prompt
raw response
workflow payload
error stack
worker id
provider latency
token usage
```

## 7. Trace 与权限

不要默认对外暴露所有 prompt 和 workflow。  
这些可能是商业资产。

建议：

```text
Free: 只看进度
Pro: 看 storyboard 和 final prompt
Admin: 看 raw prompt / raw response / stacktrace
API 客户: 可选 debug=false/true，根据套餐开放
```

## 8. Codex 实现建议

新增：

```text
pixelle_video/services/generation_trace.py
pixelle_video/models/generation_event.py
api/routers/generation_trace.py
web/components/generation_trace.py
```

服务方法：

```python
record_event()
record_llm_call()
record_validation()
record_retry()
record_worker_event()
load_events()
```

## 9. 和任务系统结合

每个任务阶段都记录：

```text
stage started
LLM prompt sent
LLM response received
validation result
retry reason
stage completed
stage failed
```

这样失败时前端可以精确提示：

```text
图片提示词第 2 批 JSON 解析失败，已重试 2 次，最终失败。
```
