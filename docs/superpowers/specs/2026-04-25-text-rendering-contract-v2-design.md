# Text Rendering Contract v2 设计方案

## 1. 结论

Pixelle 不应该继续把字幕、图片加字、重点词、模板文字分别做成不同渲染链路的局部能力。

正确方向是建立平台级 `Text Rendering Contract v2`：

```text
CreationRequest
  -> TextRenderingOrchestrator
  -> TextRenderPackage
  -> RenderManifest.text_tracks / text_cues / text_style_profiles
  -> TextRendererAdapter(HyperFrames / HTML / ASS / native prompt)
```

字幕属性不是 Python 专属参数。Python/ASS 是一个消费端，HTML/HyperFrames 也是一个消费端。字号、颜色、描边、位置、背景、换行、边距等属性必须先进入统一样式契约，再分别投影成 ASS style、CSS variables、模板能力校验或 native prompt hint。

二次复审后的更强约束：`TextRenderPackage` 必须成为唯一可持久化的文字渲染事实源。`CreationPackage` 可以引用它，`RenderManifest` 可以派生它，renderer adapter 可以消费它，但任何 pipeline 或 renderer 不允许重新拼装一套平行的 caption/overlay/style 事实。

## 2. 背景依据

本方案综合参考以下上下文：

- `docs/superpowers/specs/内容创作平台整体规划设计.md`
- `docs/superpowers/specs/零级优先改造清单.md`
- `docs/superpowers/specs/分布式视频生成生产级升级方案.md`
- `docs/superpowers/specs/图片加字方案设计.md`
- `D:\demo1\Pixelle\Pixelle\MoneyPrinterTurbo-main`
- `D:\demo1\clonecut\clonecut\domain\video\pre`
- `D:\llmtomp3tomp4\asstomp4`

关键判断：

1. MoneyPrinterTurbo 的价值主要是 API 参数直观、字幕参数用户友好，不适合作为 Pixelle 的架构参考源。
2. clonecut/asstomp4 的价值主要是 ASS 样式映射、分辨率缩放、颜色转换、换行处理和 ffmpeg burn-in 细节。
3. Pixelle 当前已经具备平台化基础，不应该回退成 renderer-specific 参数透传。
4. MoneyPrinterTurbo 的 MoviePy `TextClip` 路线只能作为 UI 字段和文本测量换行参考，不能成为 Pixelle 的 renderer boundary。
5. asstomp4 的 `subtitle_style -> standard style config -> pysubs2.SSAStyle -> ass filter + fontsdir` 链路是 ASS 侧最值得吸收的最佳实践。
6. clonecut 的价值在于生产鲁棒性：多编码解析、分辨率缩放、颜色转换、字体兜底、中文字符验证、换行和标点处理。
7. 参考项目都不应该成为 Pixelle 的平台架构源。Pixelle 的源头事实必须留在 `RenderManifest + TextStyleProfile + renderer adapters`，参考项目只提供 adapter 内部实现细节。

## 3. 当前 Pixelle 已具备的基础

当前代码已经落地了以下关键基础：

| 能力 | 文件 | 状态 |
| --- | --- | --- |
| TextRenderingPolicy / TextOverlayPlan | `pixelle_video/models/text_overlay.py` | 已有 |
| CreationPackage | `pixelle_video/models/creation_package.py` | 已有 |
| TextTrack / TextCue / RenderManifest | `pixelle_video/models/render_package.py` | 已有 |
| TemplateRenderContext.text_tracks/text_cues | `pixelle_video/models/template_render_context.py` | 已有 |
| TemplateTextCapabilities | `pixelle_video/models/template_text_capabilities.py` | 已有 |
| TextOverlayPlanner | `pixelle_video/services/text_overlay_planner.py` | 已有雏形 |
| TextCueCompiler | `pixelle_video/services/text_cue_compiler.py` | 已有雏形 |
| HyperFrames text layer render | `pixelle_video/services/hyperframes_compiler.py` | 已有雏形 |
| ASS export | `pixelle_video/services/ass_text_adapter.py` | 已有雏形但样式硬编码 |
| legacy ASS burn-in | `pixelle_video/services/video.py` | 已有 |
| Web text rendering controls | `web/components/style_config.py` | 已有基础开关 |

因此本轮不应该从零实现 Text Layer，而是补齐缺失的样式契约和 renderer adapter 边界。

当前扫描还发现以下源头级债务：

