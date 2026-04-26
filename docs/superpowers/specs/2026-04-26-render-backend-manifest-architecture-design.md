# Pixelle 三后端渲染与 Manifest 架构设计

## 1. 结论

Pixelle 不应该把最终视频合成继续写成 `legacy`、`hyperframes_compiled`、`ffmpeg_manifest` 三套互相穿插的分支逻辑。最佳实践是把渲染拆成两层：

```text
统一资产生成层
  -> Template Visual Materializer
  -> Element Motion Materializer
  -> Text Render Package

统一执行层
  -> RenderManifest / RenderExecutionPlan
  -> legacy | hyperframes_compiled | ffmpeg_manifest
```

最终对用户暴露的渲染后端保持三个：

```text
legacy
hyperframes_compiled
ffmpeg_manifest
```

`legacy` 代表当前稳定老链路；`hyperframes_compiled` 代表复杂 HTML/CSS/动画链路；`ffmpeg_manifest` 代表简单图片、视频、音频、ASS、overlay 的高速合成链路。

这里不新增名为 `python` 的视频渲染后端。Python 是调度层和资产生成层，真正的视频合成后端是 FFmpeg、HyperFrames 或 Legacy 链路。已经存在的 `PythonElementAnimationRenderer` 应作为 `Element Motion Materializer` 的一种实现接入标准 pipeline，而不是单独成为最终视频后端。

## 2. 背景

当前代码已经有几块重要基础：

- `pixelle_video/render_backend.py` 只有 `legacy` 和 `hyperframes_compiled`。
- `pixelle_video/services/frame_html.py` 能把现有 HTML 模板渲染成图片，但能力目前主要绑定在 legacy 分镜合成里。
- `templates/` 下有 31 个 HTML 分镜模板，按 `1080x1920`、`1920x1080`、`1080x1080` 组织，是当前模板库和用户样式资产的主体。
- `resources/hyperframes/templates/` 目前只有少量 HyperFrames 原生模板，不足以替代现有模板库。
- `pixelle_video/models/render_package.py` 已有 `RenderManifest`、`VisualClip`、`TextTrack`、`TextCue`、`RenderAudioTrack` 等契约雏形。
- `pixelle_video/services/element_animation_renderer.py` 已有 Python/PIL/FFmpeg 元素微动渲染实现。
- `pixelle_video/services/element_segmentation.py` 已有元素分割 manifest 生成能力。
- `RenderManifest.element_animation_manifest_path` 当前是单一路径，不适合多分镜、多 clip 的标准视频 pipeline。

因此本次设计的核心不是给 UI 多加一个后端选项，而是把模板、元素微动、文字渲染、最终合成之间的边界重新收敛。

## 3. 目标

1. 保留现有 HTML 分镜模板库，并让它成为统一视觉资产来源，而不是 legacy 私有实现。
2. 保持三种最终渲染后端：`legacy`、`hyperframes_compiled`、`ffmpeg_manifest`。
3. 新增 `ffmpeg_manifest` 高速合成路径，用于简单图片、视频、音频、ASS、overlay 的无浏览器合成。
4. 把 `PythonElementAnimationRenderer` 真正接入标准视频 pipeline。
5. 消除模板正文 `{{text}}` 与最终 ASS/HyperFrames 字幕重复渲染的问题。
6. 消除单个 `element_animation_manifest_path` 无法表达多分镜元素微动的问题。
7. 让每个任务最终产出可复盘的 `RenderExecutionPlan` 和渲染摘要，记录 requested/effective backend、fallback 原因、资产路径、耗时和最终输出。

## 4. 非目标

- 不一次性重写所有 HTML 模板为 HyperFrames 原生模板。
- 不把 FFmpeg 做成理解 HTML/CSS/GSAP 的后端。
- 不把 Python/PIL 逐帧合成当成所有场景的最快路径。
- 不移除 legacy。legacy 是稳定回退路径，并且继续承担现有模板截图合成能力。
- 不把复杂动画硬塞进 `ffmpeg_manifest`。复杂时间线、CSS 动画、GSAP 动画继续由 `hyperframes_compiled` 承担。

## 5. 两轮 Review 后的判断

### 5.1 第一轮：职责边界

当前最大风险是职责混合：

- 模板截图、字幕、音频拼接、视频合成都散落在 pipeline 分支里。
- `HTMLFrameGenerator` 是有价值的模板资产能力，但现在只被 legacy 主链路直接使用。
- HyperFrames 有自己的 project service 和 compiler，但模板覆盖率远少于现有 HTML 模板库。
- 元素微动已有 UI、配置、模型、测试和服务骨架，但没有成为每个分镜视觉资产的一部分。

