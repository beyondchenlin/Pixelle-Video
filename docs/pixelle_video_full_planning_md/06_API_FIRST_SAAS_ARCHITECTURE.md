# 06 API-first SaaS 架构

## 1. 为什么要 API-first

未来会有：

```text
Vue / Next.js 前端
管理后台
第三方开发者 API
会员系统
批量生成
企业客户
移动端
```

所以不能把能力写死在 Streamlit 或本地脚本里。

核心原则：

```text
所有能力先 service 化
所有 service 再 API 化
UI 只是 API 客户端
```

## 2. API 分层

建议分四类：

```text
/api/v1/public/*
/api/v1/app/*
/api/v1/admin/*
/api/v1/internal/*
```

### 2.1 Public API

给第三方开发者或普通 API 客户。

特点：

```text
参数少
强控制
稳定
不暴露内部 workflow
按 API Key 计费
```

### 2.2 App API

给你自己的 Web 产品前端。

特点：

```text
功能完整
支持编辑
支持分镜
支持 trace
支持重抽卡
```

### 2.3 Admin API

给后台。

特点：

```text
用户管理
套餐管理
任务监控
成本统计
Worker 状态
Provider 状态
```

### 2.4 Internal API

给 Worker 和内部服务。

特点：

```text
心跳
任务领取
任务状态上报
artifact 上传回调
```

## 3. 对外一键生成 API

```http
POST /api/v1/public/videos/generate
```

请求：

```json
{
  "topic": "如何读懂毛选",
  "ip_id": "plant_teacher_universe",
  "style": "ip_default",
  "duration_level": "short",
  "bgm": true
}
```

返回：

```json
{
  "job_id": "job_xxx",
  "status": "queued",
  "estimated_credit_cost": 8
}
```

查询：

```http
GET /api/v1/public/jobs/{job_id}
```

返回：

```json
{
  "job_id": "job_xxx",
  "status": "completed",
  "video_url": "https://...",
  "thumbnail_url": "https://...",
  "duration": 42.5,
  "credit_cost": 8
}
```

## 4. App API

### 项目

```http
POST /api/v1/app/projects
GET  /api/v1/app/projects
GET  /api/v1/app/projects/{project_id}
DELETE /api/v1/app/projects/{project_id}
```

### 文案草稿

```http
POST /api/v1/app/script-drafts
GET  /api/v1/app/script-drafts/{draft_id}
PATCH /api/v1/app/script-drafts/{draft_id}/scenes/{scene_id}
POST /api/v1/app/script-drafts/{draft_id}/validate
```

### Storyboard

```http
POST /api/v1/app/storyboards
GET  /api/v1/app/storyboards/{storyboard_id}
PATCH /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}
```

### 帧级重生成

```http
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/regenerate-image-prompt
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/regenerate-image
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/regenerate-audio
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/render-segment
POST /api/v1/app/storyboards/{storyboard_id}/render-final
```

## 5. 强控制参数原则

外部用户不应直接传：

```text
media_workflow
tts_workflow
frame_template
prompt_prefix
本地 bgm_path
本地文件路径
```

应改成：

```text
workflow_id
template_id
style_id
voice_id
bgm_id
ip_id
```

后端负责：

```text
根据用户套餐过滤可用资源
根据 workflow_id 映射真实 workflow
根据 template_id 映射真实模板
根据 style_id 映射 prompt prefix
```

## 6. FastAPI 依赖设计

建议新增依赖：

```python
CurrentUserDep
CurrentWorkspaceDep
RequirePermissionDep
RequirePlanDep
QuotaDep
RateLimitDep
UsageRecorderDep
```

示例：

```python
@router.post("/videos")
async def create_video(
    request: VideoCreateRequest,
    user: CurrentUserDep,
    workspace: CurrentWorkspaceDep,
    permission = Depends(require_permission("video.generate")),
):
    ...
```

## 7. API 版本化

从一开始使用：

```text
/api/v1
```

未来 breaking change 时新增：

```text
/api/v2
```

## 8. SDK 预留

未来可以做：

```text
Python SDK
JavaScript SDK
Webhook
OpenAPI 文档
```

API 请求尽量保持：

```text
资源 ID 化
异步任务化
状态可查询
结果 URL 化
错误码标准化
```

## 9. 错误码建议

```text
AUTH_REQUIRED
PERMISSION_DENIED
QUOTA_EXCEEDED
PLAN_REQUIRED
RESOURCE_NOT_AVAILABLE
INVALID_IP_PROFILE
JOB_NOT_FOUND
WORKER_UNAVAILABLE
PROVIDER_ERROR
GENERATION_FAILED
```
