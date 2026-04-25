# 分布式视频生成幂等注册表设计

## 背景

当前视频生成已经完成了两层防重：

- Web UI 层：生成中按钮禁用，避免同一页面连续点击重复提交。
- 单进程服务层：`GenerationCoordinator` 通过内存 single-flight 复用同一 Python 进程内的相同生成请求。

这些能力能覆盖本地开发、单进程 Web、单进程 API，但不能覆盖生产横向扩容。多个 API 进程、多个 Docker 副本或多台机器会拥有各自独立的内存，一个请求打到进程 A、另一个相同请求打到进程 B 时，进程 B 看不到进程 A 的 in-flight 状态。

本设计引入 PostgreSQL + Redis，从源头把“生成请求幂等”和“任务状态事实”移出进程内存。

## 目标

构建一个生产级分布式生成注册表，让任意 API 进程、Web 进程或后台 worker 对同一生成 fingerprint 只创建一个权威任务，并能稳定复用该任务。

成功标准：

- 同一 fingerprint 在多进程、多容器、多机器下只创建一个 active task。
- 重复请求返回已有 task_id，而不是新建任务。
- task 状态、进度、结果、错误可跨进程读取。
- 生成进程崩溃后，Redis 租约会过期，后续请求可以安全重试或接管。
- 本地开发仍能无 Redis/PostgreSQL 运行，但生产模式缺少 Redis/PostgreSQL 时必须 fail fast。
- 当前 UI 和 API 的调用方式保持稳定，业务代码不直接操作 Redis/PostgreSQL。

## 非目标

- 不在本次设计中实现完整用户账户、权限、计费或队列优先级。
- 不改变 ComfyUI、RunningHub 或生成 pipeline 的核心执行逻辑。
- 不把 PostgreSQL 替代视频文件存储；数据库只保存任务元数据、结果 storage key、路径或 URL。
- 不承诺 Redis 数据永久保存；Redis 只负责锁、租约、短期索引和运行态。

## 推荐架构

采用 PostgreSQL + Redis 双组件：

- PostgreSQL 是任务事实源，保存 task_id、generation_fingerprint、请求参数、状态、进度、结果、错误和时间戳。
- Redis 是分布式协调层，保存提交锁、运行租约、fingerprint 到 task_id 的短期索引、heartbeat TTL。
- 应用层通过 `GenerationRegistry` 访问幂等能力，通过 `TaskStore` 访问任务持久化。
- 现有 `TaskManager` 改为 facade：本地开发可用 `InMemoryTaskStore`，生产使用 `PostgresTaskStore` + `RedisGenerationLease`。
- 生产执行路径必须引入 worker role。API 负责创建/查询/取消任务，worker 负责 claim pending task 并执行生成。API 内嵌后台执行只允许作为本地开发模式。
- 生产多机器必须使用共享制品存储。Docker Compose 单机可共享 `output` volume；多机器生产必须使用 S3/MinIO 或等价对象存储，并在 task result 中保存 storage key 和可访问 URL。
- PostgreSQL 必须拥有 active task 唯一约束，作为 Redis 之外的最终一致性防线。Redis 负责降低并发竞争和提供租约，PostgreSQL 负责保证不会持久化两个相同 fingerprint 的 active task。
- Redis 租约必须带 fencing token。所有 PostgreSQL 状态写入都要校验当前 task 的 owner_id 和 lease_token，避免旧进程在租约过期后继续写入并覆盖新执行者状态。

架构图：

```text
Web / API 请求
  -> build_generation_fingerprint()
  -> GenerationRegistry.reserve_or_reuse()
      -> RedisGenerationLease.acquire_submit_lock()
      -> PostgresTaskStore.find_reusable_by_fingerprint()
      -> PostgresTaskStore.create_task()
      -> RedisGenerationLease.bind_task()
  -> TaskExecutionQueue.enqueue_or_notify()
  -> Worker.claim_and_execute()
      -> GenerationRegistry.claim_next_pending()
      -> Redis heartbeat
      -> Postgres status/progress/result updates
      -> ArtifactStore.persist_result()
```

