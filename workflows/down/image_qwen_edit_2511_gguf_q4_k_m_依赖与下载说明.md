# image_qwen_edit_2511_gguf_q4_k_m 依赖与下载说明

## 1. 对应工作流路径

- 工作流文件：`workflows/selfhost/image_qwen_edit_2511_gguf_q4_k_m.json`
- 工作流类型：`selfhost` 本地 ComfyUI 图像编辑工作流
- 输入参数：
  - `prompt`：编辑指令
  - `image`：主图 / 待编辑图片
  - `image2`：参考图 / 材质或风格参考图
  - `seed`：可选，默认 `0`
  - `steps`：可选，默认 `4`
  - `cfg`：可选，默认 `1.0`

## 2. 节点与依赖清单

### 2.1 核心节点

- `UnetLoaderGGUF`
- `CLIPLoaderGGUF`
- `VAELoader`
- `LoraLoader`
- `ModelSamplingAuraFlow`
- `CFGNorm`
- `LoadImage`
- `FluxKontextImageScale`
- `TextEncodeQwenImageEditPlus`
- `ConditioningZeroOut`
- `FluxKontextMultiReferenceLatentMethod`
- `VAEEncodeTiled`
- `KSampler`
- `VAEDecodeTiled`
- `SaveImage`

### 2.2 依赖分类

| 分类 | 依赖 | 作用 |
|---|---|---|
| ComfyUI 核心 | `TextEncodeQwenImageEditPlus`、`FluxKontextMultiReferenceLatentMethod`、`CFGNorm` 等 | 提供 Qwen Edit 2511 的编辑编码与参考 latent 逻辑 |
| 自定义节点插件 | `ComfyUI-GGUF` | 提供 `UnetLoaderGGUF`、`CLIPLoaderGGUF` |
| 主模型 | `qwen-image-edit-2511-Q4_K_M.gguf` | Qwen Image Edit 2511 主扩散模型 |
| 文本编码器 | `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf` | GGUF 文本 / 视觉文本编码器 |
| 视觉投影 | `Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf` | Qwen2.5-VL 配套 `mmproj`，缺失时 GGUF 编辑链会损坏 |
| VAE | `qwen_image_vae.safetensors` | 编解码图像 latent |
| LoRA | `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` | 4 步加速 LoRA |

## 3. 目标目录

| 依赖 | 目标目录 |
|---|---|
| `qwen-image-edit-2511-Q4_K_M.gguf` | `ComfyUI/models/unet/` |
| `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf` | `ComfyUI/models/text_encoders/` |
| `Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf` | `ComfyUI/models/text_encoders/` |
| `qwen_image_vae.safetensors` | `ComfyUI/models/vae/` |
| `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` | `ComfyUI/models/loras/lightx2v/Qwen-Image-Edit-2511-Lightning/` |
| `ComfyUI-GGUF` 插件 | `ComfyUI/custom_nodes/ComfyUI-GGUF/` |

## 4. 下载优先级

1. 默认优先 `ModelScope`
2. 仅在 `ModelScope` 缺失或不可用时，回退到 Hugging Face / GitHub

## 5. ModelScope 主地址

### 5.1 主模型

- 页面：`https://www.modelscope.cn/models/unsloth/Qwen-Image-Edit-2511-GGUF/files`
- 文件：`qwen-image-edit-2511-Q4_K_M.gguf`

### 5.2 GGUF 文本编码器与 mmproj

- 页面：`https://www.modelscope.cn/models/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/files`
- 文件：
  - `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf`
  - `mmproj-F16.gguf`

说明：

- 下载后需要把 `mmproj-F16.gguf` 重命名为 `Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf`
- 重命名后的文件必须与 `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf` 放在同一目录
- 这是 `ComfyUI-GGUF` 当前匹配 `mmproj` 的要求

### 5.3 VAE

- 页面：`https://www.modelscope.cn/models/Comfy-Org/Qwen-Image_ComfyUI/tree/master/split_files/vae`
- 文件：`qwen_image_vae.safetensors`

### 5.4 4 步 LoRA

- 页面：`https://www.modelscope.cn/models/lightx2v/Qwen-Image-Edit-2511-Lightning/files`
- 文件：`Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors`

### 5.5 插件

- 页面：`https://github.com/city96/ComfyUI-GGUF`

## 6. 备用地址

### 6.1 主模型备用地址

- `https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF/tree/main`

### 6.2 文本编码器与 mmproj 备用地址

- `https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/tree/main`

### 6.3 VAE 备用地址

- `https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/tree/main/split_files/vae`

### 6.4 LoRA 备用地址

