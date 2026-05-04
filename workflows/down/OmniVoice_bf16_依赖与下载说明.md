# OmniVoice_bf16 依赖与下载说明

## 1. 对应工作流路径

- 工作流文件：`workflows/selfhost/OmniVoice_bf16.json`
- 用途：本地 ComfyUI 中的单说话人语音克隆工作流，使用 `Qwen3-ASR` 自动转写参考音频，再交给 `OmniVoiceVoiceCloneTTS` 生成语音。

## 2. 节点与依赖清单

- `LoadAudio`
- `Qwen3ASRLoader`
- `Qwen3ASRTranscribe`
- `CR Prompt Text`
- `OmniVoiceVoiceCloneTTS`
- `PreviewAny`
- `SaveAudio`

## 3. 依赖分类

### 3.1 模型文件

- 当前默认工作流所需模型：
  - `OmniVoice-bf16`
  - `Qwen3-ASR-1.7B`
  - `whisper-large-v3`
- 可选模型：
  - `Qwen3-ASR-0.6B`
  - `whisper-large-v3-turbo`
  - `OmniVoice（完整精度）`

### 3.2 自定义节点

- `ComfyUI-OmniVoice-TTS`
- `ComfyUI-Qwen3-ASR`
- `ComfyUI_Comfyroll_CustomNodes`

### 3.3 Python 包

- `modelscope`
- `transformers`
- `accelerate`
- `safetensors`
- `sentencepiece`
- `soundfile`
- `librosa`
- `einops`
- `qwen-asr`

## 4. 目标目录

基于当前机器的实际 ComfyUI 数据目录：

- OmniVoice 模型目录：`E:\ComfyUIData\models\omnivoice\`
- Whisper 模型目录：`E:\ComfyUIData\models\audio_encoders\`
- Qwen3-ASR 模型目录：`E:\ComfyUIData\models\Qwen3-ASR\`
- 自定义节点目录：`E:\ComfyUIData\custom_nodes\`

## 5. 下载优先级

根据仓库约束，模型下载默认优先 `ModelScope`。

仅当 `ModelScope` 缺少所需文件或接口当前不可用时，才回退到其他来源。

## 6. ModelScope 检索与主地址

以下地址已于 `2026-05-04` 实测可访问：

- `k2-fsa/OmniVoice`
  - 页面：`https://www.modelscope.cn/models/k2-fsa/OmniVoice`
  - 文件 API：`https://www.modelscope.cn/api/v1/models/k2-fsa/OmniVoice/repo/files?Revision=master&Recursive=true`
  - 验证结果：`HEAD 200`，文件 API `200`
- `Qwen/Qwen3-ASR-1.7B`
  - 页面：`https://www.modelscope.cn/models/Qwen/Qwen3-ASR-1.7B`
  - 文件 API：`https://www.modelscope.cn/api/v1/models/Qwen/Qwen3-ASR-1.7B/repo/files?Revision=master&Recursive=true`
  - 验证结果：`HEAD 200`，文件 API `200`
- `Qwen/Qwen3-ASR-0.6B`
  - 页面：`https://www.modelscope.cn/models/Qwen/Qwen3-ASR-0.6B`
  - 文件 API：`https://www.modelscope.cn/api/v1/models/Qwen/Qwen3-ASR-0.6B/repo/files?Revision=master&Recursive=true`
  - 验证结果：`HEAD 200`，文件 API `200`

以下页面可访问，但仓库接口本次未通过，需记录为回退情形：

- `drbaph/OmniVoice-bf16`
  - 页面：`https://www.modelscope.cn/models/drbaph/OmniVoice-bf16`
  - 文件 API：`https://www.modelscope.cn/api/v1/models/drbaph/OmniVoice-bf16/repo/files?Revision=master&Recursive=true`
  - 验证结果：页面 `HEAD 200`，文件 API `404`
- `openai/whisper-large-v3`
  - 页面：`https://www.modelscope.cn/models/openai/whisper-large-v3`
  - 文件 API：`https://www.modelscope.cn/api/v1/models/openai/whisper-large-v3/repo/files?Revision=master&Recursive=true`
  - 验证结果：页面 `HEAD 200`，文件 API `404`
- `openai/whisper-large-v3-turbo`
  - 页面：`https://www.modelscope.cn/models/openai/whisper-large-v3-turbo`
  - 文件 API：`https://www.modelscope.cn/api/v1/models/openai/whisper-large-v3-turbo/repo/files?Revision=master&Recursive=true`
  - 验证结果：页面 `HEAD 200`，文件 API `404`

## 7. 备用地址

当 `ModelScope` 文件接口不可用时，使用以下回退源：

- `OmniVoice-bf16`
  - `https://huggingface.co/drbaph/OmniVoice-bf16`
- `whisper-large-v3`
  - `https://huggingface.co/openai/whisper-large-v3`
- `whisper-large-v3-turbo`
  - `https://huggingface.co/openai/whisper-large-v3-turbo`
- `ComfyUI-OmniVoice-TTS`
  - `https://github.com/saganaki22/ComfyUI-OmniVoice-TTS`
- `ComfyUI-Qwen3-ASR`
  - `https://github.com/DarioFT/ComfyUI-Qwen3-ASR`
- `ComfyUI_Comfyroll_CustomNodes`
  - `https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes`

## 8. 安装命令

### 8.1 下载前检查磁盘空间

