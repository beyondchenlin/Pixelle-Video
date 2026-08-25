# image_z_image_turbo_gguf 依赖与下载说明

## 1. 对应工作流路径

- 工作流文件：`workflows/selfhost/image_z_image_turbo_gguf.json`
- 工作流类型：`selfhost` 本地 ComfyUI 文生图工作流
- 输入参数：
  - `prompt`：必填，正向提示词
  - `negative_prompt`：必填，负向提示词，并由独立文本编码节点送入采样器负向条件
  - `width`：可选，默认 `768`
  - `height`：可选，默认 `768`
  - `seed`：可选，缺省占位值为 `0`；普通生成会在提交前把 `0` 替换为随机种子，视觉锚点生成可传入固定随机种子覆盖占位值
- 默认采样参数：
  - 默认采样步数：`8`
  - 采样器：`euler`
  - 调度器：`simple`
  - CFG：`1.0`

## 2. 节点与依赖清单

### 2.1 核心节点

- `UnetLoaderGGUF`
- `CLIPLoaderGGUF`
- `easy int`
- `VAELoader`
- `PrimitiveStringMultiline`
- `CLIPTextEncode`
- `EmptySD3LatentImage`
- `ModelSamplingAuraFlow`
- `KSampler`
- `VAEDecode`
- `SaveImage`

### 2.1.1 Pixelle runtime policy

- 默认工作流继续使用 `Q8_0` 主模型和 `Q8_0` 文本编码器，这是近期主线的质量/性能契约。
- 默认 VAE 解码策略使用 `VAEDecode`：显存足够时执行整图解码以减少分块开销，显存不足时自动回退到分块解码。
- 这不是 Q4 降级方案；Q4 只作为显存极端紧张时的显式可选逃生路径。
- `VAEDecode` 节点必须支持 `samples`、`vae` 输入，并由 ComfyUI 在整图解码发生显存溢出时自动转为分块解码。

### 2.2 依赖分类

| 分类 | 依赖 | 作用 |
|---|---|---|
| 自定义节点插件 | `ComfyUI-GGUF` | 提供 `UnetLoaderGGUF`、`CLIPLoaderGGUF` |
| 自定义节点插件 | `ComfyUI-Easy-Use` | 提供 `easy int`，用于 `width` / `height` 输入 |
| Python 包 | `gguf`、`sentencepiece`、`protobuf` | GGUF 模型读取与分词依赖 |
| 主模型 | `z-image-turbo-Q8_0.gguf` | `Z-Image-Turbo` GGUF 主扩散模型，默认高质量量化版本 |
| 文本编码器 | `Qwen3-4B-Q8_0.gguf` | `Z-Image-Turbo` GGUF 文本编码器，默认高质量量化版本 |
| VAE | `ae.safetensors` | `latent` 与图像之间的自动解码；显存足够时整图解码，显存不足时回退分块解码 |
| ComfyUI 前端修复 | `dialogService-*.js` 中的 GGUF loader 映射 | 修复右侧“缺失模型/未知模型”误报，不影响实际跑图，但能消除错误提示 |

## 3. 目标目录

### 3.1 标准目标目录

| 依赖 | 目标目录 |
|---|---|
| `z-image-turbo-Q8_0.gguf` | `ComfyUI/models/unet/` |
| `Qwen3-4B-Q8_0.gguf` | `ComfyUI/models/text_encoders/` |
| `ae.safetensors` | `ComfyUI/models/vae/` |
| `ComfyUI-GGUF` 插件 | `ComfyUI/custom_nodes/ComfyUI-GGUF/` |
| `ComfyUI-Easy-Use` 插件 | `ComfyUI/custom_nodes/ComfyUI-Easy-Use/` |

### 3.2 本机实际路径

以下路径已在当前机器上实际存在或已验证：