1. `pixelle_video/services/hyperframes_project_service.py` 里普通字幕 cue 使用 `manifest.template_id` 作为 `style_profile`，这会把模板身份和字幕视觉样式混在一起。
2. `pixelle_video/pipelines/custom.py` 只把 `text_rendering` 用于图片 prompt，没有进入 `TextOverlayPlan -> TextCueCompiler -> RenderManifest` 的统一文字层链路。
3. `pixelle_video/pipelines/asset_based.py` 基本没有接入 `text_rendering` 契约。用户素材视频也应能获得同一套字幕样式、overlay text layer 和 image text policy 诊断。
4. `pixelle_video/pipelines/standard.py` 的文字层规划主要发生在需要生成媒体的分支。静态模板、用户素材和后期渲染不应该因为没有图片 prompt 生成而跳过文字渲染契约。
5. `pixelle_video/services/video.py` 当前使用 ffmpeg `subtitles` filter burn-in ASS 文件，缺少 `ass=...:fontsdir=...` 的字体可靠性契约。
6. `web/components/style_config.py` 已经承载过多配置 UI。继续把字幕样式、overlay 样式、image text policy 都堆进去，会把平台契约变成 UI 局部实现。
7. 当前没有 canonical text rendering artifact。`TextOverlayPlan`、`CaptionCue`、`TextTrack/TextCue`、prompt policy、style profiles 分散在不同对象里，会让后续实现者在 pipeline 中反复组装。
8. 当前没有统一的 text content sanitization 和 layout plan。ASS/HTML/HyperFrames 都会各自处理转义、换行、花括号、HTML escape、标点清理和 safe area，长期会产生安全和视觉不一致问题。
9. 当前没有 renderer adapter protocol。即使有 `AssTextAdapter` 和 `HyperFramesCompiler`，pipeline 仍然可能直接调用具体实现，导致 summary、artifacts、diagnostics 和 fallback 格式不一致。

## 4. 核心问题

### 4.0 三条逻辑必须拆开

当前 Pixelle 的“文字渲染”不是一个单一开关，而是三条独立逻辑：

1. `caption rendering`：普通字幕。来源是 narration、`TimingPlan`、`SentenceUnit`、`CaptionCue`。它服务于旁白字幕展示，不依赖“启用文字层”。
2. `overlay text layer`：画面文字层。来源是 `TextOverlayPlan`，负责重点词、短句、图片加字、模板叠字、native hint 审计等。它才受 `启用文字层` 控制。
3. `image text policy`：图像模型文字策略。负责禁止或允许模型在画面中原生生成文字，只影响 image/video prompt，不等于字幕，也不等于后期文字层。

因此后续所有 UI、API、模型和 observability 都必须避免把“字幕样式”挂到“启用文字层”下面。字幕样式是 caption rendering 的属性；启用文字层是 overlay text layer 的开关；禁止图中文字是 image text policy 的开关。

### 4.1 样式事实源缺失

当前 `TextTrack` 和 `TextCue` 有 `style_profile` 字段，但没有平台级样式对象。结果是：

- ASS exporter 自己硬编码字体、字号、颜色、描边、边距。
- HyperFrames 模板 CSS 自己定义视觉样式。
- UI/API 只知道开关、mode、target、density，不知道字幕视觉属性。
- 同一个文字 cue 在 ASS 和 HyperFrames 下无法保证视觉一致。

### 4.2 ASS adapter 仍然是局部实现

`pixelle_video/services/ass_text_adapter.py` 当前固定输出：

```text
Style: Default,Noto Sans CJK SC,64,...
Style: Overlay,Noto Sans CJK SC,76,...
```

这适合早期验证，不适合作为平台能力。它应该被改造成 `RenderManifest + TextStyleProfile -> ASS` 的 adapter。

### 4.3 HyperFrames 还没有消费统一样式

`HyperFramesCompiler._render_text_cues(...)` 已经能渲染 `TextCue`，但缺少 `TextStyleProfile` 到 CSS variables 的投影。

模板 CSS 可以声明布局能力，但不应该独占字幕样式事实源。

### 4.4 Observability 不够复盘

当前 `text_layer_summary` 记录了 enabled、renderer、track/cue 数量和 targets，但还缺：

- style profile ids
- exported ASS artifacts
- HyperFrames payload artifacts
- planner/compiler/export/burn-in 耗时
- native prompt hint 实际注入数量
- renderer fallback 或 disabled 原因

### 4.5 Pipeline 边界没有统一

