# OmniVoice_bf16 依赖与下载说明

## 1. 对应工作流路径

- 工作流文件：`workflows/selfhost/OmniVoice_bf16.json`
- 用途：本地 ComfyUI 中的单说话人语音克隆工作流，使用 `OmniVoiceWhisperLoader` 为 `OmniVoiceVoiceCloneTTS` 提供 `WHISPER_ASR`，由 OmniVoice 插件内部完成参考音频自动转写。

## 2. 节点与依赖清单

- `LoadAudio`
- `OmniVoiceWhisperLoader`
- `OmniVoiceVoiceCloneTTS`
- `SaveAudio`

## 3. 依赖分类

### 3.1 模型文件

- 当前默认工作流所需模型已存在：
  - `OmniVoice-bf16`
  - `whisper-large-v3`
- 可选模型尚未下载：
  - `OmniVoice（完整精度）`
  - `whisper-large-v3-turbo`

### 3.2 自定义节点

- `ComfyUI-OmniVoice-TTS`

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

根据仓库规则，模型下载默认优先使用 `ModelScope`。仅当 `ModelScope` 缺少所需文件，或 `ModelScope` 当前不可用时，才回退到其他来源。

## 6. ModelScope 检索与主地址

以下地址已于 `2026-05-04` 实测：

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

当 `ModelScope` 文件接口不可用时，使用以下回退来源。本次已于 `2026-05-04` 验证页面可访问：

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

## 8. 安装命令

### 8.1 下载前检查磁盘空间

当前 `E:` 盘在 `2026-05-04` 检查到剩余空间约 `19.89 GiB`。

```powershell
Get-PSDrive -Name E | Select-Object Name, Used, Free, Root
```

### 8.2 安装自定义节点

```powershell
git clone https://github.com/saganaki22/ComfyUI-OmniVoice-TTS.git E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice-TTS
```

当前机器已验证 `E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice-TTS` 存在，且包含 `requirements.txt`。

### 8.3 安装 Python 依赖

```powershell
E:\ComfyUIData\.venv\Scripts\python.exe -m pip install -U modelscope
E:\ComfyUIData\.venv\Scripts\python.exe -m pip install -r E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice-TTS\requirements.txt
```

### 8.4 下载模型

当前默认工作流使用 `OmniVoice-bf16` 和 `whisper-large-v3`。这两个资源本次已先检查 `ModelScope`，但文件接口返回 `404`，因此按仓库规则记录为回退来源：

```powershell
huggingface-cli download drbaph/OmniVoice-bf16 --local-dir E:\ComfyUIData\models\omnivoice\OmniVoice-bf16
huggingface-cli download openai/whisper-large-v3 --local-dir E:\ComfyUIData\models\audio_encoders\whisper-large-v3
```

可选模型只有在切换工作流默认模型或显式选择时才需要补充：

```powershell
modelscope download --model k2-fsa/OmniVoice --local_dir E:\ComfyUIData\models\omnivoice\OmniVoice
huggingface-cli download openai/whisper-large-v3-turbo --local-dir E:\ComfyUIData\models\audio_encoders\whisper-large-v3-turbo
```

## 9. 当前机器已验证的文件状态

截至 `2026-05-04`，当前默认工作流所需模型已存在并验证大小合理：

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
  Where-Object Name -match 'OmniVoice'
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

### 11.1 模型能通过 ModelScope 下载吗？

要分资源看：

- `k2-fsa/OmniVoice` 本次验证可通过 `ModelScope` 文件接口访问。
- `drbaph/OmniVoice-bf16` 和 `openai/whisper-*` 本次页面可访问，但文件接口 `404`，因此应记录为“优先检索过 ModelScope，但本次需回退”。

### 11.2 为什么 bf16 工作流参考 `OmniVoice_all.json`？

`OmniVoice_all.json` 使用的是 OmniVoice 插件原生路径：`OmniVoiceWhisperLoader` 输出 `WHISPER_ASR`，直接连接到 TTS 节点的 `whisper_model` 输入。`OmniVoice_bf16.json` 现在采用同一模式，减少额外插件和额外依赖栈。

### 11.3 参考音频的文字从哪里来？

`OmniVoiceVoiceCloneTTS` 的 `ref_text` widget 默认留空。连接 `whisper_model` 后，插件会在节点内部使用 Whisper 为参考音频自动转写；如果后续需要更稳定的音色复刻，也可以在节点自身的 `ref_text` widget 中手动填写参考音频文本。

### 11.4 为什么文档里同时写 `OmniVoice` 和 `OmniVoice-bf16`？

`OmniVoice_bf16.json` 默认用的是 `OmniVoice-bf16`，但插件同时支持完整精度 `OmniVoice`。只有后续切换 widget 默认值或运行时选择时，才需要补充完整精度模型。
