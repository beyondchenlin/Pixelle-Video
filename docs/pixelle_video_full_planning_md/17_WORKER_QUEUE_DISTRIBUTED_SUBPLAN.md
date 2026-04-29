# 17 Worker / Queue / 分布式执行分方案

用途：定义异步任务、多机器 Worker、队列和恢复机制。  
上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`

---

## 1. 定位

Worker / Queue 是 Pixelle 从本地工作台走向多机器生产系统的执行基础。

FastAPI 负责控制面，Worker 负责执行面。长任务不能长期由 API 请求同步执行。

---

## 2. 任务类型

建议拆分：

```text
script.generate
storyboard.generate
prompt.generate
image.generate
image.regenerate
tts.generate
tts.regenerate
video.segment.generate
render.final
```

阶段 5 先支持 prompt、image、tts、render 的基础拆分。

---

## 3. 队列

初期队列：

```text
queue.text
queue.image.high
queue.image.low
queue.tts
queue.render
```

后续根据 Provider 和套餐拆细。

---

## 4. Worker 能力

```text
WorkerNode
  worker_id
  hostname
  capabilities
  provider_ids
  max_concurrency
  heartbeat_at
  status

WorkerLease
  job_id
  worker_id
  lease_until
  attempt
```

现有 `api/tasks` 的 lease / heartbeat 基础应优先复用。

---

## 5. 执行规则

- Worker 领取任务前检查 lease。
- Worker 开始执行后写 Trace。
- Worker 失败时写 failed event。
- 超时任务可被重新领取。
- 幂等 key 防止重复写入 ArtifactVersion。

---

## 6. 存储路线

阶段 5：

```text
Postgres task store
local artifact store
local object files
```

后续：

```text
Redis queue
MinIO / S3 object storage
Worker Registry
```

---

## 7. API 合同

```text
POST /internal/jobs/{job_id}/lease
POST /internal/jobs/{job_id}/heartbeat
POST /internal/jobs/{job_id}/complete
POST /internal/jobs/{job_id}/fail
GET  /admin/workers
```

Internal API 不对 Public API 暴露。

---

## 8. 验收标准

- FastAPI 不同步执行长任务。
- Worker 崩溃后任务能恢复、重试或失败归档。
- 每个任务有 attempt 和 trace。
- 图片任务可以按高低优先级分队列。
- ArtifactVersion 写入具备幂等保护。

---

## 9. 非目标

- 阶段 5 不上 Kubernetes。
- 阶段 5 不做复杂自动扩缩容。
- 阶段 5 不把所有本地服务一次性迁移到云。
