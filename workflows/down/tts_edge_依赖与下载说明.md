# tts_edge 工作流依赖与下载说明

## 1. 对应工作流

- 工作流路径：`workflows/selfhost/tts_edge.json`
- 工作流用途：使用 Microsoft Edge TTS 生成语音，并导出为 MP3 文件。
- 当前工作流不依赖图片或视频模型，不需要下载 `diffusion_models`、`text_encoders`、`vae`、`checkpoints` 等大模型文件。

## 2. 节点依赖清单

本工作流实际用到的节点如下：

| 节点名 | 类型 | 是否需要额外安装 | 说明 |
| --- | --- | --- | --- |
| `EdgeTTS` | 自定义节点 | 是 | 来自 `ComfyUI-EdgeTTS`，为本工作流核心依赖 |
| `SaveAudioMP3` | ComfyUI 内置节点 | 否 | 用于导出 MP3 |
| `PrimitiveStringMultiline` | ComfyUI 内置节点 | 否 | 用于输入文本和语音选项 |
| `easy showAnything` | 自定义节点 | 是 | 来自 `ComfyUI-Easy-Use` |
| `easy float` | 自定义节点 | 是 | 来自 `ComfyUI-Easy-Use` |

## 3. 下载优先级

- 所有模型资源、插件资源和大体积制品，默认先检查 `ModelScope`。
- 若 `ModelScope` 没有对应资源，或当前不可用，再回退到其他来源。
- 本工作流主要依赖的是 ComfyUI 插件和 Python 包，不是大模型文件。
- 截至 `2026-04-20`，基于当前公开检索结果，未检索到 `ComfyUI-EdgeTTS` 和 `ComfyUI-Easy-Use` 的明确可用 `ModelScope` 项目页面，因此当前记录的可执行回退来源为 GitHub。

## 4. 依赖来源说明

### 4.1 ComfyUI-EdgeTTS

- 作用：提供 `EdgeTTS` 节点。
- `ModelScope`：当前未检索到明确可用条目，执行安装时仍应先复查。
- 备用地址：
  - 仓库地址：`https://github.com/1038lab/ComfyUI-EdgeTTS`
  - ZIP 地址：`https://github.com/1038lab/ComfyUI-EdgeTTS/archive/refs/heads/main.zip`

### 4.2 ComfyUI-Easy-Use

- 作用：提供 `easy showAnything`、`easy float` 等节点。
- `ModelScope`：当前未检索到明确可用条目，执行安装时仍应先复查。
- 备用地址：
  - 仓库地址：`https://github.com/yolain/ComfyUI-Easy-Use`
  - ZIP 地址：`https://github.com/yolain/ComfyUI-Easy-Use/archive/refs/heads/main.zip`

### 4.3 Python 包依赖

- 本工作流所需 Python 依赖主要来自插件自己的 `requirements.txt`。
- 这类依赖通过 `pip` 安装，不属于 `ModelScope` 模型下载流程。
- `ComfyUI-EdgeTTS` 上游 `requirements.txt` 当前包含：
  - `edge-tts>=7.0.0`
  - `torchaudio`
  - `torchcodec==0.9`
  - `openai-whisper>=20231117`
  - `numpy`
  - `torch`
  - `googletrans-py>=3.0.0`
  - `deep-translator>=1.11.4`
- `ComfyUI-Easy-Use` 当前 `requirements.txt` 包含多个常用依赖，例如：
  - `diffusers`
  - `accelerate`
  - `clip_interrogator>=0.6.0`
  - `onnxruntime`
  - `opencv-python-headless`

## 5. 当前推荐安装路径

以下路径基于当前本机环境整理：

- ComfyUI 自定义节点目录：`E:\comfyui\comfyui\custom_nodes`
- ComfyUI Python 环境：`C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe`

如果后续 ComfyUI 启动日志中的 `** Python executable:` 发生变化，必须同步调整下面所有 `pip` 安装命令中的 Python 路径。

## 6. 推荐安装命令

### 6.1 使用 Git 方式安装

