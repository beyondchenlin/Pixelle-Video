# 双 ComfyUI 后端隔离设计

## 背景

当前 Pixelle 通过一个全局 `comfyui.comfyui_url` 连接本地 ComfyUI，标准视频生成中的图片工作流与 TTS 工作流都运行在同一个 ComfyUI 进程内。近期日志显示，首个视频可以完成，但第二个视频在 `selfhost/image_z_image_turbo_gguf.json` 第一张图生成阶段失败：

```text
DefaultCPUAllocator: not enough memory
```

现有释放逻辑可以释放 ComfyUI/Torch/GGUF 扩展的显存缓存，但释放确认主要基于 `/system_stats` 的 VRAM 指标，不能保证 Python 进程的 CPU 私有内存和 Windows commit 立即归还给系统。对 32GB 内存机器而言，图片模型、GGUF CLIP、VAE、IndexTTS2 与 ComfyUI 插件共驻一个进程时，连续视频任务容易出现 CPU 内存压力累积。

## 目标

- 将标准视频生成中的图片生成和 TTS 生成隔离到两个 ComfyUI 后端进程。
- 图片批次完成后主动重启图片后端，TTS 批次完成后主动重启 TTS 后端，让 CPU 内存通过进程退出可靠归还给 Windows。
- 保留现有 workflow、ComfyKit、RunningHub 与默认 `comfyui_url` 兼容能力。
- 第一阶段只覆盖标准视频生成的图片批次和 TTS 批次，不扩展到动作迁移、数字人、素材分析等其他流程。

## 非目标

- 不重写图片或音频推理为脱离 ComfyUI 的独立模型服务。
- 不改变 RunningHub 执行路径。
- 不在本阶段引入任意复杂 workflow 路由表。
- 不解决所有第三方 ComfyUI 插件内部的 CPU 内存释放行为，而是通过进程级隔离与阶段后重启规避该类风险。

## 推荐方案

新增两个服务专用 ComfyUI 地址，保留全局默认地址作为兜底：

```yaml
comfyui:
  comfyui_url: http://127.0.0.1:8000
  image_comfyui_url: http://127.0.0.1:8001
  tts_comfyui_url: http://127.0.0.1:8002
  restart_image_backend_after_batch: true
  restart_tts_backend_after_batch: true
```

路由规则：

- `selfhost/image_*.json` 通过图片后端执行。
- `selfhost/tts_*.json` 通过 TTS 后端执行。
- 其他 selfhost workflow 继续通过全局 `comfyui_url` 执行。
- RunningHub workflow 继续通过 RunningHub executor 执行，不受多后端配置影响。

## 生命周期

标准视频任务的本地 ComfyUI 阶段按以下顺序执行：

```text
任务开始
  等待图片后端 ready
  图片批次 -> image_comfyui_url
  图片批次完成 -> 后台重启图片后端

  等待 TTS 后端 ready
  TTS 批次 -> tts_comfyui_url
  TTS 批次完成 -> 后台重启 TTS 后端

  HyperFrames 合成
  保存任务
```

后台重启不得阻塞已经不依赖该后端的后续阶段，但下一个需要该后端的阶段必须等待 ready。例如图片后端可以在 TTS 阶段后台重启；TTS 后端可以在 HyperFrames 合成阶段后台重启。

## 组件设计

### 配置层

`ComfyUIConfig` 增加服务专用 URL 与重启开关：

- `image_comfyui_url: Optional[str]`
- `tts_comfyui_url: Optional[str]`
- `restart_image_backend_after_batch: bool = false`
- `restart_tts_backend_after_batch: bool = false`

默认值保持兼容：如果服务专用 URL 为空，对应服务继续走 `comfyui_url`。

### 后端选择

新增后端角色概念：

- `default`
- `image`
- `tts`

PixelleVideoCore 根据 workflow 或调用场景解析后端角色：

- MediaService 的 image workflow 默认角色为 `image`。
- TTSService 的 selfhost TTS workflow 默认角色为 `tts`。
- 未识别角色为 `default`。

每个角色需要独立维护：

- ComfyKit 实例缓存。
- ComfyUI 执行锁。
- workflow session 状态。
- maintenance client。
- backend manager。
- 后台重启任务状态。

### ComfyKit 缓存

当前 `_comfykit` 与 `_comfykit_config_hash` 是单例。新设计改为按后端角色缓存：

```text
_comfykit_by_backend: dict[str, ComfyKit]
_comfykit_config_hash_by_backend: dict[str, str]
```

构建 ComfyKit 配置时，根据后端角色覆盖 `comfyui_url`，其他配置如 executor、api key、RunningHub 参数沿用全局配置。

### 执行入口

本地 workflow 执行入口增加后端角色参数：

```text
_execute_local_comfykit_workflow(workflow_input, workflow_params, backend_role)
```

