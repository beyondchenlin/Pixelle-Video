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
| Qwen 情绪分类模型 | `IndexTeam/IndexTTS-2` | `E:\comfyui\comfyui\models\IndexTTS-2\qwen0.6bemo4-merge` |
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
  - `PyYAML`
  - `huggingface_hub`
  - `safetensors`
  - `transformers`
  - `accelerate`
  - `descript-audiotools==0.7.4`
- `ComfyUI-VideoHelperSuite` 当前至少需要以下包：
  - `opencv-python`
  - `imageio-ffmpeg`
- 本机于 `2026-04-20` 的实际安装环境为：
  - `torch==2.10.0+cu130`
  - `torchaudio==2.10.0+cu130`
  - `transformers==5.0.0`
  - `accelerate==1.13.0`
  - `safetensors==0.7.0`
  - `descript-audiotools==0.7.4`
  - `opencv-python==4.13.0.92`
  - `imageio-ffmpeg==0.6.0`
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

说明：

- 第一条 `snapshot_download('IndexTeam/IndexTTS-2')` 会把 `IndexTTS-2` 仓库整体同步到本地，其中包含运行期会实际读取的 `qwen0.6bemo4-merge/` 子目录。
- 如果你之前是手动拷文件，或只保留了部分基础文件，请额外确认 `E:\comfyui\comfyui\models\IndexTTS-2\qwen0.6bemo4-merge\` 仍然存在。

### 6.3 安装自定义节点

优先检查 `ModelScope` 是否已有可用镜像；若仍无可用条目，再使用 GitHub ZIP 方式。

```powershell
$customNodesDir = 'E:\comfyui\comfyui\custom_nodes'
$indexTarget = Join-Path $customNodesDir 'ComfyUI-Index-TTS'
$videoTarget = Join-Path $customNodesDir 'ComfyUI-VideoHelperSuite'

New-Item -ItemType Directory -Force $customNodesDir | Out-Null

Invoke-WebRequest -UseBasicParsing 'https://github.com/chenpipi0807/ComfyUI-Index-TTS/archive/refs/heads/main.zip' -OutFile "$env:TEMP\ComfyUI-Index-TTS-main.zip"
Expand-Archive -LiteralPath "$env:TEMP\ComfyUI-Index-TTS-main.zip" -DestinationPath "$env:TEMP" -Force
if (Test-Path $indexTarget) { Remove-Item -LiteralPath $indexTarget -Recurse -Force }
Move-Item -LiteralPath "$env:TEMP\ComfyUI-Index-TTS-main" -Destination $indexTarget

Invoke-WebRequest -UseBasicParsing 'https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite/archive/refs/heads/main.zip' -OutFile "$env:TEMP\ComfyUI-VideoHelperSuite-main.zip"
Expand-Archive -LiteralPath "$env:TEMP\ComfyUI-VideoHelperSuite-main.zip" -DestinationPath "$env:TEMP" -Force
if (Test-Path $videoTarget) { Remove-Item -LiteralPath $videoTarget -Recurse -Force }
Move-Item -LiteralPath "$env:TEMP\ComfyUI-VideoHelperSuite-main" -Destination $videoTarget
```

如果 `github.com` 大 ZIP 下载不稳定，可改用 `codeload`：

```powershell
Invoke-WebRequest -UseBasicParsing 'https://codeload.github.com/chenpipi0807/ComfyUI-Index-TTS/zip/refs/heads/main' -OutFile "$env:TEMP\ComfyUI-Index-TTS-main.zip"
```

### 6.4 安装 Python 包

```powershell
& 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -m pip install opencv-python imageio-ffmpeg librosa soundfile omegaconf modelscope json5 munch einops ffmpy docstring-parser wetext PyYAML huggingface_hub safetensors 'transformers==5.0.0' accelerate