## 组件设计

### GenerationRegistry

职责：

- 统一处理 fingerprint 幂等。
- 在新请求进入时决定返回已有 task 还是创建新 task。
- 屏蔽 Redis 和 PostgreSQL 细节。
- 对 API、Web、未来 worker 暴露稳定接口。

建议接口：

```python
class ReserveOutcome(BaseModel):
    task: Task
    created: bool
    reused_reason: Literal["active", "recent_completed"] | None = None


class ExecutionLease(BaseModel):
    task_id: str
    owner_id: str
    lease_token: str
    lease_expires_at: datetime


class ClaimedTask(BaseModel):
    task: Task
    lease: ExecutionLease


class GenerationRegistry:
    async def reserve_or_reuse(
        self,
        *,
        fingerprint: str,
        task_type: TaskType,
        request_params: dict,
        reuse_completed_within_seconds: int,
    ) -> ReserveOutcome:
        raise NotImplementedError

    async def claim_next_pending(
        self,
        *,
        worker_id: str,
        task_types: set[TaskType] | None = None,
    ) -> ClaimedTask | None:
        raise NotImplementedError

    async def mark_running(self, task_id: str, owner_id: str, lease_token: str) -> None:
        raise NotImplementedError

    async def mark_completed(
        self,
        task_id: str,
        result: dict,
        owner_id: str,
        lease_token: str,
    ) -> None:
        raise NotImplementedError

    async def mark_failed(
        self,
        task_id: str,
        error: str,
        owner_id: str,
        lease_token: str,
    ) -> None:
        raise NotImplementedError

    async def heartbeat(self, task_id: str, owner_id: str, lease_token: str) -> None:
        raise NotImplementedError

    async def cancel(self, task_id: str) -> bool:
        raise NotImplementedError
```

`reserve_or_reuse()` 只处理提交幂等，不返回执行租约。执行权只能由 worker 通过 `claim_next_pending()` 获取，避免 API 进程错误地持有或传播执行 token。

### TaskStore

职责：

- 保存和读取权威 task 记录。
- 提供事务化创建和状态更新。
- 不直接处理 Redis 锁。

实现：

- `PostgresTaskStore`：生产默认。
- `InMemoryTaskStore`：本地开发和测试 fallback。

建议接口：

```python
class TaskStore:
    async def create_task(self, task: Task) -> Task:
        raise NotImplementedError

    async def get_task(self, task_id: str) -> Task | None:
        raise NotImplementedError

    async def find_reusable_by_fingerprint(
        self,
        *,
        fingerprint: str,
        task_type: TaskType,
        active_statuses: set[TaskStatus],
        completed_after: datetime | None,
    ) -> Task | None:
        raise NotImplementedError

    async def update_status(
        self,
        *,
        task_id: str,
        status: TaskStatus,
        owner_id: str | None = None,
        lease_token: str | None = None,
        expected_owner_id: str | None = None,
        expected_lease_token: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error: str | None = None,
        result: dict | None = None,
    ) -> None:
        raise NotImplementedError

    async def update_progress(
        self,
        *,
        task_id: str,
        progress: TaskProgress,
        expected_owner_id: str | None = None,
        expected_lease_token: str | None = None,
    ) -> None:
        raise NotImplementedError

    async def list_tasks(self, status: TaskStatus | None, limit: int) -> list[Task]:
        raise NotImplementedError
```

原则上任何 running task 写入，包括 progress，都不能绕过 fencing token。

### RedisGenerationLease

职责：

- 原子抢占提交锁，避免多个进程同时创建同 fingerprint 任务。
- 保存 active task 的短期索引。
- 对 running task 做 heartbeat 续租。
- 在 worker 崩溃时通过 TTL 自动释放运行态锁。
- 生成单调递增或随机高熵 fencing token，并要求数据库状态更新使用该 token 做 compare-and-set。

