# SAM3.1 元素分割与微动动画设计

## 背景

Pixelle 当前已经具备本地 ComfyUI 图片生成、HTML 帧合成、HyperFrames 渲染桥、Python/FFmpeg 视频处理能力。下一步希望在“提示词生成图片”之后，把图片中的主体元素分割出来，并对这些元素施加轻量动画，让最终视频比静态图配音更有停留感。

截至 2026-04-24，Meta 官方 `facebookresearch/sam3` 的最新公开更新是 2026-03-27 发布的 SAM 3.1 Object Multiplex。Hugging Face `facebook/sam3.1` 说明 SAM3.1 在 SAM3 上增加 Object Multiplex，用于更快的多目标视频跟踪。ComfyUI 官方 PR `Comfy-Org/ComfyUI#13408` 已在 2026-04-23 合并 SAM3/SAM3.1 支持，新增图像分割和视频跟踪节点。因此本设计优先采用 ComfyUI 原生 SAM3.1 节点，第三方节点只作为兼容方案。

## 目标

- 默认从生成图片中分割并选中 3 个主体元素。
- 用户可以在高级选项中查看候选元素，并调整选中元素、分割提示词、动画类型、动画强度和渲染后端。
- HyperFrames/Canvas 与 Python/FFmpeg 都作为正式渲染路径，读取同一份元素动画 manifest。
- 第一版聚焦简笔风、主体突出、背景简单的图片，优先提升观赏性，不追求专业抠图工具级精修。

## 非目标

- 第一版不做复杂角色骨骼、真实物理、逐像素形变或视频级运动补全。
- 第一版不要求 SAM3.1 视频跟踪参与主链路；视频跟踪可后续用于已有视频素材。
- 第一版不替代原有图片/视频生成工作流，只在图片生成之后增加可选增强阶段。

## 推荐方案

采用“候选层 + 选中层 + 统一动画 manifest”的结构。

图片生成完成后，Pixelle 调用一个独立的 SAM3.1 分割工作流生成主体元素。默认模式只分割并选中 3 个主体，普通用户无需操作即可进入动画渲染。高级用户展开设置后，可以看到当前 3 个主体的缩略图并手动勾选、取消、调整动画；如果用户需要更多选择，可以在高级选项中把候选池扩展到最多 8 个并重新分割。

渲染阶段不直接耦合 SAM3.1 结果，而是读取统一的 `element_animation_manifest.json`。HyperFrames/Canvas 后端负责更丰富的模板化动效；Python/FFmpeg 后端负责本地批处理和无浏览器环境下的稳定逐帧合成。

背景层必须显式记录生成方式。优先生成“去主体背景”，避免元素移动后露出原位置的静态主体；如果第一版暂不做 inpaint，则必须把背景标记为 `source_image_low_motion` 并限制元素移动幅度，只允许呼吸、轻微漂浮等不会明显露底的动画。

## 数据流

```text
image prompt
 -> ComfyUI image workflow
 -> generated image
 -> ComfyUI SAM3.1 segmentation workflow
 -> background image + candidate element PNGs + masks + bboxes
 -> element_animation_manifest.json
 -> HyperFrames/Canvas renderer or Python/FFmpeg renderer
 -> final video
```

## ComfyUI 与模型策略

默认使用 ComfyUI 原生 SAM3.1 能力：

- `SAM3 Detect`：对单张图片按文本、框、点提示分割。
- `SAM3 Video Track`、`SAM3 Track Preview`、`SAM3 Track to Mask`：暂不进入默认图片增强主链路，后续作为视频素材增强能力。
- 权重优先按仓库规则检索 ModelScope；若 ModelScope 缺少对应资源或不可用，再使用 Hugging Face `Comfy-Org/sam3.1` 或 `facebook/sam3.1` 作为回退，并在 `workflows/down/` 对应说明文档中明确记录来源、目标目录、验证命令和许可证注意事项。

