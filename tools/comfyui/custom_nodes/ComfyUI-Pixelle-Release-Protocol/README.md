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

### 统一能力发现（推荐）

```bash
GET /pixelle/health
```

该接口只返回协议和扩展能力，不扫描模型对象、不读取显存，也不释放资源。
Pixelle 会优先使用这个接口，避免在后端繁忙时被旧版扩展健康检查阻塞。

### 释放内存

```bash
POST /pixelle/free
Content-Type: application/json

{"extensions": ["omnivoice"]}
```

请求只释放明确列出的扩展，禁止无关扩展和其他客户端的模型被连带卸载。

### 旧版独立接口

- `GET /pixelle/omnivoice/health`
- `POST /pixelle/omnivoice/free`
- `GET /pixelle/gguf/health`
- `POST /pixelle/gguf/free`
- `GET /pixelle/indextts2/health`
- `POST /pixelle/indextts2/free`

这些接口由历史修补版本提供。统一插件不重复注册它们，以免旧修补文件尚未
清理时发生路由冲突。新客户端先使用统一接口，仅在连接旧后端时回退到这些
接口。插件更新后必须重启 ComfyUI 才会载入新契约。
