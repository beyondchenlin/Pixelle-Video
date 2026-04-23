# image_qwen_edit_2511_gguf_q4_k_m 依赖与下载说明

## 1. 对应工作流路径

- 工作流文件：`workflows/selfhost/image_qwen_edit_2511_gguf_q4_k_m.json`
- 工作流类型：`selfhost` 本地 ComfyUI 图像编辑工作流
- 输入参数：
  - `prompt`：编辑指令
  - `image`：主输入图 / 待编辑图片
  - `image2`：参考图 / 材质图 / 风格参考图
  - `seed`：可选，默认 `0`
  - `steps`：可选，默认 `4`
  - `cfg`：可选，默认 `1.0`

说明：

- 这是双图编辑工作流，不是普通文生图工作流。
- `image` 和 `image2` 都是必填上传参数。
- 工作流 JSON 里的 `example_source.png` 与 `example_reference.png` 只是占位文件名，实际运行时应由调用端上传真实图片。

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
| ComfyUI 核心 / 当前节点集 | `TextEncodeQwenImageEditPlus`、`FluxKontextMultiReferenceLatentMethod`、`CFGNorm`、`FluxKontextImageScale`、`VAEEncodeTiled`、`VAEDecodeTiled` | 提供 Qwen Edit 2511 的编辑编码、多参考 latent 处理和分块编解码 |
| 自定义节点插件 | `ComfyUI-GGUF` | 提供 `UnetLoaderGGUF`、`CLIPLoaderGGUF` |
| Python 包 | `gguf`、`sentencepiece`、`protobuf` | GGUF 模型读取与分词依赖 |
| 主模型 | `qwen-image-edit-2511-Q4_K_M.gguf` | Qwen Image Edit 2511 GGUF 主扩散模型 |
| GGUF 文本编码器 | `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf` | GGUF 文本 / 视觉语言编码器 |
| GGUF 视觉投影 | `Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf` | Qwen2.5-VL 的 `mmproj` 文件，缺失时 GGUF 编辑链会损坏 |
| VAE | `qwen_image_vae.safetensors` | 图像与 latent 的编解码 |
| LoRA | `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` | 4 步加速 LoRA |
| ComfyUI 前端修复 | `dialogService-*.js` 中的 GGUF loader 映射 | 修复右侧“缺失模型/未知模型”误报，不影响跑图，但能消除显示层错误提示 |

## 3. 目标目录

### 3.1 标准目标目录

| 依赖 | 目标目录 |
|---|---|
| `qwen-image-edit-2511-Q4_K_M.gguf` | `ComfyUI/models/unet/` |
| `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf` | `ComfyUI/models/text_encoders/` |
| `Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf` | `ComfyUI/models/text_encoders/` |
| `qwen_image_vae.safetensors` | `ComfyUI/models/vae/` |
| `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` | `ComfyUI/models/loras/lightx2v/Qwen-Image-Edit-2511-Lightning/` |
| `ComfyUI-GGUF` 插件 | `ComfyUI/custom_nodes/ComfyUI-GGUF/` |

### 3.2 本机实际路径

以下路径已在当前机器上实际存在并已核对：

| 依赖 | 本机实际路径 |
|---|---|
| `qwen-image-edit-2511-Q4_K_M.gguf` | `E:\comfyui\comfyui\models\unet\qwen-image-edit-2511-Q4_K_M.gguf` |
| `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf` | `E:\comfyui\comfyui\models\text_encoders\Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf` |
| `Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf` | `E:\comfyui\comfyui\models\text_encoders\Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf` |
| `qwen_image_vae.safetensors` | `E:\comfyui\comfyui\models\vae\qwen_image_vae.safetensors` |
| `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` | `E:\comfyui\comfyui\models\loras\lightx2v\Qwen-Image-Edit-2511-Lightning\Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` |
| `ComfyUI-GGUF` 插件 | `E:\comfyui\comfyui\custom_nodes\ComfyUI-GGUF` |

## 4. 下载优先级

1. 默认优先使用 `ModelScope`
2. 仅在 `ModelScope` 缺失或不可用时，回退到 `Hugging Face` / `GitHub`

## 5. ModelScope 检索或主地址

### 5.1 主模型

- 页面：`https://www.modelscope.cn/models/unsloth/Qwen-Image-Edit-2511-GGUF/files`
- 文件：`qwen-image-edit-2511-Q4_K_M.gguf`

