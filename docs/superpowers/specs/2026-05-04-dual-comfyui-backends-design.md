# 双 ComfyUI 后端隔离设计

## 背景

当前 Pixelle 通过一个全局 `comfyui.comfyui_url` 连接本地 ComfyUI，标准视频生成中的图片工作流与 TTS 工作流都运行在同一个 ComfyUI 进程内。近期日志显示，首个视频可以完成，但第二个视频在 `selfhost/image_z_image_turbo_gguf.json` 第一张图生成阶段失败：

```text
DefaultCPUAllocator: not enough memory
```

现有释放逻辑可以释放 ComfyUI/Torch/GGUF 扩展的显存缓存，但释放确认主要基于 `/system_stats` 的 VRAM 指标，不能保证 Python 进程的 CPU 私有内存和 Windows commit 立即归还给系统。对 32GB 内存机器而言，图片模型、GGUF CLIP、VAE、IndexTTS2 与 ComfyUI 插件共驻一个进程时，连续视频任务容易出现 CPU 内存压力累积。

本设计从源头解决该问题：将不同模型族运行在不同 ComfyUI 后端进程中，并在阶段结束后通过进程重启释放 CPU 内存，而不是把单进程 `/free` 当作长期可靠的内存边界。

## 目标

- 将标准视频生成中的图片生成和 TTS 生成隔离到两个 ComfyUI 后端进程。
- 每个后端拥有独立 DataRoot、SQLite 数据库、input/output/user 目录、runtime 目录、日志目录和 pid 文件。
- 后端之间仅共享模型路径配置，避免重复模型文件，同时避免数据库、队列状态和插件缓存互相污染。
- 图片批次完成后主动重启图片后端，TTS 批次完成后主动重启 TTS 后端，让 CPU 内存通过进程退出可靠归还给 Windows。
- 保留现有 workflow、ComfyKit、RunningHub 与默认 `comfyui_url` 兼容能力。
- 形成可扩展的后端 profile/registry 机制，后续可以自然扩展到视频、分析、动作迁移等角色，而不是增加一次性临时字段。

## 非目标

- 不重写图片或音频推理为脱离 ComfyUI 的独立模型服务。
- 不改变 RunningHub 执行路径。
- 不让标准视频流程在运行中修改全局 `comfyui_url`。
- 不以共享 DataRoot 作为首版方案；共享 DataRoot 会引入数据库锁、队列状态和插件缓存污染风险。
- 不把 OOM 后手动重启作为主要恢复方式；重启必须进入自动生命周期管理。

## 架构原则

- 后端角色是一级概念。`default`、`image`、`tts` 是明确角色，不是临时 URL 字段。
- 后端 profile 是配置、运行时状态、ComfyKit 实例、执行锁、维护客户端和托管进程的归属边界。
- 本地 ComfyUI workflow 执行必须显式绑定一个后端角色；未绑定时只能走 `default`。
- 后端生命周期管理必须幂等：重复 start/restart 不应产生重复进程，重复 stop 不应误停其他角色。
- 阶段后重启可以后台执行，但下一次使用该角色前必须等待 ready。
- 任意一个角色的重启失败不能被静默吞掉；后续需要该角色时必须失败并给出角色、URL、端口和日志路径。

## 推荐配置

保留全局 `comfyui_url` 作为兼容入口，同时新增结构化后端 profile。新实现应优先读取 `comfyui.backends`；没有配置时自动生成一个 `default` profile 指向 `comfyui_url`。

```yaml
comfyui:
  comfyui_url: http://127.0.0.1:8000
  executor_type: null
  backend_management_mode: auto
  pre_generation_cleanup_mode: force
  pre_generation_cleanup_timeout_seconds: 20.0
  model_cleanup_mode: comfyui_and_extensions

  backends:
    default:
      url: http://127.0.0.1:8000
      managed: true
      restart_after_batch: false
      data_root: E:/ComfyUIData/pixelle-default
      runtime_dir: _runtime/comfyui/default
      logs_dir: logs/comfyui/default

    image:
      url: http://127.0.0.1:8001
      managed: true
      restart_after_batch: true
      data_root: E:/ComfyUIData/pixelle-image
      runtime_dir: _runtime/comfyui/image
      logs_dir: logs/comfyui/image

    tts:
      url: http://127.0.0.1:8002
      managed: true
      restart_after_batch: true
      data_root: E:/ComfyUIData/pixelle-tts
      runtime_dir: _runtime/comfyui/tts
      logs_dir: logs/comfyui/tts

  workflow_routing:
    image: image
    tts: tts
    default: default
```

