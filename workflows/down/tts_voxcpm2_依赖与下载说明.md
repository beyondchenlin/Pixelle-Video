# tts_voxcpm2 依赖与下载说明

## 1. 对应工作流

- `workflows/selfhost/tts_voxcpm2_rh.json`
- `workflows/selfhost/tts_voxcpm2_rh_clone.json`
- `workflows/selfhost/tts_voxcpm2_saganaki.json`
- `workflows/selfhost/tts_voxcpm2_saganaki_clone.json`

这些工作流用于在本地 ComfyUI 中通过 VoxCPM2 生成语音。前两份使用 `HM-RunningHub/ComfyUI_RH_VoxCPM`，后两份使用 `Saganaki22/ComfyUI-VoxCPM2`。

## 2. 节点与依赖清单

| 节点 / 依赖 | 类型 | 来源 | 说明 |
| --- | --- | --- | --- |
| `RunningHub_VoxCPM_LoadModel` | ComfyUI 自定义节点 | `HM-RunningHub/ComfyUI_RH_VoxCPM` | 加载 `models/voxcpm` 下的 VoxCPM2 模型 |
| `RunningHub_VoxCPM_Generate` | ComfyUI 自定义节点 | `HM-RunningHub/ComfyUI_RH_VoxCPM` | 生成语音，支持声音设计、克隆、极致克隆 |
| `VoxCPM2_TTS` | ComfyUI 自定义节点 | `Saganaki22/ComfyUI-VoxCPM2` | 普通 TTS 与声音设计 |
| `VoxCPM2_Clone` | ComfyUI 自定义节点 | `Saganaki22/ComfyUI-VoxCPM2` | 参考音频克隆 |
| `VHS_LoadAudioUpload` | ComfyUI 自定义节点 | `ComfyUI-VideoHelperSuite` | 上传参考音频 |
| `SaveAudioMP3` | ComfyUI 自定义节点 | `ComfyUI-VideoHelperSuite` | 保存 MP3 音频输出 |
| `VoxCPM2` | 模型 | ModelScope: `OpenBMB/VoxCPM2` | 必需主模型 |
| `SenseVoiceSmall` | ASR 模型 | ModelScope: `iic/SenseVoiceSmall` | 可选，用于参考音频自动转写 |
| `ZipEnhancer` | 降噪模型 | ModelScope: `iic/speech_zipenhancer_ans_multiloss_16k_base` | 可选，用于参考音频降噪 |

## 3. 下载优先级

本仓库要求模型文件优先从 ModelScope（魔搭）下载。只有在 ModelScope 缺少对应资源或当前不可用时，才允许回退到 Hugging Face。

已确认的 ModelScope 主模型地址：

- `https://modelscope.cn/models/OpenBMB/VoxCPM2`

备用 Hugging Face 地址仅作为回退记录：

- `https://huggingface.co/openbmb/VoxCPM2`

## 4. 目标目录

建议只保存一份 VoxCPM2 主模型：

- 主目录：`E:\comfyui\comfyui\models\voxcpm\VoxCPM2`
- Saganaki 兼容目录：`E:\comfyui\comfyui\models\tts\VoxCPM\VoxCPM2`

如果磁盘支持 NTFS junction，建议让 Saganaki 兼容目录指向主目录，避免重复占用约 4GB 以上空间。

可选模型目录：

- RunningHub ASR：`E:\comfyui\comfyui\models\SenseVoice\SenseVoiceSmall`
- Saganaki ASR：`E:\comfyui\comfyui\models\audio_encoders\SenseVoiceSmall`
- RunningHub 降噪：`E:\comfyui\comfyui\models\voxcpm\speech_zipenhancer_ans_multiloss_16k_base`

## 5. 安装节点

所有 Python 包都必须安装到 ComfyUI 实际运行的 Python 环境中，不要安装到 Pixelle 项目的 `.venv`。

```powershell
cd E:\comfyui\comfyui\custom_nodes
git clone https://github.com/HM-RunningHub/ComfyUI_RH_VoxCPM.git
git clone https://github.com/Saganaki22/ComfyUI-VoxCPM2.git

E:\comfyui\resources\uv\win\uv.exe pip install --python E:\comfyui-venv\.venv\Scripts\python.exe -r E:\comfyui\comfyui\custom_nodes\ComfyUI_RH_VoxCPM\requirements.txt
E:\comfyui\resources\uv\win\uv.exe pip install --python E:\comfyui-venv\.venv\Scripts\python.exe -e E:\comfyui\comfyui\custom_nodes\ComfyUI-VoxCPM2
```

说明：`ComfyUI-VoxCPM2` 的依赖主要声明在 `pyproject.toml` 中，因此手动安装时优先使用 `pip install -e` 让 Python 读取项目依赖。

如果 Windows 上安装 `editdistance` 失败，可先安装 `pdm-backend` 并设置编译编码：

```powershell
E:\comfyui\resources\uv\win\uv.exe pip install --python E:\comfyui-venv\.venv\Scripts\python.exe pdm-backend
$env:CL="/utf-8"
```

## 6. 从 ModelScope 下载模型

### 6.1 安装 ModelScope

