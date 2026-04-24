# tts_longcat 依赖与下载说明

## 对应工作流

- `workflows/selfhost/tts_longcat.json`

## 节点与依赖

- ComfyUI 自定义节点：`Saganaki22/ComfyUI-LongCat-AudioDIT-TTS`
- 主要节点：`LongCatTTS`
- 音频输出节点：`SaveAudioMP3`
- Python 依赖：以插件 `requirements.txt` 为准，包含 `numpy`、`soundfile`、`transformers`、`einops`、`librosa`、`safetensors`、`huggingface-hub`

## 模型目录

LongCat 插件通过 ComfyUI 的 `folder_paths.models_dir` 注册模型目录：

```text
<ComfyUI models dir>/audiodit
```

当前 ComfyUI Desktop 常见运行时目录：

```text
E:\comfyui-venv\models\audiodit
```

本工作流默认使用：

```text
E:\comfyui-venv\models\audiodit\LongCat-AudioDiT-1B
E:\comfyui-venv\models\audiodit\umt5-base-tokenizer
```

如果本机日志显示的 `Models folder registered` 目录不同，以日志为准。

## ModelScope 下载优先级

本工作流默认选择 `LongCat-AudioDiT-1B`，要求先从 ModelScope 放好模型，避免触发插件内置的 Hugging Face 自动下载。

首选模型：

- `meituan-longcat/LongCat-AudioDiT-1B`
- `google/umt5-base` tokenizer 文件

可选高配模型：

- `meituan-longcat/LongCat-AudioDiT-3.5B`

不要把 workflow 默认值改成带 `(auto download)` 的模型选项，否则插件会尝试从 Hugging Face 下载。

## 下载命令

在 ComfyUI 使用的 Python 环境中执行：

```powershell
@'
from modelscope import snapshot_download
from pathlib import Path

base = Path(r"E:\comfyui-venv\models\audiodit")
model_dir = base / "LongCat-AudioDiT-1B"
tokenizer_dir = base / "umt5-base-tokenizer"
base.mkdir(parents=True, exist_ok=True)

snapshot_download(
    "meituan-longcat/LongCat-AudioDiT-1B",
    local_dir=str(model_dir),
    max_workers=4,
)

snapshot_download(
    "google/umt5-base",
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

## 插件安装

```powershell
cd E:\comfyui\comfyui\custom_nodes
git clone https://github.com/Saganaki22/ComfyUI-LongCat-AudioDIT-TTS.git
E:\comfyui-venv\.venv\Scripts\python.exe -m pip install -r E:\comfyui\comfyui\custom_nodes\ComfyUI-LongCat-AudioDIT-TTS\requirements.txt
```

如果目录已经存在，先在该目录内执行 `git pull`，再安装依赖。

## 验证命令

```powershell
Test-Path E:\comfyui-venv\models\audiodit\LongCat-AudioDiT-1B\model.safetensors
Get-ChildItem E:\comfyui-venv\models\audiodit\umt5-base-tokenizer
```

启动 ComfyUI 后确认节点存在：

```powershell
@(
  'LongCatTTS',
  'SaveAudioMP3'
) | ForEach-Object {
  Select-String -Path 'E:\comfyui\comfyui\custom_nodes\ComfyUI-LongCat-AudioDIT-TTS\**\*.py' -Pattern $_
}
```

## 常见问题

- 如果 ComfyUI 中只看到带 `(auto download)` 的模型选项，说明目标目录没有放好模型文件；先完成 ModelScope 下载，再重启 ComfyUI。
- LongCat 官方/插件说明都提醒长文本更容易出现重复或漏词。Pixelle 中建议按段生成，再由视频流程做拼接和对齐。
- 纯文本 TTS 使用 `guidance_method=cfg`；克隆工作流使用 `guidance_method=apg`。
