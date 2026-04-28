# 01 项目目标与系统边界

## 1. 当前项目定位

Pixelle-Video 当前已经具备一个完整 AI 短视频生成系统的雏形：

```text
用户输入主题 / 文案
  ↓
LLM 生成旁白
  ↓
LLM 生成图片提示词
  ↓
TTS 生成音频
  ↓
ComfyUI / RunningHub / 本地模型生成图片或视频素材
  ↓
HTML 模板渲染帧画面
  ↓
FFmpeg 合成视频
  ↓
输出最终短视频
```

当前更像一个本地工具或本地 Web Demo，但未来目标应是：

```text
多用户
多 IP
多工作流
多机器
多 Provider
可计费
可追踪
可重生成
可对外提供 API
```

## 2. 未来目标

最终建议拆成四层产品：

### 2.1 Pixelle Core

核心生成引擎，不关心前端，也不直接关心会员系统。

职责：

- 文案生成
- 分镜生成
- 视觉提示词生成
- IP 上下文组装
- TTS
- 图片/视频生成
- 帧渲染
- 视频合成
- 产物版本管理

### 2.2 Pixelle Studio

你自己的网页端产品，可以用 Vue / Next.js / Nuxt / React 等重做。

职责：

- 用户登录
- 创建项目
- 选择 IP
- 输入主题
- 生成文案
- 编辑分镜
- 查看生成过程
- 每帧重抽卡
- 试听音频
- 合成视频
- 管理历史项目

### 2.3 Pixelle API

对外提供的开发者 API。

职责：

- API Key 调用
- 一键生成视频
- 创建 IP
- 查询任务
- 下载结果
- Webhook 回调
- 按套餐限制功能

### 2.4 Pixelle Workers

分布式执行层。

职责：

- 文案 Worker
- 提示词 Worker
- TTS Worker
- 图片 Worker
- 帧渲染 Worker
- 视频合成 Worker
- 上传 Worker
- 监控和心跳

## 3. 系统边界原则

### 原则 1：UI 不直接绑定生成逻辑

Streamlit 当前只是临时本地 UI。未来 Vue / Next.js 前端应该只调用 API，不应直接调用核心 Python 对象。

### 原则 2：FastAPI 不直接长时间生成视频

FastAPI 应主要负责：

```text
鉴权
参数校验
额度检查
创建任务
查询任务
返回结果
```

长时间任务交给 Worker。

### 原则 3：本地文件路径不能作为长期产物地址

多机器部署后，不能依赖：

```text
output/task_xxx/final.mp4
```

必须改成：

```text
object_key
url
artifact_id
```

例如使用 MinIO / S3 / R2 / OSS。

### 原则 4：所有生成产物都应版本化

图片、音频、提示词、单帧视频、最终视频都可能被重新生成，因此不能覆盖旧结果。

### 原则 5：所有对外参数都要强控制

外部 API 不能直接让用户传：

```text
workflow 文件路径
本地模板路径
任意 prompt_prefix
任意 bgm_path
```

应该改成：

```text
workflow_id
template_id
style_id
ip_id
voice_id
bgm_id
```

由后端根据套餐和权限做白名单过滤。

## 4. 推荐阶段路线

### 阶段 1：本地增强版

目标：

```text
IP 库
Prompt Composer
生成过程 Trace
帧级重抽卡
基础 API v1
```

### 阶段 2：多机器 Worker 版

目标：

```text
FastAPI + Redis + Postgres + MinIO
多机器 Worker
按队列分发任务
24G GPU 机器专职图片生成
M4 机器负责文案、提示词、合成
```

### 阶段 3：SaaS/API 版

目标：

```text
用户系统
会员系统
API Key
额度计费
资源权限
任务持久化
对象存储
Webhook
```

### 阶段 4：混合云版

目标：

```text
本地 GPU + 云 GPU
本地 TTS + 云 TTS
本地图像模型 + 在线图像服务
自动 Provider fallback
```