Redis key 约定：

```text
pixelle:generation:fingerprint:{fingerprint}:submit_lock -> owner_id
pixelle:generation:fingerprint:{fingerprint}:task_id -> task_id
pixelle:generation:task:{task_id}:lease -> {"owner_id": "worker-id", "lease_token": "opaque-token"}
pixelle:generation:task:{task_id}:heartbeat -> unix_timestamp
```

TTL 建议：

- submit lock：30 秒，只覆盖查询/创建任务的临界区。
- task lease：120 秒，后台任务每 30 秒 heartbeat 续租。
- fingerprint task_id：24 小时，用于 completed 复用和快速查询。

Redis 操作要求：

- acquire submit lock 使用 `SET key owner_id NX EX ttl`。
- release submit lock 使用 Lua compare-and-delete，只允许 owner 删除自己的锁。
- heartbeat 使用 Lua compare-and-expire，只允许当前 owner_id + lease_token 续租。
- release task lease 使用 Lua compare-and-delete，只允许当前 owner_id + lease_token 释放。
- 如果 heartbeat 发现 token 不匹配，执行者必须停止后续状态写入，并把任务视为 lost lease。

### TaskExecutionQueue 和 Worker

职责：

- `TaskExecutionQueue` 只负责通知有新任务可执行，不保存权威状态。
- `Worker` 通过 `GenerationRegistry.claim_next_pending()` 从 PostgreSQL 原子 claim `pending` task。
- claim 必须使用 PostgreSQL 事务和 `FOR UPDATE SKIP LOCKED`，把 task 从 `pending` 改为 `running`，同时写入 `owner_id` 和 `lease_token`。
- PostgreSQL claim 成功后创建 Redis task lease；如果 Redis lease 初始化失败，worker 不允许执行生成，必须用同一 owner/token 将 task 标记为 `failed`。
- `Worker` 获取 lease 后进入生成流程，生成过程中 heartbeat 续租。
- `Worker` 完成后调用 `ArtifactStore.persist_result()`，再 `mark_completed()`。
- `Worker` 失败时调用 `mark_failed()`，并释放 Redis lease。

开发模式：

- `TaskManager.execute_task()` 可以继续使用 in-process background task，便于本地运行和现有测试。

生产模式：

- API 不直接执行长生成任务，只创建 task 并唤醒 worker。
- Docker Compose 增加 `worker` 服务，命令为 `python -m api.worker`。
- 生产可横向扩容多个 worker；同一 task 只能被一个拥有有效 lease_token 的 worker 写状态。

### ArtifactStore

职责：

- 把生成产物从 pipeline 输出位置持久化到可被所有 API/Web/worker 读取的位置。
- 返回 `storage_key`、`video_url`、`file_size`、`duration` 等结果字段。
- 在复用 completed task 前校验制品仍存在；如果制品缺失，旧 task 必须标记为 `failed`，同时把 `artifact_status` 写为 `missing`，并允许重新生成。

实现：

- `LocalArtifactStore`：本地开发和单机 Docker 使用共享 `output/` volume。
- `ObjectArtifactStore`：多机器生产使用 S3/MinIO 兼容对象存储。

生产要求：

- 多机器部署禁止只使用容器本地磁盘保存最终视频。
- task result 不应只保存绝对本地路径；必须保存 `storage_backend`、`storage_key` 和可解析 URL。

## PostgreSQL 数据模型

新增表 `generation_tasks`：

