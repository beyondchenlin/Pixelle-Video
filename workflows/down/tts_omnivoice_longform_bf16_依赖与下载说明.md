# tts_omnivoice_longform_bf16 依赖与下载说明

## 1. 对应工作流路径

- 工作流文件：`workflows/selfhost/tts_omnivoice_longform_bf16.json`
- 用途：Pixelle API 可传参执行的 OmniVoice bf16 长文本 TTS 工作流。
- 图格式：Pixelle API 图格式，不是 ComfyUI UI 画布图格式。

## 2. 节点与依赖清单

- `PrimitiveStringMultiline`：输入待合成文本，暴露 `$text.value!`。
- `PrimitiveStringMultiline`：输入参考音频转写文本，暴露 `$reference_audio_text.value`。
- `VHS_LoadAudioUpload`：上传参考音频，暴露 `$ref_audio.~audio!`。
- `OmniVoiceLongformTTS`：长文本 TTS 主节点，使用 `OmniVoice-bf16`。
- `SaveAudio`：保存 FLAC 音频。

## 3. 依赖分类

- 模型文件：`OmniVoice-bf16`、`whisper-large-v3`。
- 自定义节点：`ComfyUI-OmniVoice-TTS`、`ComfyUI-Pixelle-TTS`、`ComfyUI-VideoHelperSuite`。
- Python 包：`modelscope`、`transformers`、`accelerate`、`safetensors`、`soundfile`、`librosa`、`soxr`，以及 OmniVoice 节点仓库 `requirements.txt` 中声明的其他包。
- 系统工具：Git、PowerShell、可用的 ComfyUI Python 虚拟环境；如需要处理音频格式，建议安装 `ffmpeg` 并加入 `PATH`。

## 4. 目标目录

- OmniVoice 模型目录：`E:\ComfyUIData\models\omnivoice\OmniVoice-bf16`
- Whisper 模型目录：`E:\ComfyUIData\models\audio_encoders\whisper-large-v3`
- 自定义节点目录：`E:\ComfyUIData\custom_nodes`
- Pixelle 自定义节点源码目录：`tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS`

## 5. 下载优先级

根据仓库规则，模型文件默认优先使用 `ModelScope`。只有当 `ModelScope` 缺少所需文件，或 `ModelScope` 当前不可用时，才允许回退到 Hugging Face 等备用来源。

开始大体积下载前，先检查磁盘空间并确认目标目录：

```powershell
Get-PSDrive E
New-Item -ItemType Directory -Force E:\ComfyUIData\models\omnivoice\OmniVoice-bf16
New-Item -ItemType Directory -Force E:\ComfyUIData\models\audio_encoders\whisper-large-v3
New-Item -ItemType Directory -Force E:\ComfyUIData\custom_nodes
```

## 6. ModelScope 检索或主地址

以下页面地址已在 `2026-05-04` 使用 HEAD 检查，返回 HTTP 200：

- `drbaph/OmniVoice-bf16`
  - 主地址：`https://www.modelscope.cn/models/drbaph/OmniVoice-bf16`
  - 目标目录：`E:\ComfyUIData\models\omnivoice\OmniVoice-bf16`
- `openai/whisper-large-v3`
  - 主地址：`https://www.modelscope.cn/models/openai/whisper-large-v3`
  - 目标目录：`E:\ComfyUIData\models\audio_encoders\whisper-large-v3`

ModelScope 优先下载命令：

```powershell
E:\ComfyUIData\.venv\Scripts\python.exe -m pip install -U modelscope
modelscope download --model drbaph/OmniVoice-bf16 --local_dir E:\ComfyUIData\models\omnivoice\OmniVoice-bf16
modelscope download --model openai/whisper-large-v3 --local_dir E:\ComfyUIData\models\audio_encoders\whisper-large-v3
```

## 7. 备用地址

仅当 ModelScope 缺少文件或当前不可用时使用以下 Hugging Face 回退地址：

- `OmniVoice-bf16`：`https://huggingface.co/drbaph/OmniVoice-bf16`
- `whisper-large-v3`：`https://huggingface.co/openai/whisper-large-v3`

回退下载命令：

```powershell
huggingface-cli download drbaph/OmniVoice-bf16 --local-dir E:\ComfyUIData\models\omnivoice\OmniVoice-bf16
huggingface-cli download openai/whisper-large-v3 --local-dir E:\ComfyUIData\models\audio_encoders\whisper-large-v3
```

## 8. 安装命令

```powershell
git clone https://github.com/saganaki22/ComfyUI-OmniVoice-TTS E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice-TTS
git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite E:\ComfyUIData\custom_nodes\ComfyUI-VideoHelperSuite
E:\ComfyUIData\.venv\Scripts\python.exe -m pip install -r E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice-TTS\requirements.txt
python tools\sync_pixelle_tts_custom_node.py --target E:\ComfyUIData\custom_nodes\ComfyUI-Pixelle-TTS --python E:\ComfyUIData\.venv\Scripts\python.exe
```

如果目标目录已存在，先检查是否为预期仓库，不要覆盖已有人工修改。

## 9. 验证命令

仓库侧验证：

```powershell
python -m pytest tests/test_selfhost_workflows.py -k tts_omnivoice -q
```

模型文件存在性和大小检查：

```powershell
Get-Item `
  E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\model.safetensors, `
  E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\audio_tokenizer\model.safetensors, `
  E:\ComfyUIData\models\audio_encoders\whisper-large-v3\model.safetensors |
  Select-Object FullName, Length
```

文件大小应处于合理范围；如果返回缺失或大小明显异常，应重新下载对应模型。

## 10. 常见问题

- 如果 `WorkflowParser` 解析不到参数，检查 `_meta.title` 是否包含 `$text.value!`、`$ref_audio.~audio!` 和 `$reference_audio_text.value`。
- 如果参考音频上传失败，检查 `ComfyUI-VideoHelperSuite` 是否已安装，并确认 `VHS_LoadAudioUpload` 可用。
- 如果参考文本为空，OmniVoice 节点可能依赖 Whisper 自动转写；为了稳定复刻音色，建议传入 `reference_audio_text`。
- 该工作流用于长文本旁白，`duration` 固定为 `0`，由 `words_per_chunk` 控制长文本分块。
- 如果 ComfyUI 启动时报 Python 包缺失，优先在 `E:\ComfyUIData\.venv` 中安装依赖，避免装到系统 Python。