`standard`、`custom`、`asset_based` 和静态模板路径都应该经过同一套 text rendering 边界。允许不同 pipeline 最终没有 overlay cue，但不允许某条 pipeline 静默绕过：

```text
request.text_rendering
  -> TextRenderingSettings
  -> TextRenderingOrchestrator
  -> CreationPackage text/render plan
  -> RenderManifest text_style_profiles/text_tracks/text_cues
  -> renderer adapters
  -> summaries/artifacts
```

如果某条 pipeline 暂不支持完整文字层，也必须输出明确的 disabled summary，说明原因、支持的 targets 和被跳过的阶段。

### 4.6 UI 文件边界会成为技术债

`web/components/style_config.py` 已经是大型配置面板。新增三段文字渲染 UI 时，不应该继续在该文件里堆积所有控件。建议拆出：

```text
web/components/text_rendering_config.py
```

职责：

1. 渲染 caption style、overlay text layer、image text policy 三个并列小节。
2. 返回平台级 `text_rendering` payload。
3. 不直接知道 ASS、CSS、ffmpeg filter 的私有字段。

`style_config.py` 只负责在合适位置调用该组件并合并 payload。

### 4.7 字体和 ASS burn-in 缺少契约

从 asstomp4/clonecut 参考项目看，ASS 稳定性主要取决于：

1. 样式使用结构化对象生成，不手写散落字符串。
2. `PlayResX/PlayResY` 与输出视频尺寸一致。
3. 字体文件路径、真实字体族名、fontsdir 三者一致。
4. ffmpeg burn-in 优先使用 `ass` filter，并传入 `fontsdir`。
5. 编码器失败时有明确 fallback 和日志，而不是静默生成缺字体或样式失真的视频。

这些规则必须属于 ASS adapter / VideoService 层，不能泄漏到 API/UI。

## 5. 设计目标

1. 建立统一 `TextStyleProfile`，作为字幕、重点词、模板文字的样式事实源。
2. ASS、HTML、HyperFrames 都只消费平台契约，不再各自维护样式模型。
3. 保留现有 `TextRenderingPolicy / TextOverlayPlan / TextTrack / TextCue` 方向，不新造平行时间线。
4. 保留 HyperFrames-first 长期方向，同时让 legacy Python/ASS 稳定可用。
5. UI/API 暴露用户友好的文字样式字段，不暴露 ASS/CSS 私有实现。
6. 诊断产物和 metadata 能复盘文字层从规划到最终渲染的完整路径。

## 6. 新增平台契约

### 6.0 CaptionRenderingSettings

普通字幕必须有独立 contract，不再只是一组隐含 caption cues：

```python
@dataclass(frozen=True)
class CaptionRenderingSettings:
    enabled: bool = True
    source: str = "narration_timing"
    style_profile: str = "caption-default"
    punctuation_mode: str = "strip_all"
    renderer_targets: tuple[str, ...] = ("hyperframes", "ass")
```

原则：

1. `caption.enabled` 控制普通旁白字幕是否显示。
2. `overlay.enabled` 控制画面重点词/模板叠字/native hint 审计层。
3. `image_text.suppress_embedded_text` 控制图像模型 prompt，不控制字幕。
4. 旧的 `caption_punctuation_mode` 可以迁移到 `CaptionRenderingSettings.punctuation_mode`，但不能继续挂在 TTS 配置里作为唯一事实源。

### 6.1 TextStyleProfile

建议新增：

```text
pixelle_video/models/text_style.py
```

核心模型：

```python
@dataclass(frozen=True)
class TextStyleProfile:
    id: str
    name: str
    version: str = "text_style_profile.v1"
    font_family: str = "Noto Sans CJK SC"
    font_file: str | None = None
    font_size: int = 64
    font_weight: int = 700
    primary_color: str = "#FFFFFF"
    background_color: str | None = None
    background_opacity: float = 0.0
    stroke_color: str = "#000000"
    stroke_width: int = 2
    shadow_color: str | None = None
    shadow_blur: int = 0
    position: str = "bottom"
    alignment: str = "center"
    margin_x: int = 80
    margin_y: int = 140
    max_width_ratio: float = 0.86
    line_height: float = 1.18
    max_chars_per_line: int | None = None
    punctuation_mode: str = "strip_all"
    scale_basis_width: int = 1080
    scale_basis_height: int = 1920
```

字段原则：

- API/UI 使用 `#RRGGBB`，不要暴露 ASS `&H00FFFFFF`。
- `font_size/stroke_width/margin_x/margin_y` 是设计基准值，adapter 根据 canvas 做缩放。
- `font_file` 可选，用于后续字体发现和嵌入。
- `position/alignment` 是平台枚举，adapter 自己映射到 ASS alignment 或 CSS layout。