| 依赖 | 本机实际路径 |
|---|---|
| `z-image-turbo-Q8_0.gguf` | `E:\ComfyUIData\models\unet\z-image-turbo-Q8_0.gguf` |
| `Qwen3-4B-Q8_0.gguf` | `E:\ComfyUIData\models\text_encoders\Qwen3-4B-Q8_0.gguf` |
| `ae.safetensors` | `E:\ComfyUIData\models\vae\ae.safetensors` |
| `ComfyUI-GGUF` 插件 | `E:\ComfyUIData\custom_nodes\ComfyUI-GGUF` |
| `ComfyUI-Easy-Use` 插件 | `E:\comfyui\resources\ComfyUI\custom_nodes\ComfyUI-Easy-Use` |

说明：

- 这台机器上的 ComfyUI Desktop 安装布局不是完全统一的。
- `ComfyUI-GGUF` 在 `E:\ComfyUIData\custom_nodes\` 下。
- `ComfyUI-Easy-Use` 在 `E:\comfyui\resources\ComfyUI\custom_nodes\` 下。
- 实际部署时，应以当前 ComfyUI 安装方式和节点管理器的实际插件目录为准。

## 4. 下载优先级

1. 默认优先使用 `ModelScope`
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

- `ComfyUI-GGUF`：`https://github.com/city96/ComfyUI-GGUF`
- `ComfyUI-Easy-Use`：`https://github.com/yolain/ComfyUI-Easy-Use`

## 6. 备用地址

### 6.1 GGUF 主模型备用地址

- `https://huggingface.co/unsloth/Z-Image-Turbo-GGUF/tree/main`

### 6.2 GGUF 文本编码器备用地址

- `https://huggingface.co/unsloth/Qwen3-4B-GGUF/tree/main`

### 6.3 VAE 备用地址

- `https://huggingface.co/Comfy-Org/z_image/tree/main/split_files/vae`

### 6.4 插件备用地址

- `https://github.com/city96/ComfyUI-GGUF`
- `https://github.com/yolain/ComfyUI-Easy-Use`

## 7. 安装命令

### 7.1 安装 GGUF 插件

```powershell
git clone https://github.com/city96/ComfyUI-GGUF.git ComfyUI\custom_nodes\ComfyUI-GGUF
```

### 7.2 安装 Easy-Use 插件

```powershell
git clone https://github.com/yolain/ComfyUI-Easy-Use.git ComfyUI\custom_nodes\ComfyUI-Easy-Use
```

说明：

- 本工作流里的 `width` / `height` 输入节点是 `easy int`
- 如果缺少 `ComfyUI-Easy-Use`，工作流虽然能被仓库 parser 识别，但在 ComfyUI 里会报缺节点

### 7.3 安装 GGUF Python 依赖

```powershell
python -m pip install -U gguf sentencepiece protobuf
```

### 7.4 使用 ModelScope 下载模型

```powershell
modelscope download --model unsloth/Z-Image-Turbo-GGUF --local_dir "E:\ComfyUIData\models\unet" "z-image-turbo-Q8_0.gguf"
modelscope download --model unsloth/Qwen3-4B-GGUF --local_dir "E:\ComfyUIData\models\text_encoders" "Qwen3-4B-Q8_0.gguf"
modelscope download --model Comfy-Org/z_image --local_dir "E:\ComfyUIData\models\vae" "split_files/vae/ae.safetensors"
```

### 7.5 修复 ComfyUI 右侧“缺失模型/未知模型”误报

适用场景：

- 工作流已经能运行
- `Load GGUF Diffusion Model` / `Load GGUF CLIP` 不再报 `Value not in list`
- 但右侧“工作流总览”仍把 GGUF 文件标成“缺失模型”或“未知”

原因：

- `ComfyUI-GGUF` 提供了后端节点和目录
- 但当前桌面版 ComfyUI 前端缺失模型面板没有自动给 `UnetLoaderGGUF` / `CLIPLoaderGGUF` 做目录分类映射

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
- 如果以后升级 ComfyUI Desktop，前端包文件名或内容可能变化，这个补丁可能需要重新应用

## 8. 验证命令

### 8.1 检查本地文件是否存在

```powershell
Get-Item `
  "E:\ComfyUIData\models\unet\z-image-turbo-Q8_0.gguf", `
  "E:\ComfyUIData\models\text_encoders\Qwen3-4B-Q8_0.gguf", `
  "E:\ComfyUIData\models\vae\ae.safetensors"
