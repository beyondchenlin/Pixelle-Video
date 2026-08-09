# API 概览

Pixelle-Video 提供 Python SDK 和 HTTP REST API 两种调用方式。

---

## Python SDK

### PixelleVideoCore

主服务类，用于视频生成。

```python
from pixelle_video.service import PixelleVideoCore

pixelle = PixelleVideoCore()
await pixelle.initialize()
```

### generate_video()

生成视频的主要方法。

**参数**：

- `text` (str): 主题或完整文案
- `mode` (str): 生成模式，`"generate"` 或 `"fixed"`
- `storyboard_mode` (str): 分镜模式，`"smart"`、`"punctuation"` 或 `"sentence"`
- `storyboard_count_mode` (str): 分镜数量模式，`"auto"` 或 `"manual"`
- `storyboard_scene_count` (int, optional): 手动分镜数量，仅在 `smart + manual` 时有效，并受部署分镜配置限制
- `storyboard_max_scene_count` (int, optional): 确定性切分模式下的最大分镜，仅在 `punctuation` 或 `sentence` 时有效；默认 60，受部署配置限制，绝对上限 200
- `script_length_mode` (str): `generate` 模式下的完整文案长度模式
- `script_target_words` (int, optional): `generate` 模式下的自定义文案目标字数；仅在 `script_length_mode="custom"` 时必填，支持 50-10000
- `title` (str, optional): 视频标题
- `tts_workflow` (str): TTS 工作流
- `media_workflow` (str): 媒体生成工作流（图片或视频）
- `frame_template` (str): 视频模板
- `template_params` (dict, optional): 模板自定义参数
- `bgm_path` (str, optional): BGM 文件路径
- `bgm_volume` (float): BGM 音量 (0.0-1.0)

**返回**：`VideoResult` 对象

---

## HTTP REST API

启动 API 服务：

```bash
uv run uvicorn api.app:app --host 127.0.0.1 --port 6789
```

本地开发时，Web 界面默认通过 `http://localhost:6789/api` 调用 Pixelle API。Swagger 文档地址为 `http://localhost:6789/docs`，健康检查地址为 `http://localhost:6789/health`。

### 视频生成 - 同步

`POST /api/video/generate/sync`

同步生成视频，等待完成后返回结果。适合较短的视频。

**请求体**：

```json
{
  "text": "为什么要养成阅读习惯",
  "mode": "generate",
  "storyboard_mode": "smart",
  "storyboard_count_mode": "auto",
  "script_length_mode": "auto",
  "frame_template": "1080x1920/image_default.html",
  "template_params": {
    "accent_color": "#3498db",
    "background": "https://example.com/custom-bg.jpg"
  },
  "title": "阅读的力量"
}
```

**响应**：

```json
{
  "success": true,
  "message": "Success",
  "video_url": "http://localhost:6789/api/files/xxx/final.mp4",
  "duration": 45.5,
  "file_size": 12345678
}
```

### 视频生成 - 异步

`POST /api/video/generate/async`

异步生成视频，立即返回任务 ID。适合较长的视频。

**响应**：

```json
{
  "success": true,
  "message": "Task created successfully",
  "task_id": "abc123"
}
```

### 查询任务状态

`GET /api/tasks/{task_id}`

**响应**：

```json
{
  "task_id": "abc123",
  "status": "completed",
  "result": {
    "video_url": "http://localhost:6789/api/files/xxx/final.mp4",
    "duration": 45.5,
    "file_size": 12345678
  }
}
```

---

## 请求参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | 是 | 主题或完整文案 |
| `mode` | string | 否 | `"generate"`（AI 生成完整文案）或 `"fixed"`（使用输入文案） |
| `storyboard_mode` | string | 否 | `"smart"`（大模型理解完整文案规划分镜）、`"punctuation"` 或 `"sentence"` |
| `storyboard_count_mode` | string | 否 | `"auto"` 或 `"manual"`；手动数量只适用于 `storyboard_mode="smart"` |
| `storyboard_scene_count` | int | 否 | `smart/manual` 下的手动分镜数量，受部署分镜配置限制 |
| `storyboard_max_scene_count` | int | 否 | `punctuation` 或 `sentence` 下的最大分镜；默认 60，受部署配置限制，绝对上限 200 |
| `script_length_mode` | string | 否 | `generate` 模式下的文案长度：`"auto"`、`"short"`、`"medium"`、`"long"` 或 `"custom"` |
| `script_target_words` | int | 否 | 仅在 `script_length_mode="custom"` 时必填，支持范围 50-10000 |
| `title` | string | 否 | 视频标题，不填则自动生成 |
| `frame_template` | string | 否 | 模板路径，如 `1080x1920/image_default.html` |
| `template_params` | object | 否 | 模板自定义参数，如颜色、背景等 |
| `media_workflow` | string | 否 | 媒体工作流（图片或视频生成） |
| `tts_workflow` | string | 否 | TTS 工作流 |
| `ref_audio` | string | 否 | 声音克隆参考音频路径 |
| `prompt_prefix` | string | 否 | 图片风格前缀 |
| `bgm_path` | string | 否 | BGM 文件路径 |
| `bgm_volume` | float | 否 | BGM 音量 (0.0-1.0，默认 0.3) |

---

## 更多信息

API 文档也可通过 Swagger UI 访问：`http://localhost:6789/docs`