```sql
CREATE TABLE generation_tasks (
    task_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    generation_fingerprint TEXT,
    status TEXT NOT NULL,
    request_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    progress JSONB,
    result JSONB,
    error TEXT,
    owner_id TEXT,
    lease_token TEXT,
    artifact_status TEXT NOT NULL DEFAULT 'none',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_generation_tasks_status
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    CONSTRAINT ck_generation_tasks_artifact_status
        CHECK (artifact_status IN ('none', 'persisted', 'missing'))
);

CREATE INDEX idx_generation_tasks_status_created_at
    ON generation_tasks (status, created_at DESC);

CREATE INDEX idx_generation_tasks_fingerprint_status
    ON generation_tasks (generation_fingerprint, status);

CREATE INDEX idx_generation_tasks_fingerprint_completed
    ON generation_tasks (generation_fingerprint, completed_at DESC)
    WHERE status = 'completed';

CREATE INDEX idx_generation_tasks_pending_claim
    ON generation_tasks (created_at, task_id)
    WHERE status = 'pending';

CREATE UNIQUE INDEX uq_generation_tasks_active_fingerprint
    ON generation_tasks (task_type, generation_fingerprint)
    WHERE status IN ('pending', 'running')
      AND generation_fingerprint IS NOT NULL;
```

不使用普通唯一约束直接限制 `generation_fingerprint`，因为同一 fingerprint 允许历史上有多个 failed、cancelled、completed 或过期任务。必须使用 partial unique index 限制 active 状态，避免 Redis 故障、网络抖动或进程竞态导致两个 active task 被持久化。

创建任务的事务要求：

1. 在 Redis submit lock 内开启 PostgreSQL 事务。
2. 先查询 reusable task。
3. 未命中时插入新 task。
4. 如果插入触发 `uq_generation_tasks_active_fingerprint` 冲突，回滚插入并重新查询 active task，返回已有 task_id。
5. 事务提交后再写 Redis fingerprint task_id 短期索引。

worker claim 的事务要求：

1. 用 `SELECT ... FOR UPDATE SKIP LOCKED` 选择最早的 `pending` task。
2. 在同一事务内生成并写入 `owner_id`、`lease_token`、`started_at`，状态改为 `running`。
3. 事务提交后立即创建 Redis task lease 并启动 heartbeat。
4. 若 Redis lease 初始化失败，必须用当前 owner/token 做 CAS，把 task 标记为 `failed`；不能在无 lease 状态下继续执行。
5. migration 必须创建 `updated_at` 自动刷新 trigger，所有状态和进度写入都要更新 `updated_at`。

## 状态机

合法状态：

```text
pending -> running -> completed
pending -> running -> failed
pending -> cancelled
running -> cancelled
running -> failed
```

复用策略：

- active 状态：`pending`, `running`
- terminal 状态：`completed`, `failed`, `cancelled`
- 同 fingerprint 有 active task：返回已有 task_id。
- 同 fingerprint 有 24 小时内 completed task，且 `ArtifactStore.exists(result.storage_key)` 为真：返回已有 task_id 和 result。
- completed task 的制品不存在：标记为 `failed`，`artifact_status='missing'`，错误为 `artifact missing`，允许创建新 task。
- 同 fingerprint 最近是 failed/cancelled：允许创建新 task。
- `running -> completed/failed/cancelled` 和 progress 写入必须校验 `expected_owner_id` 和 `expected_lease_token`。校验失败说明执行者已经失去租约，状态写入必须被拒绝。

## API 行为

### POST `/api/video/generate/async`

新流程：

1. 构建 generation_fingerprint。
2. 调 `GenerationRegistry.reserve_or_reuse()`。
3. 如果返回 `created=False`，直接返回已有 `task_id`，message 标明复用原因。
4. 如果返回 `created=True`，写入 pending task，并唤醒 worker。
5. worker claim task 后更新 PostgreSQL 状态和结果，Redis heartbeat 续租。

响应保持兼容：

```json
{
  "success": true,
  "message": "Task created successfully",
  "task_id": "task_123"
}
```

复用 active task 时：

```json
{
  "success": true,
  "message": "Task already running",
  "task_id": "task_123"
}
```

复用 recent completed task 时：

