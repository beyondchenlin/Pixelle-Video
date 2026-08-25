# image_z_image_turbo_gguf_reference 依赖与下载说明

## 一、工作流定位

- 工作流路径：`workflows/selfhost/image_z_image_turbo_gguf_reference.json`
- 基础工作流：`workflows/selfhost/image_z_image_turbo_gguf.json`
- 用途：在保持 `dev` 默认基础工作流的模型、八步采样器、调度器、画面尺寸和输出配置不变的前提下，把一张任务级真实身份参考图接入 Z-Image 原生参考条件，并与最终正向提示词共同完成首次图片生成。
- 输入：`prompt`、`negative_prompt`、`width`、`height`、`reference_image`。
- 输出：一张未经后处理补画的真实生成图片。

## 二、节点与真实绑定路径

| 节点 | 类别 | 用途 |
|---|---|---|
| `37` | `UnetLoaderGGUF` | 加载与基础工作流相同的 Z-Image Turbo 主模型 |
| `38` | `CLIPLoaderGGUF` | 加载与基础工作流相同的文本编码器 |
| `39` | `VAELoader` | 加载与基础工作流相同的变分自编码器 |
| `92` | `LoadImage` | 接收任务级 `reference_image` 真实参考资源 |
| `93` | `ImageScale` | 把完整真实参考资源限制为 `32×32` 条件输入，降低参考图原构图对新画面的干扰 |
| `94` | `TextEncodeZImageOmni` | 同时接收最终正向提示词、文本编码器、变分自编码器和唯一一张真实参考图 |
| `3` | `KSampler` | 首次图片采样 |

真实绑定路径为 `92 → 93 → 94 → 3`。节点 `94` 使用工作流内部标记 `[visual-anchor-reference-condition]`，并关闭节点自身的自动放大。运行前和运行后检查会验证：参考输入只有一张、参考资源校验值不变、缩放节点为 `32×32`、最终提示词进入同一个条件节点、条件节点直接进入首次采样，以及实际执行记录中的完整连通路径。

`32×32` 仅是身份参考条件的信息量限制，不是成图中视觉锚点的面积、位置、景别或表现形式限制。成图中的大小和位置仍完全由第二阶段针对当前场景自由决定。

## 三、依赖分类与目标目录

本工作流不新增模型文件，也不新增第三方节点。它复用基础工作流已经验证的依赖：

| 类别 | 文件或节点 | 目标目录或来源 |
|---|---|---|
| 主模型 | `z-image-turbo-Q8_0.gguf` | `ComfyUI/models/unet/` |
| 文本编码器 | `Qwen3-4B-Q8_0.gguf` | `ComfyUI/models/text_encoders/` |
| 变分自编码器 | `ae.safetensors` | `ComfyUI/models/vae/` |
| 核心节点 | `ImageScale`、`TextEncodeZImageOmni`、`KSampler` | ComfyUI 核心 |
| 既有插件 | `UnetLoaderGGUF`、`CLIPLoaderGGUF` | 仓库既有 ComfyUI-GGUF 插件 |
| 既有插件 | `easy int` | 仓库既有 ComfyUI-Easy-Use 插件 |

模型下载、文件大小、模型平台主地址和备用地址继续以 `workflows/down/image_z_image_turbo_gguf_依赖与下载说明.md` 为事实源，不重复维护第二份下载清单。

## 四、采用依据

- ComfyUI 官方 `TextEncodeZImageOmni` 节点同时建立 Z-Image 所需的参考潜变量、参考图文本嵌入和最终正向文本条件，节点源码：`https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_zimage.py`。
- ComfyUI 官方 `ImageScale` 节点负责在进入身份条件前限制参考图信息量，节点源码：`https://github.com/Comfy-Org/ComfyUI/blob/master/nodes.py`。
- Z-Image 官方基础工作流：`https://github.com/comfyanonymous/ComfyUI_examples/blob/master/z_image/README.md`。
- ComfyUI 许可证：GNU 通用公共许可证第三版，见 `https://github.com/Comfy-Org/ComfyUI/blob/master/LICENSE`。本实现没有复制第三方源码，只调用本地安装的核心节点；发布时仍需遵守项目自身及运行依赖的许可证义务。

采用理由：这条路径使用项目 `dev` 默认的 Z-Image 量化模型、本地 ComfyUI 核心节点和原采样配置。真实参考资源与最终提示词在同一个原生条件节点中结合并直接进入首次采样，不依赖文字冒充参考图，不切换模型，也不进行生成后粘贴或补画。限制参考条件信息量可避免把参考图中的书本、地图和装饰构图误当成新画面的内容事实。

未采用通用 `ReferenceLatent` 直连：它没有建立 Z-Image 原生参考文本条件，实际会把整张参考图的书本、地图和装饰构图强行带入新画面，不符合“只保持身份、重新创作整幅画”的产品要求。

未采用社区身份适配节点：当前本地环境没有项目已登记的对应权重，加入社区节点还会改变既有依赖与模型配置，不符合本任务保持 `dev` 默认生成配置的边界。

## 五、安装与验证

本工作流没有新增下载项。先按基础工作流说明确认三个既有模型文件和两个既有插件可用，再执行：

```powershell
uv run pytest tests/test_selfhost_workflows.py -k "z_image_turbo_gguf_reference" -v
uv run pytest tests/services/test_visual_anchor_two_stage_service.py -k "workflow_reference" -v
```

真实运行验证必须同时检查：

1. 实际请求使用 `selfhost/image_z_image_turbo_gguf_reference.json`。
2. 基础工作流与参考工作流的主模型、文本编码器和变分自编码器文件完全一致。
3. `reference_image` 实际绑定到节点 `92`。
4. 参考图沿 `92 → 93 → 94 → 3` 进入首次采样，节点 `94` 为 `TextEncodeZImageOmni`，只使用 `image1`，`image2`、`image3` 和额外图像编码器均为空。
5. 节点 `93` 为 `ImageScale`，实际参数为 `32×32`、`lanczos`、不裁剪；节点 `94` 的自动放大为关闭。
6. 基础工作流与参考工作流除正向条件节点、参考输入链和固定随机种子标记外，其余节点配置完全一致。
7. 任务记录保存提示词版本、身份资源版本、工作流校验值、实际模型文件、参考图校验值、固定随机种子、本地生成任务编号和实际参考条件路径。

## 六、常见问题

### 为什么不直接修改基础工作流？

基础工作流还承担不使用视觉锚点的普通文字生图。单独维护参考变体可以保证普通链路不被强制要求上传参考图。

### 为什么不使用普通控制网络？

姿态、边缘和深度控制主要约束结构，不能替代身份参考。本工作流使用 Z-Image 自身的参考条件节点同时处理真实参考图与最终提示词。

### 为什么参考条件使用 `32×32`？

默认真实参考图除红羽外还包含书本、地图和装饰线条。高信息量参考条件会把这些参考图内容误带入新场景；`32×32` 保留红色主体、轮廓和主要身份颜色信号，同时由最终提示词明确补充黑眉、白眼、橙黄色喙和黑尾羽。这个尺寸只作用于身份条件，不改变输出分辨率，也不规定红羽在最终画面中的大小或位置。

### 这会固定视觉锚点的位置或大小吗？

不会。工作流没有位置、面积、角落、遮罩或固定载体参数；最终位置、大小和表现形式由当前完整提示词与图片模型共同决定。
