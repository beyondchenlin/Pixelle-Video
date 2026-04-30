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
- `model_cleanup_mode`：本地工作流批次结束和显式恢复路径使用的模型显存释放范围。`disabled` 在批次结束后保留模型常驻，`comfyui` 调用 ComfyUI `/free`，`comfyui_and_extensions` 会同时调用 `/free` 和 Pixelle 管理的插件清理端点，例如 `/pixelle/indextts2/free`。
- `comfyui_api_key`: ComfyUI API 密钥（可选，用于 [Comfy Platform](https://platform.comfy.org/profile/api-keys)）

Pixelle 不会在本地图片批次的每张图生成前调用 `/free`。批次内会保持 GGUF 和相关模型热加载，避免每帧重复卸载和重载。整个本地工作流批次结束后，`model_cleanup_mode` 决定是否释放 ComfyUI 模型显存以及 Pixelle 管理的插件缓存。OOM 恢复仍会在重试前执行一次高强度显式清理。

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