### 5.2 GGUF 文本编码器与 mmproj

- 页面：`https://www.modelscope.cn/models/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/files`
- 文件：
  - `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf`
  - `mmproj-F16.gguf`

说明：

- `ComfyUI-GGUF` 会按文本编码器文件名自动寻找同目录下的 `mmproj` 文件。
- 当前插件匹配逻辑会去找“文件名中包含文本编码器主干名，且带 `mmproj` 字样”的 `.gguf` 文件。
- 本机当前可工作的命名是：`Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf`
- 如果从仓库下到的是 `mmproj-F16.gguf`，建议重命名为 `Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf` 后再放到 `text_encoders` 目录。

匹配依据可见：

- [loader.py](</E:/comfyui/comfyui/custom_nodes/ComfyUI-GGUF/loader.py:271>)
- [loader.py](</E:/comfyui/comfyui/custom_nodes/ComfyUI-GGUF/loader.py:293>)

### 5.3 VAE

- 页面：`https://www.modelscope.cn/models/Comfy-Org/Qwen-Image_ComfyUI/tree/master/split_files/vae`
- 文件：`qwen_image_vae.safetensors`

### 5.4 4 步 LoRA

- 页面：`https://www.modelscope.cn/models/lightx2v/Qwen-Image-Edit-2511-Lightning/files`
- 文件：`Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors`

### 5.5 插件

- `ComfyUI-GGUF`：`https://github.com/city96/ComfyUI-GGUF`

## 6. 备用地址

### 6.1 主模型备用地址

- `https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF/tree/main`

### 6.2 GGUF 文本编码器与 mmproj 备用地址

- `https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/tree/main`

### 6.3 VAE 备用地址

- `https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/tree/main/split_files/vae`

### 6.4 LoRA 备用地址

- `https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning`

### 6.5 插件备用地址

- `https://github.com/city96/ComfyUI-GGUF`

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
modelscope download --model Comfy-Org/Qwen-Image_ComfyUI --local_dir "ComfyUI\models\vae" "split_files/vae/qwen_image_vae.safetensors"
modelscope download --model lightx2v/Qwen-Image-Edit-2511-Lightning --local_dir "ComfyUI\models\loras\lightx2v\Qwen-Image-Edit-2511-Lightning" "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"
```

### 7.4 如果需要重命名 mmproj

```powershell
Rename-Item `
  "ComfyUI\models\text_encoders\mmproj-F16.gguf" `
  "Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf"
```

### 7.5 修复 ComfyUI 右侧“缺失模型/未知模型”误报

适用场景：

- 工作流已经能运行
- `Load GGUF Diffusion Model` / `Load GGUF CLIP` 不再报 `Value not in list`
- 但右侧“工作流总览”仍把 GGUF 文件标成“缺失模型”或“未知”

原因：

- `ComfyUI-GGUF` 提供了后端节点和目录
- 当前桌面版 ComfyUI 前端缺失模型面板没有自动给 `UnetLoaderGGUF` / `CLIPLoaderGGUF` 做目录分类映射

本机已执行的修复方式：

1. 备份前端文件
2. 在桌面版前端包中补 GGUF loader 映射
3. 重启 ComfyUI Desktop

本机修复涉及文件：

- 已修复文件：`E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app\assets\dialogService-DcRVP_r2.js`
- 备份文件：`E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app\assets\dialogService-DcRVP_r2.js.bak_20260423_gguf_map_fix`

说明：

- 这是 ComfyUI 前端显示层修复，不是工作流 JSON 修复
- 它不会改变跑图结果，只会修复右侧缺失模型识别
- 这条修复对所有使用 `UnetLoaderGGUF` / `CLIPLoaderGGUF` 的工作流都生效，包括本工作流

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
  Select-Object Name, Length
```

参考大小：

- `qwen-image-edit-2511-Q4_K_M.gguf`：`13244758624`
- `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf`：`4683072384`
- `Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf`：`1354163040`
- `qwen_image_vae.safetensors`：`253806246`
- `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors`：`849608296`

### 8.3 检查仓库中的工作流参数映射

```powershell
.venv\Scripts\python.exe -m pytest tests/test_selfhost_workflows.py -k qwen_edit_2511_gguf_q4_k_m -v
```

