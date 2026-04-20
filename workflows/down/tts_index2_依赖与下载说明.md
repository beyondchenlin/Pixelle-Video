# tts_index2 工作流依赖与下载说明

## 1. 对应工作流

- 工作流路径：`workflows/selfhost/tts_index2.json`
- 工作流用途：使用 IndexTTS-2 在本地 ComfyUI 中执行文本转语音，并导出为 MP3 文件。
- 当前工作流依赖的是音频相关节点和 TTS 模型，不需要下载图片生成类 `diffusion_models`、`text_encoders`、`vae`、`checkpoints` 等视觉模型。
- 当前仓库版本已移除旧的 `Text _O` 依赖，文本输入节点改为 ComfyUI 内置 `PrimitiveStringMultiline`。

## 2. 节点依赖清单

本工作流当前实际用到的节点如下：

| 节点名 | 类型 | 是否需要额外安装 | 说明 |
| --- | --- | --- | --- |
| `PrimitiveStringMultiline` | ComfyUI 内置节点 | 否 | 负责接收输入文本 |
| `VHS_LoadAudioUpload` | 自定义节点 | 是 | 来自 `ComfyUI-VideoHelperSuite`，负责加载参考音频 |
| `IndexTTS2BaseNode` | 自定义节点 | 是 | 来自 `ComfyUI-Index-TTS`，负责执行 TTS2 推理 |
| `SaveAudioMP3` | ComfyUI 内置节点 | 否 | 负责导出 MP3 |

## 3. 下载优先级

- 所有模型资源、插件资源和大体积制品，默认先检查 `ModelScope`。
- 若 `ModelScope` 没有对应资源，或当前不可用，再回退到其他来源。
- 本工作流同时依赖：
  - `ModelScope` 上可获取的模型文件
  - `ModelScope` 上暂未确认可用镜像的 ComfyUI 插件
  - 插件自身所需的 Python 包
- 截至 `2026-04-20`，当前实机验证结果如下：
  - `IndexTTS-2` 相关模型文件可从 `ModelScope` 下载。
  - `ComfyUI-Index-TTS`、`ComfyUI-VideoHelperSuite` 未检索到明确可用的 `ModelScope` 仓库 API 条目，因此本说明将 GitHub 作为当前可执行回退源记录。

## 4. 依赖来源说明

### 4.1 模型文件

以下模型均已在本机按 `ModelScope` 优先规则实际验证可下载：

| 用途 | ModelScope 标识 | 目标位置 |
| --- | --- | --- |
| IndexTTS-2 主模型 | `IndexTeam/IndexTTS-2` | `E:\comfyui\comfyui\models\IndexTTS-2` |
| semantic codec | `amphion/MaskGCT` | `E:\comfyui\comfyui\models\IndexTTS-2\semantic_codec\model.safetensors` |
| CampPlus 说话人嵌入 | `iic/speech_campplus_sv_zh-cn_16k-common` | `E:\comfyui\comfyui\models\IndexTTS-2\campplus_cn_common.bin` |
| Wav2Vec2Bert | `facebook/w2v-bert-2.0` | `E:\comfyui\comfyui\models\IndexTTS-2\w2v-bert-2.0` |
| BigVGAN 声码器 | `nv-community/bigvgan_v2_22khz_80band_256x` | `E:\comfyui\comfyui\models\IndexTTS-2\bigvgan\bigvgan_v2_22khz_80band_256x` |

### 4.2 ComfyUI-Index-TTS

- 作用：提供 `IndexTTS2BaseNode` 等节点。
- `ModelScope`：截至 `2026-04-20`，未检索到明确可用的公开仓库 API 条目，执行安装时仍应先复查。
- 备用地址：
  - 仓库地址：`https://github.com/chenpipi0807/ComfyUI-Index-TTS`
  - ZIP 地址：`https://github.com/chenpipi0807/ComfyUI-Index-TTS/archive/refs/heads/main.zip`
  - codeload 地址：`https://codeload.github.com/chenpipi0807/ComfyUI-Index-TTS/zip/refs/heads/main`

### 4.3 ComfyUI-VideoHelperSuite

- 作用：提供 `VHS_LoadAudioUpload` 等节点。
- `ModelScope`：截至 `2026-04-20`，未检索到明确可用的公开仓库 API 条目，执行安装时仍应先复查。
- 备用地址：
  - 仓库地址：`https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite`
  - ZIP 地址：`https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite/archive/refs/heads/main.zip`

### 4.4 Python 包依赖

- 这类依赖通过 `pip` 安装，不属于 `ModelScope` 模型下载流程。
- `ComfyUI-Index-TTS` 当前至少需要以下包：
  - `librosa`
  - `soundfile`
  - `omegaconf`
  - `modelscope`
  - `json5`
  - `munch`
  - `einops`
  - `ffmpy`
  - `docstring-parser`
  - `wetext`
  - `descript-audiotools==0.7.4`
- `ComfyUI-VideoHelperSuite` 当前至少需要以下包：
  - `opencv-python`
  - `imageio-ffmpeg`