每个 `data_root` 下必须包含独立的：

```text
input/
output/
user/
user/comfyui.db
```

模型文件不复制。所有后端继续通过同一个 `extra_models_config.yaml` 读取共享模型目录。

启动脚本和后端管理器必须负责初始化 profile 目录。`input/`、`output/`、`user/`、runtime 和 logs 目录不存在时自动创建；SQLite 数据库文件由 ComfyUI 在启动时创建。实现不得要求用户手工创建这些目录。

## 路由规则

- `selfhost/image_*.json` 通过 `workflow_routing.image` 指向的后端执行。
- `selfhost/tts_*.json` 通过 `workflow_routing.tts` 指向的后端执行。
- 其他 selfhost workflow 通过 `workflow_routing.default` 指向的后端执行。
- RunningHub workflow 继续通过 RunningHub executor 执行，不受本地多后端路由影响。
- 如果路由指向的 profile 不存在，任务在执行前失败，错误中包含路由名、workflow key 和缺失 profile。
- 如果路由指向 `default` 且 `restart_after_batch=false`，行为与当前单端口模式一致。

## 生命周期

标准视频任务的本地 ComfyUI 阶段按以下顺序执行：

```text
任务开始
  等待 image 后端 ready
  图片批次 -> image 后端
  图片批次完成 -> 调度 image 后端后台重启

  等待 tts 后端 ready
  TTS 批次 -> tts 后端
  TTS 批次完成 -> 调度 tts 后端后台重启

  HyperFrames 合成
  保存任务
```

后台重启不得阻塞已经不依赖该后端的后续阶段，但下一个需要该后端的阶段必须等待 ready。例如图片后端可以在 TTS 阶段后台重启；TTS 后端可以在 HyperFrames 合成阶段后台重启。

任务结束前不强制等待所有后台重启完成，但任务管理器必须保存后台重启状态。下一个任务进入对应角色前必须等待已有重启完成并确认 ready。

## 组件设计

### 配置模型

新增配置模型：

```python
ComfyUIBackendProfile:
    url: str
    managed: bool = True
    restart_after_batch: bool = False
    data_root: Optional[str] = None
    runtime_dir: Optional[str] = None
    logs_dir: Optional[str] = None
    python_exe: Optional[str] = None
    comfyui_root: Optional[str] = None
    frontend_root: Optional[str] = None
    extra_models_config: Optional[str] = None
    database_url: Optional[str] = None

ComfyUIWorkflowRouting:
    image: str = "default"
    tts: str = "default"
    default: str = "default"
```

`ComfyUIConfig` 增加：

```python
backends: dict[str, ComfyUIBackendProfile] = {}
workflow_routing: ComfyUIWorkflowRouting = ComfyUIWorkflowRouting()
```

规范化规则：

- 若 `backends` 为空，自动创建 `default` profile，URL 使用 `comfyui_url`。
- 若 `backends.default` 缺失，自动创建 `default` profile，URL 使用 `comfyui_url`。
- profile 名称只允许小写字母、数字、下划线和短横线，避免路径与日志命名问题。
- 本地托管 profile 如果没有显式 `data_root`，使用 `E:/ComfyUIData/pixelle-<profile>`。
- 本地托管 profile 如果没有显式 `runtime_dir`，使用 `_runtime/comfyui/<profile>`。
- 本地托管 profile 如果没有显式 `logs_dir`，使用 `logs/comfyui/<profile>`。
- 本地托管 profile 如果没有显式 `database_url`，使用 `sqlite:///<data_root>/user/comfyui.db`。

### 后端注册表

新增 `ComfyUIBackendRegistry`，负责：

- 从配置生成规范化 profile。
- 按 workflow key 解析后端角色。
- 为每个角色提供 ComfyKit 配置。
- 为每个角色提供 maintenance client。
- 为每个角色提供 managed backend。
- 暴露 `is_dedicated_backend(role)`，用于判断是否允许阶段后后台重启。

PixelleVideoCore 不应把多后端逻辑散落在 MediaService、TTSService 和 pipeline 中。服务层只传递“我要执行 image/tts/default 角色”，注册表负责 URL 与托管信息。

### ComfyKit 缓存

当前 `_comfykit` 与 `_comfykit_config_hash` 是单例。新设计改为按后端角色缓存：

