# image_z_image_turbo_gguf_reference 依赖与下载说明

## 一、工作流定位

- 工作流路径：`workflows/selfhost/image_z_image_turbo_gguf_reference.json`
- 基础工作流：`workflows/selfhost/image_z_image_turbo_gguf.json`
- 用途：在保持基础工作流全部图片模型文件不变的前提下，把一张任务级真实身份参考图编码为参考潜变量，并接入正向条件后完成首次图片生成。
- 输入：`prompt`、`negative_prompt`、`width`、`height`、`reference_image`。
- 输出：一张未经后处理补画的真实生成图片。

## 二、节点与真实绑定路径

| 节点 | 类别 | 用途 |
|---|---|---|
| `37` | `UnetLoaderGGUF` | 加载与基础工作流相同的 Z-Image Turbo 主模型 |
| `38` | `CLIPLoaderGGUF` | 加载与基础工作流相同的文本编码器 |
| `39` | `VAELoader` | 加载与基础工作流相同的变分自编码器 |
| `92` | `LoadImage` | 接收任务级 `reference_image` 真实参考资源 |
| `93` | `VAEEncode` | 把真实参考图编码为潜变量 |
| `94` | `ReferenceLatent` | 把参考潜变量写入正向生成条件 |
| `3` | `KSampler` | 首次图片采样 |

真实绑定路径为 `92 → 93 → 94 → 3`。节点 `94` 使用工作流内部标记 `[visual-anchor-reference-condition]`，运行前检查会同时验证参考输入节点、条件节点、采样节点、完整连通路径、工作流文件校验值和任务级参考图校验值。

## 三、依赖分类与目标目录

本工作流不新增模型文件，也不新增第三方节点。它复用基础工作流已经验证的依赖：

| 类别 | 文件或节点 | 目标目录或来源 |
|---|---|---|
| 主模型 | `z-image-turbo-Q8_0.gguf` | `ComfyUI/models/unet/` |
| 文本编码器 | `Qwen3-4B-Q8_0.gguf` | `ComfyUI/models/text_encoders/` |
| 变分自编码器 | `ae.safetensors` | `ComfyUI/models/vae/` |
| 核心节点 | `VAEEncode`、`ReferenceLatent`、`KSampler` | ComfyUI 核心 |
| 既有插件 | `UnetLoaderGGUF`、`CLIPLoaderGGUF` | 仓库既有 ComfyUI-GGUF 插件 |
| 既有插件 | `easy int` | 仓库既有 ComfyUI-Easy-Use 插件 |

模型下载、文件大小、模型平台主地址和备用地址继续以 `workflows/down/image_z_image_turbo_gguf_依赖与下载说明.md` 为事实源，不重复维护第二份下载清单。

## 四、采用依据

- ComfyUI 官方 `ReferenceLatent` 节点把参考潜变量写入生成条件，节点源码：`https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_edit_model.py`。
- ComfyUI 官方 `Lumina2` 模型基类读取 `reference_latents`；Z-Image 使用该模型基类，源码：`https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/model_base.py`。
- Z-Image 官方基础工作流：`https://github.com/comfyanonymous/ComfyUI_examples/blob/master/z_image/README.md`。
- ComfyUI 许可证：GNU 通用公共许可证第三版，见 `https://github.com/Comfy-Org/ComfyUI/blob/master/LICENSE`。本实现没有复制第三方源码，只调用本地安装的核心节点；发布时仍需遵守项目自身及运行依赖的许可证义务。

采用理由：这条路径使用项目现有 Z-Image 模型和本地 ComfyUI 核心能力，真实参考图直接进入首次采样条件，不依赖文字冒充参考图，也不切换成其他图片模型。

未采用社区 `ReferenceLatentPlus` 节点：其仓库未提供许可证文件，而且文档明确说明 Z-Image 参数只给出未验证的起始建议，不满足本任务的依赖许可和成熟度要求。

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
4. 参考图沿 `92 → 93 → 94 → 3` 进入首次采样。
5. 任务记录保存工作流校验值、参考图校验值、固定随机种子和任务编号。

## 六、常见问题

### 为什么不直接修改基础工作流？

基础工作流还承担不使用视觉锚点的普通文字生图。单独维护参考变体可以保证普通链路不被强制要求上传参考图。

### 为什么不使用普通控制网络？

姿态、边缘和深度控制主要约束结构，不能替代身份参考。本工作流直接把真实参考图编码为模型原生读取的参考潜变量。

### 这会固定视觉锚点的位置或大小吗？

不会。工作流没有位置、面积、角落、遮罩或固定载体参数；最终位置、大小和表现形式由当前完整提示词与图片模型共同决定。
