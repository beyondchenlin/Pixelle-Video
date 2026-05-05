# OmniVoice Longform TTS 依赖与下载说明

## 1. 对应工作流路径

- 工作流路径：`workflows/selfhost/tts_omnivoice_longform_bf16.json`
- 工作流用途：在本地 ComfyUI 中调用 OmniVoice 长文本语音合成节点，生成高质量音频。
- 适用场景：Pixelle 长文本语音合成，支持长段落连续生成，无需手动分割文本。

## 2. 节点与依赖清单

- `PrimitiveStringMultiline`：文本输入节点。
- `VHS_LoadAudioUpload`：参考音频上传加载节点，来自 `ComfyUI-VideoHelperSuite`。
- `OmniVoiceLongformTTS`：OmniVoice 长文本 TTS 推理节点，来自 ComfyUI-OmniVoice 插件。
- `SaveAudio`：ComfyUI 内置音频保存节点，输出 FLAC。

## 3. 依赖分类

- 模型文件：`OmniVoice-bf16` 等 OmniVoice 模型。
- 插件：`ComfyUI-OmniVoice`（或其他提供 OmniVoice 节点的插件）、`ComfyUI-VideoHelperSuite`。
- Python 包：`torch`、`torchaudio`、`transformers`、`accelerate`、`safetensors`、`huggingface_hub`、`soundfile`、`librosa` 等。
- 系统工具：Windows 下建议安装 Visual Studio C++ Build Tools。

## 4. 目标目录

- ComfyUI 模型目录（根据 OmniVoice 插件配置而定，通常为 ComfyUI 的 models 目录下的子目录）
- 当前机器插件目录：`E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice`（以实际路径为准）
- ComfyUI 输入目录：`E:\comfyui-venv\input`
- 默认参考音频：`E:\comfyui-venv\input\ref_audio.wav`

如果本机 ComfyUI 目录不同，应把命令中的路径替换为实际路径。

## 5. 下载优先级

根据仓库规则，模型文件默认优先使用 `ModelScope`。只有 `ModelScope` 缺少所需文件或不可用时，才回退到其他来源。

## 6. 安装命令

### 6.1 安装 OmniVoice 插件

OmniVoice 插件需要从对应的 GitHub 或其他来源克隆安装：

```powershell
# 进入 ComfyUI custom_nodes 目录
cd E:\ComfyUIData\custom_nodes

# 克隆 OmniVoice 插件（请以实际插件仓库地址为准）
git clone https://github.com/example/ComfyUI-OmniVoice.git

# 安装依赖
cd ComfyUI-OmniVoice
pip install -r requirements.txt
```

### 6.2 Pixelle 显存释放补丁

**重要：如果不安装此补丁，Pixelle 无法正确释放 OmniVoice 占用的 GPU 显存，会导致阶段切换时抛出异常。**

`tools/patch_omnivoice_plugin.py` 会为 ComfyUI-OmniVoice 安装 `POST /pixelle/omnivoice/free` 端点，用于释放插件私有的 OmniVoice PyTorch 缓存。这个端点解决的是 ComfyUI 标准 `/free` 管不到的插件全局模型缓存。

执行补丁：

```powershell
python tools\patch_omnivoice_plugin.py --target E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice
```

或者设置环境变量后执行：

```powershell
$env:OMNIVOICE_PLUGIN_DIR = "E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice"
python tools\patch_omnivoice_plugin.py
```

验证端点文件已安装：

```powershell
Test-Path E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice\pixelle_routes.py
Select-String -Path E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice\pixelle_routes.py -Pattern "/pixelle/omnivoice/free"
```

补丁后需要**重启 ComfyUI**。重启后可验证 HTTP 端点：

```powershell
# 健康检查
Invoke-RestMethod -Uri http://127.0.0.1:8002/pixelle/omnivoice/health

# 显存释放
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8002/pixelle/omnivoice/free
```

Pixelle 的 `model_cleanup_mode: comfyui_and_extensions` 会先调用 ComfyUI `/free`，再调用 `/pixelle/omnivoice/free`，同时覆盖标准模型和 OmniVoice 插件私有缓存。

## 7. 验证命令

### 验证补丁脚本

```powershell
# 验证补丁脚本存在
Test-Path tools\patch_omnivoice_plugin.py

# 验证脚本内容正确
Select-String -Path tools\patch_omnivoice_plugin.py -Pattern "/pixelle/omnivoice/free"
Select-String -Path tools\patch_omnivoice_plugin.py -Pattern "OMNIVOICE_PLUGIN_DIR"
```

### 验证端点响应格式

补丁安装后，端点应返回如下格式的 JSON：

健康检查 (`/pixelle/omnivoice/health`)：
```json
{
  "protocol_version": 2,
  "contract_revision": 1,
  "ok": true,
  "extension": "omnivoice",
  "release_endpoint": "/pixelle/omnivoice/free",
  "safe_to_continue": true,
  "objects_seen": [],
  "residual_objects": [],
  "errors": [],
  "cuda_allocated": 0,
  "cuda_reserved": 0
}
```

释放端点 (`/pixelle/omnivoice/free`)：
```json
{
  "protocol_version": 2,
  "contract_revision": 1,
  "extension": "omnivoice",
  "released": true,
  "safe_to_continue": true,
  "release_confirmation_reason": "omnivoice_objects_released",
  "objects_seen": [],
  "objects_released": [],
  "diagnostic_objects": [],
  "residual_objects": [],
  "errors": [],
  "cuda_allocated_before": 1000000000,
  "cuda_allocated_after": 100000000,
  "cuda_reserved_before": 1500000000,
  "cuda_reserved_after": 500000000
}
```

## 8. 常见问题

### Q: 为什么会出现 "ComfyUI post-workflow memory release was not confirmed" 错误？

A: 这是因为 OmniVoice 插件没有安装 Pixelle 的显存释放补丁。ComfyUI 标准 `/free` 端点无法释放插件私有的 PyTorch 模型缓存，导致 Pixelle 无法确认显存已释放。

**解决方案**：执行 `python tools\patch_omnivoice_plugin.py --target <插件目录>` 安装补丁，然后重启 ComfyUI。

### Q: 补丁执行后需要重启 ComfyUI 吗？

A: 是的，补丁修改了插件文件，必须重启 ComfyUI 才能使新的 HTTP 端点生效。

### Q: 如何确认补丁已正确安装？

A: 执行以下 PowerShell 命令验证：

```powershell
# 验证文件存在
Test-Path E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice\pixelle_routes.py

# 验证端点已注册
Select-String -Path E:\ComfyUIData\custom_nodes\ComfyUI-OmniVoice\pixelle_routes.py -Pattern "/pixelle/omnivoice/free"

# 验证 HTTP 端点可访问（ComfyUI 启动后）
Invoke-RestMethod -Uri http://127.0.0.1:8002/pixelle/omnivoice/health
```

### Q: 如果 OmniVoice 插件不是 ComfyUI-OmniVoice，而是其他名称？

A: 请将 `--target` 参数指向实际的 OmniVoice 插件目录。补丁脚本会检测插件的 `__init__.py` 文件并在同级目录创建 `pixelle_routes.py`。

## 9. 相关文件

- 补丁脚本：`tools/patch_omnivoice_plugin.py`
- 工作流：`workflows/selfhost/tts_omnivoice_longform_bf16.json`
- 测试文件：`tests/test_patch_omnivoice_plugin.py`
- Pixelle 维护客户端：`pixelle_video/services/comfyui_maintenance.py`