```python
_comfykit_by_backend: dict[str, ComfyKit]
_comfykit_config_hash_by_backend: dict[str, str]
```

构建 ComfyKit 配置时，根据后端 profile 覆盖 `comfyui_url`，其他配置如 executor、api key、RunningHub 参数沿用全局配置。重启某个后端后，只关闭并删除该角色对应的 ComfyKit 实例。

### 执行锁与 session

当前本地 ComfyUI 执行锁是全局锁。新设计改为每后端角色一把锁：

```python
_local_comfyui_execution_locks: dict[str, asyncio.Lock]
```

同一角色内串行执行，避免同一 ComfyUI 队列互相抢占；不同角色之间允许并行，图片后端重启不会阻塞 TTS 后端执行。

workflow session 需要记录 `backend_role`，一个 session 只绑定一个后端角色。跨角色阶段不得复用同一个 session。

### 执行入口

本地 workflow 执行入口增加后端角色参数：

```python
_execute_local_comfykit_workflow(
    workflow_input,
    workflow_params: dict,
    *,
    backend_role: str = "default",
)
```

MediaService 与 TTSService 在调用核心执行入口时传入角色：

- MediaService 的 image workflow 使用 `registry.resolve_role_for_media(workflow_key, media_type)`。
- TTSService 的 selfhost TTS workflow 使用 `registry.resolve_role_for_tts(workflow_key)`。
- 已有调用方不传角色时默认使用 `default`，保证兼容。

### 托管后端管理

`ManagedComfyUIBackend` 改为接收完整 profile，而不是只接收 URL。启动脚本调用时必须传入：

- `-Port`
- `-DataRoot`
- `-RuntimeDir`
- `-LogsDir`
- `-DatabaseUrl`
- 可选 `-PythonExe`
- 可选 `-ComfyUIRoot`
- 可选 `-ExtraModelsConfig`
- 可选 `-FrontEndRoot`

启动脚本职责：

- 自动创建 `DataRoot`、`DataRoot/input`、`DataRoot/output`、`DataRoot/user`、`RuntimeDir` 和 `LogsDir`。
- 根据 profile DataRoot 推导默认 SQLite URL，不复用其他 profile 的数据库。
- 启动前校验端口占用者是否属于同一 profile；如果不是，失败并输出占用进程命令行。
- 停止和失败清理只匹配同一 DataRoot、同一端口、同一 ComfyUI main.py 的进程。
- 所有 JSON 输出必须包含 profile、host、port、data_root、runtime_dir、logs_dir、pid_file、stdout_log 和 stderr_log。

脚本层必须按 profile/port 隔离 pid 和日志文件：

```text
_runtime/comfyui/image/comfyui-backend.pid
_runtime/comfyui/tts/comfyui-backend.pid
logs/comfyui/image/comfyui-backend.stdout.log
logs/comfyui/tts/comfyui-backend.stdout.log
```

停止、启动、重启和失败清理都必须只作用于目标 profile 对应的 DataRoot 与端口。禁止因为同一个 ComfyUIRoot、同一个 extra model config 或同一台机器而停止其他 profile。

### 后台重启调度

新增异步后台重启调度能力：

```python
schedule_comfyui_backend_restart(backend_role: str, reason: str) -> None
await_comfyui_backend_ready(backend_role: str) -> None
```

行为要求：

- 同一后端已有重启任务时，不重复启动第二个重启。
- 下次使用该后端前必须等待已有重启任务完成。
- 重启成功后关闭该后端角色对应 ComfyKit 实例，下一次执行重新创建。
- 重启失败时记录明确错误，并在下次需要该后端时失败，不静默继续。
- 如果 profile `managed=false`，不执行进程重启，只执行 `/free`，并在日志中说明跳过托管重启。

### 释放与 OOM 恢复

保留现有 `/free` 和扩展释放逻辑，但按后端角色调用对应 URL。

遇到 `DefaultCPUAllocator`、`not enough memory`、`std::bad_alloc` 等内存错误时：

1. 记录后端角色、URL、workflow key、底层错误。
2. 尝试该后端角色的强制释放。
3. 若 profile `managed=true`，重启对应后端。
4. 后端 ready 后重试当前 workflow 一次。
5. 若仍失败，向用户报告具体后端角色、URL、workflow、pid/log 路径和底层错误。

