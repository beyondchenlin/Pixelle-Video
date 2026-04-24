# tts_longcat_clone 依赖与下载说明

## 对应工作流

- `workflows/selfhost/tts_longcat_clone.json`

## 节点与依赖

- ComfyUI 自定义节点：`Saganaki22/ComfyUI-LongCat-AudioDIT-TTS`
- 主要节点：`LongCatVoiceCloneTTS`
- 音频输入节点：`VHS_LoadAudioUpload`
- 音频输出节点：`SaveAudioMP3`
- Python 依赖：`numpy`、`soundfile`、`transformers>=4.45.2`、`einops>=0.7.0`、`librosa>=0.10.1`、`safetensors>=0.4.0`、`huggingface-hub`

## 模型目录

LongCat 节点会在启动日志中打印实际目录：

```text
[LongCatAudioDiT] Models folder registered: <ComfyUI models dir>/audiodit
```

ComfyUI Desktop 当前常见目录为：

```text
E:\comfyui-venv\models\audiodit
```

模型和 tokenizer 需要放置为：

```text
E:\comfyui-venv\models\audiodit\LongCat-AudioDiT-1B
E:\comfyui-venv\models\audiodit\umt5-base-tokenizer
```

如果本机日志显示的目录不同，以日志中的 `Models folder registered` 为准。

## ModelScope 下载优先级

本工作流默认使用魔搭社区模型，避免触发节点内置的 Hugging Face 自动下载。

首选模型：

- `meituan-longcat/LongCat-AudioDiT-1B`
- `google/umt5-base` tokenizer 文件

可选高配模型：

- `meituan-longcat/LongCat-AudioDiT-3.5B`

当前不要把工作流默认值改成带 `(auto download)` 的模型选项，否则节点会尝试从 Hugging Face 下载。

## 下载命令

在 ComfyUI 使用的 Python 环境中执行：

```powershell
@'
from modelscope.hub.snapshot_download import snapshot_download
from pathlib import Path

base = Path(r"E:\comfyui-venv\models\audiodit")
model_dir = base / "LongCat-AudioDiT-1B"
tokenizer_dir = base / "umt5-base-tokenizer"
base.mkdir(parents=True, exist_ok=True)

snapshot_download(
    model_id="meituan-longcat/LongCat-AudioDiT-1B",
    local_dir=str(model_dir),
    max_workers=4,
)

snapshot_download(
    model_id="google/umt5-base",
    local_dir=str(tokenizer_dir),
    allow_file_pattern=[
        "tokenizer*.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "added_tokens.json",
        "spiece.model",
        "*.txt",
    ],
    max_workers=4,
)
'@ | E:\comfyui-venv\.venv\Scripts\python.exe -
```

## 验证命令

```powershell
Get-Item E:\comfyui-venv\models\audiodit\LongCat-AudioDiT-1B\model.safetensors
Get-FileHash E:\comfyui-venv\models\audiodit\LongCat-AudioDiT-1B\model.safetensors -Algorithm SHA256
Get-ChildItem E:\comfyui-venv\models\audiodit\umt5-base-tokenizer
```

1B 模型的 `model.safetensors` 参考信息：

- 大小：`5679831348` bytes
- SHA256：`7F41B20933E4466400B8487FD20CA195EFA65C5CA7C61F8E9BBA6316AA3EDCDE`

## 常见问题

- ComfyUI 中只看到 `LongCat-AudioDiT-1B` 且其他模型显示 `(auto download)` 是正常现象；只要工作流默认选择 `LongCat-AudioDiT-1B`，就不会触发 Hugging Face 模型下载。
- 声音克隆建议上传 3-15 秒参考音频，并填写参考音频对应文本 `prompt_text`。
- 生成长音频时建议先按段生成，再由 Pixelle 负责拼接和对齐。
