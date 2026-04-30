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
  pre_generation_cleanup_mode: "force"
  pre_generation_cleanup_timeout_seconds: 20
  model_cleanup_mode: "comfyui_and_extensions"
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
- `pre_generation_cleanup_mode`: 本地生成批次前的清理策略
  - `"force"`：中断并清空繁忙队列，等待 ComfyUI 恢复空闲后再开始 Pixelle 生成
  - `"conservative"`：不强制干预现有队列
  - 这里只做队列清理，不会在每张图片生成前卸载模型
- `pre_generation_cleanup_timeout_seconds`: 强制清理时等待 ComfyUI 队列恢复空闲的秒数；超时后会快速失败并提示队列可能卡住
- `model_cleanup_mode`：Pixelle 本地工作流阶段边界和显式恢复路径使用的模型显存释放范围。`disabled` 在阶段结束后保留模型常驻，`comfyui` 调用 ComfyUI `/free`，`comfyui_and_extensions` 会在需要插件私有缓存释放的阶段额外调用 Pixelle 管理的插件清理端点，例如 IndexTTS2 TTS。
- `comfyui_api_key`: ComfyUI API 密钥（可选，用于 [Comfy Platform](https://platform.comfy.org/profile/api-keys)）

Pixelle 假设配置的自托管 ComfyUI 实例由 Pixelle 独占。Pixelle 不会在本地图片批次的每张图生成前调用 `/free`；批次内会保持 GGUF 和相关模型热加载，避免每帧重复卸载和重载。图片阶段结束后，Pixelle 会释放 ComfyUI 标准模型显存，再进入下一阶段。IndexTTS2 TTS 阶段结束后，Pixelle 会释放 ComfyUI 标准模型，并额外调用补丁端点 `/pixelle/indextts2/free` 释放插件私有缓存。如果本地 IndexTTS2 工作流在 `comfyui_and_extensions` 模式下运行，Pixelle 会在执行工作流前预检无副作用的 `/pixelle/indextts2/health` 端点，让缺少插件补丁的问题提前失败，同时不会卸载热加载模型。OOM 恢复仍会在重试前执行一次高强度显式清理。

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