分割工作流建议新增：

- `workflows/selfhost/image_sam31_segment.json`
- `workflows/down/image_sam31_segment_依赖与下载说明.md`

第一版可以先用文本提示进行开放词汇分割。默认自动模式下，根据图片生成提示词和 storyboard 内容提取 3 个候选名词；如果无法稳定提取，则使用通用提示词组合，例如 `character, object, prop`。高级选项中可把候选池扩展到 4-8 个，并使用更宽的提示词组合，例如 `character, object, prop, animal, plant, building`。后续可加入视觉分析服务自动生成更准确的标签。

## 候选筛选

SAM3.1 可能输出多个 masks 和 bboxes。候选元素需要经过统一排序与过滤：

- 过滤面积太小、太大、太碎、透明 PNG 近似空白的 mask。
- 合并或丢弃高度重叠的候选，避免同一主体重复出现。
- 综合 `score`、面积占比、居中程度、与其他主体的重叠度排序。
- 默认只保留并选中 3 个主体。
- 用户在高级选项中增加候选池上限或修改分割提示词时，重新跑分割；只勾选/取消已有元素或修改动画时，不重新分割。

## Manifest

统一 manifest 示例：

```json
{
  "version": 1,
  "source_image": "image.png",
  "canvas": {
    "width": 1080,
    "height": 1920
  },
  "timeline": {
    "duration": 4.2,
    "fps": 30,
    "audio_path": "audio/frame_001.mp3",
    "duration_source": "audio"
  },
  "background": {
    "asset": "background.png",
    "mode": "inpainted",
    "fallback_mode": "source_image_low_motion"
  },
  "segmentation": {
    "model": "sam3.1",
    "workflow": "selfhost/image_sam31_segment.json",
    "candidate_limit": 3,
    "max_candidate_limit": 8,
    "default_selected_count": 3,
    "prompt": "auto"
  },
  "elements": [
    {
      "id": "element_001",
      "label": "character",
      "asset": "elements/element_001.png",
      "mask": "masks/element_001.png",
      "bbox": [180, 520, 620, 980],
      "score": 0.91,
      "z_index": 2,
      "anchor": [0.5, 0.85],
      "selected": true,
      "motion_bounds": {
        "max_translate_px": 24,
        "max_scale_delta": 0.03,
        "max_rotate_deg": 2
      },
      "animation": {
        "preset": "float_breathe",
        "intensity": "medium"
      }
    }
  ],
  "render": {
    "backend": "hyperframes_canvas"
  }
}
```

## 高级选项

默认界面不打扰用户，只展示“元素微动增强”开关和当前默认值。高级选项展开后提供：

- 主体数量：默认 3，可调 1-5；超过当前候选数量时提示重新分割。
- 候选池上限：默认 3，高级模式可调到 8。
- 分割提示词：默认自动，可输入如“人物, 气球, 房子”。
- 候选元素列表：缩略图、标签、置信度、面积、选中状态。
- 每个元素的动画 preset：自动、漂浮、呼吸、轻摆、弹入、漂移。
- 动画强度：低、中、高，默认中。
- 渲染后端：HyperFrames/Canvas 或 Python/FFmpeg。

高级选项应复用同一份候选数据。用户勾选/取消元素或改变动画 preset 时，只更新 manifest；用户修改分割提示词或重新生成图片时，才重新调用 SAM3.1。

## 动画预设

第一版预制 8 种轻量效果：

- `slow_zoom_bg`：背景缓慢推近。
- `parallax_float`：前景轻微浮动，背景反向慢移。
- `breathe`：主体 1-3% 缩放。
- `float_breathe`：上下漂浮叠加轻呼吸。
- `sway`：左右轻摆，适合树、人物、物体。
- `drift`：云、烟、气泡、小物件慢漂。
- `pop_in`：轻弹入场。
- `focus_pulse`：主体短暂放大再回落。