正确边界应该是：

```text
HTML template rendering is asset materialization.
HyperFrames and FFmpeg are final renderers.
Legacy is compatibility renderer.
```

也就是说，模板不是某个后端的附属物，而是先被物化成视觉资产，再交给最终后端消费。

### 5.2 第二轮：性能、迁移与故障回退

`ffmpeg_manifest` 会更快，但只在它做 FFmpeg 擅长的工作时成立：

- concat
- image to video
- audio mux
- BGM mix
- ASS burn-in
- overlay
- scale/pad/crop

它不会因为叫 "Python renderer" 就天然更快。Python 逐帧 PIL 合成元素微动通常比纯 FFmpeg 慢，除非已经缓存或只处理少量短片段。真正的速度收益来自：

- 用 manifest 明确输入输出，减少重复推导。
- HTML 模板只预渲染一次，后续由 FFmpeg 消费图片/视频资产。
- 简单场景跳过浏览器和 HyperFrames。
- BGM、字幕、拼接尽量合并到少数 FFmpeg 命令中。
- 对已物化的模板帧、元素微动视频、ASS 文件做 task-local 缓存。

CloneCut 项目中值得借鉴的是阶段产物、manifest、fallback、语义化输出记录；不应照搬脚本式 MoviePy concat 或分散的阶段调用方式。Pixelle 应该围绕 `RenderManifest` 和 `RenderExecutionPlan` 统一这些工程方法。

## 6. 推荐架构

### 6.1 总体数据流

```text
CreationRequest
  -> Storyboard / TimingPlan / TTS
  -> raw media assets
  -> Template Visual Materializer
  -> Element Motion Materializer
  -> TextRenderPackage
  -> RenderManifest
  -> RenderExecutionPlan
  -> BackendRenderer
  -> final video + diagnostics
```

### 6.2 Template Visual Materializer

这是新增的正式层，负责把模板和媒体物化成视觉资产。

输入：

- `storyboard.frames`
- `frame_template`
- `template_params`
- raw image/video media
- canvas size
- text policy

输出：

- 每个分镜的 `template_frame` 图片或 overlay 图片。
- 模板能力摘要。
- 参与最终合成的 `VisualClip`。

现有 `HTMLFrameGenerator` 应被封装到这一层。legacy 继续可以直接使用它，但标准 pipeline 不应再把 HTML 模板能力视为 legacy 私有逻辑。

### 6.3 Element Motion Materializer

这是元素微动的正式接入点。

输入：

- 每个分镜的 source visual asset。
- 元素分割配置。
- duration、fps、canvas。
- 目标元素动画实现：`hyperframes_canvas` 或 `python_ffmpeg`。

输出：

- 每个分镜独立的 `element_animation_manifest.json`。
- 如果使用 `python_ffmpeg`，输出 silent motion video 或 motion image sequence artifact。
- 如果使用 `hyperframes_canvas`，输出可由 HyperFrames project materializer 本地化的元素动画 manifest 和资产。

规则：

- 元素动画 manifest 必须绑定到具体 `VisualClip` 或 frame asset，不能继续作为 `RenderManifest` 的单个全局字段。
- 单个任务中可以有多个分镜启用元素微动，也可以只有部分分镜启用。
- 如果分割失败，应按 frame 粒度记录 fallback，不能让整个任务静默退回无元素微动。

### 6.4 Text Render Package

文字渲染继续以 `TextRenderPackage`、`TextTrack`、`TextCue`、`TextStyleProfile` 为事实源。

模板正文和最终字幕必须通过 `text_policy` 明确分流，禁止隐式双渲染。

推荐策略：

```text
caption_renderer  默认。正文字幕交给 ASS/HyperFrames，模板不写正文。
template_body      正文烧进模板图片，最终字幕 renderer 不再重复写同一正文。
none               模板和最终字幕都不写正文。
explicit_both      明确允许双层文字，仅用于特殊模板。
```

现有包含 `{{text}}` 的模板不删除，但在标准 pipeline 中默认传空正文或受 `template_body` 策略控制。

## 7. RenderManifest 与 ExecutionPlan 契约

### 7.1 VisualClip 扩展

`VisualClip` 需要表达视觉资产来源和角色。推荐新增字段：

```text
source_kind: raw_media | template_frame | template_overlay | element_motion_video
media_role: background | foreground | overlay | final_frame
template_id
template_path
text_policy
element_animation_manifest_path
source_media_path
diagnostics
```

这些字段让三种后端都能用同一份视觉资产计划工作。

### 7.2 RenderManifest 扩展

`RenderManifest` 应继续保留全局 canvas、fps、audio、text、visual clips，但移除或降级全局 `element_animation_manifest_path` 的权威地位。