### 6.2 RenderManifest 扩展

`RenderManifest` 增加：

```python
text_style_profiles: list[TextStyleProfile]
```

迁移期规则：

1. 旧 manifest 缺字段时默认空列表。
2. `TextTrack.style_profile` 和 `TextCue.style_profile` 仍然保存 profile id。
3. 如果 cue 没有 style profile，则使用 track profile。
4. 如果 track 也没有，则 adapter 使用平台默认 profile，但必须在 summary 记录 fallback。

### 6.2.1 TextRenderPackage

新增：

```text
pixelle_video/models/text_render_package.py
```

核心字段：

```python
@dataclass(frozen=True)
class TextRenderPackage:
    version: str
    task_id: str
    caption_settings: CaptionRenderingSettings
    overlay_policy: TextRenderingPolicy
    image_text_policy: ImageTextPromptPolicy
    text_style_profiles: tuple[TextStyleProfile, ...]
    caption_cues: tuple[CaptionCue, ...]
    text_tracks: tuple[TextTrack, ...]
    text_cues: tuple[TextCue, ...]
    layout_plan: TextLayoutPlan
    diagnostics: Mapping[str, Any]
```

职责：

1. 作为 `TextRenderingOrchestrator` 的持久化输出。
2. 作为 `RenderManifest`、ASS、HyperFrames、HTML、History summary 的共同输入。
3. 存到任务目录，例如 `text_rendering/text_render_package.json`。
4. 禁止 renderer adapter 修改 package；adapter 只能返回 export result。

`RenderManifest` 是渲染器需要的 manifest，不是唯一事实源。`CreationPackage` 是创作阶段包，不应继续承担完整文字渲染事实源。

### 6.3 TextRenderingRequest 扩展

API schema 增加：

```python
caption_style: TextStyleProfileRequest | None
overlay_style: TextStyleProfileRequest | None
style_profiles: list[TextStyleProfileRequest]
```

用户友好字段示例：

```json
{
  "caption_style": {
    "font_family": "Noto Sans CJK SC",
    "font_size": 64,
    "primary_color": "#FFFF00",
    "stroke_color": "#000000",
    "stroke_width": 3,
    "position": "bottom",
    "margin_y": 120,
    "background_color": "#000000",
    "background_opacity": 0.35
  }
}
```

不允许 API 直接传入：

- ASS `force_style`
- CSS 字符串
- ffmpeg filter 字符串
- renderer-specific magic params

### 6.4 TextStyleResolver

新增共享 resolver，避免 adapter 各自实现 fallback：

```text
pixelle_video/services/text_style_resolver.py
```

职责：

1. 合并平台默认 styles、request styles、manifest styles。
2. 按 `cue.style_profile -> track.style_profile -> role default` 解析有效 profile。
3. 对找不到的 profile 记录 diagnostic fallback；对模板能力禁止的 profile 直接失败。
4. 提供 `profiles_by_id`、`resolve_for_cue(...)` 和 `diagnostics`。

所有 renderer adapter 必须使用 resolver，不允许在 ASS/HyperFrames 内部重新写一套 style fallback 逻辑。

### 6.5 TextRenderingOrchestrator

新增 orchestration boundary，避免 `StandardPipeline.plan_visuals` 独占文字渲染契约：

```text
pixelle_video/services/text_rendering_orchestrator.py
```

输入：

- `text_rendering` request payload
- narration/sentence/timing context
- template metadata / render backend
- optional media generation context

输出：

- `TextRenderingSettings`
- `TextRenderingPolicy`
- `TextOverlayPlan`
- `text_style_profiles`
- planner diagnostics
- disabled reasons

`standard`、`custom`、`asset_based` 和静态模板路径都应该调用它。某条 pipeline 如果不生成 overlay cue，也应该拿到 caption style、image text policy summary 和 disabled reason。

### 6.6 TextContentSanitizer 与 TextLayoutPlan

新增：

```text
pixelle_video/services/text_content_sanitizer.py
pixelle_video/services/text_layout_planner.py
```

`TextContentSanitizer` 负责平台层文本清洗：

1. 保留原始文本 `raw_text`，生成展示文本 `display_text`。
2. 禁止 ASS override tag 注入，例如 `{\\pos(...)}`。
3. 禁止 HTML/script 注入；HTML escaping 仍由 HTML adapter 做，但平台层必须记录文本安全状态。
4. 统一处理不可见控制字符、异常换行、零宽字符和过长文本。

