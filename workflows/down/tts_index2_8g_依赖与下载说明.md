# IndexTTS2 8G 低显存版依赖与下载说明

## 1. 对应工作流路径

- 工作流路径：`workflows/selfhost/tts_index2_8g.json`
- 工作流用途：在本地 ComfyUI 中调用 `ComfyUI-Index-TTS` 的 `IndexTTS2BaseNode` 生成语音，并通过 `SaveAudio` 保存为 FLAC 音频。
- 适用场景：Pixelle 已经在进入 ComfyUI 前完成长段落分割，单次传入 ComfyUI 的文本较短；模型在长文案任务内保持缓存，避免每段重载。

## 2. 节点与依赖清单

- `PrimitiveStringMultiline`：文本输入节点。
- `VHS_LoadAudioUpload`：参考音频上传加载节点，来自 `ComfyUI-VideoHelperSuite`。
- `IndexTTS2BaseNode`：IndexTTS2 基础推理节点，来自 `ComfyUI-Index-TTS`。
- `IndexTTS2CacheControlNode`：IndexTTS2 模型缓存控制节点，来自 `ComfyUI-Index-TTS`。
- `SaveAudio`：ComfyUI 内置音频保存节点，输出 FLAC。

## 3. 依赖分类

- 模型文件：与 `workflows/selfhost/tts_index2.json` 共用 `IndexTTS-2` 模型目录，不新增模型。
- 插件：`ComfyUI-Index-TTS`、`ComfyUI-VideoHelperSuite`。
- Python 包：`torch`、`torchaudio`、`transformers`、`deepspeed`、`accelerate`、`safetensors`、`huggingface_hub`、`tokenizers`、`omegaconf`、`soundfile`、`librosa`。
- 系统工具：Windows 下建议安装 Visual Studio C++ Build Tools；如需要 DeepSpeed 或 CUDA 扩展，需匹配当前 CUDA/PyTorch 环境。

## 4. 目标目录

- ComfyUI 模型目录：`E:\comfyui\comfyui\models\IndexTTS-2`
- 当前机器插件目录：`E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS`
- ComfyUI 输入目录：`E:\comfyui-venv\input`
- 默认参考音频：`E:\comfyui-venv\input\ref_audio.wav`

如果本机 ComfyUI 目录不同，应把命令中的路径替换为实际路径。

## 5. 下载优先级

根据仓库规则，模型文件默认优先使用 `ModelScope`。只有 `ModelScope` 缺少所需文件或不可用时，才回退到其他来源。

本工作流不新增模型下载项，沿用默认 IndexTTS2 工作流的模型集合。

## 6. ModelScope 检索与主地址

截至 `2026-04-30`，本机实际验证结果如下：

- `IndexTeam/IndexTTS-2`
  - ModelScope 主地址：`https://www.modelscope.cn/models/IndexTeam/IndexTTS-2`
  - 文件 API：`https://www.modelscope.cn/api/v1/models/IndexTeam/IndexTTS-2/repo/files?Revision=master&Recursive=true`
  - 验证结果：主页面 `HEAD 200`，文件 API `200`。
- `amphion/MaskGCT`
  - ModelScope 主地址：`https://www.modelscope.cn/models/amphion/MaskGCT`
  - 验证结果：主页面 `HEAD 200`。
- `facebook/w2v-bert-2.0`
  - ModelScope 主地址：`https://www.modelscope.cn/models/facebook/w2v-bert-2.0`
  - 验证结果：主页面 `HEAD 200`。
- `funasr/campplus`
  - ModelScope 文件 API 本次验证返回 `404`，当前不作为主来源。
  - 备用地址：`https://huggingface.co/funasr/campplus`，本次验证 `HEAD 200`。
- `nvidia/bigvgan_v2_22khz_80band_256x`
  - ModelScope 文件 API 本次验证返回 `404`，当前不作为主来源。
  - 备用地址：`https://huggingface.co/nvidia/bigvgan_v2_22khz_80band_256x`，本次验证 `HEAD 200`。

## 7. 安装命令

模型下载仍使用默认 IndexTTS2 说明中的命令。若需要重新安装模型，可执行：

```powershell
$ModelRoot = "E:\comfyui\comfyui\models\IndexTTS-2"
New-Item -ItemType Directory -Force -Path $ModelRoot | Out-Null

modelscope download --model IndexTeam/IndexTTS-2 --local_dir $ModelRoot
modelscope download --model amphion/MaskGCT --local_dir $ModelRoot
modelscope download --model facebook/w2v-bert-2.0 --local_dir (Join-Path $ModelRoot "w2v-bert-2.0")
```

