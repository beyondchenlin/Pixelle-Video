# tts_edge 依赖与下载说明

## 1. 对应工作流
- 工作流路径：`workflows/selfhost/tts_edge.json`
- 工作流用途：使用 Pixelle 自有 `PixelleEdgeTTS` 节点调用 Microsoft Edge TTS 生成语音，并导出为 MP3。
- 当前工作流不依赖 `diffusion_models`、`text_encoders`、`vae`、`checkpoints` 等模型文件，不需要下载大模型。

## 2. 节点与依赖清单

| 节点 / 依赖 | 类型 | 是否额外安装 | 说明 |
| --- | --- | --- | --- |
| `PixelleEdgeTTS` | Pixelle 自定义节点 | 是 | 仓库内维护的 Edge TTS 节点，负责联网合成与 FFmpeg 解码 |
| `PixelleFloatInput` | Pixelle 自定义节点 | 是 | 用于暴露 `$speed.value` 工作流参数 |
| `PrimitiveStringMultiline` | ComfyUI 内置节点 | 否 | 用于输入文本与真实 voice ID |
| `SaveAudioMP3` | ComfyUI 内置节点 | 否 | 用于导出 MP3 |
| `edge-tts==7.2.7` | Python 包 | 是 | Edge TTS SDK |
| `ffmpeg` | 系统工具 | 是 | 将返回的 MP3 解码为 ComfyUI `AUDIO` |

## 3. 依赖分类与目标目录

### 3.1 仓库内源码
- 插件源码目录：`tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS`
- 同步脚本：`tools/sync_pixelle_tts_custom_node.py`

### 3.2 ComfyUI 部署目录
- ComfyUI 自定义节点目录：`E:\comfyui\comfyui\custom_nodes`
- 本工作流实际部署目标：`E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS`

### 3.3 ComfyUI Python 环境
- 当前建议使用：`C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe`
- 如果 ComfyUI 启动日志中的 `Python executable` 发生变化，后文所有安装命令都要同步改成实际路径。

## 4. 下载优先级
- 本工作流不依赖模型文件，因此当前没有需要从 `ModelScope` 下载的模型资源。
- 如后续版本新增模型依赖，必须先检查 `ModelScope`，仅在 `ModelScope` 缺失或不可用时才回退到其他来源。
- 当前工作流的核心依赖是仓库内源码、Python 包和 FFmpeg，不属于模型下载流程。

## 5. 来源说明

### 5.1 Pixelle 自定义节点
- 主来源：当前仓库 `tools/comfyui/custom_nodes/ComfyUI-Pixelle-TTS`
- 部署方式：通过仓库自带脚本同步到 ComfyUI `custom_nodes`
- 不再依赖第三方 `ComfyUI-EdgeTTS`
- 不再依赖第三方 `ComfyUI-Easy-Use`

### 5.2 Python 包
- `edge-tts==7.2.7`
- 安装方式：由同步脚本触发 `pip install -r requirements.txt`

### 5.3 系统工具
- `ffmpeg`
- 要求：`ffmpeg` 命令必须可在 ComfyUI 运行环境的 `PATH` 中找到
- 用途：将 Edge TTS 返回的 MP3 解码为单声道 24kHz 浮点波形

## 6. 安装与同步命令

### 6.1 首次同步或更新插件
```powershell
uv run python tools/sync_pixelle_tts_custom_node.py `
  --target 'E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS' `
  --python 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe'
```

### 6.2 仅同步源码，不重新安装依赖
```powershell
uv run python tools/sync_pixelle_tts_custom_node.py `
  --target 'E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS' `
  --python 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' `
  --skip-install
```

### 6.3 检查 FFmpeg
```powershell
ffmpeg -version
```

## 7. 验证命令

### 7.1 验证仓库测试
```powershell
uv run pytest tests/test_selfhost_workflows.py tests/test_pixelle_tts_custom_node.py tests/test_sync_pixelle_tts_custom_node.py tests/test_tts_util.py -v
```

### 7.2 验证部署目录存在且文件齐全
```powershell
Get-ChildItem 'E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS' -Recurse |
Select-Object FullName, Length
```

### 7.3 重启 ComfyUI 后验证节点注册
```powershell
$resp = Invoke-RestMethod 'http://127.0.0.1:8000/object_info'
@('PixelleEdgeTTS', 'PixelleFloatInput', 'SaveAudioMP3', 'PrimitiveStringMultiline') |
ForEach-Object {
    if ($resp.PSObject.Properties.Name -contains $_) {
        "FOUND`t$_"
    } else {
        "MISSING`t$_"
    }
}
```

### 7.4 验证插件可直接生成有声波形
```powershell
@'
import sys
sys.path.insert(0, r'E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS')
from pixelle_edge_tts import PixelleEdgeTTS

node = PixelleEdgeTTS()
audio = node.tts('床前明月光，疑是地上霜。', 'zh-CN-YunjianNeural', 1.0, 0)[0]
print(audio['sample_rate'])
print(float(audio['waveform'].abs().max()))
'@ | & 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -
```

预期结果：
- `sample_rate` 为 `24000`
- 幅值为非零值

## 8. 常见问题

### 8.1 报错 `Node 'PixelleEdgeTTS' not found`
- 原因：插件还没同步到 `custom_nodes`，或 ComfyUI 未重启。
- 处理：
  - 重新执行同步脚本。
  - 检查 `E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS` 是否存在。
  - 重启 ComfyUI 后重新执行节点注册验证命令。

### 8.2 报错 `ffmpeg was not found in PATH`
- 原因：运行 ComfyUI 的环境里找不到 `ffmpeg`。
- 处理：
  - 先执行 `ffmpeg -version`。
  - 确保 ComfyUI 启动进程可访问到 FFmpeg 所在目录。
  - 修复后重启 ComfyUI 再跑工作流。

### 8.3 报错 `Use a real Edge voice ID instead of a display label`
- 原因：把旧工作流里的展示标签，例如 `[Chinese] zh-CN Yunjian`，当成了 voice 参数传入。
- 处理：
  - 改用真实 voice ID，例如 `zh-CN-YunjianNeural`。
  - `tts_edge.json` 当前默认值已经切换为真实 ID，不要再改回展示标签。

### 8.4 生成失败并提示 Edge 网络错误
- 现象：工作流直接报错，不再输出静音 MP3。
- 说明：这是刻意的最佳实践行为。Pixelle 节点会在网络重试后仍失败时显式报错，而不是伪造一段静音波形。
- 处理：
  - 稍后重试一次。
  - 检查本机网络是否能访问 `speech.platform.bing.com`。

### 8.5 生成失败并提示 FFmpeg 解码错误
- 原因：FFmpeg 不可用、输入 MP3 不完整，或环境异常。
- 处理：
  - 先执行 `ffmpeg -version`。
  - 用第 7.4 节的直调命令复现。
  - 查看错误信息，不要把失败结果当成“成功但无声”。

## 9. 维护要求
- 后续如修改 `workflows/selfhost/tts_edge.json`，必须同时保持 `text`、`voice`、`speed` 三个工作流参数映射可被 `WorkflowParser` 正确解析。
- 后续如修改 Pixelle 节点源码，必须先更新仓库内源码，再通过同步脚本部署，不要直接把外部 `custom_nodes` 目录当成唯一源码。
- 后续如新增依赖，必须同步更新本说明文档，并补充验证命令。
