# ComfyUI-Pixelle-Release-Protocol

提供 Pixelle 标准的健康检查和内存释放接口，支持多种 TTS/图像插件。

## 功能

- 统一接口：`GET /pixelle/health`、`POST /pixelle/free`
- 自动检测并集成：
  - OmniVoice TTS
  - GGUF 图像模型
  - IndexTTS2

## 安装（推荐）

在 Pixelle 项目根目录运行：

```bash
cd d:\demo1\Pixelle\Pixelle
python tools/install_pixelle_release_protocol.py --custom-nodes "E:\ComfyUIData\custom_nodes"
```

或者手动创建符号链接：

```powershell
# PowerShell
New-Item -ItemType Junction -Path "E:\ComfyUIData\custom_nodes\ComfyUI-Pixelle-Release-Protocol" -Target "d:\demo1\Pixelle\Pixelle\tools\comfyui\custom_nodes\ComfyUI-Pixelle-Release-Protocol"
```

然后**重启 ComfyUI**。

## 接口

### 健康检查

```bash
GET /pixelle/health
```

### 释放内存

```bash
POST /pixelle/free
```

### 各插件独立接口

- `GET /pixelle/omnivoice/health`
- `POST /pixelle/omnivoice/free`
- `GET /pixelle/gguf/health`
- `POST /pixelle/gguf/free`
- `GET /pixelle/indextts2/health`
- `POST /pixelle/indextts2/free`
