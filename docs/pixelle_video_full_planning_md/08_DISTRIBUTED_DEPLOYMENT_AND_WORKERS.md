# 08 分布式部署与 Worker 架构

## 1. 当前硬件条件

当前本地资源：

```text
4 台 Apple M4 小主机
2 台 Windows 主机：
  - NVIDIA 16G 显存 / 64G 内存
  - NVIDIA 24G 显存 / 32G 内存
```

目标：

```text
多机协同
局域网部署
不同机器按能力执行不同任务
用户少时单机即可
用户多时多机并发
未来可扩展到云端
```

## 2. 不建议一开始上 K8S

当前更适合：

```text
Docker Compose 多机部署
中央 Redis/RabbitMQ
中央 PostgreSQL
中央 MinIO
多类型 Worker
```

K8S / k3s 适合未来阶段：

```text
需要自动扩缩容
多副本 API
节点故障迁移
云端 GPU
统一滚动升级
```

## 3. 推荐第一阶段架构

```text
FastAPI API 节点
  ↓
Redis / RabbitMQ 队列
  ↓
不同 Worker 消费不同队列
  ↓
PostgreSQL 保存元数据
  ↓
MinIO 保存图片/音频/视频/trace
```

## 4. 机器分工

### M4-1：控制节点

运行：

```text
FastAPI
PostgreSQL
Redis / RabbitMQ
MinIO
管理后台
调度器
```

### M4-2 / M4-3 / M4-4：轻任务节点

运行：

```text
script-worker
prompt-worker
scene-cast-worker
trace-worker
frame-render-worker
compose-worker
tts-worker-lite
```

适合：

```text
文案生成
图片提示词生成
IP prompt 组装
HTML 渲染
FFmpeg 合成
BGM 混音
封面生成
```

### Windows 24G：主图像生成节点

运行：

```text
ComfyUI / Z-Image
image-worker-high
image-regenerate-worker
```

适合：

```text
高质量图片生成
批量图片抽卡
高优先级图像任务
未来视频模型
```

### Windows 16G：副图像/TTS节点

运行：

```text
image-worker-fast
image-worker-preview
tts-worker
backup-compose-worker
```

适合：

```text
预览图
低优先级图片
TTS
备用任务
```

## 5. 队列拆分

建议队列：

```text
queue.script
queue.prompt
queue.scene_cast
queue.tts
queue.image.fast
queue.image.high
queue.image.regenerate
queue.frame_render
queue.compose
queue.upload
queue.review
```

## 6. Worker 环境变量

### M4 文案节点

```env
NODE_NAME=m4-text-01
ENABLE_WORKER=true
WORKER_QUEUES=script,prompt,scene_cast,trace
WORKER_CONCURRENCY=8
```

### M4 合成节点

```env
NODE_NAME=m4-compose-01
ENABLE_WORKER=true
WORKER_QUEUES=frame_render,compose,upload
WORKER_CONCURRENCY=3
```

### Windows 24G

```env
NODE_NAME=win-gpu-24g
ENABLE_WORKER=true
ENABLE_COMFYUI=true
WORKER_QUEUES=image.high,image.regenerate
WORKER_CONCURRENCY=1
IMAGE_PROVIDER=local_comfyui
COMFYUI_URL=http://127.0.0.1:8188
GPU_VRAM_GB=24
```

### Windows 16G

```env
NODE_NAME=win-gpu-16g
ENABLE_WORKER=true
ENABLE_COMFYUI=true
WORKER_QUEUES=image.fast,image.preview,tts
WORKER_CONCURRENCY=1
IMAGE_PROVIDER=local_comfyui
GPU_VRAM_GB=16
```

## 7. Docker Compose Profiles

同一套代码镜像，通过 profile 启动不同角色：

```yaml
services:
  api:
    image: pixelle-video:latest
    profiles: ["api"]
    command: ["python", "-m", "api.app"]

  worker:
    image: pixelle-video:latest
    profiles: ["worker"]
    command: ["python", "-m", "pixelle_video.workers.worker_app"]
    environment:
      WORKER_QUEUES: "${WORKER_QUEUES}"
      WORKER_CONCURRENCY: "${WORKER_CONCURRENCY}"

  postgres:
    image: postgres:16
    profiles: ["control"]

  redis:
    image: redis:7
    profiles: ["control"]

  minio:
    image: minio/minio
    profiles: ["control"]
```

## 8. Worker Registry

每个 Worker 启动后向中心注册：

```json
{
  "node_id": "win-gpu-24g",
  "status": "online",
  "capabilities": {
    "image_generation": true,
    "tts": false,
    "frame_render": false,
    "gpu": {
      "vendor": "nvidia",
      "vram_gb": 24
    },
    "providers": ["local_zimage", "comfyui"]
  },
  "queues": ["image.high", "image.regenerate"],
  "max_concurrency": {
    "image": 1
  },
  "last_heartbeat": "..."
}
```

API：

```http
GET /api/v1/admin/workers
GET /api/v1/admin/workers/{node_id}
POST /api/v1/internal/workers/heartbeat
```

## 9. 并发建议

图像生成不要盲目高并发：

```text
24G GPU: IMAGE_CONCURRENCY=1 起步，测试稳定后可尝试 2
16G GPU: IMAGE_CONCURRENCY=1
M4 文案/提示词: 6-10 并发
M4 合成: 2-3 并发
```

## 10. 任务超时

```text
文案生成：60s
图片提示词：60s
TTS：180s
图片生成：300s
视频合成：600s
上传：180s
```

## 11. 失败重试

```text
文案/prompt：最多 3 次
TTS：最多 2 次
图片生成：最多 2 次
视频合成：最多 1 次
```

## 12. 本地到云端演进

### 阶段 1

```text
局域网多机
Docker Compose
Redis
PostgreSQL
MinIO
```

### 阶段 2

```text
Worker Registry
资源监控
自动 fallback
```

### 阶段 3

```text
k3s / K8S
GPU 节点标签
云 GPU
对象存储上云
```

### 阶段 4

```text
混合云调度
本地低成本产能
云端高峰兜底
```