```

### 8.2 检查文件大小是否合理

```powershell
Get-Item `
  "E:\ComfyUIData\models\unet\z-image-turbo-Q8_0.gguf", `
  "E:\ComfyUIData\models\text_encoders\Qwen3-4B-Q8_0.gguf", `
  "E:\ComfyUIData\models\vae\ae.safetensors" |
  Select-Object Name, Length
```

参考大小：

- `z-image-turbo-Q8_0.gguf`：`7224707136`
- `Qwen3-4B-Q8_0.gguf`：`4280405792`
- `ae.safetensors`：`335304388`

### 8.3 检查工作流节点是否匹配

```powershell
rg -n "UnetLoaderGGUF|CLIPLoaderGGUF|easy int|VAEDecode" "workflows/selfhost/image_z_image_turbo_gguf.json"
```

### 8.4 检查仓库中的工作流参数映射

```powershell
.venv\Scripts\python.exe -m pytest tests/test_selfhost_workflows.py -k z_image_turbo_gguf -v
```

该检查必须同时确认 `prompt`、`negative_prompt`、`width`、`height` 和可选的 `seed` 五个参数，确认 `seed` 缺省占位值为 `0` 且执行组件会在提交前将其替换为随机种子，并确认采样器负向输入连接到 `negative_prompt` 对应的独立 `CLIPTextEncode` 节点，不能连接 `ConditioningZeroOut`。

### 8.5 检查 ComfyUI 前端是否已经包含 GGUF 分类映射

```powershell
rg -n "UnetLoaderGGUF|CLIPLoaderGGUF|unet_gguf|clip_gguf" `
  "E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app\assets\dialogService-DcRVP_r2.js"
```

### 8.6 检查前端备份文件是否存在

```powershell
Get-Item `
  "E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app\assets\dialogService-DcRVP_r2.js", `
  "E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app\assets\dialogService-DcRVP_r2.js.bak_20260423_gguf_map_fix"
```

## 9. 已验证结果

以下项目已在 `2026-04-30` 重新验证：

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
  - `https://github.com/yolain/ComfyUI-Easy-Use`
- ModelScope 已确认存在默认高质量量化文件：
  - `z-image-turbo-Q8_0.gguf`，大小 `7224707136`
  - `Qwen3-4B-Q8_0.gguf`，大小 `4280405792`
- 本机目标模型路径：
  - `E:\ComfyUIData\models\unet\z-image-turbo-Q8_0.gguf`
  - `E:\ComfyUIData\models\text_encoders\Qwen3-4B-Q8_0.gguf`
  - `E:\ComfyUIData\models\vae\ae.safetensors`
- 本机插件路径已存在：
  - `E:\ComfyUIData\custom_nodes\ComfyUI-GGUF`
  - `E:\comfyui\resources\ComfyUI\custom_nodes\ComfyUI-Easy-Use`
- 本机前端修复文件和备份文件已存在：
  - `E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app\assets\dialogService-DcRVP_r2.js`
  - `E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app\assets\dialogService-DcRVP_r2.js.bak_20260423_gguf_map_fix`
- 当前机器上，修复后 ComfyUI 右侧“缺失模型/未知模型”提示已消失

以下项目已在 `2026-08-20` 重新执行验证：

- 三份智图像模型工作流的参数解析和负向节点连线测试：`36 passed`
- `image_z_image_turbo_gguf.json` 使用固定六帧、三个固定种子完成十八张真实生成，正向与负向条件均被后端接受
- `image_z_image_turbo.json` 使用 `512 × 512`、固定种子 `424242` 完成真实双条件生成，输出大小 `221684` 字节
- `image_z_image.json` 使用 `512 × 512`、固定种子 `424242` 完成真实双条件生成，输出大小 `238929` 字节
- 三个工作流的真实生成均返回单张图片，未出现未知节点、缺失模型、负向参数缺失或采样器连线错误

## 10. 常见问题

### 10.1 这个工作流和 `image_z_image_turbo.json` 的区别是什么？

