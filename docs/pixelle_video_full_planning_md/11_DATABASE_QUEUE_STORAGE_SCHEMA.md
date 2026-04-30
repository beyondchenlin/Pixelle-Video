# 11 数据库、队列与对象存储设计

## 1. 数据库选择

建议：

```text
PostgreSQL：主数据库
Redis/RabbitMQ：任务队列和状态缓存
MinIO：本地对象存储
```

未来上云：

```text
PostgreSQL 云数据库
Redis 云服务
S3 / R2 / OSS 对象存储
```

## 2. 核心表

### 用户与权限

```text
users
workspaces
workspace_members
plans
subscriptions
api_keys
usage_ledger
credit_transactions
```

### IP 与资源

```text
ip_profiles
ip_characters
ip_assets
ip_worlds
style_presets
resource_presets
workflow_presets
template_presets
bgm_assets
voice_presets
```

### 项目与分镜

```text
projects
script_drafts
script_scenes
storyboards
storyboard_frames
artifact_versions
generation_jobs
generation_events
```

### Worker

```text
worker_nodes
worker_heartbeats
provider_status
queue_snapshots
```

## 3. projects

```sql
CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

## 4. storyboards

```sql
CREATE TABLE storyboards (
    storyboard_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL,
    ip_id TEXT,
    style_id TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

## 5. storyboard_frames

```sql
CREATE TABLE storyboard_frames (
    frame_id TEXT PRIMARY KEY,
    storyboard_id TEXT NOT NULL,
    frame_index INT NOT NULL,
    narration TEXT,
    scene_goal TEXT,
    base_image_prompt TEXT,
    final_image_prompt TEXT,
    negative_prompt TEXT,
    selected_image_version_id TEXT,
    selected_audio_version_id TEXT,
    selected_segment_version_id TEXT,
    ip_id TEXT,
    style_id TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

## 6. artifact_versions

```sql
CREATE TABLE artifact_versions (
    artifact_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    storyboard_id TEXT,
    frame_id TEXT,
    artifact_type TEXT NOT NULL,
    version INT NOT NULL,
    status TEXT NOT NULL,
    provider TEXT,
    prompt TEXT,
    seed BIGINT,
    object_key TEXT,
    url TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL
);
```

## 7. generation_jobs

```sql
CREATE TABLE generation_jobs (
    job_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    project_id TEXT,
    storyboard_id TEXT,
    frame_id TEXT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INT DEFAULT 0,
    queue_name TEXT,
    estimated_credit_cost NUMERIC,
    actual_credit_cost NUMERIC,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

## 8. generation_events

```sql
CREATE TABLE generation_events (
    event_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    project_id TEXT,
    storyboard_id TEXT,
    frame_id TEXT,
    stage TEXT NOT NULL,
    role TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    content JSONB,
    raw_prompt_object_key TEXT,
    raw_response_object_key TEXT,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL
);
```

## 9. worker_nodes

```sql
CREATE TABLE worker_nodes (
    node_id TEXT PRIMARY KEY,
    host TEXT,
    status TEXT NOT NULL,
    capabilities JSONB DEFAULT '{}',
    queues JSONB DEFAULT '[]',
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

## 10. 对象存储结构

```text
workspaces/{workspace_id}/
  projects/{project_id}/
    scripts/
    storyboards/
    frames/
      frame_001/
        prompts/
        images/
        audio/
        segments/
      frame_002/
        ...
    final/
      final_v1.mp4
      final_v2.mp4
    thumbnails/
    traces/
```

## 11. 队列消息结构

```json
{
  "job_id": "job_xxx",
  "job_type": "regenerate_image",
  "workspace_id": "ws_xxx",
  "project_id": "proj_xxx",
  "storyboard_id": "sb_xxx",
  "frame_id": "frame_001",
  "artifact_id": "art_xxx",
  "priority": 10,
  "payload": {
    "provider_id": "local_zimage_24g",
    "prompt": "...",
    "width": 1080,
    "height": 1920,
    "seed": 123
  },
  "idempotency_key": "..."
}
```

## 12. 幂等设计

每个任务都要有：

```text
job_id
artifact_id
idempotency_key
```

避免：

```text
Worker 重启后重复扣费
重复生成多个无主文件
重复上传
重复改 selected version
```

## 13. Stage 0.5 执行原则

第一阶段可以先不实现所有生产数据库表和对象存储客户端，但不能把 SQLite / JSON 文件作为领域事实源合同。必须先定义并使用：

```text
Repository / Store interfaces
PostgreSQL schema contract
Object Storage key contract
InMemory / Filesystem dev adapters
Production fail-fast config
```

本地开发适配器只能在 dev/test profile 下由工厂注入。生产 profile 缺少 PostgreSQL、Redis 或对象存储配置时必须启动失败，避免把临时本地文件误认为可部署架构。