推荐兼容策略：

- 保留全局字段只作为旧 HyperFrames 模板兼容输入。
- 新字段以每个 `VisualClip` 的 `element_animation_manifest_path` 为准。
- 写出 manifest 时记录 `version`，新旧字段同时存在时以后者为准。

### 7.3 RenderExecutionPlan

新增轻量执行计划对象，记录后端选择和执行策略：

```text
requested_backend
effective_backend
fallback_reason
template_materialization_mode
element_motion_mode
subtitle_mode
audio_strategy
ffmpeg_plan
artifacts
diagnostics
```

这是任务可观测性的关键。UI 历史记录和日志应展示 requested/effective backend，而不是只展示用户请求值。

## 8. 三个后端行为

### 8.1 legacy

职责：

- 稳定兼容老链路。
- 继续使用 HTML 模板生成分镜图片或 overlay。
- 继续支持 per-frame segment concat。
- 继续可用 ASS burn-in。

必须改正：

- 默认不再把 narration 同时传给模板 `{{text}}` 和 ASS 字幕。
- legacy 的模板截图能力要通过 `Template Visual Materializer` 复用，而不是只藏在 `FrameProcessor._step_compose_frame`。

### 8.2 hyperframes_compiled

职责：

- 复杂 HTML/CSS/GSAP 动画。
- HyperFrames 原生模板。
- 多层文字、字幕、复杂时间线。
- 可消费模板预渲染资产。
- 可消费 `hyperframes_canvas` 元素微动 manifest。

模板策略：

- 有 HyperFrames 原生模板时，优先使用原生模板。
- 无原生模板时，先用现有 HTML 模板预渲染成视觉资产，再由 HyperFrames 负责最终时间线、字幕和音频。
- 不要求一次性把 `templates/` 下所有模板搬到 `resources/hyperframes/templates/`。

### 8.3 ffmpeg_manifest

职责：

- 高速合成简单场景。
- 图片/视频 visual clips 拼接。
- narration/master audio mux。
- BGM mix。
- ASS burn-in。
- PNG/video overlay。
- scale/pad/crop 适配画幅。

限制：

- 不解释 HTML。
- 不执行 GSAP/CSS 动画。
- 不直接处理复杂浏览器模板。
- 元素微动只能消费已物化的 motion video/image sequence。

推荐实现：

- 新增 `FfmpegManifestRenderer`。
- 读取 `RenderExecutionPlan.ffmpeg_plan`，生成确定性 FFmpeg filter graph。
- 对简单场景尽量减少中间 mp4 数量。
- 对复杂或不支持场景给出明确 fallback reason，回退到 legacy 或 hyperframes。

## 9. 后端能力解析

新增 capability resolver，输入用户请求、模板类型、媒体类型、文字策略、元素微动策略，输出 effective backend。

示例规则：

```text
requested=ffmpeg_manifest
  支持：静态图片、已生成视频、ASS、BGM、简单 overlay、python_ffmpeg motion artifact
  不支持：未预渲染 HTML、GSAP 动画、HyperFrames 原生动态模板

requested=hyperframes_compiled
  支持：HyperFrames 原生模板、预渲染模板资产、hyperframes_canvas element motion
  不支持：缺失模板且禁止预渲染时回退

requested=legacy
  始终作为稳定兼容路径
```

所有 fallback 必须写入 metadata：

```text
render_backend_requested
render_backend_effective
render_backend_fallback_reason
```

## 10. 模板库保留策略

现有 `templates/` 是正式模板库，不是临时 legacy 资产。

每个模板应逐步补充能力元数据：

```text
template_id
template_path
canvas_width
canvas_height
template_type: static | image | video
supports_html_prerender
supports_hyperframes_native
supports_text_slot
default_text_policy
media_slot
safe_areas
```

短期可以从路径和占位符自动推断：

- 路径尺寸解析 canvas。
- 文件名推断 `static`、`image`、`video`。
- 是否包含 `{{image}}` 判断是否需要媒体。
- 是否包含 `{{text}}` 判断是否支持 template body text。

长期应为模板库增加显式 manifest，避免靠 HTML 字符串扫描做产品级决策。

## 11. Python/FFmpeg 元素微动接入

当前 `PythonElementAnimationRenderer` 能逐帧渲染并调用 FFmpeg 输出视频，但没有接入标准 pipeline。

接入方式：

```text
frame visual asset
  -> ElementSegmentationService
  -> element_animation_manifest.frame_XXX.json
  -> PythonElementAnimationRenderer.render_video(...)
  -> VisualClip(source_kind=element_motion_video)
  -> backend renderer
```

不同后端消费方式：