```json
{
  "success": true,
  "message": "Task already completed",
  "task_id": "task_123"
}
```

### GET `/api/tasks/{task_id}`

从 `TaskStore` 读取任务，而不是只读当前进程内存。这样任意 API 副本都能查询任意任务。

### GET `/api/tasks`

从 `TaskStore` 列表读取，按 `created_at DESC` 排序。

### Cancel

取消请求先在 PostgreSQL 中把 task 状态改为 `cancelled`，并清空或轮换 `lease_token`，让旧执行者后续 CAS 写入失败。随后可以按数据库中记录的 owner/token 尝试释放 Redis lease。实际底层生成如果已经进入不可中断的外部 ComfyUI 调用，取消语义为“停止继续跟踪并阻止后续进度写入”，不保证外部服务立即停止。Worker 在每次 progress callback 和每次 heartbeat 前后都要检查 task 是否已 cancelled；若已取消，停止后续状态写入。

## Web 行为

Web 侧继续保留按钮禁用和当前 session 状态，用于即时体验。但源头防重依赖 `GenerationRegistry`，不是 UI 状态。

本地 Web 直接调用 `pixelle_video.generate_video()` 时，也要走 registry。设计上让 `PixelleVideoCore` 初始化 `GenerationRegistry`，使 Web direct、API sync、API async、batch 都共享同一套幂等入口。

生产 Web 不应直接执行长生成任务。生产 Web 应调用 API async endpoint 创建任务，再通过 task endpoint 轮询状态和读取结果。这样 Streamlit 容器重启不会中断生成，生成执行由 worker 承担。

## 配置

新增环境变量：

```text
PIXELLE_TASK_BACKEND=memory|postgres
PIXELLE_POSTGRES_DSN=postgresql+asyncpg://pixelle:pixelle@postgres:5432/pixelle
PIXELLE_REDIS_URL=redis://redis:6379/0
PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION=false|true
PIXELLE_GENERATION_LEASE_TTL_SECONDS=120
PIXELLE_GENERATION_HEARTBEAT_SECONDS=30
PIXELLE_COMPLETED_REUSE_SECONDS=86400
PIXELLE_EXECUTION_MODE=embedded|worker
PIXELLE_ARTIFACT_BACKEND=local|s3
PIXELLE_ARTIFACT_BASE_URL=http://localhost:8000/api/files
PIXELLE_S3_ENDPOINT_URL=http://minio:9000
PIXELLE_S3_BUCKET=pixelle-output
PIXELLE_S3_REGION=us-east-1
PIXELLE_S3_PUBLIC_BASE_URL=https://cdn.example.com/pixelle-output
AWS_ACCESS_KEY_ID=<secret-from-deployment>
AWS_SECRET_ACCESS_KEY=<secret-from-deployment>
```

默认：

- 本地非 Docker：`PIXELLE_TASK_BACKEND=memory`
- Docker Compose：`PIXELLE_TASK_BACKEND=postgres`
- 生产：`PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION=true`
- 本地开发：`PIXELLE_EXECUTION_MODE=embedded`
- Docker/生产：`PIXELLE_EXECUTION_MODE=worker`

当 `PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION=true` 且 Redis 或 PostgreSQL 不可用时，API 启动失败。这样避免用户误以为已经具备横向扩容防重能力。

## Docker Compose

新增服务：

```text
postgres:
  image: postgres:16
  volumes:
    - postgres_data:/var/lib/postgresql/data

redis:
  image: redis:7
  command: redis-server --appendonly yes
  volumes:
    - redis_data:/data

worker:
  build:
    context: .
    dockerfile: Dockerfile
  command: .venv/bin/python -m api.worker
  depends_on:
    - postgres
    - redis
  volumes:
    - ./config.yaml:/app/config.yaml
    - ./data:/app/data
    - ./output:/app/output
```

`api` 和 `web` 增加：