- 本机于 `2026-04-20` 的实际安装环境为：
  - `torch==2.10.0+cu130`
  - `torchaudio==2.10.0+cu130`
  - `transformers==5.0.0`
  - `safetensors==0.7.0`
- 当前实机冷启动验证中，`ComfyUI-Index-TTS` 已在上述环境下成功导入。
- 推理阶段若出现 `transformers` 兼容性问题，这是基于上游 README 的推断：可优先回退到 `4.54.1` 或 `4.52.1` 再复测。

## 5. 当前推荐安装路径

以下路径基于当前本机环境整理：

- 生效中的 ComfyUI 额外模型配置：`C:\Users\ai\AppData\Roaming\ComfyUI\extra_models_config.yaml`
- 生效中的自定义节点目录：`E:\comfyui\comfyui\custom_nodes`
- 生效中的模型目录：`E:\comfyui\comfyui\models`
- 当前 ComfyUI Python 环境：`C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe`

说明：

- 当前桌面版 ComfyUI 虽然程序本体位于 `E:\comfyui`，但后端实际使用的是 `C:\Users\ai\Documents\ComfyUI\.venv` 作为 Python 环境。
- 所有 `pip install` 命令都必须以 ComfyUI 启动日志里的 `** Python executable:` 为准，不能误装到项目自己的 `.venv`。

## 6. 推荐安装命令

### 6.1 先检查磁盘空间

```powershell
Get-PSDrive E | Select-Object Used,Free,Root
```

### 6.2 通过 ModelScope 下载模型

```powershell
uv run --with modelscope python -c "from modelscope import snapshot_download; print(snapshot_download('IndexTeam/IndexTTS-2', local_dir=r'E:\comfyui\comfyui\models\IndexTTS-2'))"

uv run --with modelscope python -c "from modelscope import snapshot_download; print(snapshot_download('amphion/MaskGCT', local_dir=r'E:\comfyui\comfyui\models\IndexTTS-2', allow_patterns=['semantic_codec/model.safetensors']))"

uv run --with modelscope python -c "from modelscope import snapshot_download; print(snapshot_download('iic/speech_campplus_sv_zh-cn_16k-common', local_dir=r'E:\comfyui\comfyui\models\IndexTTS-2', allow_patterns=['campplus_cn_common.bin']))"

uv run --with modelscope python -c "from modelscope import snapshot_download; print(snapshot_download('facebook/w2v-bert-2.0', local_dir=r'E:\comfyui\comfyui\models\IndexTTS-2\w2v-bert-2.0'))"

uv run --with modelscope python -c "from modelscope import snapshot_download; print(snapshot_download('nv-community/bigvgan_v2_22khz_80band_256x', local_dir=r'E:\comfyui\comfyui\models\IndexTTS-2\bigvgan\bigvgan_v2_22khz_80band_256x'))"
```

### 6.3 安装自定义节点

优先检查 `ModelScope` 是否已有可用镜像；若仍无可用条目，再使用 GitHub ZIP 方式。

```powershell
New-Item -ItemType Directory -Force 'E:\comfyui\comfyui\custom_nodes' | Out-Null

Invoke-WebRequest -UseBasicParsing 'https://github.com/chenpipi0807/ComfyUI-Index-TTS/archive/refs/heads/main.zip' -OutFile "$env:TEMP\ComfyUI-Index-TTS-main.zip"
Expand-Archive -LiteralPath "$env:TEMP\ComfyUI-Index-TTS-main.zip" -DestinationPath "$env:TEMP" -Force
Move-Item -LiteralPath "$env:TEMP\ComfyUI-Index-TTS-main" -Destination 'E:\comfyui\comfyui\custom_nodes\ComfyUI-Index-TTS' -Force

Invoke-WebRequest -UseBasicParsing 'https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite/archive/refs/heads/main.zip' -OutFile "$env:TEMP\ComfyUI-VideoHelperSuite-main.zip"
Expand-Archive -LiteralPath "$env:TEMP\ComfyUI-VideoHelperSuite-main.zip" -DestinationPath "$env:TEMP" -Force
Move-Item -LiteralPath "$env:TEMP\ComfyUI-VideoHelperSuite-main" -Destination 'E:\comfyui\comfyui\custom_nodes\ComfyUI-VideoHelperSuite' -Force
```

如果 `github.com` 大 ZIP 下载不稳定，可改用 `codeload`：

```powershell
Invoke-WebRequest -UseBasicParsing 'https://codeload.github.com/chenpipi0807/ComfyUI-Index-TTS/zip/refs/heads/main' -OutFile "$env:TEMP\ComfyUI-Index-TTS-main.zip"
```

### 6.4 安装 Python 包

```powershell
& 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -m pip install imageio-ffmpeg librosa soundfile omegaconf modelscope json5 munch ffmpy docstring-parser wetext

& 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -m pip install 'C:\Users\ai\AppData\Local\Temp\descript-audiotools-0.7.4.zip'
```

说明：