- `https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning/tree/main`

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
modelscope download --model unsloth/Qwen-Image-Edit-2511-GGUF --local_dir "ComfyUI\models\unet" "qwen-image-edit-2511-Q4_K_M.gguf"
modelscope download --model unsloth/Qwen2.5-VL-7B-Instruct-GGUF --local_dir "ComfyUI\models\text_encoders" "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"
modelscope download --model unsloth/Qwen2.5-VL-7B-Instruct-GGUF --local_dir "ComfyUI\models\text_encoders" "mmproj-F16.gguf"
Rename-Item "ComfyUI\models\text_encoders\mmproj-F16.gguf" "Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf"
modelscope download --model Comfy-Org/Qwen-Image_ComfyUI --local_dir "ComfyUI\models\vae" "split_files/vae/qwen_image_vae.safetensors"
modelscope download --model lightx2v/Qwen-Image-Edit-2511-Lightning --local_dir "ComfyUI\models\loras\lightx2v\Qwen-Image-Edit-2511-Lightning" "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"
```

## 8. 验证命令

### 8.1 检查本地文件是否存在

```powershell
Get-Item `
  "ComfyUI\models\unet\qwen-image-edit-2511-Q4_K_M.gguf", `
  "ComfyUI\models\text_encoders\Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf", `
  "ComfyUI\models\text_encoders\Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf", `
  "ComfyUI\models\vae\qwen_image_vae.safetensors", `
  "ComfyUI\models\loras\lightx2v\Qwen-Image-Edit-2511-Lightning\Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"
```

### 8.2 检查文件大小是否合理

```powershell
Get-Item `
  "ComfyUI\models\unet\qwen-image-edit-2511-Q4_K_M.gguf", `
  "ComfyUI\models\text_encoders\Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf", `
  "ComfyUI\models\text_encoders\Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf", `
  "ComfyUI\models\vae\qwen_image_vae.safetensors", `
  "ComfyUI\models\loras\lightx2v\Qwen-Image-Edit-2511-Lightning\Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors" |
  Select-Object Name,Length
```

参考大小：

- `qwen-image-edit-2511-Q4_K_M.gguf`：`13244758624`
- `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf`：`4683072384`
- `Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf`：`1354163040`
- `qwen_image_vae.safetensors`：`253806246`
- `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors`：`849608296`

### 8.3 检查本机节点是否支持该工作流

```powershell
rg -n "TextEncodeQwenImageEditPlus|FluxKontextMultiReferenceLatentMethod|CFGNorm" "ComfyUI"
```

### 8.4 检查仓库中的工作流参数映射

```powershell
.venv\Scripts\python.exe -m pytest tests/test_selfhost_workflows.py -k qwen_edit_2511_gguf_q4_k_m -v
```

## 9. 已验证结果

以下项目已在 `2026-04-23` 实际验证通过：

- `ModelScope` 文件列表 API 可访问：
  - `unsloth/Qwen-Image-Edit-2511-GGUF`
  - `unsloth/Qwen2.5-VL-7B-Instruct-GGUF`
  - `Comfy-Org/Qwen-Image_ComfyUI`
  - `lightx2v/Qwen-Image-Edit-2511-Lightning`
- 本机已验证存在：
  - `E:\comfyui\comfyui\custom_nodes\ComfyUI-GGUF`
  - `E:\comfyui\resources\ComfyUI\comfy_extras\nodes_qwen.py`
  - `E:\comfyui\resources\ComfyUI\comfy_extras\nodes_flux.py`
  - `E:\comfyui\resources\ComfyUI\comfy_extras\nodes_cfg.py`
- 本机已下载并校验：
  - `E:\comfyui\comfyui\models\unet\qwen-image-edit-2511-Q4_K_M.gguf`
  - `E:\comfyui\comfyui\models\text_encoders\Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf`
  - `E:\comfyui\comfyui\models\text_encoders\Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf`
  - `E:\comfyui\comfyui\models\vae\qwen_image_vae.safetensors`
  - `E:\comfyui\comfyui\models\loras\lightx2v\Qwen-Image-Edit-2511-Lightning\Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors`

## 10. 常见问题

### 10.1 为什么这个 GGUF 工作流不能直接复用 `qwen_2.5_vl_7b_fp8_scaled.safetensors`？

因为 `CLIPLoaderGGUF` 当前不支持把 `scaled fp8 safetensors` 文本编码器和 GGUF 链路混用。这个 GGUF 工作流需要：

- `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf`
- `Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf`

### 10.2 为什么必须重命名 `mmproj-F16.gguf`？

`ComfyUI-GGUF` 会按文本编码器文件名去同目录查找包含同名基串的 `mmproj` 文件。直接保留 `mmproj-F16.gguf` 时，`Qwen-Image-Edit` 链路可能找不到配套投影模型。

### 10.3 为什么这个工作流需要两张图？

这个版本按“主图编辑 + 参考图迁移”设计：

- `image`：主图 / 被编辑图
- `image2`：参考图 / 材质、纹理、风格来源图

如果你只想做单图编辑，可以先把同一张图同时传给 `image` 和 `image2`，后续再单独拆一个单图版工作流。

### 10.4 为什么这里没有继续使用 `KJNodes` 或 `rgthree`？

GitHub 社区里有使用 `rgthree`、`ColorMatch` 等节点的版本，但这份仓库内新增的工作流刻意收敛为：

- 依赖 ComfyUI 核心内置的 `Qwen Edit` / `FluxKontext` / `CFGNorm`
- 只额外依赖 `ComfyUI-GGUF`

这样更接近仓库可维护的最小依赖集。
