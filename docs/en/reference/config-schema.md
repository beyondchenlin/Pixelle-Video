# Config Schema

Detailed explanation of the `config.yaml` configuration file.

---

## Configuration Structure

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
  comfyui_api_key: ""  # ComfyUI API key (optional)
  runninghub_api_key: ""
  runninghub_concurrent_limit: 1  # Concurrent limit (1-10)
  runninghub_instance_type: ""  # Instance type (optional, set to "plus" for 48GB VRAM)
  
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

## LLM Configuration

- `api_key`: API key
- `base_url`: API service address (supports any OpenAI-compatible interface)
- `model`: Model name

---

## ComfyUI Configuration

### Basic Configuration

- `comfyui_url`: Local ComfyUI address (default `http://127.0.0.1:8188`)
- `pre_generation_cleanup_mode`: Cleanup before a local generation batch
  - `"force"`: Interrupt and clear a busy queue, then wait for ComfyUI to become idle before Pixelle starts
  - `"conservative"`: Leave the existing queue untouched and avoid forced cleanup
  - This is queue cleanup only; it does not unload models before each generated image.
- `pre_generation_cleanup_timeout_seconds`: How long a forced cleanup waits for the ComfyUI queue to become idle before Pixelle fails fast with an actionable error
- `model_cleanup_mode`: Model memory cleanup scope used at Pixelle-owned local workflow stage boundaries and explicit recovery paths. `disabled` leaves models loaded after the stage, `comfyui` calls ComfyUI `/free`, and `comfyui_and_extensions` calls `/free` plus Pixelle-managed extension cleanup endpoints for stages that need them, such as IndexTTS2 TTS.
- `comfyui_api_key`: ComfyUI API key (optional, for [Comfy Platform](https://platform.comfy.org/profile/api-keys))

Pixelle assumes the configured self-hosted ComfyUI instance is dedicated to Pixelle. It does not call `/free` before each image in a local image batch; the batch keeps GGUF and related models hot so every frame does not pay the unload/reload cost. When the image stage finishes, Pixelle releases ComfyUI-managed models before moving to the next stage. When an IndexTTS2 TTS stage finishes, Pixelle releases ComfyUI-managed models and then the patched `/pixelle/indextts2/free` plugin cache. If a local IndexTTS2 workflow is used with `comfyui_and_extensions`, Pixelle preflights the side-effect-free `/pixelle/indextts2/health` endpoint before executing the workflow so a missing plugin patch fails early without unloading hot models. OOM recovery still triggers an explicit high-intensity cleanup before one retry.

Runtime task logs include structured `local_media_batch` start/end events with elapsed milliseconds and frame counts, plus `comfyui_memory_release` events. ComfyUI `/free` releases capture `/system_stats` VRAM snapshots before and after the release when the endpoint is available. IndexTTS2 release responses also include CUDA allocated/reserved before/after snapshots when the patched endpoint provides them.

### RunningHub Cloud Configuration

- `runninghub_api_key`: RunningHub API key (required for cloud workflows)
- `runninghub_concurrent_limit`: Concurrent execution limit (1-10, default 1 for regular members)
- `runninghub_instance_type`: Instance type (optional)
  - Empty or unset: Use 24GB VRAM machine
  - `"plus"`: Use 48GB VRAM machine (suitable for large video generation)

### Image Configuration

- `default_workflow`: Default image generation workflow
  - `selfhost/image_z_image_turbo.json`: Built-in default for the repo's illustration flow
  - Saved user configuration overrides the built-in default
- `prompt_prefix`: Prompt prefix

### Video Configuration

- `default_workflow`: Default video generation workflow
  - `runninghub/video_wan2.1_fusionx.json`: Cloud workflow (recommended, no local setup required)
  - `selfhost/video_wan2.1_fusionx.json`: Local workflow (requires local ComfyUI support)
- `prompt_prefix`: Video prompt prefix (controls video generation style)

### TTS Configuration

- `default_workflow`: Default TTS workflow

---

## Template Configuration

- `default_template`: Default frame template path (e.g., `1080x1920/image_default.html`)

---

## More Information

The configuration file is automatically created on first run.
