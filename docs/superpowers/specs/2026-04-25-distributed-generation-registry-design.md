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
- 不把 PostgreSQL 替代现有本地 `output/` 视频文件存储；数据库只保存任务元数据和结果路径/URL。
- 不承诺 Redis 数据永久保存；Redis 只负责锁、租约、短期索引和运行态。

## 推荐架构

采用 PostgreSQL + Redis 双组件：

- PostgreSQL 是任务事实源，保存 task_id、generation_fingerprint、请求参数、状态、进度、结果、错误和时间戳。
- Redis 是分布式协调层，保存提交锁、运行租约、fingerprint 到 task_id 的短期索引、heartbeat TTL。
- 应用层通过 `GenerationRegistry` 访问幂等能力，通过 `TaskStore` 访问任务持久化。
- 现有 `TaskManager` 改为 facade：本地开发可用 `InMemoryTaskStore`，生产使用 `PostgresTaskStore` + `RedisGenerationLease`。

架构图：

```text
Web / API 请求
  -> build_generation_fingerprint()
  -> GenerationRegistry.reserve_or_reuse()
      -> RedisGenerationLease.acquire_submit_lock()
      -> PostgresTaskStore.find_reusable_by_fingerprint()
      -> PostgresTaskStore.create_task()
      -> RedisGenerationLease.bind_task()
  -> TaskManager.execute_task()
      -> Redis heartbeat
      -> Postgres status/progress/result updates
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

    async def mark_running(self, task_id: str, owner_id: str) -> None:
        raise NotImplementedError

    async def mark_completed(self, task_id: str, result: dict) -> None:
        raise NotImplementedError

    async def mark_failed(self, task_id: str, error: str) -> None:
        raise NotImplementedError

    async def heartbeat(self, task_id: str, owner_id: str) -> None:
        raise NotImplementedError

    async def cancel(self, task_id: str) -> bool:
        raise NotImplementedError
```

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
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error: str | None = None,
        result: dict | None = None,
    ) -> None:
        raise NotImplementedError

    async def update_progress(self, task_id: str, progress: TaskProgress) -> None:
        raise NotImplementedError

    async def list_tasks(self, status: TaskStatus | None, limit: int) -> list[Task]:
        raise NotImplementedError
```

### RedisGenerationLease

职责：

- 原子抢占提交锁，避免多个进程同时创建同 fingerprint 任务。
- 保存 active task 的短期索引。
- 对 running task 做 heartbeat 续租。
- 在 worker 崩溃时通过 TTL 自动释放运行态锁。

Redis key 约定：

```text
pixelle:generation:fingerprint:{fingerprint}:submit_lock -> owner_id
pixelle:generation:fingerprint:{fingerprint}:task_id -> task_id
pixelle:generation:task:{task_id}:lease -> owner_id
pixelle:generation:task:{task_id}:heartbeat -> unix_timestamp
```

TTL 建议：

- submit lock：30 秒，只覆盖查询/创建任务的临界区。
- task lease：120 秒，后台任务每 30 秒 heartbeat 续租。
- fingerprint task_id：24 小时，用于 completed 复用和快速查询。

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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_generation_tasks_status_created_at
    ON generation_tasks (status, created_at DESC);

CREATE INDEX idx_generation_tasks_fingerprint_status
    ON generation_tasks (generation_fingerprint, status);

CREATE INDEX idx_generation_tasks_fingerprint_completed
    ON generation_tasks (generation_fingerprint, completed_at DESC)
    WHERE status = 'completed';
```

不使用唯一约束直接限制 `generation_fingerprint`，因为同一 fingerprint 允许历史上有多个 failed 或过期任务。active 去重由 Redis submit lock + PostgreSQL 事务查询共同保证。

## 状态机

合法状态：

```text
pending -> running -> completed
pending -> running -> failed
pending -> cancelled
running -> cancelled
```

复用策略：

- active 状态：`pending`, `running`
- terminal 状态：`completed`, `failed`, `cancelled`
- 同 fingerprint 有 active task：返回已有 task_id。
- 同 fingerprint 有 24 小时内 completed task：返回已有 task_id 和 result。
- 同 fingerprint 最近是 failed/cancelled：允许创建新 task。

## API 行为

### POST `/api/video/generate/async`

新流程：

1. 构建 generation_fingerprint。
2. 调 `GenerationRegistry.reserve_or_reuse()`。
3. 如果返回 `created=False`，直接返回已有 `task_id`，message 标明复用原因。
4. 如果返回 `created=True`，启动后台执行。
5. 后台执行更新 PostgreSQL 状态和结果，Redis heartbeat 续租。

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