OOM 恢复不应依赖“显存释放确认”作为 CPU 内存恢复的证明。对 CPU OOM，进程重启是主要恢复路径。

## 用户体验

设置页保留简单模式，同时提供高级后端配置入口。

简单模式显示：

- 默认 ComfyUI 地址
- 图片 ComfyUI 地址
- TTS ComfyUI 地址
- 图片批次后重启
- TTS 批次后重启

保存时写入结构化 `backends` 和 `workflow_routing`，而不是写入临时平铺字段。

高级模式允许编辑每个 profile 的 DataRoot、runtime、logs、managed 开关与重启策略。高级模式应清楚标明：每个本地托管后端建议使用独立 DataRoot。

标准视频生成日志需要输出：

- 当前 workflow 使用的后端角色与 URL。
- 该后端的 DataRoot 和日志目录。
- 批次后是否调度重启。
- 重启开始、结束、失败原因。
- 下个阶段等待后端 ready 的耗时。

## 迁移策略

第一阶段以兼容为主，但不引入会长期存在的临时配置：

- 不自动修改用户现有 `comfyui_url`。
- `backends` 为空时自动生成 `default` profile，现有行为不变。
- UI 保存多后端配置时直接写入结构化 `backends`。
- 本地开发和测试默认仍可只启动 `8000`。
- 用户显式配置 `image` 和 `tts` profile 后才启用多后端路由。

如果用户开启阶段后重启但路由仍指向 `default`，标准视频流程不进行后台阶段后重启，只保留现有批次后释放。阶段后重启只在角色指向非 `default` 的专用 profile 时启用，避免单端口模式下图片阶段重启影响后续 TTS。

## 风险与缓解

- 多端口脚本误停进程：通过独立 DataRoot、独立 runtime/logs、目标端口检查和 managed process 校验缓解。
- 后台重启与下一阶段抢占同一后端：通过每角色重启任务和 ready 等待缓解。
- 配置错误导致端口不可达：在使用阶段前 health check，错误信息包含角色、URL、DataRoot 和日志目录。
- 两个 ComfyUI 进程同时驻留导致内存更高：图片阶段完成后立即后台重启图片后端，TTS 阶段完成后立即后台重启 TTS 后端；同时每个后端只加载对应模型族。
- 独立 DataRoot 增加目录管理成本：提供默认目录推导和启动前目录初始化检查；模型仍通过共享 extra model paths 使用同一份文件。
- 多后端 profile 配置复杂：设置页提供简单模式生成结构化配置，高级模式只用于排查和自定义部署。
- 旧配置与新配置共存导致歧义：读取时以 `backends` 为准；`comfyui_url` 仅作为 default profile 的兼容输入。

## 验证计划

- 单元测试配置默认值、profile 规范化和旧配置兼容。
- 单元测试 workflow 到后端角色的路由。
- 单元测试多 ComfyKit 缓存不会互相覆盖。
- 单元测试每后端执行锁互相独立。
- 单元测试 backend manager 对不同 profile 生成不同 DataRoot、pid、runtime 和 log 路径。
- 单元测试启动脚本在 DataRoot 子目录缺失时生成正确目录和 SQLite URL。
- 单元测试 OOM 恢复对 CPU OOM 走重启路径，而不是只依赖 `/free`。
- 集成测试或手动验证：
  - 只配置 `8000` 时现有流程不变。
  - 配置 `image/tts` profile 后，图片生成日志使用 `8001`，TTS 日志使用 `8002`。
  - 图片和 TTS 后端使用不同 DataRoot 与 SQLite 数据库。
  - 图片批次完成后 `image` 后端后台重启，TTS 阶段仍能进行。
  - TTS 批次完成后 `tts` 后端后台重启，HyperFrames 合成不受影响。
  - 第二个视频任务开始前后端 ready，并且不再复用上一轮高 CPU 私有内存的 ComfyUI 进程。

## 实施边界

本设计后续实施应拆为小步提交：

1. 配置 profile、workflow routing 和规范化逻辑。
2. 后端注册表与角色解析。
3. 多 ComfyKit 缓存和角色化执行入口。
4. 每角色执行锁与 workflow session 隔离。
5. 托管脚本 profile/DataRoot/runtime/logs 隔离。
6. 标准视频图片/TTS 阶段路由。
7. 阶段后后台重启与 ready 等待。
8. CPU OOM 重启恢复。
9. 设置页结构化多后端配置。
10. 日志、错误信息和测试补齐。