当前 `E:` 盘在 `2026-05-04` 检查到剩余空间约 `22.82 GB`，足够覆盖本工作流主要模型。

```powershell
Get-PSDrive -Name E | Select-Object Name, Used, Free, Root
```

### 8.2 安装自定义节点

```powershell
git clone https://github.com/saganaki22/ComfyUI-OmniVoice-TTS.git E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice-TTS
git clone https://github.com/DarioFT/ComfyUI-Qwen3-ASR.git E:\ComfyUIData\custom_nodes\ComfyUI-Qwen3-ASR
git clone https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes.git E:\ComfyUIData\custom_nodes\ComfyUI_Comfyroll_CustomNodes
```

### 8.3 安装 Python 依赖

```powershell
E:\ComfyUIData\.venv\Scripts\python.exe -m pip install -U modelscope
E:\ComfyUIData\.venv\Scripts\python.exe -m pip install -r E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice-TTS\requirements.txt
E:\ComfyUIData\.venv\Scripts\python.exe -m pip install -r E:\ComfyUIData\custom_nodes\ComfyUI-Qwen3-ASR\requirements.txt
```

### 8.4 下载模型

当前默认工作流所需模型里，`Qwen3-ASR-1.7B` 已验证可直接通过 `ModelScope` 下载：

```powershell
modelscope download --model Qwen/Qwen3-ASR-1.7B --local_dir E:\ComfyUIData\models\Qwen3-ASR\Qwen3-ASR-1.7B
```

以下默认所需资源已先检查 `ModelScope`，但文件接口本次返回 `404`，因此按仓库规则使用回退来源：

```powershell
huggingface-cli download drbaph/OmniVoice-bf16 --local-dir E:\ComfyUIData\models\omnivoice\OmniVoice-bf16
huggingface-cli download openai/whisper-large-v3 --local-dir E:\ComfyUIData\models\audio_encoders\whisper-large-v3
```

可选模型尚未下载，只有在你切换工作流默认值或需要额外轻量/完整精度模型时再补充：

```powershell
modelscope download --model k2-fsa/OmniVoice --local_dir E:\ComfyUIData\models\omnivoice\OmniVoice
modelscope download --model Qwen/Qwen3-ASR-0.6B --local_dir E:\ComfyUIData\models\Qwen3-ASR\Qwen3-ASR-0.6B
huggingface-cli download openai/whisper-large-v3-turbo --local-dir E:\ComfyUIData\models\audio_encoders\whisper-large-v3-turbo
```

## 9. 当前机器已验证的文件状态

截至 `2026-05-04`，当前默认工作流所需模型已存在并验证：

- `E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\model.safetensors`：`1225189520`
- `E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\audio_tokenizer\model.safetensors`：`805665628`
- `E:\ComfyUIData\models\Qwen3-ASR\Qwen3-ASR-1.7B\model-00001-of-00002.safetensors`：`4220320824`
- `E:\ComfyUIData\models\Qwen3-ASR\Qwen3-ASR-1.7B\model-00002-of-00002.safetensors`：`478200688`
- `E:\ComfyUIData\models\audio_encoders\whisper-large-v3\model.safetensors`：`3087130976`

可选模型尚未下载：

- `E:\ComfyUIData\models\Qwen3-ASR\Qwen3-ASR-0.6B`：不存在
- `E:\ComfyUIData\models\audio_encoders\whisper-large-v3-turbo`：不存在
- `E:\ComfyUIData\models\omnivoice\OmniVoice`：不存在

## 10. 验证命令

### 10.1 验证文件存在与大小

```powershell
Get-Item `
  E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\model.safetensors, `
  E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\audio_tokenizer\model.safetensors, `
  E:\ComfyUIData\models\Qwen3-ASR\Qwen3-ASR-1.7B\model-00001-of-00002.safetensors, `
  E:\ComfyUIData\models\Qwen3-ASR\Qwen3-ASR-1.7B\model-00002-of-00002.safetensors, `
  E:\ComfyUIData\models\audio_encoders\whisper-large-v3\model.safetensors |
  Select-Object FullName, Length
```

### 10.2 验证节点是否已加载

```powershell
Invoke-RestMethod http://127.0.0.1:8000/object_info |
  Select-Object -ExpandProperty PSObject |
  Select-Object -ExpandProperty Properties |
  Where-Object Name -match 'OmniVoice|Qwen3ASR'
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

### 11.1 模型能通过魔搭下载吗？

可以，但要分资源看：

- `k2-fsa/OmniVoice`、`Qwen/Qwen3-ASR-1.7B`、`Qwen/Qwen3-ASR-0.6B` 本次已验证可通过 `ModelScope` 文件接口下载。
- `drbaph/OmniVoice-bf16` 和 `openai/whisper-*` 本次页面可访问，但文件接口 `404`，因此应记录为“优先检索过 ModelScope，但本次需回退”。

### 11.2 为什么 workflow 里还需要 `Qwen3-ASR`？

因为这个工作流默认允许参考音频文本为空，由 `Qwen3ASRTranscribe` 先生成 `ref_text`，再传给 `OmniVoiceVoiceCloneTTS`。

### 11.3 为什么文档里同时写 `OmniVoice` 和 `OmniVoice-bf16`？

`OmniVoice_bf16.json` 默认用的是 `OmniVoice-bf16`，但插件同时支持完整精度 `OmniVoice`。如果后续切换 widget 默认值，目录结构不需要重做。