### 8.4 检查 ComfyUI 前端是否已经包含 GGUF 分类映射

```powershell
rg -n "UnetLoaderGGUF|CLIPLoaderGGUF|unet_gguf|clip_gguf" `
  "E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app\assets\dialogService-DcRVP_r2.js"
```

### 8.5 检查前端备份文件是否存在

```powershell
Get-Item `
  "E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app\assets\dialogService-DcRVP_r2.js", `
  "E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app\assets\dialogService-DcRVP_r2.js.bak_20260423_gguf_map_fix"
```

## 9. 已验证结果

以下项目已在 `2026-04-23` 实际验证通过：

- `ModelScope` 页面可访问：
  - `https://www.modelscope.cn/models/unsloth/Qwen-Image-Edit-2511-GGUF/files`
  - `https://www.modelscope.cn/models/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/files`
  - `https://www.modelscope.cn/models/Comfy-Org/Qwen-Image_ComfyUI/tree/master/split_files/vae`
  - `https://www.modelscope.cn/models/lightx2v/Qwen-Image-Edit-2511-Lightning/files`
- 备用地址可访问：
  - `https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF/tree/main`
  - `https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/tree/main`
  - `https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/tree/main/split_files/vae`
  - `https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning`
- 插件源可访问：
  - `https://github.com/city96/ComfyUI-GGUF`
- 本机模型文件已存在，大小已核对：
  - `E:\comfyui\comfyui\models\unet\qwen-image-edit-2511-Q4_K_M.gguf`
  - `E:\comfyui\comfyui\models\text_encoders\Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf`
  - `E:\comfyui\comfyui\models\text_encoders\Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf`
  - `E:\comfyui\comfyui\models\vae\qwen_image_vae.safetensors`
  - `E:\comfyui\comfyui\models\loras\lightx2v\Qwen-Image-Edit-2511-Lightning\Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors`
- 本机插件路径已存在：
  - `E:\comfyui\comfyui\custom_nodes\ComfyUI-GGUF`
- 本机前端修复文件和备份文件已存在：
  - `E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app\assets\dialogService-DcRVP_r2.js`
  - `E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app\assets\dialogService-DcRVP_r2.js.bak_20260423_gguf_map_fix`

## 10. 常见问题

### 10.1 这条工作流为什么不能像普通文生图一样只传 `prompt`？

因为它是编辑工作流，不是文生图工作流。

它要求同时提供：

- `prompt`
- `image`
- `image2`

其中：

- `image` 是主输入图
- `image2` 是参考图 / 材质图 / 风格图

### 10.2 `mmproj` 为什么这么重要？

因为这套 GGUF 编辑链不是只靠一个文本编码器文件就能完成视觉理解。

`ComfyUI-GGUF` 的加载逻辑会：

1. 先读取 `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf`
2. 再去同目录寻找匹配的 `mmproj` 文件

如果找不到，插件会报：

- `Can't find mmproj file`
- `Qwen-Image-Edit will be broken`

### 10.3 为什么工作流 JSON 里没直接写 `mmproj`，但文档还要单独写？

因为 `mmproj` 不是作为独立节点参数暴露出来的。

它是 `CLIPLoaderGGUF` 在运行时根据文本编码器文件自动匹配加载的隐式依赖，所以必须单独写进说明文档。

### 10.4 为什么修复右侧红字要改 ComfyUI 文件，而不是改我们的 JSON？

因为：

- 工作流 JSON 负责“节点引用哪个模型名”
- ComfyUI 右侧缺失模型面板负责“这个节点类型属于哪个模型目录”

当前问题出在第二层，所以应修 ComfyUI 前端映射，而不是继续改工作流 JSON。

### 10.5 这条工作流用了 GGUF，右侧“缺失模型/未知模型”会不会也误报？

会，如果 ComfyUI 桌面版前端没有补 GGUF loader 映射。

但本机这次已经做了源头修复，所以当前机器上这条工作流也会一起受益。

### 10.6 如果我换成别的量化版本怎么办？

可以换，但必须同时保证：

- 主模型文件名和你本机真实下载的文件一致
- 文本编码器量化文件和对应 `mmproj` 能匹配
- `LoRA`、`VAE` 仍然保持当前这套依赖

如果只是简单替换 `.gguf` 名称，不检查 `mmproj` 匹配关系，这条工作流很容易在运行时损坏。