& 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -m pip install 'git+https://github.com/descriptinc/audiotools@0.7.4#egg=descript-audiotools'
```

说明：

- 上面先补齐 `ComfyUI-Index-TTS` 与 `ComfyUI-VideoHelperSuite` 的关键 Python 依赖，避免只装了一部分导致节点仍然导入失败。
- `ComfyUI-Index-TTS` 的情绪分类模型会通过 `AutoModelForCausalLM.from_pretrained(..., device_map=\"auto\")` 加载 Qwen 子模型；当前 `transformers` 路径下这会额外依赖 `accelerate`。
- 当前机器实测的 pip 镜像索引只提供 `descript-audiotools` 的 `0.7.1`、`0.7.2`，不提供 `0.7.4`，因此需要按插件上游 `requirements.txt` 的写法从 Git 源安装 `0.7.4`。
- 若当前机器的临时目录中已经存在 `C:\Users\ai\AppData\Local\Temp\descript-audiotools-0.7.4.zip`，也可改为安装该本地 ZIP。
- Windows 下 `pynini` 与 `WeTextProcessing` 不是当前工作流的硬性前置项。

### 6.5 准备参考音频

- 当前仓库版 `workflows/selfhost/tts_index2.json` 默认读取 `C:\Users\ai\Documents\ComfyUI\input\ref_audio.wav`。
- 如果该文件不存在，工作流虽然能加载节点，但 `VHS_LoadAudioUpload` 会直接报 `Invalid file path`。
- 运行前请确保：
  - `C:\Users\ai\Documents\ComfyUI\input\` 目录下存在 `ref_audio.wav`
  - 或者在 `VHS_LoadAudioUpload` 节点面板里手动改选一个已经存在的 `.wav` / `.mp3` 文件

## 7. 安装完成后的验证命令

### 7.1 验证关键模型文件与目录

```powershell
Get-ChildItem 'E:\comfyui\comfyui\models\IndexTTS-2' -Recurse |
Where-Object {
    $_.Name -in @(
        'gpt.pth',
        's2mel.pth',
        'bpe.model',
        'campplus_cn_common.bin',
        'wav2vec2bert_stats.pt',
        'qwen0.6bemo4-merge',
        'w2v-bert-2.0',
        'bigvgan_v2_22khz_80band_256x',
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
  - `qwen0.6bemo4-merge/`
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

### 8.7 `VHS_LoadAudioUpload` 提示 `Invalid file path`

- 现象：工作流已能加载节点，但右侧错误面板提示：
  - `audio - Invalid file path: C:\Users\ai\Documents\ComfyUI\input\...`
- 原因：
  - `VHS_LoadAudioUpload` 只能从 `ComfyUI/input/` 目录读取本地音频；
  - 工作流中的默认文件名在当前机器上不存在时，就会直接校验失败。
- 处理：
  - 把参考音频放到 `C:\Users\ai\Documents\ComfyUI\input\` 目录；
  - 或在节点面板里重新选择一个已经存在的 `.wav` / `.mp3` 文件；
  - 当前仓库版 `workflows/selfhost/tts_index2.json` 默认文件名已改为 `ref_audio.wav`，建议保持该文件位于 `ComfyUI/input/` 下。

### 8.8 运行时提示 `requires accelerate`

- 现象：执行 `IndexTTS2BaseNode` 时，堆栈里出现：
  - `ValueError: Using a device_map ... requires accelerate`
- 原因：
  - `ComfyUI-Index-TTS` 会在情绪分类分支加载 `qwen0.6bemo4-merge`；
  - 这条加载路径使用了 `device_map="auto"`，在当前 `transformers` 环境下必须额外安装 `accelerate`。
- 处理：
  - 在 ComfyUI 实际使用的 Python 环境中执行：
  - `& 'C:\Users\ai\Documents\ComfyUI\.venv\Scripts\python.exe' -m pip install accelerate`
  - 安装后重启 ComfyUI，再重新运行工作流。

### 8.9 每次运行都重新加载 `IndexTTS-2` 全套模型，导致重复等待

- 现象：
  - 每次执行工作流时，日志都会重复出现：
  - `>> GPT weights restored from: ...`
  - `Loading w2v-bert-2.0 from local path: ...`
  - `>> bigvgan weights restored from: ...`
- 原因：
  - `ComfyUI-Index-TTS` 默认允许在单次调用结束后卸载 TTS 模型；
  - 如果工作流没有显式连接 `IndexTTS2CacheControlNode`，就会在每次执行后触发 `unload_tts()`，下一次只能整套重载。
- 处理：
  - 当前仓库版 `workflows/selfhost/tts_index2.json` 已显式接入 `IndexTTS2CacheControlNode`，并将 `keep_models_cached` 设为 `true`；
  - 修改后首次执行仍需完整加载模型，后续重复执行同一工作流时应避免再次整套重载；
  - 如果你手动改过工作流，请确认 `IndexTTS2BaseNode` 的 `cache_control` 输入已连接到 `IndexTTS2CacheControlNode`。

## 9. 维护要求

- 后续若本工作流新增节点、模型或系统依赖，必须同步更新本文件。
- 若后续在 `ModelScope` 找到可用官方或稳定镜像，应把 `ModelScope` 地址补回本文件，并将其提升为主下载源。
- 只有在下载、安装、重启、验证全部通过后，才能将依赖标记为已完成。

## 10. 参考来源

- `ComfyUI-Index-TTS`：`https://github.com/chenpipi0807/ComfyUI-Index-TTS`
- `ComfyUI-VideoHelperSuite`：`https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite`
- `IndexTeam/IndexTTS-2`：`https://modelscope.cn/models/IndexTeam/IndexTTS-2`
- `iic/speech_campplus_sv_zh-cn_16k-common`：`https://modelscope.cn/models/iic/speech_campplus_sv_zh-cn_16k-common`