`TextLayoutPlan` 负责跨 renderer 共享布局意图：

1. 使用 Unicode grapheme cluster 和 CJK display width，而不是简单 `len(text)`。
2. 生成推荐 `wrapped_lines`、`safe_area`、`max_width_ratio`、`line_height`、`layer`。
3. 明确 caption safe area 与 overlay slots 的碰撞规则。
4. adapter 可以根据目标能力做最终投影，但不能重新决定高层布局意图。

### 6.7 Schema version 与迁移

所有新增 artifact 必须带版本：

- `text_render_package.v1`
- `text_style_profile.v1`
- `caption_rendering_settings.v1`
- `text_layout_plan.v1`

读取旧任务时：

1. 缺 `text_render_package.json` 时，从旧 `RenderManifest`/metadata 做只读兼容，不反写旧任务。
2. 缺 `text_style_profiles` 时注入默认 profile，并在 diagnostics 记录 compatibility fallback。
3. History 页面必须能显示旧 `text_layer_summary`，同时支持新的 caption/text/image 三段 summary。

## 7. Renderer Adapter 设计

### 7.0 TextRendererAdapter protocol

新增：

```text
pixelle_video/services/text_renderer_adapter.py
```

统一接口：

```python
class TextRendererAdapter(Protocol):
    target: str

    def supports(self, package: TextRenderPackage) -> TextRendererSupport:
        ...

    def export(
        self,
        *,
        package: TextRenderPackage,
        manifest: RenderManifest,
        output_dir: Path,
    ) -> TextRenderExportResult:
        ...
```

`TextRenderExportResult` 必须包含：

- `target`
- `enabled`
- `artifacts`
- `cue_count`
- `style_profile_ids`
- `fallbacks`
- `warnings`
- `duration_ms`

pipeline 只能依赖 adapter protocol，不允许直接依赖 `AssTextAdapter` 或 HyperFrames 私有方法。

### 7.1 ASS adapter

新增：

```text
pixelle_video/services/ass_style_builder.py
```

职责：

1. `#RRGGBB -> ASS &HAABBGGR` 颜色转换。
2. 按 canvas 与 `scale_basis_width/height` 计算字体、描边、边距缩放。
3. `position/alignment -> ASS Alignment`。
4. 生成 `Style:` 行。
5. 处理背景透明度、描边、阴影。

`AssTextAdapter` 只做：

```text
RenderManifest
  -> resolve TextStyleProfile per TextCue
  -> AssStyleBuilder
  -> master.ass / subtitle_only.ass / overlay_only.ass
```

clonecut/asstomp4 可参考点：

- 分辨率自适应缩放。
- ASS 颜色转换。
- CJK 换行和标点清理。
- font discovery 可作为后续增强，不放第一轮主路径。

### 7.1.1 ASS burn-in contract

`VideoService.burn_ass_subtitles(...)` 不应只拼接 `subtitles='path'`。目标行为：

```text
ASS artifact path
  -> resolved fontsdir
  -> ffmpeg ass='artifact.ass':fontsdir='fonts'
  -> libx264 fallback when hardware encoder fails
```

`fontsdir` 来源优先级：

1. `TextStyleProfile.font_file` 所在目录。
2. 项目字体目录。
3. 系统可用 CJK 字体目录。

如果没有可用字体目录，仍可继续 burn-in，但必须把 fallback 写入 summary。

### 7.2 HyperFrames / HTML adapter

`TemplateRenderContext` 增加：

```python
text_style_profiles: list[TextStyleProfile]
```

`HyperFramesCompiler` 输出：

```html
<div
  class="clip text-cue text-cue--keyword"
  data-style-profile="caption-default"
  style="
    --text-font-family: 'Noto Sans CJK SC';
    --text-font-size: 64px;
    --text-fill: #ffffff;
    --text-stroke-color: #000000;
    --text-stroke-width: 2px;
  "
>
```

模板仍然可以声明 slot 布局，例如 lower_third、center、top_left，但不能重新定义平台样式事实。

### 7.3 Native prompt adapter

native prompt 仍然由 `TextRenderingPolicy` 控制。

规则不变：

1. native hint 必须发生在 image prompt 生成之前。
2. native hint 不能等 `StyledImagePromptBatch` 返回后补注入。
3. render-time 的 `TextTrack(kind="native_hint")` 只用于审计、复跑、A/B，不代表 prompt 注入执行点。

