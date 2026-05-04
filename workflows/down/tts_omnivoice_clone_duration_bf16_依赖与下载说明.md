# tts_omnivoice_clone_duration_bf16 依赖与下载说明

## 1. 对应工作流路径

- 工作流文件：`workflows/selfhost/tts_omnivoice_clone_duration_bf16.json`
- 用途：Pixelle 可传参执行的 OmniVoice bf16 短文本定长克隆工作流。
- 图格式：Pixelle API 图格式，不是 ComfyUI UI 画布图格式。

## 2. 节点与依赖清单

- `PrimitiveStringMultiline`：输入待合成文本，暴露 `$text.value!`。
- `PrimitiveStringMultiline`：输入参考音频转写文本，暴露 `$reference_audio_text.value`。
- `VHS_LoadAudioUpload`：上传参考音频，暴露 `$ref_audio.~audio!`。
- `PixelleDurationInput`：输入目标时长秒数，暴露 `$duration.value`。
- `OmniVoiceVoiceCloneTTS`：短文本语音克隆 TTS 主节点。
- `SaveAudio`：保存 FLAC 音频。

## 3. 依赖分类

- 模型文件：`OmniVoice-bf16`、`whisper-large-v3`。
- 自定义节点：`ComfyUI-OmniVoice-TTS`、`ComfyUI-Pixelle-TTS`、`ComfyUI-VideoHelperSuite`。
- Python 包：`modelscope`、`transformers`、`accelerate`、`safetensors`、`soundfile`、`librosa`、`soxr`。

## 4. 目标目录

- OmniVoice 模型目录：`E:\ComfyUIData\models\omnivoice\OmniVoice-bf16`
- Whisper 模型目录：`E:\ComfyUIData\models\audio_encoders\whisper-large-v3`
- 自定义节点目录：`E:\ComfyUIData\custom_nodes`
- Pixelle 自定义节点源码目录：`tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS`

## 5. 下载优先级

根据仓库规则，模型文件默认优先使用 `ModelScope`。仅当 `ModelScope` 缺少所需文件，或 `ModelScope` 当前不可用时，才回退到 Hugging Face 等备用来源。

## 6. ModelScope 检索或主地址

以下地址已于 `2026-05-04` 验证：

- `drbaph/OmniVoice-bf16`
  - 页面：`https://www.modelscope.cn/models/drbaph/OmniVoice-bf16`
  - 页面验证结果：`200`
  - 文件 API：`https://www.modelscope.cn/api/v1/models/drbaph/OmniVoice-bf16/repo/files?Revision=master&Recursive=true`
  - 文件 API 验证结果：`404`
- `openai/whisper-large-v3`
  - 页面：`https://www.modelscope.cn/models/openai/whisper-large-v3`
  - 页面验证结果：`200`
  - 文件 API：`https://www.modelscope.cn/api/v1/models/openai/whisper-large-v3/repo/files?Revision=master&Recursive=true`
  - 文件 API 验证结果：`404`

结论：已先检查 `ModelScope`。本次两个必需模型页面可访问，但文件 API 不可用，因此下载命令记录 Hugging Face 作为回退来源。

## 7. 备用地址

- `OmniVoice-bf16`：`https://huggingface.co/drbaph/OmniVoice-bf16`
- `whisper-large-v3`：`https://huggingface.co/openai/whisper-large-v3`
- `ComfyUI-OmniVoice-TTS`：`https://github.com/saganaki22/ComfyUI-OmniVoice-TTS`
- `ComfyUI-Pixelle-TTS`：当前仓库 `tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS`

## 8. 安装命令

```powershell
E:\ComfyUIData\.venv\Scripts\python.exe -m pip install -U modelscope
E:\ComfyUIData\.venv\Scripts\python.exe -m pip install -r E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice-TTS\requirements.txt
python tools\sync_pixelle_tts_custom_node.py --target E:\ComfyUIData\custom_nodes\ComfyUI-Pixelle-TTS --python E:\ComfyUIData\.venv\Scripts\python.exe
```

当需要重新下载必需模型且 `ModelScope` 文件接口仍不可用时，使用回退命令：

```powershell
huggingface-cli download drbaph/OmniVoice-bf16 --local-dir E:\ComfyUIData\models\omnivoice\OmniVoice-bf16
huggingface-cli download openai/whisper-large-v3 --local-dir E:\ComfyUIData\models\audio_encoders\whisper-large-v3
```

## 9. 验证命令

```powershell
python -m pytest tests/test_selfhost_workflows.py -k tts_omnivoice -q
```

```powershell
Get-Item `
  E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\model.safetensors, `
  E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\audio_tokenizer\model.safetensors, `
  E:\ComfyUIData\models\audio_encoders\whisper-large-v3\model.safetensors |
  Select-Object FullName, Length
```

本机已验证存在且大小合理：

- `E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\model.safetensors`：`1225189520`
- `E:\ComfyUIData\models\omnivoice\OmniVoice-bf16\audio_tokenizer\model.safetensors`：`805665628`
- `E:\ComfyUIData\models\audio_encoders\whisper-large-v3\model.safetensors`：`3087130976`

## 10. 常见问题

- 如果 `WorkflowParser` 解析不到参数，检查 `_meta.title` 是否包含 `$text.value!`、`$ref_audio.~audio!`、`$reference_audio_text.value` 和 `$duration.value`。
- 如果参考音频上传失败，检查 `VHS_LoadAudioUpload` 是否安装。
- `PixelleDurationInput` 来自 `ComfyUI-Pixelle-TTS`，用于暴露 0.5-60 秒范围的 `$duration.value`；不要使用 `PixelleFloatInput`，它保留给 Edge TTS speed 参数。
- `duration` 只适合短文本定长，不建议用于长文本整体控时长。