MediaService 与 TTSService 在调用核心执行入口时传入角色。已有调用方不传角色时默认使用 `default`，保证兼容。

### 托管后端管理

现有 `ManagedComfyUIBackend` 可以接收不同 URL 并调用 `scripts/comfyui/start_backend.ps1 -Port`。但脚本当前 pid/log 文件名固定，不能直接稳定支持多端口并发。需要改为按端口区分：

```text
_runtime/comfyui/comfyui-backend-8001.pid
_runtime/comfyui/comfyui-backend-8002.pid
logs/comfyui/comfyui-backend-8001.stdout.log
logs/comfyui/comfyui-backend-8002.stdout.log
```

停止、启动、重启和失败清理都必须只作用于目标端口对应的进程。禁止因为同一个 `DataRoot` 而停止其他端口后端。

### 阶段后重启

新增异步后台重启调度能力：

```text
schedule_comfyui_backend_restart(backend_role, reason)
await_comfyui_backend_ready(backend_role)
```

行为要求：

- 同一后端已有重启任务时，不重复启动第二个重启。
- 下次使用该后端前必须等待已有重启任务完成。
- 重启成功后关闭该后端角色对应 ComfyKit 实例，下一次执行重新创建。
- 重启失败时记录明确错误，并在下次需要该后端时失败，不静默继续。

### 释放与 OOM 恢复

保留现有 `/free` 和扩展释放逻辑，但按后端角色调用对应 URL。

遇到 `DefaultCPUAllocator`、`not enough memory`、`std::bad_alloc` 等内存错误时：

1. 先尝试该后端角色的强制释放。
2. 若服务专用重启开关开启，重启对应后端。
3. 后端 ready 后重试当前 workflow 一次。
4. 若仍失败，向用户报告具体后端角色、URL、workflow 和底层错误。

## 用户体验

设置页增加可选字段：

- 图片 ComfyUI 地址
- TTS ComfyUI 地址
- 图片批次后重启
- TTS 批次后重启

如果用户不配置专用地址，界面和行为保持当前单端口模式。

标准视频生成日志需要输出：

- 当前 workflow 使用的后端角色与 URL。
- 批次后是否调度重启。
- 重启开始、结束、失败原因。
- 下个阶段等待后端 ready 的耗时。

## 迁移策略

第一阶段以兼容为主：

- 不自动修改用户现有 `comfyui_url`。
- 新配置为空时完全保留当前行为。
- 本地开发和测试默认仍可只启动 `8000`。
- 用户显式配置 `8001/8002` 后才启用多后端路由。

如果用户开启阶段后重启但未配置服务专用 URL，则重启将作用于默认后端。为避免单端口模式下图片阶段重启影响后续 TTS，标准视频流程应只在服务专用 URL 与默认 URL 不同的时候启用后台阶段后重启；否则降级为现有批次后释放。

## 风险与缓解

- 多端口脚本误停进程：通过按端口 pid/log 文件和按目标端口检查监听进程缓解。
- 后台重启与下一阶段抢占同一后端：通过每角色重启任务和 ready 等待缓解。
- 配置错误导致端口不可达：在使用阶段前 health check，错误信息包含角色和 URL。
- 两个 ComfyUI 进程同时驻留导致内存更高：图片阶段完成后立即后台重启图片后端，TTS 阶段完成后立即后台重启 TTS 后端；同时建议用户不要同时开启无关大型 ComfyUI 工作流。
- 共享 DataRoot 与数据库并发风险：首版建议两个后端共享模型目录和输出目录，但运行不同端口。若 ComfyUI 数据库锁冲突出现，再升级为每角色独立 DataRoot、共享 extra model paths。

## 验证计划

- 单元测试配置默认值与专用 URL 解析。
- 单元测试 workflow 到后端角色的路由。
- 单元测试多 ComfyKit 缓存不会互相覆盖。
- 单元测试 backend manager 对不同端口生成不同 pid/log 文件。
- 集成测试或手动验证：
  - 只配置 `8000` 时现有流程不变。
  - 配置 `8001/8002` 后，图片生成日志使用 `8001`，TTS 日志使用 `8002`。
  - 图片批次完成后 `8001` 后台重启，TTS 阶段仍能进行。
  - TTS 批次完成后 `8002` 后台重启，HyperFrames 合成不受影响。
  - 第二个视频任务开始前后端 ready，并且不再复用上一轮高 CPU 私有内存的 ComfyUI 进程。

## 实施边界

本设计后续实施应拆为小步提交：

1. 配置和后端角色模型。
2. 多 ComfyKit 缓存和角色化执行入口。
3. 托管脚本端口级 pid/log 隔离。
4. 标准视频图片/TTS 阶段路由。
5. 阶段后后台重启与 ready 等待。
6. 日志、错误信息和测试补齐。