所有预设都应以确定性参数生成。相同 task、element id、preset 和 intensity 应得到稳定结果，便于复现和测试。

动画参数必须受背景模式约束。如果 `background.mode` 是 `inpainted`，允许轻微位移、缩放和旋转；如果使用 `source_image_low_motion`，默认禁用明显位移，只保留缩放、透明度和 3-6px 以内的漂浮，以降低重影风险。

## 渲染后端

HyperFrames/Canvas 后端：

- 在 HyperFrames 项目中 materialize 背景和元素 PNG。
- 由模板读取 manifest，在 Canvas 或 DOM layer 上按时间计算 transform。
- 适合字幕、节奏、模板化视觉包装和未来更丰富的动画。

Python/FFmpeg 后端：

- 使用 PIL/OpenCV 按帧合成背景和透明元素。
- 对每个元素应用 translate、scale、rotate、opacity。
- 用 ffmpeg 编码输出视频并合成音频。
- 适合批处理、无浏览器环境和稳定本地渲染。

两个后端必须共享动画 preset 名称、强度映射、时间曲线和 manifest schema。允许视觉表现有轻微差异，但同一 manifest 的主体选择、起止时间和整体运动方向应一致。

两个后端都必须从 manifest 的 `canvas` 和 `timeline` 字段读取画布尺寸、fps 和总时长。图片帧场景下，`timeline.duration` 默认来自该帧 narration 音频；无音频时使用 storyboard frame duration 或配置默认值。

## 错误处理

- SAM3.1 不可用：跳过元素增强，继续原有静态图片视频流程，并在任务日志中标记原因。
- 无候选元素：使用背景慢缩放作为退化动画。
- 候选少于 3 个：选中所有有效候选，其余不补假元素。
- mask 质量过差：丢弃该候选，保留原图背景。
- 去主体背景生成失败：将 `background.mode` 降级为 `source_image_low_motion`，并自动把元素动画限制为低幅度 preset。
- HyperFrames 渲染失败：若用户选择 Python/FFmpeg，可直接使用该后端；若用户选择 HyperFrames，则返回明确错误并保留可重试任务状态。
- Python/FFmpeg 渲染失败：返回 ffmpeg stderr 摘要，保留 manifest 和中间元素产物用于复现。

## 测试策略

- Manifest schema 单元测试：默认 3 个主体、候选上限、选中状态、动画字段。
- 候选筛选测试：面积过滤、重叠去重、候选不足、用户修改选中集合。
- 渲染参数测试：不同 preset/intensity 输出稳定 transform。
- 背景模式测试：inpainted 背景允许轻位移；source_image_low_motion 背景限制移动幅度。
- HyperFrames 项目导出测试：manifest、元素 PNG、背景 PNG 能正确 materialize。
- Python/FFmpeg 合成测试：用小尺寸 fixture 验证视频时长、分辨率、帧数、透明元素合成。
- API/UI 测试：高级选项默认折叠，展开后能修改主体数量、元素勾选和后端。

## 实施顺序

1. 定义元素候选和动画 manifest 数据模型。
2. 新增 SAM3.1 分割 workflow 和依赖说明文档。
3. 新增分割服务：调用 ComfyUI、保存背景/元素/mask、生成候选列表。
4. 新增候选筛选与默认选中逻辑：默认选中 3 个主体。
5. 新增高级选项 UI 与状态持久化。
6. 扩展 HyperFrames/Canvas 模板读取 manifest 并执行微动动画。
7. 新增 Python/FFmpeg 渲染后端读取同一 manifest。
8. 补充测试与失败退化路径。

## 参考

- Meta SAM3 仓库：https://github.com/facebookresearch/sam3
- Meta SAM3.1 权重：https://huggingface.co/facebook/sam3.1
- ComfyUI SAM3.1 PR：https://github.com/Comfy-Org/ComfyUI/pull/13408
- ComfyUI 重打包权重：https://huggingface.co/Comfy-Org/sam3.1