```text
PIXELLE_TASK_BACKEND=postgres
PIXELLE_POSTGRES_DSN=postgresql+asyncpg://pixelle:pixelle@postgres:5432/pixelle
PIXELLE_REDIS_URL=redis://redis:6379/0
PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION=true
PIXELLE_EXECUTION_MODE=worker
PIXELLE_ARTIFACT_BACKEND=local
```

上面的 `local` artifact backend 只适用于单机 Docker Compose，必须通过同一个 `./output:/app/output` volume 让 api、web、worker 读取同一份文件。多机器生产必须改为 `PIXELLE_ARTIFACT_BACKEND=s3`，并配置 S3/MinIO endpoint、bucket、region 和凭证。

新增一次性 migration 服务：

```text
migrate:
  build:
    context: .
    dockerfile: Dockerfile
  command: .venv/bin/python -m api.tasks.migrate upgrade
  depends_on:
    postgres:
      condition: service_healthy
  environment:
    PIXELLE_TASK_BACKEND: postgres
    PIXELLE_POSTGRES_DSN: postgresql+asyncpg://pixelle:pixelle@postgres:5432/pixelle
```

`api`、`web`、`worker` 必须依赖 `migrate` 成功完成。`postgres` 和 `redis` 需要 healthcheck，不能只依赖容器启动顺序。

## 依赖

新增 Python 依赖：

- `redis>=5.0.0`
- `sqlalchemy[asyncio]>=2.0.0`
- `asyncpg>=0.29.0`
- `alembic>=1.13.0`
- `boto3>=1.34.0`，仅在启用 `PIXELLE_ARTIFACT_BACKEND=s3` 时需要

SQLAlchemy 用于 async PostgreSQL 访问。Alembic 用于 schema migration，避免启动时靠 ad hoc SQL 悄悄改库。

## 迁移与启动

新增 migration：

- `0001_create_generation_tasks`

启动策略：

1. API 启动时读取 `PIXELLE_TASK_BACKEND`。
2. 如果是 `postgres`，初始化 database engine，执行连接健康检查。
3. 校验 Redis 连接。
4. 不在 API 进程自动执行破坏性 migration；Docker/部署文档提供显式 migration 命令。
5. 开发环境允许显式命令 `python -m api.tasks.migrate upgrade`。
6. Docker Compose 增加一次性 `migrate` 服务，API 和 worker 必须等待 migration 成功后启动。

## 故障处理

### Redis 不可用

- 生产模式：启动失败或请求失败，不回退内存。
- 开发模式：记录 warning，回退 `InMemoryGenerationRegistry`。

### PostgreSQL 不可用

- 生产模式：启动失败或请求失败。
- 开发模式：回退内存。

### 执行进程崩溃

- Redis lease TTL 到期。
- PostgreSQL 仍保留 task 为 `running`。
- 下一次相同 fingerprint 请求发现 lease 已过期，可将旧 task 标记为 `failed`，创建新 task。
- 如果旧进程恢复并尝试写 completed，PostgreSQL owner_id + lease_token 校验必须拒绝该写入。

### Redis 数据丢失

- PostgreSQL 仍是事实源。
- active task 去重短时间内可能依赖 PostgreSQL 查询。
- 新请求先查 PostgreSQL active task，再尝试重建 Redis active 索引。
- 正在执行的 worker 如果发现 Redis lease 丢失，但 PostgreSQL 中 owner/token 仍匹配当前执行者，可以先重建同 owner/token 的 Redis lease；如果数据库 token 已变化，必须停止写入。

### PostgreSQL 中 active task 无 lease

如果 task 是 `pending` 或 `running` 且没有有效 Redis lease：

- 若 `updated_at` 超过 lease TTL 的宽限窗口，标记为 `failed`，错误为 `generation lease expired`。
- 然后允许创建新 task。

### 制品缺失

