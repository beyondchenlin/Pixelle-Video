# OmniVoice_all 依赖与下载说明

## 1. 对应工作流路径

- 工作流文件：`workflows/selfhost/OmniVoice_all.json`
- 用途：本地 ComfyUI 中的 OmniVoice 功能集合工作流，覆盖 `Whisper Loader`、`Voice Design`、`Voice Clone`、`Longform TTS`、`Multi-Speaker TTS`。

## 2. 节点与依赖清单

- `OmniVoiceWhisperLoader`
- `OmniVoiceVoiceDesignTTS`
- `OmniVoiceVoiceCloneTTS`
- `OmniVoiceLongformTTS`
- `OmniVoiceMultiSpeakerTTS`
- `LoadAudio`
- `PreviewAudio`
- `SaveAudio`
- `MarkdownNote`
- `Fast Groups Bypasser (rgthree)`

## 3. 依赖分类

### 3.1 模型文件

- 当前默认工作流所需模型：
  - `OmniVoice-bf16`
  - `whisper-large-v3`
- 可选模型：
  - `OmniVoice（完整精度）`
  - `whisper-large-v3-turbo`

### 3.2 自定义节点

- `ComfyUI-OmniVoice-TTS`
- `rgthree-comfy`

### 3.3 Python 包

- `modelscope`
- `transformers`
- `accelerate`
- `safetensors`
- `sentencepiece`
- `soundfile`
- `librosa`
- `einops`

## 4. 目标目录

- OmniVoice 模型目录：`E:\ComfyUIData\models\omnivoice\`
- Whisper 模型目录：`E:\ComfyUIData\models\audio_encoders\`
- 自定义节点目录：`E:\ComfyUIData\custom_nodes\`

## 5. 下载优先级

模型默认优先 `ModelScope`。仅在 `ModelScope` 缺文件或接口不可用时回退到其他源。

## 6. ModelScope 检索与主地址

以下地址已于 `2026-05-04` 验证：

- `k2-fsa/OmniVoice`
  - 页面：`https://www.modelscope.cn/models/k2-fsa/OmniVoice`
  - 文件 API：`https://www.modelscope.cn/api/v1/models/k2-fsa/OmniVoice/repo/files?Revision=master&Recursive=true`
  - 验证结果：页面 `200`，文件 API `200`
- `drbaph/OmniVoice-bf16`
  - 页面：`https://www.modelscope.cn/models/drbaph/OmniVoice-bf16`
  - 文件 API：`https://www.modelscope.cn/api/v1/models/drbaph/OmniVoice-bf16/repo/files?Revision=master&Recursive=true`
  - 验证结果：页面 `200`，文件 API `404`
- `openai/whisper-large-v3`
  - 页面：`https://www.modelscope.cn/models/openai/whisper-large-v3`
  - 文件 API：`https://www.modelscope.cn/api/v1/models/openai/whisper-large-v3/repo/files?Revision=master&Recursive=true`
  - 验证结果：页面 `200`，文件 API `404`
- `openai/whisper-large-v3-turbo`
  - 页面：`https://www.modelscope.cn/models/openai/whisper-large-v3-turbo`
  - 文件 API：`https://www.modelscope.cn/api/v1/models/openai/whisper-large-v3-turbo/repo/files?Revision=master&Recursive=true`
  - 验证结果：页面 `200`，文件 API `404`

## 7. 备用地址

- `OmniVoice`
  - `https://huggingface.co/k2-fsa/OmniVoice`
- `OmniVoice-bf16`
  - `https://huggingface.co/drbaph/OmniVoice-bf16`
- `whisper-large-v3`
  - `https://huggingface.co/openai/whisper-large-v3`
- `whisper-large-v3-turbo`
  - `https://huggingface.co/openai/whisper-large-v3-turbo`
- `ComfyUI-OmniVoice-TTS`
  - `https://github.com/saganaki22/ComfyUI-OmniVoice-TTS`
- `rgthree-comfy`
  - `https://github.com/rgthree/rgthree-comfy`

## 8. 安装命令

### 8.1 下载前检查磁盘空间

```powershell
Get-PSDrive -Name E | Select-Object Name, Used, Free, Root
```

当前 `E:` 盘在 `2026-05-04` 检查到剩余空间约 `22.82 GB`。

### 8.2 安装自定义节点