## 8. Pipeline 接入规则

### 8.1 StandardPipeline

当前 `StandardPipeline` 已经在 `plan_visuals` 阶段创建 `CreationPackage`，在 render 阶段调用 `TextCueCompiler`。

需要补齐：

1. 根据 `text_rendering` request 构建默认 `TextStyleProfile`。
2. 把 style profiles 写入 `CreationPackage` 或 render plan 摘要。
3. `TextCueCompiler` 分配 cue/track 的 style profile id。
4. `RenderManifest` 携带 `text_style_profiles`。
5. HyperFrames 和 ASS adapter 均消费同一批 profiles。

### 8.2 legacy Python/ASS

接入点保持当前方向：

```text
concat/BGM
  -> export ASS
  -> burn ASS
  -> update ctx.final_video_path/storyboard.final_video_path
  -> copy user output
```

这点是正确的，不应该改成每帧提前烧录。

### 8.3 HyperFrames compiled

HyperFrames 继续是长期主线。

要求：

1. `render_manifest.json`、`text_tracks.json`、compiled context 必须来自同一份 normalized manifest。
2. `text_style_profiles` 也必须写入诊断产物。
3. 模板缺少 text capabilities 时，含 hyperframes text cue 的任务必须失败并说明原因，不能静默降级。

### 8.4 Custom / AssetBased / Static 接入规则

所有 pipeline 的最低要求：

1. 接受并解析 `text_rendering` payload。
2. 通过 `TextRenderingOrchestrator` 生成统一 settings、policy、styles 和 diagnostics。
3. 后期 RenderManifest 统一携带 `text_style_profiles`。
4. 如果 pipeline 暂不支持 overlay text layer，必须在 `text_layer_summary` 中记录 disabled reason。
5. caption style 不受 overlay disabled 影响。
6. image text policy 只影响 image/video prompt；如果 pipeline 不生成图片 prompt，则记录为 not_applicable，而不是静默忽略。

## 9. UI 设计

当前 UI 可以继续使用一个总的“文字渲染”折叠面板，但面板内部必须拆成三个并列小节，不能把字幕属性放到“启用文字层”下面。

### 9.1 字幕样式

这部分控制普通旁白字幕，即 `CaptionCue`、`captions.html`、legacy 字幕烧录或旧 HTML 模板中的字幕区域。

字幕样式不依赖 `启用文字层`。即使用户关闭画面文字层，字幕仍然可以按这里的样式渲染。

- 字体
- 字号
- 主色
- 描边颜色
- 描边宽度
- 背景颜色
- 背景透明度
- 位置
- 底部边距

### 9.2 画面文字层

这部分控制 `TextOverlayPlan -> TextTrack/TextCue`，用于重点词、短句、图片加字、模板叠字和 native hint 审计。

- 启用画面文字层
- 模式：programmatic / native / hybrid
- 目标：HyperFrames / ASS / Both
- 密度
- 每帧最多文字项
- overlay style profile

关闭这里时，只关闭 overlay text layer，不关闭普通字幕。

### 9.3 图像模型文字策略

这部分只影响图像或视频生成 prompt。

- 禁止模型生成画面文字
- 禁止图中文字提示词

开启这里时，系统只是向 image/video prompt 注入 no-text 规则，不代表开启或关闭字幕。

### 9.4 高级层

- style preset
- 每行最多字符
- line height
- 标点策略

不暴露：

- ASS alignment 数字
- ASS color
- ffmpeg force_style
- CSS 源码

### 9.5 UI 实现边界

UI 改造必须遵守：

1. `web/components/text_rendering_config.py` 负责文字渲染面板。
2. `web/components/style_config.py` 只调用新组件，不继续堆积细节控件。
3. `caption_style` 控件永远不受 overlay text layer checkbox 控制。
4. overlay checkbox 只控制 `TextOverlayPlan` 相关 cue。
5. image text policy checkbox 只控制 prompt 注入。
6. i18n 文案避免使用“字幕开关”指代 overlay text layer。

## 10. Observability 与 artifacts

metadata 建议拆成三块。为了兼容现有历史页面，可以保留 `text_layer_summary`，但它只表示 overlay text layer。普通字幕使用新的 `caption_rendering_summary`。

`metadata.result.caption_rendering_summary`：

