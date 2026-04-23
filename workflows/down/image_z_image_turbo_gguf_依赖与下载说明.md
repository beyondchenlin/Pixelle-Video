# image_z_image_turbo_gguf 依赖与下载说明

## 1. 对应工作流路径

- 工作流文件：`workflows/selfhost/image_z_image_turbo_gguf.json`
- 工作流类型：`selfhost` 本地 ComfyUI 文生图工作流
- 输入参数：
  - `prompt`：必填，正向提示词
  - `width`：可选，默认 `960`
  - `height`：可选，默认 `1280`

## 2. 节点与依赖清单

### 2.1 核心节点

- `UnetLoaderGGUF`
- `CLIPLoaderGGUF`
- `VAELoader`
- `PrimitiveStringMultiline`
- `CLIPTextEncode`
- `ConditioningZeroOut`
- `EmptySD3LatentImage`
- `ModelSamplingAuraFlow`
- `KSampler`
- `VAEDecode`
- `SaveImage`

### 2.2 依赖分类

| 分类 | 依赖 | 作用 |
|---|---|---|
| 自定义节点插件 | `ComfyUI-GGUF` | 提供 `UnetLoaderGGUF`、`CLIPLoaderGGUF` |
| Python 包 | `gguf`、`sentencepiece`、`protobuf` | GGUF 模型读取与分词依赖 |
| 主模型 | `z-image-turbo-Q8_0.gguf` | `Z-Image-Turbo` GGUF 主扩散模型 |
| 文本编码器 | `Qwen3-4B-Q8_0.gguf` | `Z-Image-Turbo` GGUF 版文本编码器 |
| VAE | `ae.safetensors` | `latent` 与图像之间的编解码 |

## 3. 目标目录

| 依赖 | 目标目录 |
|---|---|
| `z-image-turbo-Q8_0.gguf` | `ComfyUI/models/unet/` |
| `Qwen3-4B-Q8_0.gguf` | `ComfyUI/models/text_encoders/` |
| `ae.safetensors` | `ComfyUI/models/vae/` |
| `ComfyUI-GGUF` 插件 | `ComfyUI/custom_nodes/ComfyUI-GGUF/` |

## 4. 下载优先级

1. 默认优先 `ModelScope`
2. 仅在 `ModelScope` 缺失或不可用时，回退到 `Hugging Face` / `GitHub`

## 5. ModelScope 检索或主地址

### 5.1 GGUF 主模型

- 页面：`https://www.modelscope.cn/models/unsloth/Z-Image-Turbo-GGUF/files`
- 文件：`z-image-turbo-Q8_0.gguf`

### 5.2 GGUF 文本编码器

- 页面：`https://www.modelscope.cn/models/unsloth/Qwen3-4B-GGUF/files`
- 文件：`Qwen3-4B-Q8_0.gguf`

### 5.3 VAE

- 页面：`https://www.modelscope.cn/models/Comfy-Org/z_image/tree/master/split_files/vae`
- 文件：`ae.safetensors`

### 5.4 参考的原版 BF16 工作流模型页

- 页面：`https://www.modelscope.cn/models/Comfy-Org/z_image_turbo/tree/master/split_files/diffusion_models`
- 说明：这是仓库现有 `image_z_image_turbo.json` 对应的 BF16 / NVFP4 主模型来源，不是当前 GGUF 工作流的主模型来源

### 5.5 插件

- 页面：`https://github.com/city96/ComfyUI-GGUF`

## 6. 备用地址

### 6.1 GGUF 主模型备用地址

- `https://huggingface.co/unsloth/Z-Image-Turbo-GGUF/tree/main`

### 6.2 GGUF 文本编码器备用地址

- `https://huggingface.co/unsloth/Qwen3-4B-GGUF/tree/main`

### 6.3 VAE 备用地址

- `https://huggingface.co/Comfy-Org/z_image/tree/main/split_files/vae`

## 7. 安装命令

### 7.1 安装 GGUF 插件

```powershell
git clone https://github.com/city96/ComfyUI-GGUF.git ComfyUI\custom_nodes\ComfyUI-GGUF
```

### 7.2 安装 GGUF Python 依赖

```powershell
python -m pip install -U gguf sentencepiece protobuf
```

### 7.3 使用 ModelScope 下载模型