取消请求更新 PostgreSQL 为 `cancelled`，同时释放 Redis lease。实际底层生成如果已经进入不可中断的外部 ComfyUI 调用，取消语义为“停止继续跟踪并阻止后续进度写入”，不保证外部服务立即停止。

## Web 行为

Web 侧继续保留按钮禁用和当前 session 状态，用于即时体验。但源头防重依赖 `GenerationRegistry`，不是 UI 状态。

本地 Web 直接调用 `pixelle_video.generate_video()` 时，也要走 registry。设计上让 `PixelleVideoCore` 初始化 `GenerationRegistry`，使 Web direct、API sync、API async、batch 都共享同一套幂等入口。

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
```

默认：

- 本地非 Docker：`PIXELLE_TASK_BACKEND=memory`
- Docker Compose：`PIXELLE_TASK_BACKEND=postgres`
- 生产：`PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION=true`

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
```

`api` 和 `web` 增加：

```text
PIXELLE_TASK_BACKEND=postgres
PIXELLE_POSTGRES_DSN=postgresql+asyncpg://pixelle:pixelle@postgres:5432/pixelle
PIXELLE_REDIS_URL=redis://redis:6379/0
PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION=true
```

## 依赖

新增 Python 依赖：

- `redis>=5.0.0`
- `sqlalchemy[asyncio]>=2.0.0`
- `asyncpg>=0.29.0`
- `alembic>=1.13.0`

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

### Redis 数据丢失

- PostgreSQL 仍是事实源。
- active task 去重短时间内可能依赖 PostgreSQL 查询。
- 新请求先查 PostgreSQL active task，再尝试重建 Redis active 索引。

### PostgreSQL 中 active task 无 lease

如果 task 是 `pending` 或 `running` 且没有有效 Redis lease：

- 若 `updated_at` 超过 lease TTL 的宽限窗口，标记为 `failed`，错误为 `generation lease expired`。
- 然后允许创建新 task。

## 测试计划

单元测试：

- `RedisGenerationLease` 使用 fake Redis 或 adapter mock 验证 SET NX、TTL、heartbeat、release。
- `PostgresTaskStore` 使用测试数据库或 repository fake 验证 create/get/list/update/find reusable。
- `GenerationRegistry` 验证 active task 复用、completed 复用、failed 重试、lease 过期重试。
- `PixelleVideoCore.generate_video` 验证 Web/direct 入口也走 registry。

API 测试：

- 两个模拟进程同时提交同 fingerprint，只创建一个 task。
- duplicate async request 返回已有 task_id。
- `/api/tasks/{task_id}` 能读取持久化 task。
- completed 复用返回已有 task_id。
- failed 不复用，允许创建新 task。

集成测试：

- Docker Compose 启动 postgres + redis + api。
- 提交两个相同请求，确认 PostgreSQL 只有一个 active task。
- 停止执行进程后等待 TTL，再提交同 fingerprint，确认可重试。

回归测试：

- 现有 UI 按钮禁用、按钮恢复、最近视频刷新测试继续通过。
- 现有单进程 `GenerationCoordinator` 测试继续通过；它保留为同进程内的轻量优化，但不再是唯一防线。

## 安全与可观测性

日志字段：

- `task_id`
- `generation_fingerprint` 前 12 位
- `owner_id`
- `registry_backend`
- `reuse_reason`

指标建议：

- task_created_total
- task_reused_total
- generation_lock_acquire_failed_total
- generation_lease_expired_total
- task_status_transition_total

不在日志中输出完整用户文本或完整请求参数，沿用现有 `build_content_observability()` 的摘要策略。

## 推进顺序

1. 定义 `TaskStore`、`GenerationLease`、`GenerationRegistry` 接口和内存实现。
2. 增加 PostgreSQL store 和 migration。
3. 增加 Redis lease。
4. 改造 `TaskManager` 为 facade，API 读取持久化任务。
5. 接入 `PixelleVideoCore`，让 Web/direct/API/batch 共享 registry。
6. 更新 Docker Compose、配置和文档。
7. 补齐并运行单元、API、集成测试。

## 验收标准

- 无 Redis/PostgreSQL 的本地开发模式仍能运行现有 Web 和测试。
- Docker Compose 启动后包含 postgres、redis、api、web。
- `POST /api/video/generate/async` 对同 fingerprint 的并发请求只创建一个任务。
- 任意 API 副本都能通过 `/api/tasks/{task_id}` 查询任务。
- Redis lease 过期后相同 fingerprint 能重新创建任务。
- 生产配置缺少 Redis 或 PostgreSQL 时启动失败。
- 相关测试、ruff、语法编译通过。
