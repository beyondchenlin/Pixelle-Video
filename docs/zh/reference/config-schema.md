# 配置文件详解

`config.yaml` 配置文件的详细说明。

---

## 配置结构

```yaml
llm:
  api_key: "your-api-key"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  model: "qwen-plus"

comfyui:
  comfyui_url: "http://127.0.0.1:8188"
  backend_management_mode: "auto"
  comfyui_api_key: ""  # ComfyUI API 密钥（可选）
  runninghub_api_key: ""
  runninghub_concurrent_limit: 1  # 并发限制 (1-10)
  runninghub_instance_type: ""  # 实例类型（可选，设为 "plus" 使用 48GB 显存）
  
  image:
    default_workflow: "selfhost/image_z_image_turbo.json"
    prompt_prefix: "Minimalist illustration style"
  
  video:
    default_workflow: "runninghub/video_wan2.1_fusionx.json"
    prompt_prefix: "Minimalist illustration style"
  
  tts:
    default_workflow: "selfhost/tts_edge.json"

template:
  default_template: "1080x1920/image_default.html"
```

---

## LLM 配置

- `api_key`: API 密钥
- `base_url`: API 服务地址（支持任何 OpenAI 兼容接口）
- `model`: 模型名称

---

## ComfyUI 配置

### 基础配置

- `comfyui_url`: 本地 ComfyUI 地址（默认 `http://127.0.0.1:8188`）
- `backend_management_mode`: ComfyUI 生命周期策略。`"auto"` 优先复用健康的现有后端，只在地址不可用且配置允许时启动新进程；`"required"` 只接受由 Pixelle 启动并拥有的进程；`"disabled"` 只连接外部后端，永不启动、停止或重启 ComfyUI。
- `comfyui_api_key`: ComfyUI API 密钥（可选，用于 [Comfy Platform](https://platform.comfy.org/profile/api-keys)）

Pixelle 在提交本地工作流前通过 `/system_stats` 验证后端健康，并只观察共享队列，不中断或清空其他客户端任务。对 Pixelle 自己启动的进程，`restart_after_batch: true` 可以在阶段边界重启并释放显存；对外部启动并被复用的进程，Pixelle 不执行停止、重启或全局队列清理。图片和语音任务仍提交到同一队列，因此可以在现有 ComfyUI 界面查看生成过程和历史记录。严格依赖阶段重启释放显存的部署应使用 `backend_management_mode: "required"`。

任务运行日志会写入结构化的 `local_media_batch` start/end 事件，包含耗时毫秒数和帧数量；也会写入 `comfyui_memory_release` 事件。ComfyUI `/free` 释放会在 `/system_stats` 可用时记录释放前后的显存快照；IndexTTS2 释放响应中如果包含 CUDA allocated/reserved 的 before/after 快照，也会保存在日志字段里。

### RunningHub 云端配置

- `runninghub_api_key`: RunningHub API 密钥（使用云端工作流时必填）
- `runninghub_concurrent_limit`: 并发执行限制（1-10，普通会员默认为 1）
- `runninghub_instance_type`: 实例类型（可选）
  - 留空或不设置：使用 24GB 显存机器
  - `"plus"`: 使用 48GB 显存机器（适合大尺寸视频生成）

### 图像配置

- `default_workflow`: 默认图像生成工作流
- `prompt_prefix`: 提示词前缀

### 视频配置

- `default_workflow`: 默认视频生成工作流
  - `runninghub/video_wan2.1_fusionx.json`: 云端工作流（推荐，无需本地环境）
  - `selfhost/video_wan2.1_fusionx.json`: 本地工作流（需要本地 ComfyUI 支持）
- `prompt_prefix`: 视频提示词前缀（用于控制视频生成风格）

### TTS 配置

- `default_workflow`: 默认 TTS 工作流

---

## 模板配置

- `default_template`: 默认帧模板路径（例如 `1080x1920/image_default.html`）

---

## 更多信息

配置文件会自动在首次运行时创建。