```powershell
New-Item -ItemType Directory -Force 'E:\comfyui\comfyui\custom_nodes' | Out-Null
Set-Location 'E:\comfyui\comfyui\custom_nodes'

git clone https://github.com/yolain/ComfyUI-Easy-Use.git
git clone https://github.com/1038lab/ComfyUI-EdgeTTS.git

& 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -m pip install -U pip
& 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -m pip install -r 'E:\comfyui\comfyui\custom_nodes\ComfyUI-Easy-Use\requirements.txt'
& 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -m pip install -r 'E:\comfyui\comfyui\custom_nodes\ComfyUI-EdgeTTS\requirements.txt'

& 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -m pip uninstall -y torchcodec
& 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -m pip install --no-cache-dir "torchcodec==0.9"
```

### 6.2 Git 不可用时的备用安装方式

- 先检查 `ModelScope` 是否已有可用资源。
- 若 `ModelScope` 仍无可用资源，再使用 GitHub ZIP 下载。
- 将 ZIP 解压到以下目录，目录名需保持不变：
  - `E:\comfyui\comfyui\custom_nodes\ComfyUI-Easy-Use`
  - `E:\comfyui\comfyui\custom_nodes\ComfyUI-EdgeTTS`
- 解压后执行同样的 `pip install -r ...` 命令。

## 7. 可选系统依赖说明

- `ComfyUI-EdgeTTS` 上游说明中提到 `FFmpeg` 用于 `Whisper STT` 相关能力。
- 当前 `tts_edge.json` 只使用 TTS，不直接使用 Whisper STT，因此 `FFmpeg` 不是本工作流的硬性前置条件。
- 如果未来改用同一插件内的 STT 节点，再补充 `FFmpeg` 的安装和 PATH 配置说明。

## 8. 安装完成后的验证命令

安装完成后，重启 ComfyUI，然后执行以下验证：

```powershell
$resp = Invoke-RestMethod 'http://127.0.0.1:8000/object_info'
@('EdgeTTS', 'SaveAudioMP3', 'PrimitiveStringMultiline', 'easy showAnything', 'easy float') |
ForEach-Object {
    if ($resp.PSObject.Properties.Name -contains $_) {
        "FOUND`t$_"
    } else {
        "MISSING`t$_"
    }
}
```

预期结果：

- `EdgeTTS` 显示为 `FOUND`
- `easy showAnything` 显示为 `FOUND`
- `easy float` 显示为 `FOUND`
- 其余内置节点也应显示为 `FOUND`

## 9. 常见问题

### 9.1 报错 `Node 'EdgeTTS' not found`

- 原因：`ComfyUI-EdgeTTS` 未安装，或已安装但 ComfyUI 未重启。
- 处理：
  - 检查 `E:\comfyui\comfyui\custom_nodes\ComfyUI-EdgeTTS` 是否存在。
  - 检查 `requirements.txt` 是否安装完成。
  - 重启 ComfyUI 后再次执行验证命令。

### 9.2 报错 `easy showAnything` 或 `easy float` 不存在

- 原因：`ComfyUI-Easy-Use` 未安装或加载失败。
- 处理：
  - 检查 `E:\comfyui\comfyui\custom_nodes\ComfyUI-Easy-Use` 是否存在。
  - 检查其 `requirements.txt` 是否安装完成。
  - 查看 ComfyUI 启动日志中是否有 `ComfyUI-Easy-Use` 的加载报错。

### 9.3 `git clone` 失败

- 原因通常是网络、DNS 或 GitHub 访问问题。
- 处理：
  - 先按仓库规则重新检查 `ModelScope` 是否已有可用资源。
  - 若仍无可用资源，则改用 GitHub ZIP 方式。

### 9.4 安装到了错误的 Python 环境

- 现象：目录里有插件，但节点仍然找不到。
- 处理：
  - 以 ComfyUI 启动日志中的 `** Python executable:` 为准。
  - 确认所有 `pip install` 命令都使用了同一个 Python 路径。

## 10. 维护要求

- 后续若本工作流新增节点、模型或系统依赖，必须同步更新本文件。
- 若后续在 `ModelScope` 找到可用官方或稳定镜像，应把 `ModelScope` 地址补回本文件，并将其提升为主下载源。
- 只有在下载、安装、重启、验证全部通过后，才能将依赖标记为已完成。

## 11. 参考来源

- `ComfyUI-EdgeTTS`：`https://github.com/1038lab/ComfyUI-EdgeTTS`
- `ComfyUI-Easy-Use`：`https://github.com/yolain/ComfyUI-Easy-Use`