```json
{
  "enabled": true,
  "caption_cue_count": 14,
  "style_profile_id": "caption-default",
  "punctuation_mode": "strip_all",
  "alignment_engine": "qwen_forced_aligner",
  "renderer_targets": ["hyperframes", "ass"],
  "artifacts": {
    "captions": "hyperframes/data/captions.json",
    "master_ass": "text_layer/master.ass",
    "subtitle_only_ass": "text_layer/subtitle_only.ass"
  }
}
```

`metadata.result.text_layer_summary`：

```json
{
  "enabled": true,
  "policy_mode": "programmatic_only",
  "renderer_targets": ["hyperframes", "ass"],
  "track_count": 2,
  "cue_count": 14,
  "style_profile_ids": ["caption-default", "overlay-default"],
  "native_prompt_hint_count": 0,
  "planner_ms": 120,
  "compiler_ms": 18,
  "adapter_ms": {
    "hyperframes": 840,
    "ass": 310
  },
  "artifacts": {
    "text_overlay_plan": "hyperframes/data/text_overlay_plan.json",
    "text_tracks": "hyperframes/data/text_tracks.json",
    "text_styles": "hyperframes/data/text_styles.json",
    "overlay_only_ass": "text_layer/overlay_only.ass"
  },
  "fallbacks": []
}
```

metadata 只存摘要和相对路径，大对象落任务目录。

## 11. 测试策略

### 11.1 模型测试

- `TextStyleProfile.to_dict/from_dict`
- 旧 `RenderManifest` 缺 `text_style_profiles` 时兼容
- `TextCue` 使用 cue style 覆盖 track style
- 非法颜色、非法 position、非法 opacity 被拒绝

### 11.2 ASS adapter 测试

- `#FFFFFF` 转换为 ASS 白色
- `#000000` 转换为 ASS 黑色
- 1080x1920 下保持基准字号
- 720x1280 下按比例缩放字号、描边、边距
- subtitle/overlay 使用不同 style profile
- 中文、空格、逗号、换行、花括号正确转义

### 11.3 HyperFrames 测试

- context 包含 `text_style_profiles`
- compiled `text_layer.html` 包含 `data-style-profile`
- CSS variables 来自 `TextStyleProfile`
- 无 capability 的模板拒绝 hyperframes text cue
- diagnostic payload 写入 `text_styles.json`

### 11.4 Pipeline 集成测试

- legacy 路线最终输出是 burn-in 后的视频
- hyperframes 路线不经过 ASS 文件
- same manifest 导出 ASS 和 HyperFrames 时 cue 数量一致
- 关闭画面文字层时，普通字幕仍然按字幕样式渲染
- 关闭字幕或无字幕 cue 时，画面文字层仍然可以独立渲染 overlay cue
- native hint 注入发生在 prompt batch 之前

### 11.5 全链路验收矩阵

| 场景 | 期望 |
| --- | --- |
| standard + legacy ASS | 输出 burn-in 后视频，ASS 使用 manifest styles，summary 记录 ASS artifacts |
| standard + HyperFrames | `text_styles.json`、`captions.json`、`text_tracks.json` 来自同一 normalized manifest |
| custom pipeline | 至少解析 text_rendering，并记录支持/不支持原因 |
| asset_based pipeline | 用户素材路线保留 caption style，overlay 不支持时显式 disabled |
| 静态模板 | 不因没有 media prompt 而跳过 caption style |
| overlay disabled | 普通字幕样式仍生效 |
| image text suppress enabled | 只影响 prompt，不关闭字幕或 overlay post layer |
| 缺失 style id | resolver 记录 fallback 或直接失败，禁止 adapter 静默默认 |
| 字体缺失 | summary 记录 fallback 字体/目录 |
| ASS 和 HyperFrames 同源渲染 | cue count、style id、timing 一致 |

### 11.6 Golden artifacts 与视觉回归

必须新增 golden fixtures：

```text
tests/fixtures/text_rendering/text_render_package_legacy_caption.json
tests/fixtures/text_rendering/text_render_package_overlay_hybrid.json
tests/fixtures/text_rendering/render_manifest_with_text_styles.json
```

验证要求：

1. `TextRenderPackage.from_dict(to_dict())` 稳定。
2. 旧 manifest 缺 `text_style_profiles` 时兼容读取并记录 fallback。
3. ASS golden snapshot 检查 `PlayResX/Y`、Style、Dialogue、转义文本。
4. HyperFrames compiled snapshot 检查 `data-style-profile`、CSS variables、HTML escaped text。
5. Playwright 或 HyperFrames preview 截图至少验证 caption/overlay 非空、未越界、未覆盖保留 safe area。