```powershell
git clone https://github.com/saganaki22/ComfyUI-OmniVoice-TTS.git E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice-TTS
git clone https://github.com/rgthree/rgthree-comfy.git E:\ComfyUIData\custom_nodes\rgthree-comfy
```

### 8.3 安装 Python 依赖

```powershell
E:\ComfyUIData\.venv\Scripts\python.exe -m pip install -U modelscope
E:\ComfyUIData\.venv\Scripts\python.exe -m pip install -r E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice-TTS\requirements.txt
```

如果同一套 ComfyUI 运行时还要同时跑 `workflows/selfhost/OmniVoice_bf16.json`，则必须继续执行：

```powershell
.\scripts\comfyui\sync_omnivoice_qwen_asr_compat.ps1
```

原因是 `OmniVoice_bf16.json` 额外依赖 `Qwen3-ASR`，而官方 `qwen-asr 0.0.6` 与 `omnivoice 0.1.5` 对 `transformers` 的版本要求存在冲突。该脚本会把共享的 ComfyUI Python 环境锁定到已验证兼容的 HF 版本栈，避免一个工作流能跑、另一个工作流因 `thinker_config` 报错而失效。

### 8.4 下载模型

当前默认工作流使用 `OmniVoice-bf16` 和 `whisper-large-v3`。这两个资源本次已先检查 `ModelScope`，但文件接口未通过，因此按仓库规则记录为回退来源：

```powershell
huggingface-cli download drbaph/OmniVoice-bf16 --local-dir E:\ComfyUIData\models\omnivoice\OmniVoice-bf16
huggingface-cli download openai/whisper-large-v3 --local-dir E:\ComfyUIData\models\audio_encoders\whisper-large-v3
```

可选模型尚未下载。只有当你把工作流模型选择切换到完整精度 `OmniVoice` 或 `whisper-large-v3-turbo` 时，才需要补充下载：

```powershell
modelscope download --model k2-fsa/OmniVoice --local_dir E:\ComfyUIData\models\omnivoice\OmniVoice
huggingface-cli download openai/whisper-large-v3-turbo --local-dir E:\ComfyUIData\models\audio_encoders\whisper-large-v3-turbo
```

## 9. 当前机器已验证的文件状态

截至 `2026-05-04`，当前默认工作流所需模型已存在并验证：

- `E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\model.safetensors`：`1225189520`
- `E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\audio_tokenizer\model.safetensors`：`805665628`
- `E:\ComfyUIData\models\audio_encoders\whisper-large-v3\model.safetensors`：`3087130976`

可选模型尚未下载：

- `E:\ComfyUIData\models\omnivoice\OmniVoice`：不存在
- `E:\ComfyUIData\models\audio_encoders\whisper-large-v3-turbo`：不存在

## 10. 验证命令

### 10.1 验证文件存在与大小

```powershell
Get-Item `
  E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\model.safetensors, `
  E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\audio_tokenizer\model.safetensors, `
  E:\ComfyUIData\models\audio_encoders\whisper-large-v3\model.safetensors |
  Select-Object FullName, Length
```

### 10.2 验证节点是否已加载

```powershell
Invoke-RestMethod http://127.0.0.1:8000/object_info |
  Select-Object -ExpandProperty PSObject |
  Select-Object -ExpandProperty Properties |
  Where-Object Name -match 'OmniVoice|rgthree|MarkdownNote'
```

### 10.3 验证 workflow 结构

```powershell
python -m pytest tests/test_selfhost_workflows.py -k omnivoice -q
```

### 10.4 验证后端启动

```powershell
python -m pytest tests/test_comfyui_backend_scripts.py -q
.\scripts\comfyui\check_backend.ps1 -Json
```

## 11. 常见问题

### 11.1 `OmniVoice_all.json` 为什么比 `OmniVoice_bf16.json` 多依赖？

因为它包含完整示例集合，不只是单一路径，还包括长文本、多说话人和说明面板节点。

### 11.2 `Fast Groups Bypasser (rgthree)` 会阻断后端吗？

不会。它主要是前端增强节点。后端日志里 `rgthree-comfy` 已成功加载；此前真正阻断启动的是 Windows `GBK` 日志编码和插件 emoji 输出冲突，不是该节点本身缺失。

### 11.3 `MarkdownNote` 不在 `/object_info` 里是不是有问题？

不是阻断问题。它是前端说明节点，工作流结构校验时可以按“允许缺失的前端节点”处理，只要其他执行型节点都存在即可。