```powershell
modelscope download --model unsloth/Z-Image-Turbo-GGUF --local_dir "ComfyUI\models\unet" "z-image-turbo-Q8_0.gguf"
modelscope download --model unsloth/Qwen3-4B-GGUF --local_dir "ComfyUI\models\text_encoders" "Qwen3-4B-Q8_0.gguf"
modelscope download --model Comfy-Org/z_image --local_dir "ComfyUI\models\vae" "split_files/vae/ae.safetensors"
```

## 8. 验证命令

### 8.1 检查本地文件是否存在

```powershell
Get-Item `
  "ComfyUI\models\unet\z-image-turbo-Q8_0.gguf", `
  "ComfyUI\models\text_encoders\Qwen3-4B-Q8_0.gguf", `
  "ComfyUI\models\vae\ae.safetensors"
```

### 8.2 检查文件大小是否合理

```powershell
Get-Item `
  "ComfyUI\models\unet\z-image-turbo-Q8_0.gguf", `
  "ComfyUI\models\text_encoders\Qwen3-4B-Q8_0.gguf", `
  "ComfyUI\models\vae\ae.safetensors" |
  Select-Object Name, Length
```

参考大小：

- `z-image-turbo-Q8_0.gguf`：`7224707136`
- `Qwen3-4B-Q8_0.gguf`：`4280405792`
- `ae.safetensors`：`335304388`

### 8.3 检查本机节点是否支持该工作流

```powershell
rg -n "UnetLoaderGGUF|CLIPLoaderGGUF" "ComfyUI"
```

### 8.4 检查仓库中的工作流参数映射

```powershell
.venv\Scripts\python.exe -m pytest tests/test_selfhost_workflows.py -k z_image_turbo_gguf -v
```

## 9. 已验证结果

以下项目已在 `2026-04-23` 实际验证通过：

- `ModelScope` 页面可访问：
  - `https://www.modelscope.cn/models/unsloth/Z-Image-Turbo-GGUF/files`
  - `https://www.modelscope.cn/models/unsloth/Qwen3-4B-GGUF/files`
  - `https://www.modelscope.cn/models/Comfy-Org/z_image/tree/master/split_files/vae`
  - `https://www.modelscope.cn/models/Comfy-Org/z_image_turbo/tree/master/split_files/diffusion_models`
- 备用地址可访问：
  - `https://huggingface.co/unsloth/Z-Image-Turbo-GGUF/tree/main`
  - `https://huggingface.co/unsloth/Qwen3-4B-GGUF/tree/main`
  - `https://huggingface.co/Comfy-Org/z_image/tree/main/split_files/vae`
- 插件源可访问：
  - `https://github.com/city96/ComfyUI-GGUF`
- 本机 `ComfyUI-GGUF` 插件目录已存在：
  - `E:\comfyui\comfyui\custom_nodes\ComfyUI-GGUF`

## 10. 常见问题

### 10.1 这个工作流和 `image_z_image_turbo.json` 的区别是什么？

- `image_z_image_turbo.json`：BF16 / NVFP4 版，主模型放在 `ComfyUI/models/diffusion_models/`
- `image_z_image_turbo_gguf.json`：GGUF 版，主模型放在 `ComfyUI/models/unet/`

它们的输入接口保持一致，都是：

- `prompt`
- `width`
- `height`

### 10.2 为什么这里还是用 `ae.safetensors`？

因为 `Z-Image-Turbo` 的 GGUF 版本只替换了主模型和文本编码器，VAE 仍然沿用现有 `z_image` / `z_image_turbo` 工作流使用的 `ae.safetensors`。

### 10.3 如果我想换成更小的量化怎么办？

可以直接把工作流里的文件名改成同一仓库里的其他量化版本，例如：

- `z-image-turbo-Q6_K.gguf`
- `z-image-turbo-Q4_K_M.gguf`
- `Qwen3-4B-Q6_K.gguf`
- `Qwen3-4B-Q4_K_M.gguf`

但要保证主模型和文本编码器的量化组合是你实际下载到本机的文件名。

### 10.4 为什么这个 GGUF 工作流可以像普通文生图一样使用？

因为它沿用了 `11.txt` / `z-image-turbo` 那套文生图结构：

- 只使用 `prompt`
- 用 `EmptySD3LatentImage` 生成空 `latent`
- 不需要上传参考图

所以它可以像现有 `image_z_image_turbo.json` 一样走项目当前的 prompt-only 图片生成链路。