- 若 `descript-audiotools==0.7.4` 在当前镜像索引中不存在，可从上游源码 ZIP 安装。
- Windows 下 `pynini` 与 `WeTextProcessing` 不是当前工作流的硬性前置项。

## 7. 安装完成后的验证命令

### 7.1 验证关键模型文件

```powershell
Get-ChildItem 'E:\comfyui\comfyui\models\IndexTTS-2' -Recurse |
Where-Object {
    $_.Name -in @(
        'gpt.pth',
        's2mel.pth',
        'bpe.model',
        'campplus_cn_common.bin',
        'wav2vec2bert_stats.pt',
        'model.safetensors',
        'config.yaml'
    )
} |
Select-Object FullName,Length
```

### 7.2 验证节点是否已注册

重启 ComfyUI 后执行：

```powershell
$resp = Invoke-RestMethod 'http://127.0.0.1:8000/object_info'
@('PrimitiveStringMultiline', 'VHS_LoadAudioUpload', 'IndexTTS2BaseNode', 'SaveAudioMP3') |
ForEach-Object {
    if ($resp.PSObject.Properties.Name -contains $_) {
        "FOUND`t$_"
    } else {
        "MISSING`t$_"
    }
}
```

预期结果：

- `VHS_LoadAudioUpload` 显示为 `FOUND`
- `IndexTTS2BaseNode` 显示为 `FOUND`
- 内置节点也应显示为 `FOUND`

### 7.3 本机实测冷启动结果

本机于 `2026-04-20` 使用当前 ComfyUI Python 环境做过冷启动验证，日志显示：

- `ComfyUI-VideoHelperSuite` 成功导入
- `ComfyUI-Index-TTS` 成功导入
- `Import times for custom nodes` 中已出现以上两个目录

## 8. 常见问题

### 8.1 打开工作流时提示缺少 `IndexTTS2BaseNode`

- 原因：`ComfyUI-Index-TTS` 未安装，或安装后未重启 ComfyUI。
- 处理：
  - 检查 `E:\comfyui\comfyui\custom_nodes\ComfyUI-Index-TTS` 是否存在。
  - 检查依赖包是否装到了 `C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe`。
  - 完全退出 ComfyUI 再重新启动。

### 8.2 打开工作流时提示缺少 `VHS_LoadAudioUpload`

- 原因：`ComfyUI-VideoHelperSuite` 未安装，或安装后未重启 ComfyUI。
- 处理：
  - 检查 `E:\comfyui\comfyui\custom_nodes\ComfyUI-VideoHelperSuite` 是否存在。
  - 检查 `opencv-python`、`imageio-ffmpeg` 是否安装完成。
  - 重启后执行 `object_info` 验证。

### 8.3 工作流不再报缺节点，但运行时报模型缺失

- 原因：`IndexTTS-2` 目录不完整，常见缺项为：
  - `campplus_cn_common.bin`
  - `semantic_codec/model.safetensors`
  - `w2v-bert-2.0/`
  - `bigvgan/bigvgan_v2_22khz_80band_256x/`
- 处理：
  - 逐项核对第 7.1 节的文件清单。
  - 缺什么补什么，不要只下载主仓库后就停止。

### 8.4 安装到了错误的 Python 环境

- 现象：插件目录存在，但 ComfyUI 仍提示节点缺失或导入失败。
- 处理：
  - 以 ComfyUI 启动日志中的 `** Python executable:` 为准。
  - 确认所有 `pip install` 命令都使用同一条 Python 路径。

### 8.5 `GitHub ZIP` 下载中断或损坏

- 现象：ZIP 无法解压，或提示压缩包损坏。
- 处理：
  - 先重新检查 `ModelScope` 是否已有可用镜像。
  - 若仍无镜像，重试 GitHub ZIP。
  - 对于 `ComfyUI-Index-TTS`，可优先改用 `codeload` 地址。

### 8.6 运行期出现 `transformers` 兼容错误

- 当前情况：本机冷启动导入已通过，但这不等于所有推理路径都完全验证完毕。
- 处理建议：
  - 若推理时出现 `transformers` API 报错，可先尝试：
    - `& 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -m pip install 'transformers==4.54.1'`
  - 之后重启 ComfyUI 再次验证。

## 9. 维护要求

- 后续若本工作流新增节点、模型或系统依赖，必须同步更新本文件。
- 若后续在 `ModelScope` 找到可用官方或稳定镜像，应把 `ModelScope` 地址补回本文件，并将其提升为主下载源。
- 只有在下载、安装、重启、验证全部通过后，才能将依赖标记为已完成。

## 10. 参考来源

- `ComfyUI-Index-TTS`：`https://github.com/chenpipi0807/ComfyUI-Index-TTS`
- `ComfyUI-VideoHelperSuite`：`https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite`
- `IndexTeam/IndexTTS-2`：`https://modelscope.cn/models/IndexTeam/IndexTTS-2`
- `iic/speech_campplus_sv_zh-cn_16k-common`：`https://modelscope.cn/models/iic/speech_campplus_sv_zh-cn_16k-common`