- completed task 的 result 指向的 `storage_key` 不存在时，不复用该 task。
- 将 task 标记为 `failed`，错误为 `artifact missing`。
- 允许创建新 task。

## 测试计划

单元测试：

- `RedisGenerationLease` 使用 fake Redis 或 adapter mock 验证 SET NX、TTL、heartbeat、release。
- `PostgresTaskStore` 使用测试数据库或 repository fake 验证 create/get/list/update/find reusable。
- `GenerationRegistry` 验证 active task 复用、completed 复用、failed 重试、lease 过期重试。
- `GenerationRegistry.claim_next_pending` 验证两个 worker 并发 claim 时只有一个 worker 拿到同一 task。
- `PixelleVideoCore.generate_video` 验证 Web/direct 入口也走 registry。
- `ArtifactStore` 验证 local 存在性检查、缺失制品不复用、结果字段包含 storage key。
- `Worker` 验证 claim pending task、heartbeat、lost lease 后拒绝写 progress 和完成态。

API 测试：

- 两个模拟进程同时提交同 fingerprint，只创建一个 task。
- duplicate async request 返回已有 task_id。
- `/api/tasks/{task_id}` 能读取持久化 task。
- completed 复用返回已有 task_id。
- failed 不复用，允许创建新 task。
- production Web/API 路径验证 API 创建 task 后由 worker 执行，而不是 API 进程直接执行长任务。

集成测试：

- Docker Compose 启动 postgres + redis + migrate + api + worker。
- 提交两个相同请求，确认 PostgreSQL 只有一个 active task。
- 停止执行进程后等待 TTL，再提交同 fingerprint，确认可重试。
- completed task 制品被删除后，再提交同 fingerprint，确认重新生成。

回归测试：

- 现有 UI 按钮禁用、按钮恢复、最近视频刷新测试继续通过。
- 现有单进程 `GenerationCoordinator` 测试继续通过；它保留为同进程内的轻量优化，但不再是唯一防线。

## 安全与可观测性

日志字段：

- `task_id`
- `generation_fingerprint` 前 12 位
- `owner_id`
- `lease_token` 前 12 位
- `registry_backend`
- `reuse_reason`
- `artifact_backend`
- `storage_key`

指标建议：

- task_created_total
- task_reused_total
- generation_lock_acquire_failed_total
- generation_lease_expired_total
- generation_lost_lease_total
- artifact_missing_total
- task_status_transition_total

不在日志中输出完整用户文本或完整请求参数，沿用现有 `build_content_observability()` 的摘要策略。

## 推进顺序

1. 定义 `TaskStore`、`GenerationLease`、`GenerationRegistry` 接口和内存实现。
2. 增加 PostgreSQL store 和 migration。
3. 增加 Redis lease。
4. 增加 `ArtifactStore` 本地实现，并把 completed 复用绑定到制品存在性检查。
5. 增加 worker role 和 task claim/heartbeat 执行循环。
6. 改造 `TaskManager` 为 facade，API 读取持久化任务。
7. 接入 `PixelleVideoCore`，让 Web/direct/API/batch 共享 registry。
8. 更新 Docker Compose、migration 服务、配置和文档。
9. 补齐并运行单元、API、集成测试。

## 验收标准

- 无 Redis/PostgreSQL 的本地开发模式仍能运行现有 Web 和测试。
- Docker Compose 启动后包含 postgres、redis、api、web、worker、migrate。
- `POST /api/video/generate/async` 对同 fingerprint 的并发请求只创建一个任务。
- 任意 API 副本都能通过 `/api/tasks/{task_id}` 查询任务。
- Redis lease 过期后相同 fingerprint 能重新创建任务。
- 生产模式下生成任务由 worker 执行，API 不直接承担长任务。
- completed task 的制品存在时才复用；制品缺失时自动重新生成。
- 生产配置缺少 Redis 或 PostgreSQL 时启动失败。
- 相关测试、ruff、语法编译通过。