```powershell
E:\comfyui\resources\uv\win\uv.exe pip install --python E:\comfyui-venv\.venv\Scripts\python.exe modelscope
```

### 6.2 下载 VoxCPM2 主模型

```powershell
@'
from modelscope import snapshot_download

snapshot_download(
    "OpenBMB/VoxCPM2",
    local_dir=r"E:\comfyui\comfyui\models\voxcpm\VoxCPM2",
)
'@ | & E:\comfyui-venv\.venv\Scripts\python.exe -
```

### 6.3 让 Saganaki 节点复用同一份模型

```powershell
New-Item -ItemType Directory -Force -Path 'E:\comfyui\comfyui\models\tts\VoxCPM'
cmd /c mklink /J "E:\comfyui\comfyui\models\tts\VoxCPM\VoxCPM2" "E:\comfyui\comfyui\models\voxcpm\VoxCPM2"
```

如果目标目录已存在，不要直接覆盖。先确认它不是已有真实模型目录，再决定是否删除或改名。

### 6.4 可选：下载 ASR 模型

```powershell
@'
from modelscope import snapshot_download

snapshot_download(
    "iic/SenseVoiceSmall",
    local_dir=r"E:\comfyui\comfyui\models\SenseVoice\SenseVoiceSmall",
)
'@ | & E:\comfyui-venv\.venv\Scripts\python.exe -
```

Saganaki 节点默认会检查 `models/audio_encoders/SenseVoiceSmall`。如需让它也复用 ModelScope 下载结果：

```powershell
New-Item -ItemType Directory -Force -Path 'E:\comfyui\comfyui\models\audio_encoders'
cmd /c mklink /J "E:\comfyui\comfyui\models\audio_encoders\SenseVoiceSmall" "E:\comfyui\comfyui\models\SenseVoice\SenseVoiceSmall"
```

### 6.5 可选：下载参考音频降噪模型

```powershell
@'
from modelscope import snapshot_download

snapshot_download(
    "iic/speech_zipenhancer_ans_multiloss_16k_base",
    local_dir=r"E:\comfyui\comfyui\models\voxcpm\speech_zipenhancer_ans_multiloss_16k_base",
)
'@ | & E:\comfyui-venv\.venv\Scripts\python.exe -
```

## 7. 验证命令

### 7.1 验证文件存在

```powershell
Test-Path 'E:\comfyui\comfyui\models\voxcpm\VoxCPM2\config.json'
Test-Path 'E:\comfyui\comfyui\models\voxcpm\VoxCPM2\model.safetensors'
Test-Path 'E:\comfyui\comfyui\models\voxcpm\VoxCPM2\audiovae.pth'
Test-Path 'E:\comfyui\comfyui\models\tts\VoxCPM\VoxCPM2\config.json'
```

预期结果均为 `True`。

### 7.2 验证 ComfyUI 节点注册

重启 ComfyUI 后执行：

```powershell
$resp = Invoke-RestMethod 'http://127.0.0.1:8000/object_info'
@(
  'RunningHub_VoxCPM_LoadModel',
  'RunningHub_VoxCPM_Generate',
  'VoxCPM2_TTS',
  'VoxCPM2_Clone',
  'VHS_LoadAudioUpload',
  'SaveAudioMP3'
) | ForEach-Object {
    if ($resp.PSObject.Properties.Name -contains $_) {
        "FOUND`t$_"
    } else {
        "MISSING`t$_"
    }
}
```

### 7.3 验证 Pixelle 工作流解析

```powershell
uv run pytest tests/test_selfhost_workflows.py -k voxcpm2 -v
```

## 8. 常见问题

### 8.1 找不到 `RunningHub_VoxCPM_LoadModel`

说明 `ComfyUI_RH_VoxCPM` 未安装、依赖安装失败，或 ComfyUI 尚未重启。先检查 `E:\comfyui\comfyui\custom_nodes\ComfyUI_RH_VoxCPM` 是否存在。

### 8.2 找不到 `VoxCPM2_TTS`

说明 `ComfyUI-VoxCPM2` 未安装、依赖安装失败，或 ComfyUI 尚未重启。先检查 `E:\comfyui\comfyui\custom_nodes\ComfyUI-VoxCPM2` 是否存在。

### 8.3 节点尝试从 Hugging Face 下载模型

优先确认 ModelScope 下载目录和 junction 是否存在：

```powershell
Get-Item 'E:\comfyui\comfyui\models\voxcpm\VoxCPM2'
Get-Item 'E:\comfyui\comfyui\models\tts\VoxCPM\VoxCPM2'
```

如果 Saganaki 节点仍尝试下载，说明它没有识别到 `models\tts\VoxCPM\VoxCPM2` 下的完整模型文件。

### 8.4 显存不足

VoxCPM2 是 20 亿参数模型，官方说明约需 8GB 显存。若与图像/视频模型同时使用，建议在 TTS 工作流中先保持默认 `torch_compile=false`、`force_offload=false`，确认能跑通后再调整。

### 8.5 生成结果不稳定

声音设计和可控克隆有随机性。可固定 `seed`，或生成 1 到 3 次选择效果更好的结果。
