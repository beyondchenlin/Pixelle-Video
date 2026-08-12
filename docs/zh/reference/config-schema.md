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
  backend_management_mode: "required"
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
- `backend_management_mode`: ComfyUI 生命周期策略。`"required"` 是本地单机生成的推荐配置，只接受由 Pixelle 验证所有权的完整本地服务；工作流需要时按需启动，批次结束后停止。`"auto"` 可复用外部服务，因此无法保证释放内存；`"disabled"` 是兼容旧部署的默认值，只连接外部服务，永不启动或停止它。
- `comfyui_api_key`: ComfyUI API 密钥（可选，用于 [Comfy Platform](https://platform.comfy.org/profile/api-keys)）

Pixelle 在提交本地工作流前通过 `/system_stats` 验证服务健康，并只观察共享队列，不中断或清空其他客户端任务。对 Pixelle 验证所有权的服务，`stop_after_batch: true` 会在完整图片或音频批次结束且队列为空后停止整个服务；下一批本地工作流才重新启动。进程退出同时释放显存和系统内存，不依赖插件私有的释放接口。对外部启动或所有权无法验证的服务，Pixelle 不执行停止操作。服务运行期间，仍可通过配置地址在浏览器中查看队列、历史和生成内容。

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