## 12. 分阶段落地

### 阶段 0：契约冻结

目标：先定义平台契约，不碰 renderer 行为。

产物：

- `pixelle_video/models/text_render_package.py`
- `pixelle_video/models/text_style.py`
- `pixelle_video/models/text_layout.py`
- `RenderManifest.text_style_profiles`
- `pixelle_video/services/text_style_resolver.py`
- `pixelle_video/services/text_rendering_orchestrator.py`
- `pixelle_video/services/text_renderer_adapter.py`
- `pixelle_video/services/text_content_sanitizer.py`
- `pixelle_video/services/text_layout_planner.py`
- golden fixtures
- schema 序列化测试
- 文档更新

### 阶段 1：ASS 去硬编码

目标：把 clonecut/asstomp4 的 ASS 样式映射能力平台化。

产物：

- `pixelle_video/services/ass_style_builder.py`
- `pixelle_video/services/font_resolver.py`
- `AssTextAdapter` 消费 `TextStyleProfile`
- `VideoService.burn_ass_subtitles` 支持 `ass` filter + `fontsdir`
- ASS adapter 测试

### 阶段 2：HyperFrames 消费统一样式

目标：HTML/HyperFrames 和 ASS 使用同源样式。

产物：

- `TemplateRenderContext.text_style_profiles`
- `HyperFramesProjectService` 写 `text_styles.json`
- `HyperFramesCompiler` 输出 CSS variables
- 模板测试

### 阶段 3：API/UI 样式输入

目标：用户可以独立配置字幕样式、画面文字层和图像模型文字策略，但三者仍然走平台契约。

产物：

- `api/schemas/text_rendering.py` 扩展样式 request
- `web/components/text_rendering_config.py` 承载三段文字渲染控件
- `web/components/style_config.py` 调用新组件，不继续堆积实现细节
- i18n 文案
- schema/UI 测试

### 阶段 4：Observability 与工作台

目标：可以分别复盘字幕、画面文字层和图像模型文字策略的完整路径。

产物：

- `caption_rendering_summary` 新增
- `text_layer_summary` 扩展
- `image_text_policy_summary` 新增或并入 text rendering 总摘要
- artifact path 写入 metadata
- History 分别显示字幕摘要和画面文字层摘要

### 阶段 5：全 pipeline 接入

目标：`standard`、`custom`、`asset_based`、静态模板路径都不绕过文字渲染契约。

产物：

- `StandardPipeline` 调用 orchestrator，而不是只在 media prompt 分支局部构造 text policy
- `CustomPipeline` 至少记录 text rendering contract summary
- `AssetBasedPipeline` 保留 caption style，并记录 overlay/image text policy 的支持状态
- 跨 pipeline disabled reason 测试

## 13. 明确禁止事项

1. 不允许只修改 `ass_text_adapter.py` 的硬编码字号颜色作为最终方案。
2. 不允许 UI 直接传 ASS `force_style`。
3. 不允许 HTML 模板、ASS exporter、HyperFrames 各自维护不同样式模型。
4. 不允许把图片加字重新做成独立时间线。
5. 不允许让 `StyledImagePromptBatch` 拥有完整文字层。
6. 不允许 silent fallback 到默认 slot 或默认 style，必须记录或失败。
7. 不允许某条 pipeline 因为不生成图片 prompt 就跳过 caption style。
8. 不允许 renderer adapter 各自实现 style fallback。
9. 不允许 UI/API 暴露 `fontsdir`、`ass` filter、`force_style`、CSS 字符串等私有字段。
10. 不允许继续把文字渲染 UI 细节全部堆进 `style_config.py`。
11. 不允许绕过 `TextRenderPackage` 直接从 pipeline 拼 ASS/HTML 文本。
12. 不允许 renderer adapter 私自清洗、截断或重排文本；平台层必须先产出 sanitized display text 和 layout plan。
13. 不允许只靠单元测试验收文字渲染；必须有 golden artifact 和至少一条视觉非空/不越界验证。

## 14. 最终推荐

本方案的关键不是多加几个字幕字段，而是补齐文字层的最后一个平台契约：样式事实源。

落地后，Pixelle 可以同时满足：

1. legacy Python/ASS 稳定烧录字幕。
2. HyperFrames/HTML 作为长期主渲染路线消费同一批 cue 和 style。
3. 图片加字、字幕、重点词、模板文字、native prompt hint 都进入同一个平台治理模型。
4. 后续工作台、A/B、局部复跑、产物复盘都有统一依据。