插件补丁必须通过仓库脚本应用，确保 `max_tokens_per_sentence` 能从 ComfyUI 工作流正确传到底层 `infer_v2.py`：

```powershell
python tools\patch_indextts2_plugin.py --target E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS
```

### Pixelle 显存释放补丁

`tools/patch_indextts2_plugin.py` 还会为 `ComfyUI-Index-TTS` 安装 `POST /pixelle/indextts2/free` 端点，用于释放插件私有的 IndexTTS2 PyTorch 缓存。这个端点解决的是 ComfyUI 标准 `/free` 管不到的插件全局 loader/cache；它不要求关闭工作流里的 `keep_models_cached`，因此批次内仍可复用模型，批次结束或恢复路径再释放。

执行补丁：

```powershell
python tools\patch_indextts2_plugin.py --target E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS
```

验证端点文件已安装：

```powershell
Test-Path E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS\pixelle_routes.py
Select-String -Path E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS\pixelle_routes.py -Pattern "/pixelle/indextts2/free"
```

补丁后需要重启 ComfyUI。重启后可验证 HTTP 端点：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/pixelle/indextts2/free
```

Pixelle 的 `model_cleanup_mode: comfyui_and_extensions` 会先调用 ComfyUI `/free`，再调用 `/pixelle/indextts2/free`，同时覆盖 z-image 这类标准模型和 IndexTTS2 插件私有缓存。

## 8. 8G 版关键参数

`workflows/selfhost/tts_index2_8g.json` 相对默认版的主要变化：

- `num_beams = 1`
- `top_k = 20`
- `max_mel_tokens = 800`
- `max_tokens_per_sentence = 60`
- `keep_models_cached = true`
- 输出前缀：`audio/ComfyUI_8g`

这些参数假设 Pixelle 已经先做长段落分割，不需要 ComfyUI 单次处理超长文本。8G 版通过降低单次推理峰值来控制显存，而不是通过每段生成后卸载模型来控制显存。

## 9. 验证命令

验证仓库补丁脚本与工作流结构：

```powershell
uv run pytest tests\test_patch_indextts2_plugin.py tests\test_selfhost_workflows.py -q
```

验证当前安装的插件是否已被补丁修复：

```powershell
Select-String -Path "E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS\indextts2\infer.py" `
  -Pattern "max_text_tokens_per_sentence|max_text_tokens_per_segment"
```

期望看到 `max_text_tokens_per_sentence`，不应再看到 `max_text_tokens_per_segment`。

验证工作流依赖输入：

```powershell
Test-Path "E:\comfyui-venv\input\ref_audio.wav"
Test-Path "E:\comfyui\comfyui\models\IndexTTS-2\gpt.pth"
Test-Path "E:\comfyui\comfyui\models\IndexTTS-2\s2mel.pth"
```

## 10. 常见问题

### 为什么不直接覆盖默认 `tts_index2.json`？

默认工作流偏质量和连续生成效率，8G 版偏低显存稳定性。两者并存可以按机器显存选择，也便于回退。

### 修插件会不会影响默认工作流？

会让工作流里的 `max_tokens_per_sentence` 真正生效。原版 `tts_index2.json` 配置为 `90`，8G 版 `tts_index2_8g.json` 配置为 `60`；修复后底层会按所选工作流参数分句，而不是回退到底层默认值。

### 为什么 8G 版开启 `keep_models_cached`？

Pixelle 的长文案流程会先切分文本，再连续调用 ComfyUI IndexTTS2 处理多个短段。开启缓存后，第一段加载模型，后续段复用已加载模型，速度更接近常驻 TTS 服务。显存峰值仍由 `num_beams = 1`、`top_k = 20`、`max_mel_tokens = 800`、`max_tokens_per_sentence = 60` 和 Pixelle 上游分段控制。

### 如果音频自然度下降怎么办？

先把 `max_mel_tokens` 从 `800` 调到 `900` 或 `1000`，再观察显存峰值。不要同时把 `num_beams` 调回 `3`，否则显存压力会明显增加。

### 如果仍然超过 8G 怎么办？

先确认补丁脚本已经应用到当前 ComfyUI 插件，然后把 `max_tokens_per_sentence` 降到 `50`，并确认 Pixelle 上游分段没有把过长文本传入 ComfyUI。