- `image_z_image_turbo.json`：BF16 / NVFP4 版，主模型放在 `ComfyUI/models/diffusion_models/`
- `image_z_image_turbo_gguf.json`：GGUF 版，主模型放在 `ComfyUI/models/unet/`

它们的核心输入接口保持一致，都是：

- `prompt`
- `negative_prompt`
- `width`
- `height`

`image_z_image_turbo_gguf.json` 另外暴露可选的 `seed` 参数：普通生成缺省时由执行组件把占位值 `0` 替换为随机种子，视觉锚点生成传入固定随机种子时直接覆盖该占位值。

### 10.2 为什么这里还是用 `ae.safetensors`？

因为 `Z-Image-Turbo` 的 GGUF 版本只替换了主模型和文本编码器，VAE 仍然沿用 `z_image` / `z_image_turbo` 工作流使用的 `ae.safetensors`。

### 10.3 如果我想换成其他量化怎么办？

当前默认使用 `Q8_0`，保持近期主线的高质量与高性能配置。如果显存紧张，可以把工作流里的文件名改成同一仓库里的较低量化版本，例如：

- `z-image-turbo-Q8_0.gguf`
- `z-image-turbo-Q6_K.gguf`
- `z-image-turbo-Q5_K_M.gguf`
- `z-image-turbo-Q4_K_M.gguf`
- `Qwen3-4B-Q8_0.gguf`
- `Qwen3-4B-Q6_K.gguf`
- `Qwen3-4B-Q5_K_M.gguf`
- `Qwen3-4B-Q4_K_M.gguf`

但要保证主模型和文本编码器的量化组合，是你实际下载到本机的文件名。

仓库下载 helper 已提供显式 Q4 逃生入口，但不会改变默认 Q8：

```python
from pathlib import Path
from pixelle_video.utils.z_image_downloads import build_z_image_download_tasks

tasks = build_z_image_download_tasks(
    Path(r"E:\ComfyUIData\models"),
    include_turbo_gguf_q4=True,
)
```

如果启用 Q4，必须同时替换主模型和文本编码器文件名，不能只替换其中一个；默认工作流文件仍应保持 `Q8_0`。

### 10.4 为什么这个 GGUF 工作流可以像普通文生图一样使用？

因为它沿用了 `11.txt` / `z-image-turbo` 那套文生图结构：

- 使用 `prompt` 和 `negative_prompt` 两路独立文本条件
- 用 `EmptySD3LatentImage` 生成空 `latent`
- 不需要上传参考图

所以它可以像现有 `image_z_image_turbo.json` 一样，走项目当前的 `prompt-only` 图片生成链路。

### 10.5 为什么文档里还要单独写 `ComfyUI-Easy-Use`？

因为这份工作流沿用了仓库现有 `z-image` / `flux` 工作流的参数输入形式，`width` 和 `height` 用的是 `easy int` 节点。

也就是说它不是“只依赖 GGUF 插件”的纯核心节点图，而是：

- `ComfyUI-GGUF` 负责加载 `.gguf`
- `ComfyUI-Easy-Use` 负责 `easy int` 参数输入

### 10.6 为什么模型明明存在，右侧还会显示“缺失模型”或“未知”？

这是 ComfyUI 右侧缺失模型面板的分类问题，不一定代表模型真的缺失。

判断方式：

- 如果节点报 `Value not in list`，那通常是真缺模型或模型列表没刷新
- 如果节点已经不报错、工作流也能跑，但右侧仍显示红字，那通常是前端面板没有识别自定义 GGUF loader

本机这次的源头修复是：

- 不改工作流 JSON
- 改 ComfyUI 前端包里的 GGUF loader 分类映射

### 10.7 为什么修复右侧红字要改 ComfyUI 文件，而不是改我们的 JSON？

因为：

- 工作流 JSON 负责“节点引用哪个模型名”
- ComfyUI 右侧缺失模型面板负责“这个节点类型属于哪个模型目录”

当前问题出在第二层，所以应修 ComfyUI 前端映射，不应继续改工作流 JSON。