- `legacy`：用 motion video 替代静态 composed image segment，或在 video branch 中走 overlay/merge audio。
- `hyperframes_compiled`：优先消费 manifest 做 canvas 动画；如果 backend 是 `python_ffmpeg`，消费已渲染 motion video。
- `ffmpeg_manifest`：只消费已渲染 motion video，不自己逐帧做元素动画。

## 12. 从 CloneCut 借鉴的部分

借鉴：

- 每个阶段输出 manifest。
- 每个阶段明确 artifacts。
- fallback 需要写入 metadata。
- 输出文件语义明确，例如 no_subtitle、subtitled、overlay assets。
- FFmpeg 错误要记录到诊断信息里。

不借鉴：

- MoviePy concat 主链路。
- 分散脚本式 stage 调用。
- 每个阶段各自拼路径和猜输入。
- 让字幕、转码、overlay 各自维护一套事实源。

Pixelle 应该把这些经验吸收到 `RenderExecutionPlan` 和 renderer diagnostics，而不是把 CloneCut 的 stage pipeline 搬进来。

## 13. 迁移计划

### 阶段 1：契约补齐

- 扩展 `RenderBackend`，新增 `ffmpeg_manifest`。
- 扩展 `VisualClip`，支持 template、motion、text policy、diagnostics。
- 新增 `RenderExecutionPlan`。
- 保留旧字段兼容现有测试和 HyperFrames project service。

### 阶段 2：模板资产层

- 新增 `TemplateVisualMaterializer`。
- 把 `HTMLFrameGenerator` 封装进去。
- legacy 改为通过 materializer 获取 composed frame。
- hyperframes 和 ffmpeg_manifest 都可以消费预渲染 template frame。

### 阶段 3：元素微动标准接入

- 新增 frame-level element animation artifacts。
- 将 `ElementSegmentationService` 和 `PythonElementAnimationRenderer` 接到标准 pipeline。
- HyperFrames project materializer 支持多 clip element animation manifest。

### 阶段 4：ffmpeg_manifest renderer

- 新增 `FfmpegManifestRenderer`。
- 支持 image/video clips、audio tracks、ASS、BGM、overlay。
- 写出 ffmpeg command diagnostics。
- 能力不足时明确 fallback。

### 阶段 5：UI 与元数据

- 渲染后端 UI 展示三个后端。
- 元素微动 UI 保持 `hyperframes_canvas` 和 `python_ffmpeg`，但文案说明它是元素微动渲染方式，不是最终视频后端。
- 任务历史展示 requested/effective backend 和 fallback reason。

## 14. 测试策略

需要覆盖：

- `render_backend` 校验支持三个后端。
- UI 后端选择和持久化。
- `TemplateVisualMaterializer` 能复用现有 HTML 模板。
- 默认 `caption_renderer` 策略不会把 narration 同时写入模板和 ASS。
- `template_body` 策略会禁用同一正文的最终字幕重复渲染。
- `VisualClip` round-trip 保留 template 和 element motion 字段。
- 多分镜元素动画 manifest 能绑定到对应 clip。
- `python_ffmpeg` 元素微动产物能进入 legacy 和 ffmpeg manifest 路径。
- `ffmpeg_manifest` 简单图片 + 音频 + ASS 输出成功。
- 请求 `ffmpeg_manifest` 但模板未预渲染时记录 fallback。
- HyperFrames 缺失原生模板时可以消费预渲染 template frame。
- metadata 包含 requested/effective backend、fallback reason、artifacts。

## 15. 风险与约束

主要风险：

- 一次性改动 pipeline 太大，容易破坏 legacy 稳定性。
- 模板文字策略如果不先收敛，会继续出现双字幕。
- 如果 `ffmpeg_manifest` 直接侵入 pipeline 分支，会形成第四套技术债。
- 如果元素微动只接 UI，不接 `VisualClip`，后续仍然无法被三后端统一消费。

约束：

- legacy 必须可回退。
- 新路径必须能记录明确 fallback reason。
- 不能把未归属的测试改动混入实现提交。
- 新增设计和实现应按原子变更提交。

## 16. 最终推荐

采用“统一资产生成层 + 统一执行计划 + 三后端执行器”的方案。

这比单纯添加 `ffmpeg_manifest` 后端更稳，因为它先修正了源头事实源：

- 模板库成为正式视觉资产层。
- 元素微动成为 frame/clip 级视觉资产。
- 文字渲染由统一 text package 控制。
- 后端只负责各自擅长的最终合成。

这样可以保留现有模板库价值，又能引入高速 FFmpeg 合成，并把当前已有的 Python/FFmpeg 元素微动实现真正纳入标准 pipeline。
